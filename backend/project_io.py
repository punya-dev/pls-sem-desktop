import sqlite3
import json
import os
from datetime import datetime
import settings_io

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


def save_data(path: str, rows: list, columns: list, dtypes: list, dataset_name: str = None):
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
    if dataset_name:
        cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('dataset_name', ?)", (dataset_name,))
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

    cur.execute("SELECT value FROM metadata WHERE key='dataset_name'")
    ds_row = cur.fetchone()
    dataset_name = ds_row[0] if ds_row else None

    conn.close()

    return {"columns": columns, "rows": [list(r) for r in rows], "dataset_name": dataset_name}


def delete_data(path: str):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS raw_data")
    cur.execute("DELETE FROM metadata WHERE key='dataset_name'")
    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (datetime.utcnow().isoformat(),))
    conn.commit()
    conn.close()


def load_metadata(path: str):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM metadata")
    rows = cur.fetchall()
    conn.close()
    return dict(rows)


def add_recent_project(path: str):
    settings_io.add_recent("recent_projects",path)

def get_recent_projects():
    paths = settings_io.get_recent("recent_projects")
    projects = []
    for path in paths:
        if not os.path.exists(path):
            continue
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