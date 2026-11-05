import json
import os

SETTINGS_PATH = os.path.expanduser("~/.pls_sem_desktop_settings.json")

def load_settings():
    if not os.path.exists(SETTINGS_PATH):
        return {"recent_projects": [], "recent_workspaces": [], "archived_workspaces": []}
    try:
        with open(SETTINGS_PATH, "r") as f:
            content = f.read().strip()
            if not content:
                return {"recent_projects": [], "recent_workspaces": [], "archived_workspaces": []}
            data = json.loads(content)
            data.setdefault("recent_projects", [])
            data.setdefault("recent_workspaces", [])
            data.setdefault("archived_workspaces", [])
            return data
    except Exception:
        return {"recent_projects": [], "recent_workspaces": [], "archived_workspaces": []}

def save_settings(settings):
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f)

def add_recent(key: str, path: str):
    settings = load_settings()
    recents = [p for p in settings[key] if p != path]
    recents.insert(0, path)
    settings[key] = recents[:10]
    save_settings(settings)

def remove_recent(key: str, path: str):
    settings = load_settings()
    if key in settings:
        settings[key] = [p for p in settings[key] if p != path]
        save_settings(settings)

def get_recent(key: str):
    return load_settings()[key]