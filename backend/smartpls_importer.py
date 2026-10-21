import os
import glob
import json
import base64
import subprocess
import zipfile
import tempfile
import shutil
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
    Inspects a directory or ZIP file and returns whether it is a valid SmartPLS export,
    along with summary details (models found, datasets found).
    """
    folder_path = os.path.expanduser(folder_path)
    if not os.path.exists(folder_path):
        return {"valid": False, "error": "Path does not exist"}

    if zipfile.is_zipfile(folder_path):
        try:
            with zipfile.ZipFile(folder_path, "r") as zf:
                names = zf.namelist()
                splsm_files = [n for n in names if n.endswith(".splsm") and not os.path.basename(n).startswith(".")]
                data_files = [
                    n for n in names
                    if (n.endswith(".txt") or n.endswith(".csv"))
                    and not n.endswith(".settings")
                    and not n.endswith(".ok")
                    and not os.path.basename(n).startswith(".")
                ]
                has_meta = any(n.endswith(".meta") for n in names)
                if not splsm_files and not data_files and not has_meta:
                    return {"valid": False, "error": "No SmartPLS files (.splsm, datasets) found in ZIP archive"}

                proj_name = os.path.splitext(os.path.basename(folder_path))[0]
                model_summaries = [
                    {"file": os.path.basename(sf), "name": os.path.splitext(os.path.basename(sf))[0]}
                    for sf in splsm_files
                ]
                data_summaries = [os.path.basename(df) for df in data_files]

                return {
                    "valid": True,
                    "is_zip": True,
                    "project_name": proj_name,
                    "folder_path": folder_path,
                    "has_meta": has_meta,
                    "models_count": len(splsm_files),
                    "models": model_summaries,
                    "datasets_count": len(data_files),
                    "datasets": data_summaries,
                }
        except Exception as e:
            return {"valid": False, "error": f"Failed to read ZIP archive: {e}"}

    if not os.path.isdir(folder_path):
        parent_dir = os.path.dirname(folder_path)
        if os.path.isdir(parent_dir) and (
            glob.glob(os.path.join(parent_dir, "*.splsm"))
            or os.path.exists(os.path.join(parent_dir, ".meta"))
        ):
            folder_path = parent_dir
        else:
            return {"valid": False, "error": "Path is neither a directory nor a valid ZIP archive"}

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
        "is_zip": False,
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
    Fully imports a SmartPLS project (folder or ZIP file):
    - Sets up or opens the Workspace
    - Loads datasets into SQLite .pls Study databases
    - Decrypts and converts all .splsm models
    - Saves models into model_spec tables
    - Optionally loads .splsrp reports into results tables
    """
    folder_path = os.path.expanduser(folder_path)
    if os.path.isfile(folder_path) and not zipfile.is_zipfile(folder_path):
        parent_dir = os.path.dirname(folder_path)
        if os.path.isdir(parent_dir) and (
            glob.glob(os.path.join(parent_dir, "*.splsm"))
            or os.path.exists(os.path.join(parent_dir, ".meta"))
        ):
            folder_path = parent_dir

    detection = detect_smartpls_folder(folder_path)
    if not detection.get("valid"):
        raise ValueError(detection.get("error", "Invalid SmartPLS project"))

    proj_name = detection.get("project_name") or "SmartPLS Project"

    temp_extract_dir = None
    if zipfile.is_zipfile(folder_path):
        temp_extract_dir = tempfile.mkdtemp(prefix="smartpls_zip_")
        with zipfile.ZipFile(folder_path, "r") as zf:
            zf.extractall(temp_extract_dir)

        # Locate folder containing .splsm or data files
        candidate_dir = temp_extract_dir
        for root, dirs, files in os.walk(temp_extract_dir):
            if any(f.endswith(".splsm") or f.endswith(".txt") or f.endswith(".csv") for f in files):
                candidate_dir = root
                break
        active_source_dir = candidate_dir
    else:
        active_source_dir = folder_path

    try:
        # Destination directory for workspace
        if not target_workspace_folder:
            ws_title = workspace_name or proj_name
            target_workspace_folder = os.path.join(os.path.dirname(folder_path), f"{ws_title} - Workspace")
        target_workspace_folder = os.path.expanduser(target_workspace_folder)
        os.makedirs(target_workspace_folder, exist_ok=True)

        # 1. Initialize or load workspace.json
        ws_file = os.path.join(target_workspace_folder, "workspace.json")
        if os.path.exists(ws_file):
            ws_meta = workspace_io.load_workspace(target_workspace_folder) or {}
        else:
            ws_title = workspace_name or proj_name
            now_iso = datetime.now(timezone.utc).isoformat()
            ws_meta = {
                "name": ws_title,
                "created_at": now_iso,
                "modified_at": now_iso,
                "projects": [],
            }
            with open(ws_file, "w", encoding="utf-8") as f:
                json.dump(ws_meta, f, indent=2)

        # 2. Parse all data files
        data_files = sorted(
            [
                f for f in glob.glob(os.path.join(active_source_dir, "*.txt")) + glob.glob(os.path.join(active_source_dir, "*.csv"))
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
            datasets_cache["default_data.csv"] = (pd.DataFrame(), "Default Data")

        # 3. Decrypt and load all .splsm model files
        splsm_files = sorted(glob.glob(os.path.join(active_source_dir, "*.splsm")))
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

        # 4. Create Studies (.pls SQLite files) per dataset
        created_studies = []
        created_models = []
        now_iso = datetime.now(timezone.utc).isoformat()

        primary_datafile = list(datasets_cache.keys())[0] if datasets_cache else None

        for datafile_name, (df, ds_name) in datasets_cache.items():
            study_clean_name = ds_name.replace(" ", "_").replace("/", "_")
            study_filename = f"{study_clean_name}.pls"
            study_path = os.path.join(target_workspace_folder, study_filename)

            # Avoid collision with existing unrelated studies in workspace
            counter = 1
            while os.path.exists(study_path) and any(
                p.get("path") == study_filename and p.get("name") != ds_name
                for p in ws_meta.get("projects", [])
            ):
                study_filename = f"{study_clean_name}_{counter}.pls"
                study_path = os.path.join(target_workspace_folder, study_filename)
                counter += 1

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

                # Matching reports
                model_base = m_info["name"]
                matching_reports = glob.glob(os.path.join(active_source_dir, f"{model_base}*.splsrp"))
                if matching_reports:
                    try:
                        rep_dict = decrypt_smartpls_file(matching_reports[0])
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
                "description": f"Imported from SmartPLS project: {proj_name}",
                "lastModified": "Just now",
                "createdAt": now_iso,
                "path": study_path,
                "dataset_rows": 0,
                "dataset_columns": [],
            })
            workspace_io.add_project_to_workspace(target_workspace_folder, study_filename, proj_name)

        workspace_io.add_recent_workspace(target_workspace_folder)

        final_ws_meta = workspace_io.load_workspace(target_workspace_folder) or ws_meta
        return {
            "status": "success",
            "project_name": proj_name,
            "workspace": {
                "id": target_workspace_folder,
                "name": final_ws_meta.get("name", proj_name),
                "path": target_workspace_folder,
                "createdAt": final_ws_meta.get("created_at", now_iso),
                "modifiedAt": final_ws_meta.get("modified_at", now_iso),
            },
            "studies": created_studies,
            "models": created_models,
            "imported_from": folder_path,
        }
    finally:
        if temp_extract_dir and os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir, ignore_errors=True)


def detect_folder_type(folder_path: str) -> Dict[str, Any]:
    """
    Classifies a folder or file:
    - 'cspls_workspace': Has workspace.json or *.pls files
    - 'smartpls_workspace': Has .smartpls4workspace or subdirectories that are SmartPLS projects
    - 'smartpls_project': Contains .splsm files directly or is a ZIP archive containing .splsm
    - 'unknown': Other directory
    """
    folder_path = os.path.expanduser(folder_path)
    if not os.path.exists(folder_path):
        return {"kind": "not_found", "valid": False, "error": "Path does not exist"}

    if zipfile.is_zipfile(folder_path):
        det = detect_smartpls_folder(folder_path)
        if det.get("valid"):
            return {
                "kind": "smartpls_project",
                "is_zip": True,
                "path": folder_path,
                "project_name": det.get("project_name"),
                "models_count": det.get("models_count", 0),
                "datasets_count": det.get("datasets_count", 0),
            }
        return {"kind": "unknown", "path": folder_path}

    if not os.path.isdir(folder_path):
        return {"kind": "file", "path": folder_path}

    # 1. Check if CSPLS Workspace
    has_ws_json = os.path.exists(os.path.join(folder_path, "workspace.json"))
    has_pls_files = len(glob.glob(os.path.join(folder_path, "*.pls"))) > 0
    if has_ws_json or has_pls_files:
        ws_name = os.path.basename(folder_path.rstrip("/\\"))
        if has_ws_json:
            try:
                ws_meta = workspace_io.load_workspace(folder_path) or {}
                ws_name = ws_meta.get("name") or ws_name
            except Exception:
                pass
        return {
            "kind": "cspls_workspace",
            "path": folder_path,
            "name": ws_name,
        }

    # Direct splsm in folder? -> SmartPLS Project
    direct_splsm = glob.glob(os.path.join(folder_path, "*.splsm"))
    if direct_splsm:
        det = detect_smartpls_folder(folder_path)
        return {
            "kind": "smartpls_project",
            "is_zip": False,
            "path": folder_path,
            "project_name": det.get("project_name") or os.path.basename(folder_path.rstrip("/\\")),
            "models_count": det.get("models_count", 0),
            "datasets_count": det.get("datasets_count", 0),
        }

    # 2. Check if SmartPLS Workspace
    has_smartpls_ws_marker = os.path.exists(os.path.join(folder_path, ".smartpls4workspace"))
    sub_projects = []
    for item in os.listdir(folder_path):
        if item.startswith(".") or item == "Archive":
            continue
        sub_path = os.path.join(folder_path, item)
        if os.path.isdir(sub_path):
            sub_det = detect_smartpls_folder(sub_path)
            if sub_det.get("valid") and (sub_det.get("models_count", 0) > 0 or sub_det.get("datasets_count", 0) > 0):
                sub_projects.append({"name": item, "path": sub_path, **sub_det})

    if has_smartpls_ws_marker or len(sub_projects) > 0:
        return {
            "kind": "smartpls_workspace",
            "path": folder_path,
            "name": os.path.basename(folder_path.rstrip("/\\")),
            "projects_count": len(sub_projects),
            "projects": sub_projects,
        }

    return {
        "kind": "unknown",
        "path": folder_path,
        "name": os.path.basename(folder_path.rstrip("/\\")),
    }


def import_smartpls_workspace(workspace_folder: str) -> Dict[str, Any]:
    """
    Imports a full SmartPLS workspace (a directory containing .smartpls4workspace
    and/or subdirectories that are SmartPLS projects).
    Creates/updates workspace.json and imports all subprojects into studies in this workspace.
    """
    workspace_folder = os.path.expanduser(workspace_folder)
    if not os.path.isdir(workspace_folder):
        raise ValueError("Provided path is not a directory")

    ws_name = os.path.basename(workspace_folder.rstrip("/\\")) or "Workspace"
    ws_file = os.path.join(workspace_folder, "workspace.json")
    if not os.path.exists(ws_file):
        now_iso = datetime.now(timezone.utc).isoformat()
        ws_meta = {
            "name": ws_name,
            "created_at": now_iso,
            "modified_at": now_iso,
            "projects": [],
        }
        with open(ws_file, "w", encoding="utf-8") as f:
            json.dump(ws_meta, f, indent=2)

    all_studies = []
    all_models = []

    subdirs = [
        os.path.join(workspace_folder, d)
        for d in os.listdir(workspace_folder)
        if os.path.isdir(os.path.join(workspace_folder, d)) and not d.startswith(".") and d != "Archive"
    ]

    for subdir in subdirs:
        det = detect_smartpls_folder(subdir)
        if det.get("valid") and (det.get("models_count", 0) > 0 or det.get("datasets_count", 0) > 0):
            res = import_smartpls_folder(
                subdir,
                target_workspace_folder=workspace_folder,
                workspace_name=ws_name,
            )
            all_studies.extend(res.get("studies", []))
            all_models.extend(res.get("models", []))

    workspace_io.add_recent_workspace(workspace_folder)
    ws_meta = workspace_io.load_workspace(workspace_folder) or {}
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "status": "success",
        "workspace": {
            "id": workspace_folder,
            "name": ws_meta.get("name", ws_name),
            "path": workspace_folder,
            "createdAt": ws_meta.get("created_at", now_iso),
            "modifiedAt": ws_meta.get("modified_at", now_iso),
            "projects": ws_meta.get("projects", []),
        },
        "studies": all_studies,
        "models": all_models,
        "imported_from": workspace_folder,
    }

