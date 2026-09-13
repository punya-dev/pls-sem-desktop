import sqlite3
import json
import os
from datetime import datetime

SETTINGS_PATH = os.path.expanduser("~/.pls_sem_desktop_settings.json")

def create_project(path: str, project_name: str):
    if os.path.exists(path):
        raise FileExistsError("Project file already exists")

    os.makedirs(os.path.dirname(path), exist_ok=True)

    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE model_spec (
            id INTEGER PRIMARY KEY,
            spec_json TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE results (
            id INTEGER PRIMARY KEY,
            algorithm TEXT,
            results_json TEXT,
            created_at TEXT
        )
    """)
    # raw_data table is created dynamically in save_data(), since its
    # columns depend on the dataset's actual column names

    now = datetime.utcnow().isoformat()
    cur.executemany(
        "INSERT INTO metadata (key, value) VALUES (?, ?)",
        [("name", project_name), ("created_at", now), ("modified_at", now)],
    )

    conn.commit()
    conn.close()


def save_data(path: str, rows: list, columns: list, dtypes: list):
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS raw_data")

    def sql_type(dtype: str) -> str:
        if "int" in dtype or "float" in dtype:
            return "REAL"
        return "TEXT"

    col_defs = ", ".join(f'"{c}" {sql_type(t)}' for c, t in zip(columns, dtypes))
    cur.execute(f"CREATE TABLE raw_data ({col_defs})")

    placeholders = ", ".join("?" for _ in columns)
    col_names = ", ".join(f'"{c}"' for c in columns)
    cur.executemany(f"INSERT INTO raw_data ({col_names}) VALUES ({placeholders})", rows)

    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (datetime.utcnow().isoformat(),))
    conn.commit()
    conn.close()


def load_data(path: str):
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='raw_data'")
    if cur.fetchone() is None:
        conn.close()
        return None

    cur.execute("PRAGMA table_info(raw_data)")
    columns = [row[1] for row in cur.fetchall()]

    cur.execute("SELECT * FROM raw_data")
    rows = cur.fetchall()
    conn.close()

    return {"columns": columns, "rows": [list(r) for r in rows]}


def load_metadata(path: str):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM metadata")
    rows = cur.fetchall()
    conn.close()
    return dict(rows)

def _load_settings():
    if not os.path.exists(SETTINGS_PATH):
        return {"recent_projects": []}
    with open(SETTINGS_PATH, "r") as f:
        return json.load(f)

def _save_settings(settings):
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f)

def add_recent_project(path: str):
    settings = _load_settings()
    recents = [p for p in settings["recent_projects"] if p != path]  # dedupe
    recents.insert(0, path)  # most recent first
    settings["recent_projects"] = recents[:10]  # keep last 10
    _save_settings(settings)

def get_recent_projects():
    settings = _load_settings()
    projects = []
    for path in settings["recent_projects"]:
        if not os.path.exists(path):
            continue  # skip deleted/moved files
        try:
            meta = load_metadata(path)
            projects.append({
                "path": path,
                "name": meta.get("name", os.path.basename(path)),
                "modified_at": meta.get("modified_at"),
            })
        except Exception:
            continue
    return projects