import json
import os
from datetime import datetime, timezone
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

    