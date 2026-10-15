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
            updated_at TEXT,
            model_key TEXT
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


def save_model_spec(path: str, spec: dict, diagram_layout: dict = None, model_id: str = None):
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='model_spec'")
    if cur.fetchone() is None:
        cur.execute("""
            CREATE TABLE model_spec (
                id INTEGER PRIMARY KEY,
                spec_json TEXT,
                diagram_layout_json TEXT,
                updated_at TEXT,
                model_key TEXT
            )
        """)
    else:
        cur.execute("PRAGMA table_info(model_spec)")
        cols = [r[1] for r in cur.fetchall()]
        if "diagram_layout_json" not in cols:
            cur.execute("ALTER TABLE model_spec ADD COLUMN diagram_layout_json TEXT")
        if "updated_at" not in cols:
            cur.execute("ALTER TABLE model_spec ADD COLUMN updated_at TEXT")
        if "model_key" not in cols:
            cur.execute("ALTER TABLE model_spec ADD COLUMN model_key TEXT")

    now = datetime.now(timezone.utc).isoformat()
    spec_str = json.dumps(spec)
    layout_str = json.dumps(diagram_layout) if diagram_layout is not None else None

    if model_id:
        cur.execute("SELECT id FROM model_spec WHERE model_key = ?", (model_id,))
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE model_spec SET spec_json = ?, diagram_layout_json = ?, updated_at = ? WHERE id = ?",
                (spec_str, layout_str, now, row[0]),
            )
        else:
            cur.execute(
                "INSERT INTO model_spec (spec_json, diagram_layout_json, updated_at, model_key) VALUES (?, ?, ?, ?)",
                (spec_str, layout_str, now, model_id),
            )
    else:
        cur.execute("DELETE FROM model_spec WHERE id = 1")
        cur.execute(
            "INSERT INTO model_spec (id, spec_json, diagram_layout_json, updated_at, model_key) VALUES (1, ?, ?, ?, 'default')",
            (spec_str, layout_str, now),
        )

    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (now,))
    conn.commit()
    conn.close()


def load_model_spec(path: str, model_id: str = None):
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

    row = None
    if model_id and "model_key" in cols:
        cur.execute("SELECT * FROM model_spec WHERE model_key = ?", (model_id,))
        row = cur.fetchone()

    if not row and not model_id:
        cur.execute("SELECT * FROM model_spec WHERE id = 1")
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT * FROM model_spec ORDER BY id ASC LIMIT 1")
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
        "model_key": row_dict.get("model_key") if "model_key" in row_dict else None,
    }


def duplicate_model_spec(path: str, source_model_id: str, new_model_id: str):
    source = load_model_spec(path, source_model_id)
    if not source:
        source = load_model_spec(path)

    spec = json.loads(json.dumps(source.get("spec", {}))) if source else {}
    diagram_layout = json.loads(json.dumps(source.get("diagram_layout", {}))) if source else {}
    save_model_spec(path, spec, diagram_layout, model_id=new_model_id)

    # Duplicate calculation results specifically for the new model so they are completely independent
    source_res = load_results(path, algorithm="pls", model_id=source_model_id)
    if source_res and source_res.get("results"):
        save_results(
            path,
            "pls",
            json.loads(json.dumps(source_res["results"])),
            model_id=new_model_id,
            spec=json.loads(json.dumps(source_res.get("spec") or spec)),
            diagram_layout=json.loads(json.dumps(source_res.get("diagram_layout") or diagram_layout)),
        )

    return {"status": "duplicated", "model_id": new_model_id}


def duplicate_project(folder_path: str, source_path: str, new_name: str, model_id_map: dict = None):
    import shutil
    import workspace_io
    folder_path = os.path.expanduser(folder_path)
    source_path = os.path.expanduser(source_path)

    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source project file not found: {source_path}")

    clean_name = "".join(c for c in new_name if c.isalnum() or c in (" ", "-", "_")).strip()
    if not clean_name:
        clean_name = "Untitled Study Copy"

    base_filename = f"{clean_name}.pls"
    target_path = os.path.join(folder_path, base_filename)
    counter = 1
    while os.path.exists(target_path):
        target_path = os.path.join(folder_path, f"{clean_name} ({counter}).pls")
        counter += 1

    shutil.copyfile(source_path, target_path)

    conn = sqlite3.connect(target_path)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cur.execute("UPDATE metadata SET value = ? WHERE key = 'name'", (new_name,))
    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (now,))

    if model_id_map and isinstance(model_id_map, dict):
        for old_id, new_id in model_id_map.items():
            cur.execute("UPDATE model_spec SET model_key = ? WHERE model_key = ?", (new_id, old_id))
            cur.execute("UPDATE results SET model_key = ? WHERE model_key = ?", (new_id, old_id))
            cur.execute("UPDATE snapshots SET source_model_id = ? WHERE source_model_id = ?", (new_id, old_id))

    conn.commit()
    conn.close()

    try:
        workspace_io.add_project_to_workspace(folder_path, os.path.basename(target_path), new_name)
    except Exception as e:
        print(f"Warning: could not add to workspace: {e}")

    return {
        "status": "duplicated",
        "project_path": target_path,
        "name": new_name
    }


def save_results(path: str, algorithm: str, results_dict: dict, model_id: str = None, spec: dict = None, diagram_layout: dict = None):
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY,
            algorithm TEXT,
            results_json TEXT,
            created_at TEXT,
            model_key TEXT,
            spec_json TEXT,
            diagram_layout_json TEXT
        )
    """)
    cur.execute("PRAGMA table_info(results)")
    cols = [r[1] for r in cur.fetchall()]
    if "model_key" not in cols:
        cur.execute("ALTER TABLE results ADD COLUMN model_key TEXT")
    if "spec_json" not in cols:
        cur.execute("ALTER TABLE results ADD COLUMN spec_json TEXT")
    if "diagram_layout_json" not in cols:
        cur.execute("ALTER TABLE results ADD COLUMN diagram_layout_json TEXT")

    now = datetime.now(timezone.utc).isoformat()
    results_str = json.dumps(results_dict)
    spec_str = json.dumps(spec) if spec is not None else None
    layout_str = json.dumps(diagram_layout) if diagram_layout is not None else None

    if model_id:
        cur.execute("DELETE FROM results WHERE algorithm = ? AND model_key = ?", (algorithm, model_id))
        cur.execute(
            """INSERT INTO results (algorithm, results_json, created_at, model_key, spec_json, diagram_layout_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (algorithm, results_str, now, model_id, spec_str, layout_str),
        )
    else:
        cur.execute("DELETE FROM results WHERE algorithm = ? AND (model_key IS NULL OR model_key = '' OR model_key = 'default')", (algorithm,))
        cur.execute(
            """INSERT INTO results (algorithm, results_json, created_at, model_key, spec_json, diagram_layout_json)
               VALUES (?, ?, ?, 'default', ?, ?)""",
            (algorithm, results_str, now, spec_str, layout_str),
        )

    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (now,))
    conn.commit()
    conn.close()
    return {"status": "saved", "created_at": now}


def load_results(path: str, algorithm: str = "pls", model_id: str = None):
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='results'")
    if cur.fetchone() is None:
        conn.close()
        return None

    cur.execute("PRAGMA table_info(results)")
    cols = [r[1] for r in cur.fetchall()]

    row = None
    if model_id and "model_key" in cols:
        cur.execute(
            "SELECT * FROM results WHERE algorithm = ? AND model_key = ? ORDER BY id DESC LIMIT 1",
            (algorithm, model_id),
        )
        row = cur.fetchone()
    elif not model_id:
        cur.execute(
            "SELECT * FROM results WHERE algorithm = ? AND (model_key IS NULL OR model_key = '' OR model_key = 'default') ORDER BY id DESC LIMIT 1",
            (algorithm,),
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                "SELECT * FROM results WHERE algorithm = ? ORDER BY id DESC LIMIT 1",
                (algorithm,),
            )
            row = cur.fetchone()

    conn.close()
    if not row:
        return None

    row_dict = dict(zip(cols, row))
    return {
        "algorithm": algorithm,
        "results": json.loads(row_dict["results_json"]) if row_dict.get("results_json") else None,
        "created_at": row_dict.get("created_at"),
        "spec": json.loads(row_dict["spec_json"]) if row_dict.get("spec_json") else None,
        "diagram_layout": json.loads(row_dict["diagram_layout_json"]) if row_dict.get("diagram_layout_json") else None,
        "model_key": row_dict.get("model_key"),
    }


def save_snapshot(path: str, name: str, algorithm: str, results: dict, spec: dict, diagram_layout: dict, description: str = "", source_model_id: str = None) -> dict:
    import uuid
    if not os.path.exists(path):
        raise FileNotFoundError(f"Project not found: {path}")

    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            algorithm TEXT NOT NULL,
            results_json TEXT NOT NULL,
            model_spec_json TEXT NOT NULL,
            diagram_layout_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            source_model_id TEXT
        )
    """)
    snapshot_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    cur.execute(
        """
        INSERT INTO snapshots (id, name, description, algorithm, results_json, model_spec_json, diagram_layout_json, created_at, source_model_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_id,
            name,
            description or "",
            algorithm,
            json.dumps(results),
            json.dumps(spec),
            json.dumps(diagram_layout),
            now,
            source_model_id,
        )
    )
    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (now,))
    conn.commit()
    conn.close()
    return {
        "id": snapshot_id,
        "name": name,
        "description": description,
        "algorithm": algorithm,
        "created_at": now,
        "source_model_id": source_model_id,
    }


def list_snapshots(path: str) -> list:
    if not os.path.exists(path):
        return []
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='snapshots'")
    if cur.fetchone() is None:
        conn.close()
        return []

    cur.execute("""
        SELECT id, name, description, algorithm, created_at, source_model_id
        FROM snapshots
        ORDER BY created_at DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "name": r[1],
            "description": r[2],
            "algorithm": r[3],
            "created_at": r[4],
            "source_model_id": r[5],
        }
        for r in rows
    ]


def get_snapshot(path: str, snapshot_id: str) -> dict:
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='snapshots'")
    if cur.fetchone() is None:
        conn.close()
        return None

    cur.execute("""
        SELECT id, name, description, algorithm, results_json, model_spec_json, diagram_layout_json, created_at, source_model_id
        FROM snapshots
        WHERE id = ?
    """, (snapshot_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2],
        "algorithm": row[3],
        "results": json.loads(row[4]) if row[4] else {},
        "spec": json.loads(row[5]) if row[5] else {},
        "diagram_layout": json.loads(row[6]) if row[6] else {},
        "created_at": row[7],
        "source_model_id": row[8],
    }


def delete_snapshot(path: str, snapshot_id: str) -> bool:
    if not os.path.exists(path):
        return False
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("DELETE FROM snapshots WHERE id = ?", (snapshot_id,))
    now = datetime.now(timezone.utc).isoformat()
    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (now,))
    conn.commit()
    conn.close()
    return True


def create_model_from_snapshot(path: str, snapshot_id: str, new_model_id: str, new_model_name: str) -> dict:
    snapshot = get_snapshot(path, snapshot_id)
    if not snapshot:
        raise ValueError("Snapshot not found")

    spec = json.loads(json.dumps(snapshot.get("spec", {})))
    diagram_layout = json.loads(json.dumps(snapshot.get("diagram_layout", {})))
    save_model_spec(path, spec, diagram_layout=diagram_layout, model_id=new_model_id)

    # Save snapshot results under the new model so it is completely independent
    if snapshot.get("results"):
        save_results(
            path,
            snapshot.get("algorithm") or "pls",
            json.loads(json.dumps(snapshot["results"])),
            model_id=new_model_id,
            spec=spec,
            diagram_layout=diagram_layout,
        )

    return {
        "status": "created",
        "model_id": new_model_id,
        "name": new_model_name,
        "results": snapshot.get("results"),
        "diagram_layout": diagram_layout,
        "spec": spec
    }