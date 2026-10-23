import json
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import settings_io
def create_workspace(folder_path: str, name: str):
    folder_path = os.path.expanduser(folder_path)
    if os.path.exists(folder_path):
        raise FileExistsError("A folder already exists at this location")

    os.makedirs(folder_path)

    now = datetime.now(timezone.utc).isoformat()
    metadata = {
        "name": name,
        "created_at": now,
        "modified_at": now,
        "projects": [],
    }

    with open(os.path.join(folder_path, "workspace.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    return metadata


def load_workspace(folder_path: str):
    folder_path = os.path.expanduser(folder_path)
    ws_file = os.path.join(folder_path, "workspace.json")
    if not os.path.exists(ws_file):
        return None
    with open(ws_file, "r") as f:
        data = json.load(f)
    if "projects" in data and isinstance(data["projects"], list):
        seen = set()
        deduped = []
        for p in data["projects"]:
            pth = p.get("path")
            if pth and pth not in seen:
                seen.add(pth)
                deduped.append(p)
        data["projects"] = deduped
    return data


def add_project_to_workspace(folder_path: str, project_filename: str, project_name: str):
    folder_path = os.path.expanduser(folder_path)
    ws = load_workspace(folder_path)
    if ws is None:
        raise FileNotFoundError("Not a valid workspace")

    if not any(p.get("path") == project_filename for p in ws["projects"]):
        ws["projects"].append({"path": project_filename, "name": project_name})
        ws["modified_at"] = datetime.now(timezone.utc).isoformat()

        with open(os.path.join(folder_path, "workspace.json"), "w") as f:
            json.dump(ws, f, indent=2)

    return ws


def remove_project_from_workspace(folder_path: str, project_filename: str):
    folder_path = os.path.expanduser(folder_path)
    ws = load_workspace(folder_path)
    if ws is None:
        raise FileNotFoundError("Not a valid workspace")

    ws["projects"] = [p for p in ws["projects"] if p["path"] != project_filename]
    ws["modified_at"] = datetime.now(timezone.utc).isoformat()

    with open(os.path.join(folder_path, "workspace.json"), "w") as f:
        json.dump(ws, f, indent=2)

    return ws


def delete_workspace(folder_path: str):
    folder_path = os.path.expanduser(folder_path)
    if not os.path.exists(folder_path):
        raise FileNotFoundError("Workspace folder not found")
    import shutil
    shutil.rmtree(folder_path)
    settings_io.remove_recent("recent_workspaces", folder_path)
    return {"status": "deleted", "path": folder_path}



# --- recent workspaces tracking, same pattern as recent projects ---

def add_recent_workspace(folder_path: str):
    settings_io.add_recent("recent_workspaces", folder_path)

def get_recent_workspaces():
    settings = settings_io.load_settings()
    workspaces = []
    for path in settings["recent_workspaces"]:
        ws = load_workspace(path)
        if ws is None:
            continue
        workspaces.append({
            "path": path,
            "name": ws.get("name", os.path.basename(path)),
            "modified_at": ws.get("modified_at"),
            "workspace_count": len(ws.get("workspaces", [])),
        })
    return workspaces


def duplicate_workspace(source_folder_path: str, new_name: str):
    import shutil
    source_folder_path = os.path.expanduser(source_folder_path)
    if not os.path.exists(source_folder_path):
        raise FileNotFoundError("Source workspace folder not found")

    parent_dir = os.path.dirname(source_folder_path)
    clean_name = "".join(c for c in new_name if c.isalnum() or c in (" ", "-", "_")).strip()
    if not clean_name:
        clean_name = "Workspace Copy"
    target_folder_path = os.path.join(parent_dir, clean_name)
    counter = 1
    while os.path.exists(target_folder_path):
        target_folder_path = os.path.join(parent_dir, f"{clean_name} ({counter})")
        counter += 1

    shutil.copytree(source_folder_path, target_folder_path)

    ws_file = os.path.join(target_folder_path, "workspace.json")
    if os.path.exists(ws_file):
        with open(ws_file, "r") as f:
            data = json.load(f)
        now = datetime.now(timezone.utc).isoformat()
        data["name"] = new_name
        data["created_at"] = now
        data["modified_at"] = now
        with open(ws_file, "w") as f:
            json.dump(data, f, indent=2)

    add_recent_workspace(target_folder_path)
    return {
        "status": "duplicated",
        "workspace_path": target_folder_path,
        "name": new_name
    }


def export_workspace_zip(workspace_path: str, out_zip_path: str) -> str:
    import zipfile
    workspace_path = os.path.expanduser(workspace_path)
    out_zip_path = os.path.expanduser(out_zip_path)
    if not os.path.exists(workspace_path):
        raise FileNotFoundError(f"Workspace folder not found: {workspace_path}")

    parent_dir = os.path.dirname(out_zip_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with zipfile.ZipFile(out_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(workspace_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for f in files:
                if f.startswith(".") or f.endswith(".pyc") or f.endswith(".tmp"):
                    continue
                file_path = os.path.join(root, f)
                arcname = os.path.relpath(file_path, workspace_path)
                zf.write(file_path, arcname)

    return out_zip_path


def import_workspace_zip(zip_path: str, target_parent_folder: Optional[str] = None) -> Dict[str, Any]:
    import zipfile
    import glob
    import project_io

    zip_path = os.path.expanduser(zip_path)
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"Zip file not found: {zip_path}")
    if not zipfile.is_zipfile(zip_path):
        raise ValueError(f"File is not a valid zip archive: {zip_path}")

    base_dir = target_parent_folder or os.path.expanduser("~/StatSEM/Workspaces")
    base_dir = os.path.expanduser(base_dir)
    os.makedirs(base_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            if member.startswith("/") or member.startswith("\\") or ".." in member:
                raise ValueError(f"Unsafe zip archive entry: {member}")

        names = zf.namelist()
        ws_json_entry = next((n for n in names if n == "workspace.json" or n.endswith("/workspace.json")), None)

        ws_name = os.path.splitext(os.path.basename(zip_path))[0]
        if ws_json_entry:
            try:
                raw_meta = json.loads(zf.read(ws_json_entry).decode("utf-8"))
                ws_name = raw_meta.get("name") or ws_name
            except Exception:
                pass

        target_ws_dir = os.path.join(base_dir, ws_name)
        counter = 1
        while os.path.exists(target_ws_dir):
            target_ws_dir = os.path.join(base_dir, f"{ws_name}_{counter}")
            counter += 1

        os.makedirs(target_ws_dir, exist_ok=True)

        prefix = ""
        if ws_json_entry and "/" in ws_json_entry:
            prefix = ws_json_entry.rsplit("workspace.json", 1)[0]

        for member in zf.infolist():
            if member.is_dir():
                continue
            filename = member.filename
            if filename.startswith("__MACOSX") or os.path.basename(filename).startswith("."):
                continue
            rel_name = filename
            if prefix and rel_name.startswith(prefix):
                rel_name = rel_name[len(prefix):]
            rel_name = rel_name.lstrip("/\\")
            if not rel_name:
                continue

            target_file_path = os.path.join(target_ws_dir, rel_name)
            os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
            with open(target_file_path, "wb") as f_out:
                f_out.write(zf.read(member.filename))

    actual_ws_name = os.path.basename(target_ws_dir)
    ws_file = os.path.join(target_ws_dir, "workspace.json")
    if not os.path.exists(ws_file):
        now = datetime.now(timezone.utc).isoformat()
        ws_meta = {
            "name": actual_ws_name,
            "created_at": now,
            "modified_at": now,
            "projects": [],
        }
    else:
        try:
            with open(ws_file, "r") as f:
                ws_meta = json.load(f)
        except Exception:
            ws_meta = {"name": actual_ws_name, "projects": []}
        ws_meta["name"] = actual_ws_name

    pls_files = glob.glob(os.path.join(target_ws_dir, "*.pls"))
    existing_proj_paths = {p.get("path") for p in ws_meta.get("projects", []) if isinstance(p, dict)}
    for pf in pls_files:
        try:
            project_io.migrate_project(pf)
        except Exception as e:
            print(f"Warning migrating {pf}: {e}")
        rel_pf = os.path.basename(pf)
        if rel_pf not in existing_proj_paths:
            p_name = os.path.splitext(rel_pf)[0]
            ws_meta.setdefault("projects", []).append({"path": rel_pf, "name": p_name})

    with open(ws_file, "w") as f:
        json.dump(ws_meta, f, indent=2)

    add_recent_workspace(target_ws_dir)

    studies_list = []
    models_list = []
    for p in ws_meta.get("projects", []):
        p_path = p.get("path")
        p_name = p.get("name") or os.path.splitext(p_path)[0]
        full_p_path = p_path if os.path.isabs(p_path) else os.path.join(target_ws_dir, p_path)
        if os.path.exists(full_p_path):
            studies_list.append({
                "id": full_p_path,
                "name": p_name,
                "type": "PLS-SEM",
                "path": full_p_path,
                "createdAt": "Just now",
                "lastModified": "Just now",
            })
            try:
                tree = project_io.get_project_tree(full_p_path)
                for m in tree.get("models", []):
                    models_list.append({
                        "id": m["id"],
                        "studyId": full_p_path,
                        "name": m["name"],
                        "type": "PLS-SEM",
                        "lastModified": "Just now",
                    })
            except Exception as e:
                print(f"Warning reading models from {full_p_path}: {e}")

    return {
        "status": "imported",
        "path": target_ws_dir,
        "workspace": {
            "id": target_ws_dir,
            "name": actual_ws_name,
            "path": target_ws_dir,
            "projects": ws_meta.get("projects", []),
        },
        "studies": studies_list,
        "models": models_list,
    }
    