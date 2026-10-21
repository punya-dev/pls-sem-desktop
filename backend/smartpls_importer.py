import os
import glob
import json
import base64
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd

import project_io
import workspace_io

SMARTPLS_AES_KEY = bytes.fromhex("cd2a06087b5b9dcfda8e517ae0db395e")


def decrypt_smartpls_content(encrypted_text: str) -> str:
    """
    Decrypts SmartPLS AES-128-ECB encrypted Base64 string.
    Tries Python cryptography library first; falls back to openssl subprocess.
    """
    clean_text = encrypted_text.strip()
    if not clean_text:
        return ""

    raw = base64.urlsafe_b64decode(clean_text + "=" * (-len(clean_text) % 4))

    # 1. Try cryptography library
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding

        cipher = Cipher(algorithms.AES(SMARTPLS_AES_KEY), modes.ECB())
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(raw) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        unpadded = unpadder.update(decrypted) + unpadder.finalize()
        return unpadded.decode("utf-8")
    except Exception:
        pass

    # 2. Fallback to openssl CLI
    try:
        p = subprocess.Popen(
            ["openssl", "enc", "-d", "-aes-128-ecb", "-K", SMARTPLS_AES_KEY.hex()],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = p.communicate(input=raw)
        if p.returncode == 0:
            return stdout.decode("utf-8")
    except Exception:
        pass

    raise ValueError("Failed to decrypt SmartPLS file using both cryptography and openssl")


def decrypt_smartpls_file(file_path: str) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    decrypted_str = decrypt_smartpls_content(content)
    return json.loads(decrypted_str)


def parse_smartpls_dataset(txt_path: str) -> Tuple[pd.DataFrame, str]:
    """
    Parses a SmartPLS dataset text file, inspecting associated .settings file if present
    to determine delimiter (semicolon, comma, tab).
    """
    sep = ";"
    settings_path = txt_path + ".settings"
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                s_json = json.load(f)
                sep_code = str(s_json.get("separator", "")).upper()
                if "COMMA" in sep_code:
                    sep = ","
                elif "TAB" in sep_code:
                    sep = "\t"
                elif "SEMICOLON" in sep_code:
                    sep = ";"
        except Exception:
            sep = ";"

    # Try reading with determined separator, fall back to sniff/comma/tab if failed
    try:
        df = pd.read_csv(txt_path, sep=sep)
    except Exception:
        try:
            df = pd.read_csv(txt_path, sep=None, engine="python")
        except Exception:
            df = pd.read_csv(txt_path, sep=",")

    dataset_name = os.path.splitext(os.path.basename(txt_path))[0]
    return df, dataset_name


def convert_smartpls_model(splsm_dict: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Converts a decrypted SmartPLS model dictionary (.splsm JSON) into:
    1) model_spec dict (constructs, indicators, paths)
    2) diagram_layout dict (nodes, edges, transform)
    """
    nodes = []
    edges = []

    # Map manifest variable ID to parent latent ID via connections
    ind_to_parent: Dict[str, str] = {}
    for conn in splsm_dict.get("connections", []):
        if conn.get("modelType") == "CONNECTION_BETWEEN_LV_AND_MV":
            ind_to_parent[conn.get("targetId")] = conn.get("sourceId")

    # 1. Convert Nodes
    for n in splsm_dict.get("nodes", []):
        mtype = n.get("modelType")
        nid = n.get("id")
        w = float(n.get("width", 70.0) or 70.0)
        h = float(n.get("height", 70.0) or 70.0)
        # Center coordinates for canvas
        cx = float(n.get("x", 0.0) or 0.0) + w / 2.0
        cy = float(n.get("y", 0.0) or 0.0) + h / 2.0

        if mtype == "LATENT_VARIABLE":
            meas_type = "formative" if str(n.get("measurementModelType", "")).upper() == "FORMATIVE" else "reflective"
            label = n.get("caption") or n.get("description") or "Construct"
            nodes.append({
                "id": nid,
                "label": label,
                "x": round(cx, 1),
                "y": round(cy, 1),
                "isLatent": True,
                "type": meas_type,
            })
        elif mtype == "STANDARD_MANIFEST_VARIABLE":
            parent_id = ind_to_parent.get(nid)
            col_name = n.get("indicator") or n.get("caption") or "Indicator"
            nodes.append({
                "id": nid,
                "label": col_name,
                "x": round(cx, 1),
                "y": round(cy, 1),
                "isLatent": False,
                "parentId": parent_id,
            })
        elif mtype == "POSTIT":
            text = n.get("description") or n.get("caption") or ""
            nodes.append({
                "id": nid,
                "label": text,
                "x": round(cx, 1),
                "y": round(cy, 1),
                "isLatent": None,
                "isText": True,
            })

    # 2. Convert Connections
    for conn in splsm_dict.get("connections", []):
        ctype = conn.get("modelType")
        cid = conn.get("id") or f"edge_{len(edges)}"
        sid = conn.get("sourceId")
        tid = conn.get("targetId")

        if ctype in ("CONNECTION_BETWEEN_LV_AND_LV", "CONNECTION_FOR_PLS_MODERATION"):
            if sid and tid:
                edges.append({
                    "id": cid,
                    "sourceId": sid,
                    "targetId": tid,
                })

    # 3. Build ModelSpec
    latent_nodes = [n for n in nodes if n.get("isLatent") is True]
    manifest_nodes = [n for n in nodes if n.get("isLatent") is False]

    constructs = []
    for ln in latent_nodes:
        lid = ln["id"]
        c_inds = [m["id"] for m in manifest_nodes if m.get("parentId") == lid]
        constructs.append({
            "id": lid,
            "name": ln["label"],
            "type": ln.get("type", "reflective"),
            "indicators": c_inds,
        })

    indicators = [
        {"id": mn["id"], "column": mn["label"]}
        for mn in manifest_nodes
    ]

    paths = [
        {"from": e["sourceId"], "to": e["targetId"]}
        for e in edges
    ]

    model_spec = {
        "constructs": constructs,
        "indicators": indicators,
        "paths": paths,
    }

    diagram_layout = {
        "nodes": nodes,
        "edges": edges,
        "transform": {"x": 0, "y": 0, "k": 1},
    }

    return model_spec, diagram_layout


def detect_smartpls_folder(folder_path: str) -> Dict[str, Any]:
    """
    Inspects a directory and returns whether it is a valid SmartPLS export,
    along with summary details (models found, datasets found).
    """
    folder_path = os.path.expanduser(folder_path)
    if not os.path.isdir(folder_path):
        return {"valid": False, "error": "Path is not a directory"}

    meta_file = os.path.join(folder_path, ".meta")
    splsm_files = sorted(glob.glob(os.path.join(folder_path, "*.splsm")))
    data_files = sorted(
        [
            f for f in glob.glob(os.path.join(folder_path, "*.txt")) + glob.glob(os.path.join(folder_path, "*.csv"))
            if not f.endswith(".settings") and not f.endswith(".ok")
        ]
    )

    if not splsm_files and not data_files and not os.path.exists(meta_file):
        return {"valid": False, "error": "No SmartPLS files (.splsm, datasets) found in directory"}

    project_name = os.path.basename(folder_path.rstrip("/\\"))
    model_summaries = []
    for sf in splsm_files:
        mname = os.path.splitext(os.path.basename(sf))[0]
        model_summaries.append({"file": os.path.basename(sf), "name": mname})

    data_summaries = [os.path.basename(df) for df in data_files]

    return {
        "valid": True,
        "project_name": project_name,
        "folder_path": folder_path,
        "has_meta": os.path.exists(meta_file),
        "models_count": len(splsm_files),
        "models": model_summaries,
        "datasets_count": len(data_files),
        "datasets": data_summaries,
    }


def import_smartpls_folder(
    folder_path: str,
    target_workspace_folder: Optional[str] = None,
    workspace_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fully imports a SmartPLS project folder:
    - Sets up or opens the Workspace
    - Loads datasets into SQLite .pls Study databases
    - Decrypts and converts all .splsm models
    - Saves models into model_spec tables
    - Optionally loads .splsrp reports into results tables
    """
    folder_path = os.path.expanduser(folder_path)
    detection = detect_smartpls_folder(folder_path)
    if not detection.get("valid"):
        raise ValueError(detection.get("error", "Invalid SmartPLS folder"))

    proj_name = workspace_name or detection.get("project_name") or "SmartPLS Project"

    # Destination directory for workspace
    if not target_workspace_folder:
        target_workspace_folder = os.path.join(os.path.dirname(folder_path), f"{proj_name} - Workspace")
    target_workspace_folder = os.path.expanduser(target_workspace_folder)
    os.makedirs(target_workspace_folder, exist_ok=True)

    # 1. Initialize or load workspace.json
    ws_file = os.path.join(target_workspace_folder, "workspace.json")
    if os.path.exists(ws_file):
        ws_meta = workspace_io.load_workspace(target_workspace_folder) or {}
    else:
        now_iso = datetime.now(timezone.utc).isoformat()
        ws_meta = {
            "name": proj_name,
            "created_at": now_iso,
            "modified_at": now_iso,
            "projects": [],
        }
        with open(ws_file, "w", encoding="utf-8") as f:
            json.dump(ws_meta, f, indent=2)

    # 2. Parse all data files
    data_files = sorted(
        [
            f for f in glob.glob(os.path.join(folder_path, "*.txt")) + glob.glob(os.path.join(folder_path, "*.csv"))
            if not f.endswith(".settings") and not f.endswith(".ok")
        ]
    )

    datasets_cache: Dict[str, Tuple[pd.DataFrame, str]] = {}
    for df_path in data_files:
        df_filename = os.path.basename(df_path)
        try:
            df, ds_name = parse_smartpls_dataset(df_path)
            datasets_cache[df_filename] = (df, ds_name)
        except Exception as e:
            print(f"Warning: could not parse dataset {df_filename}: {e}")

    # Fallback dataset if none found
    if not datasets_cache:
        # Create an empty dummy DataFrame
        datasets_cache["default_data.csv"] = (pd.DataFrame(), "Default Data")

    # 3. Decrypt and load all .splsm model files
    splsm_files = sorted(glob.glob(os.path.join(folder_path, "*.splsm")))
    models_by_datafile: Dict[str, List[Dict[str, Any]]] = {}

    for sf in splsm_files:
        mfilename = os.path.basename(sf)
        mname = os.path.splitext(mfilename)[0]
        try:
            splsm_dict = decrypt_smartpls_file(sf)
            target_datafile = splsm_dict.get("dataFileId") or (list(datasets_cache.keys())[0] if datasets_cache else None)
            
            spec, layout = convert_smartpls_model(splsm_dict)
            model_info = {
                "name": mname,
                "file": mfilename,
                "spec": spec,
                "layout": layout,
                "splsm_dict": splsm_dict,
            }
            if target_datafile not in models_by_datafile:
                models_by_datafile[target_datafile] = []
            models_by_datafile[target_datafile].append(model_info)
        except Exception as e:
            print(f"Warning: could not decrypt or convert {mfilename}: {e}")

    # 4. Create Studies (.pls SQLite files) per dataset (or per primary study)
    created_studies = []
    created_models = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # Assign primary dataset if some models have unmatched dataFileId
    primary_datafile = list(datasets_cache.keys())[0] if datasets_cache else None

    # Group datasets with their models
    processed_datafiles = set()
    for datafile_name, (df, ds_name) in datasets_cache.items():
        processed_datafiles.add(datafile_name)
        study_clean_name = ds_name.replace(" ", "_").replace("/", "_")
        study_filename = f"{study_clean_name}.pls"
        study_path = os.path.join(target_workspace_folder, study_filename)

        # Create or overwrite SQLite project file
        if os.path.exists(study_path):
            os.remove(study_path)
        project_io.create_project(study_path, ds_name)

        # Save dataset into raw_data table
        if df is not None and not df.empty:
            df_clean = df.astype(object).where(pd.notnull(df), None)
            dtypes = list(df.dtypes.astype(str))
            project_io.save_data(study_path, df_clean.values.tolist(), list(df.columns), dtypes, dataset_name=ds_name)

        study_id = f"study_smartpls_{int(datetime.now().timestamp()*1000)}_{len(created_studies)}"
        study_models_list = models_by_datafile.get(datafile_name, [])
        # If this is the primary dataset, also attach models that had no matched dataFileId
        if datafile_name == primary_datafile:
            for df_key, orphan_models in models_by_datafile.items():
                if df_key not in datasets_cache:
                    study_models_list.extend(orphan_models)

        # Save all models into this study's SQLite DB
        for m_idx, m_info in enumerate(study_models_list):
            model_key = f"model_smartpls_{int(datetime.now().timestamp()*1000)}_{m_idx}"
            project_io.save_model_spec(
                study_path,
                m_info["spec"],
                diagram_layout=m_info["layout"],
                model_id=model_key,
            )

            # Check if there is an associated report (.splsrp)
            # e.g., "1 Simple model - PLS - 2026-10-15.splsrp" matches "1 Simple model"
            model_base = m_info["name"]
            matching_reports = glob.glob(os.path.join(folder_path, f"{model_base}*.splsrp"))
            if matching_reports:
                try:
                    rep_dict = decrypt_smartpls_file(matching_reports[0])
                    # Store report summary in results
                    project_io.save_results(
                        study_path,
                        "pls",
                        {"smartpls_imported_report": rep_dict.get("reports", [])},
                        model_id=model_key,
                        spec=m_info["spec"],
                        diagram_layout=m_info["layout"],
                    )
                except Exception as ex:
                    print(f"Notice: could not import report for {model_base}: {ex}")

            created_models.append({
                "id": model_key,
                "studyId": study_id,
                "name": m_info["name"],
                "type": "pls",
                "lastModified": "Just now",
            })

        # Register study in workspace
        created_studies.append({
            "id": study_id,
            "workspaceId": target_workspace_folder,
            "name": ds_name,
            "type": "PLS-SEM",
            "description": f"Imported from SmartPLS project: {proj_name}",
            "lastModified": "Just now",
            "createdAt": now_iso,
            "path": study_path,
            "dataset_rows": len(df) if df is not None else 0,
            "dataset_columns": list(df.columns) if df is not None else [],
        })

        workspace_io.add_project_to_workspace(target_workspace_folder, study_filename, ds_name)

    # In case there were models but 0 datasets, create a study for models
    if not created_studies and models_by_datafile:
        study_filename = f"{proj_name.replace(' ', '_')}.pls"
        study_path = os.path.join(target_workspace_folder, study_filename)
        project_io.create_project(study_path, proj_name)
        study_id = f"study_smartpls_{int(datetime.now().timestamp()*1000)}"

        for m_idx, m_info in enumerate([m for m_list in models_by_datafile.values() for m in m_list]):
            model_key = f"model_smartpls_{int(datetime.now().timestamp()*1000)}_{m_idx}"
            project_io.save_model_spec(
                study_path,
                m_info["spec"],
                diagram_layout=m_info["layout"],
                model_id=model_key,
            )
            created_models.append({
                "id": model_key,
                "studyId": study_id,
                "name": m_info["name"],
                "type": "pls",
                "lastModified": "Just now",
            })

        created_studies.append({
            "id": study_id,
            "workspaceId": target_workspace_folder,
            "name": proj_name,
            "type": "PLS-SEM",
            "description": f"Imported from SmartPLS: {proj_name}",
            "lastModified": "Just now",
            "createdAt": now_iso,
            "path": study_path,
            "dataset_rows": 0,
            "dataset_columns": [],
        })
        workspace_io.add_project_to_workspace(target_workspace_folder, study_filename, proj_name)

    workspace_io.add_recent_workspace(target_workspace_folder)

    return {
        "status": "success",
        "workspace": {
            "id": target_workspace_folder,
            "name": proj_name,
            "path": target_workspace_folder,
            "createdAt": now_iso,
            "modifiedAt": now_iso,
        },
        "studies": created_studies,
        "models": created_models,
        "imported_from": folder_path,
    }
