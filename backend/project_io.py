import sqlite3
import json
import os
from datetime import datetime, timezone
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
            spec_json TEXT,
            diagram_layout_json TEXT,
            updated_at TEXT
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

    now = datetime.now(timezone.utc).isoformat()
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

    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (datetime.now(timezone.utc).isoformat(),))
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
    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (datetime.now(timezone.utc).isoformat(),))
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


def save_model_spec(path: str, spec: dict, diagram_layout: dict = None):
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='model_spec'")
    if cur.fetchone() is None:
        cur.execute("""
            CREATE TABLE model_spec (
                id INTEGER PRIMARY KEY,
                spec_json TEXT,
                diagram_layout_json TEXT,
                updated_at TEXT
            )
        """)
    else:
        cur.execute("PRAGMA table_info(model_spec)")
        cols = [r[1] for r in cur.fetchall()]
        if "diagram_layout_json" not in cols:
            cur.execute("ALTER TABLE model_spec ADD COLUMN diagram_layout_json TEXT")
        if "updated_at" not in cols:
            cur.execute("ALTER TABLE model_spec ADD COLUMN updated_at TEXT")

    now = datetime.now(timezone.utc).isoformat()
    spec_str = json.dumps(spec)
    layout_str = json.dumps(diagram_layout) if diagram_layout is not None else None

    cur.execute("DELETE FROM model_spec WHERE id = 1")
    cur.execute(
        "INSERT INTO model_spec (id, spec_json, diagram_layout_json, updated_at) VALUES (1, ?, ?, ?)",
        (spec_str, layout_str, now),
    )

    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (now,))
    conn.commit()
    conn.close()


def load_model_spec(path: str):
    if not os.path.exists(path):
        return None

    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='model_spec'")
    if cur.fetchone() is None:
        conn.close()
        return None

    cur.execute("PRAGMA table_info(model_spec)")
    cols = [r[1] for r in cur.fetchall()]

    cur.execute("SELECT * FROM model_spec WHERE id = 1")
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    row_dict = dict(zip(cols, row))
    spec_data = json.loads(row_dict["spec_json"]) if row_dict.get("spec_json") else None
    layout_data = json.loads(row_dict["diagram_layout_json"]) if row_dict.get("diagram_layout_json") else None

    return {
        "spec": spec_data,
        "diagram_layout": layout_data,
        "updated_at": row_dict.get("updated_at"),
    }