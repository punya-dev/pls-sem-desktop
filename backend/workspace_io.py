import json
import os
from datetime import datetime
import settings_io
def create_workspace(folder_path: str, name: str):
    if os.path.exists(folder_path):
        raise FileExistsError("A folder already exists at this location")

    os.makedirs(folder_path)

    now = datetime.utcnow().isoformat()
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
    ws_file = os.path.join(folder_path, "workspace.json")
    if not os.path.exists(ws_file):
        return None
    with open(ws_file, "r") as f:
        return json.load(f)


def add_project_to_workspace(folder_path: str, project_filename: str, project_name: str):
    ws = load_workspace(folder_path)
    if ws is None:
        raise FileNotFoundError("Not a valid workspace")

    ws["projects"].append({"path": project_filename, "name": project_name})
    ws["modified_at"] = datetime.utcnow().isoformat()

    with open(os.path.join(folder_path, "workspace.json"), "w") as f:
        json.dump(ws, f, indent=2)

    return ws


def remove_project_from_workspace(folder_path: str, project_filename: str):
    ws = load_workspace(folder_path)
    if ws is None:
        raise FileNotFoundError("Not a valid workspace")

    ws["projects"] = [p for p in ws["projects"] if p["path"] != project_filename]
    ws["modified_at"] = datetime.utcnow().isoformat()

    with open(os.path.join(folder_path, "workspace.json"), "w") as f:
        json.dump(ws, f, indent=2)

    return ws


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

    