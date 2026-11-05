import json
import os
import shutil
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import settings_io


def create_workspace(folder_path: str, name: str):
    folder_path = os.path.expanduser(folder_path)
    if os.path.exists(folder_path):
        raise FileExistsError("A folder already exists at this location")

    os.makedirs(folder_path)
    os.makedirs(os.path.join(folder_path, "Archive"), exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    metadata = {
        "name": name,
        "created_at": now,
        "modified_at": now,
        "projects": [],
        "archived_projects": [],
    }

    with open(os.path.join(folder_path, "workspace.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    return metadata


def load_workspace(folder_path: str):
    folder_path = os.path.expanduser(folder_path)
    ws_file = os.path.join(folder_path, "workspace.json")
    if not os.path.exists(ws_file):
        return None

    # Ensure physical Archive folder exists on disk in the offline workspace folder
    archive_dir = os.path.join(folder_path, "Archive")
    try:
        os.makedirs(archive_dir, exist_ok=True)
    except Exception:
        pass

    with open(ws_file, "r") as f:
        data = json.load(f)

    seen = set()
    if "projects" in data and isinstance(data["projects"], list):
        deduped = []
        for p in data["projects"]:
            pth = p.get("path")
            if pth and pth not in seen:
                seen.add(pth)
                deduped.append(p)
        data["projects"] = deduped

    data.setdefault("archived_projects", [])
    if isinstance(data.get("archived_projects"), list):
        seen_arch = set()
        deduped_arch = []
        for p in data["archived_projects"]:
            pth = p.get("path")
            if pth and pth not in seen_arch and pth not in seen:
                seen_arch.add(pth)
                deduped_arch.append(p)
        data["archived_projects"] = deduped_arch

    # Automatically discover any existing archived projects present in Archive/
    if os.path.exists(archive_dir):
        existing_arch_paths = {
            os.path.abspath(p.get("path")) if p.get("path") and os.path.isabs(p.get("path"))
            else os.path.abspath(os.path.join(folder_path, p.get("path", "")))
            for p in data.get("archived_projects", []) if isinstance(p, dict)
        }
        existing_arch_names = {
            p.get("name") for p in data.get("archived_projects", []) if isinstance(p, dict)
        }
        for item in os.listdir(archive_dir):
            if item.startswith(".") or item == "__MACOSX":
                continue
            item_path = os.path.join(archive_dir, item)
            if item.endswith(".pls") or item.endswith(".zip") or os.path.isdir(item_path):
                abs_item_path = os.path.abspath(item_path)
                p_name = os.path.splitext(item)[0]
                if abs_item_path not in existing_arch_paths and p_name not in existing_arch_names:
                    now = datetime.now(timezone.utc).isoformat()
                    rel_p = os.path.relpath(item_path, folder_path)
                    data.setdefault("archived_projects", []).append({
                        "name": p_name,
                        "path": item_path,
                        "relative_path": rel_p,
                        "archived_at": now,
                    })

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

    ws["projects"] = [p for p in ws.get("projects", []) if p.get("path") != project_filename]
    ws["archived_projects"] = [p for p in ws.get("archived_projects", []) if p.get("path") != project_filename]
    ws["modified_at"] = datetime.now(timezone.utc).isoformat()

    with open(os.path.join(folder_path, "workspace.json"), "w") as f:
        json.dump(ws, f, indent=2)

    return ws


def archive_project_in_workspace(folder_path: str, project_filename: str):
    folder_path = os.path.expanduser(folder_path)
    ws = load_workspace(folder_path)
    if ws is None:
        raise FileNotFoundError("Not a valid workspace")

    archive_dir = os.path.join(folder_path, "Archive")
    os.makedirs(archive_dir, exist_ok=True)

    target = None
    remaining = []
    norm_target = os.path.normpath(project_filename)
    base_target = os.path.basename(project_filename)

    for p in ws.get("projects", []):
        p_path = p.get("path", "")
        p_norm = os.path.normpath(p_path) if p_path else ""
        p_base = os.path.basename(p_path) if p_path else ""
        p_rel = os.path.normpath(p.get("relative_path", "")) if p.get("relative_path") else ""
        p_name = p.get("name", "")

        if (p_norm == norm_target or p_base == base_target or p_rel == norm_target or 
            p_path == project_filename or p_name == project_filename):
            target = p
        else:
            remaining.append(p)

    if not target:
        candidates = [
            project_filename,
            os.path.join(folder_path, project_filename),
            os.path.join(folder_path, base_target),
        ]
        found = next((c for c in candidates if os.path.exists(c)), None)
        if found:
            p_name = os.path.splitext(base_target)[0]
            target = {"name": p_name, "path": found, "relative_path": os.path.relpath(found, folder_path)}
        else:
            raise FileNotFoundError(f"Project '{project_filename}' not found in active projects")

    # Locate the project on disk and physically move into Archive/
    found_disk_path = None
    p_path = target.get("path") or project_filename
    disk_candidates = [
        p_path,
        os.path.join(folder_path, p_path),
        os.path.join(folder_path, os.path.basename(p_path)),
        os.path.join(folder_path, target.get("relative_path", "")),
    ]
    for c in disk_candidates:
        if c and os.path.exists(c):
            found_disk_path = os.path.abspath(c)
            break

    new_path = p_path
    new_rel_path = target.get("relative_path", "")
    if found_disk_path and os.path.exists(found_disk_path):
        src_parent = os.path.abspath(os.path.dirname(found_disk_path))
        ws_abs = os.path.abspath(folder_path)
        archive_abs = os.path.abspath(archive_dir)

        if not found_disk_path.startswith(archive_abs):
            if src_parent != ws_abs and os.path.dirname(src_parent) == ws_abs and os.path.basename(src_parent) != "Archive":
                # Project resides in its own subfolder under workspace
                dest_dir = os.path.join(archive_dir, os.path.basename(src_parent))
                if os.path.exists(dest_dir) and os.path.abspath(dest_dir) != src_parent:
                    shutil.rmtree(dest_dir, ignore_errors=True)
                if os.path.abspath(dest_dir) != src_parent:
                    shutil.move(src_parent, dest_dir)
                new_path = os.path.join(dest_dir, os.path.basename(found_disk_path))
            else:
                dest_file = os.path.join(archive_dir, os.path.basename(found_disk_path))
                if os.path.exists(dest_file) and os.path.abspath(dest_file) != found_disk_path:
                    os.remove(dest_file)
                if os.path.abspath(dest_file) != found_disk_path:
                    shutil.move(found_disk_path, dest_file)
                new_path = dest_file
            new_rel_path = os.path.relpath(new_path, folder_path)

    now = datetime.now(timezone.utc).isoformat()
    ws["projects"] = remaining
    archived_list = ws.get("archived_projects", [])
    archived_list = [p for p in archived_list if p.get("name") != target.get("name") and p.get("path") != target.get("path")]
    archived_item = dict(target)
    archived_item["path"] = new_path
    archived_item["relative_path"] = new_rel_path
    archived_item["archived_at"] = now
    archived_list.append(archived_item)
    ws["archived_projects"] = archived_list
    ws["modified_at"] = now

    with open(os.path.join(folder_path, "workspace.json"), "w") as f:
        json.dump(ws, f, indent=2)

    return ws


def restore_project_in_workspace(folder_path: str, project_filename: str):
    folder_path = os.path.expanduser(folder_path)
    ws = load_workspace(folder_path)
    if ws is None:
        raise FileNotFoundError("Not a valid workspace")

    archive_dir = os.path.join(folder_path, "Archive")
    os.makedirs(archive_dir, exist_ok=True)

    target = None
    remaining_archived = []
    norm_target = os.path.normpath(project_filename)
    base_target = os.path.basename(project_filename)

    for p in ws.get("archived_projects", []):
        p_path = p.get("path", "")
        p_norm = os.path.normpath(p_path) if p_path else ""
        p_base = os.path.basename(p_path) if p_path else ""
        p_rel = os.path.normpath(p.get("relative_path", "")) if p.get("relative_path") else ""
        p_name = p.get("name", "")

        if (p_norm == norm_target or p_base == base_target or p_rel == norm_target or 
            p_path == project_filename or p_name == project_filename):
            target = p
        else:
            remaining_archived.append(p)

    if not target:
        raise FileNotFoundError(f"Project '{project_filename}' not found in archived projects")

    p_path = target.get("path") or project_filename
    disk_candidates = [
        p_path,
        os.path.join(archive_dir, p_path),
        os.path.join(archive_dir, os.path.basename(p_path)),
        os.path.join(folder_path, target.get("relative_path", "")),
        os.path.join(folder_path, p_path),
    ]
    found_disk_path = None
    for c in disk_candidates:
        if c and os.path.exists(c):
            found_disk_path = os.path.abspath(c)
            break

    new_path = p_path
    new_rel_path = target.get("relative_path", "")
    if found_disk_path and os.path.exists(found_disk_path):
        src_parent = os.path.abspath(os.path.dirname(found_disk_path))
        archive_abs = os.path.abspath(archive_dir)
        ws_abs = os.path.abspath(folder_path)

        if src_parent != archive_abs and os.path.dirname(src_parent) == archive_abs:
            dest_dir = os.path.join(folder_path, os.path.basename(src_parent))
            if os.path.exists(dest_dir) and os.path.abspath(dest_dir) != src_parent:
                shutil.rmtree(dest_dir, ignore_errors=True)
            if os.path.abspath(dest_dir) != src_parent:
                shutil.move(src_parent, dest_dir)
            new_path = os.path.join(dest_dir, os.path.basename(found_disk_path))
        else:
            dest_file = os.path.join(folder_path, os.path.basename(found_disk_path))
            if os.path.exists(dest_file) and os.path.abspath(dest_file) != found_disk_path:
                os.remove(dest_file)
            if os.path.abspath(dest_file) != found_disk_path:
                shutil.move(found_disk_path, dest_file)
            new_path = dest_file
        new_rel_path = os.path.relpath(new_path, folder_path)

    ws["archived_projects"] = remaining_archived
    projects_list = ws.get("projects", [])
    restored_item = {k: v for k, v in target.items() if k != "archived_at"}
    restored_item["path"] = new_path
    restored_item["relative_path"] = new_rel_path
    projects_list.append(restored_item)
    ws["projects"] = projects_list
    ws["modified_at"] = datetime.now(timezone.utc).isoformat()

    with open(os.path.join(folder_path, "workspace.json"), "w") as f:
        json.dump(ws, f, indent=2)

    return ws


def delete_archived_project_from_workspace(folder_path: str, project_filename: str):
    folder_path = os.path.expanduser(folder_path)
    ws = load_workspace(folder_path)
    if ws is None:
        raise FileNotFoundError("Not a valid workspace")

    archive_dir = os.path.join(folder_path, "Archive")
    target = None
    remaining_archived = []
    norm_target = os.path.normpath(project_filename)
    base_target = os.path.basename(project_filename)

    for p in ws.get("archived_projects", []):
        p_path = p.get("path", "")
        p_norm = os.path.normpath(p_path) if p_path else ""
        p_base = os.path.basename(p_path) if p_path else ""
        p_rel = os.path.normpath(p.get("relative_path", "")) if p.get("relative_path") else ""
        p_name = p.get("name", "")

        if (p_norm == norm_target or p_base == base_target or p_rel == norm_target or 
            p_path == project_filename or p_name == project_filename):
            target = p
        else:
            remaining_archived.append(p)

    ws["archived_projects"] = remaining_archived
    ws["modified_at"] = datetime.now(timezone.utc).isoformat()

    p_path = target.get("path") if target else project_filename
    disk_candidates = [
        p_path,
        os.path.join(archive_dir, p_path),
        os.path.join(archive_dir, os.path.basename(p_path)),
        os.path.join(folder_path, p_path),
        os.path.join(folder_path, os.path.basename(p_path)),
    ]
    for c in disk_candidates:
        if c and os.path.exists(c):
            if os.path.isdir(c):
                shutil.rmtree(c, ignore_errors=True)
            else:
                os.remove(c)
                parent = os.path.dirname(c)
                if os.path.abspath(parent) != os.path.abspath(archive_dir) and os.path.dirname(os.path.abspath(parent)) == os.path.abspath(archive_dir):
                    try:
                        if not os.listdir(parent):
                            os.rmdir(parent)
                    except Exception:
                        pass
            break

    with open(os.path.join(folder_path, "workspace.json"), "w") as f:
        json.dump(ws, f, indent=2)

    if target and target.get("path"):
        settings_io.remove_recent("recent_projects", target.get("path"))
    return ws


def delete_workspace(folder_path: str):
    folder_path = os.path.expanduser(folder_path)
    if not os.path.exists(folder_path):
        raise FileNotFoundError("Workspace folder not found")
    shutil.rmtree(folder_path)
    settings_io.remove_recent("recent_workspaces", folder_path)
    settings_io.remove_recent("archived_workspaces", folder_path)
    return {"status": "deleted", "path": folder_path}


def get_statsem_archive_dir() -> str:
    archive_dir = os.path.expanduser("~/StatSEM/Archive")
    os.makedirs(archive_dir, exist_ok=True)
    return archive_dir


def archive_workspace(folder_path: str) -> Dict[str, Any]:
    folder_path = os.path.expanduser(folder_path)
    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"Workspace folder not found: {folder_path}")

    archive_base = get_statsem_archive_dir()
    ws_name = os.path.basename(os.path.abspath(folder_path))

    ws_file = os.path.join(folder_path, "workspace.json")
    ws_meta = {}
    if os.path.exists(ws_file):
        try:
            with open(ws_file, "r") as f:
                ws_meta = json.load(f)
        except Exception:
            ws_meta = {}

    now_iso = datetime.now(timezone.utc).isoformat()
    ws_meta["original_path"] = os.path.abspath(folder_path)
    ws_meta["archived_at"] = now_iso
    ws_meta["name"] = ws_meta.get("name") or ws_name

    try:
        with open(ws_file, "w") as f:
            json.dump(ws_meta, f, indent=2)
    except Exception as e:
        print(f"Warning writing original_path to workspace.json: {e}")

    dest_dir = os.path.join(archive_base, ws_name)
    if os.path.exists(dest_dir) and os.path.abspath(dest_dir) != os.path.abspath(folder_path):
        counter = 1
        while os.path.exists(dest_dir):
            dest_dir = os.path.join(archive_base, f"{ws_name} ({counter})")
            counter += 1

    if os.path.abspath(folder_path) != os.path.abspath(dest_dir):
        shutil.move(folder_path, dest_dir)

    settings_io.remove_recent("recent_workspaces", folder_path)
    settings_io.add_recent("archived_workspaces", dest_dir)

    return {
        "status": "archived",
        "old_path": folder_path,
        "new_path": dest_dir,
        "name": ws_name,
        "archived_at": now_iso,
    }


def restore_workspace(folder_path: str) -> Dict[str, Any]:
    folder_path = os.path.expanduser(folder_path)
    if not os.path.exists(folder_path):
        candidate = os.path.join(get_statsem_archive_dir(), folder_path)
        if os.path.exists(candidate):
            folder_path = candidate
        else:
            raise FileNotFoundError(f"Archived workspace folder not found: {folder_path}")

    ws_file = os.path.join(folder_path, "workspace.json")
    ws_meta = {}
    if os.path.exists(ws_file):
        try:
            with open(ws_file, "r") as f:
                ws_meta = json.load(f)
        except Exception:
            ws_meta = {}

    original_path = ws_meta.get("original_path")
    ws_name = ws_meta.get("name") or os.path.basename(folder_path)

    if original_path:
        dest_dir = os.path.abspath(original_path)
        if os.path.exists(dest_dir) and os.path.abspath(dest_dir) != os.path.abspath(folder_path):
            parent = os.path.dirname(dest_dir)
            base_n = os.path.basename(dest_dir)
            counter = 1
            while os.path.exists(dest_dir):
                dest_dir = os.path.join(parent, f"{base_n} ({counter})")
                counter += 1
    else:
        default_parent = os.path.expanduser("~/StatSEM/Workspaces")
        os.makedirs(default_parent, exist_ok=True)
        dest_dir = os.path.join(default_parent, ws_name)
        if os.path.exists(dest_dir) and os.path.abspath(dest_dir) != os.path.abspath(folder_path):
            counter = 1
            while os.path.exists(dest_dir):
                dest_dir = os.path.join(default_parent, f"{ws_name} ({counter})")
                counter += 1

    os.makedirs(os.path.dirname(dest_dir), exist_ok=True)

    if os.path.abspath(folder_path) != os.path.abspath(dest_dir):
        shutil.move(folder_path, dest_dir)

    new_ws_file = os.path.join(dest_dir, "workspace.json")
    if os.path.exists(new_ws_file):
        try:
            with open(new_ws_file, "r") as f:
                saved_meta = json.load(f)
            saved_meta.pop("original_path", None)
            saved_meta.pop("archived_at", None)
            saved_meta["modified_at"] = datetime.now(timezone.utc).isoformat()
            with open(new_ws_file, "w") as f:
                json.dump(saved_meta, f, indent=2)
        except Exception as e:
            print(f"Warning updating restored workspace.json: {e}")

    settings_io.remove_recent("archived_workspaces", folder_path)
    settings_io.add_recent("recent_workspaces", dest_dir)

    return {
        "status": "restored",
        "old_path": folder_path,
        "new_path": dest_dir,
        "name": os.path.basename(dest_dir),
    }


def get_statsem_archived_workspaces() -> List[Dict[str, Any]]:
    archive_dir = get_statsem_archive_dir()
    archived_list = []
    seen = set()

    if os.path.exists(archive_dir):
        for item in os.listdir(archive_dir):
            if item.startswith(".") or item == "__MACOSX":
                continue
            item_path = os.path.join(archive_dir, item)
            if os.path.isdir(item_path):
                ws = load_workspace(item_path)
                seen.add(os.path.abspath(item_path))
                archived_list.append({
                    "id": item_path,
                    "path": item_path,
                    "name": ws.get("name", item) if ws else item,
                    "original_path": ws.get("original_path") if ws else None,
                    "archived_at": ws.get("archived_at") if ws else None,
                    "project_count": len(ws.get("projects", [])) if ws else 0,
                })

    settings = settings_io.load_settings()
    for p in settings.get("archived_workspaces", []):
        p_exp = os.path.expanduser(p)
        if os.path.exists(p_exp) and os.path.abspath(p_exp) not in seen:
            ws = load_workspace(p_exp)
            seen.add(os.path.abspath(p_exp))
            archived_list.append({
                "id": p_exp,
                "path": p_exp,
                "name": ws.get("name", os.path.basename(p_exp)) if ws else os.path.basename(p_exp),
                "original_path": ws.get("original_path") if ws else None,
                "archived_at": ws.get("archived_at") if ws else None,
                "project_count": len(ws.get("projects", [])) if ws else 0,
            })

    return archived_list



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

    def resolve_project_path(p_entry):
        p_path = p_entry.get("path", "")
        rel_path = p_entry.get("relative_path", "")
        candidates = []
        if rel_path:
            candidates.append(os.path.join(target_ws_dir, rel_path))
        if not os.path.isabs(p_path):
            candidates.append(os.path.join(target_ws_dir, p_path))
        else:
            candidates.append(os.path.join(target_ws_dir, os.path.basename(p_path)))
            p_name = p_entry.get("name") or os.path.splitext(os.path.basename(p_path))[0]
            candidates.append(os.path.join(target_ws_dir, p_name, os.path.basename(p_path)))
            candidates.append(p_path)

        for cand in candidates:
            if os.path.exists(cand):
                return cand

        base_name = os.path.basename(p_path) if p_path else ""
        if base_name:
            for root, _, files in os.walk(target_ws_dir):
                if base_name in files:
                    return os.path.join(root, base_name)
        return candidates[0] if candidates else p_path

    for p in ws_meta.get("projects", []):
        if isinstance(p, dict):
            p["path"] = resolve_project_path(p)
            try:
                p["relative_path"] = os.path.relpath(p["path"], target_ws_dir)
            except Exception:
                p["relative_path"] = os.path.basename(p["path"])

    for p in ws_meta.get("archived_projects", []):
        if isinstance(p, dict):
            p["path"] = resolve_project_path(p)
            try:
                p["relative_path"] = os.path.relpath(p["path"], target_ws_dir)
            except Exception:
                p["relative_path"] = os.path.basename(p["path"])

    pls_files = []
    for root, _, files in os.walk(target_ws_dir):
        for f in files:
            if f.endswith(".pls"):
                pls_files.append(os.path.join(root, f))

    existing_proj_paths = {p.get("path") for p in ws_meta.get("projects", []) if isinstance(p, dict)}
    existing_archived_paths = {p.get("path") for p in ws_meta.get("archived_projects", []) if isinstance(p, dict)}
    for pf in pls_files:
        try:
            project_io.migrate_project(pf)
        except Exception as e:
            print(f"Warning migrating {pf}: {e}")
        rel_pf = os.path.relpath(pf, target_ws_dir)
        if pf not in existing_proj_paths and pf not in existing_archived_paths and rel_pf not in existing_proj_paths and rel_pf not in existing_archived_paths:
            p_name = os.path.splitext(os.path.basename(pf))[0]
            ws_meta.setdefault("projects", []).append({"path": pf, "relative_path": rel_pf, "name": p_name})

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
                "isArchived": False,
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

    for p in ws_meta.get("archived_projects", []):
        p_path = p.get("path")
        p_name = p.get("name") or os.path.splitext(p_path)[0]
        full_p_path = p_path if os.path.isabs(p_path) else os.path.join(target_ws_dir, p_path)
        if os.path.exists(full_p_path):
            studies_list.append({
                "id": full_p_path,
                "name": p_name,
                "type": "PLS-SEM",
                "path": full_p_path,
                "createdAt": p.get("archived_at") or "Just now",
                "lastModified": "Archived",
                "isArchived": True,
                "archivedAt": p.get("archived_at"),
            })
            try:
                tree = project_io.get_project_tree(full_p_path)
                for m in tree.get("models", []):
                    models_list.append({
                        "id": m["id"],
                        "studyId": full_p_path,
                        "name": m["name"],
                        "type": "PLS-SEM",
                        "lastModified": "Archived",
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
            "archived_projects": ws_meta.get("archived_projects", []),
        },
        "studies": studies_list,
        "models": models_list,
    }
    