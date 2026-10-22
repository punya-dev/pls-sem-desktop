import sqlite3
import json
import os
import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import pandas as pd
import numpy as np

import settings_io
from data.datasets import (
    init_datasets_schema,
    migrate_legacy_raw_data,
    save_dataset as ds_save,
    load_dataset as ds_load,
    list_datasets as ds_list,
    delete_dataset as ds_delete,
    compute_dataframe_hash,
)

SCHEMA_VERSION = "2.0"


def compute_spec_hash(spec: Optional[Dict[str, Any]]) -> str:
    if not spec:
        return "empty"
    serialized = json.dumps(spec, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def init_project_schema(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS model_spec (
            id INTEGER PRIMARY KEY,
            spec_json TEXT,
            diagram_layout_json TEXT,
            updated_at TEXT,
            model_key TEXT UNIQUE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY,
            algorithm TEXT,
            analysis_type TEXT,
            results_json TEXT,
            created_at TEXT,
            model_key TEXT,
            spec_json TEXT,
            diagram_layout_json TEXT,
            dataset_id TEXT,
            dataset_hash TEXT,
            spec_hash TEXT,
            params_json TEXT
        )
    """)
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
    init_datasets_schema(conn)

    # Check and migrate columns
    cur.execute("PRAGMA table_info(results)")
    cols = [r[1] for r in cur.fetchall()]
    for col_def in [
        ("analysis_type", "TEXT"),
        ("model_key", "TEXT"),
        ("spec_json", "TEXT"),
        ("diagram_layout_json", "TEXT"),
        ("dataset_id", "TEXT"),
        ("dataset_hash", "TEXT"),
        ("spec_hash", "TEXT"),
        ("params_json", "TEXT"),
    ]:
        if col_def[0] not in cols:
            cur.execute(f"ALTER TABLE results ADD COLUMN {col_def[0]} {col_def[1]}")

    conn.commit()


def migrate_project(path: str):
    """Executes schema migrations on project opening."""
    if not os.path.exists(path):
        return
    conn = sqlite3.connect(path)
    init_project_schema(conn)
    migrate_legacy_raw_data(conn)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
    conn.commit()
    conn.close()


def create_project(path: str, project_name: str):
    if os.path.exists(path):
        raise FileExistsError("Project file already exists")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    init_project_schema(conn)
    cur = conn.cursor()

    now = datetime.now(timezone.utc).isoformat()
    cur.executemany(
        "INSERT INTO metadata (key, value) VALUES (?, ?)",
        [
            ("name", project_name),
            ("created_at", now),
            ("modified_at", now),
            ("schema_version", SCHEMA_VERSION),
        ],
    )

    # PRJ-01: Auto-create initial empty model named after the project
    initial_spec = {
        "constructs": [],
        "indicators": [],
        "paths": [],
    }
    cur.execute(
        """
        INSERT INTO model_spec (spec_json, diagram_layout_json, updated_at, model_key)
        VALUES (?, ?, ?, ?)
        """,
        (json.dumps(initial_spec), None, now, "default"),
    )

    conn.commit()
    conn.close()


def save_data(path: str, rows: list, columns: list, dtypes: list, dataset_name: str = None, dataset_id: str = "1"):
    migrate_project(path)
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    df = pd.DataFrame(rows, columns=columns)
    name = dataset_name or "Imported data"

    # Also keep legacy raw_data for complete backward compatibility
    cur.execute("DROP TABLE IF EXISTS raw_data")
    def sql_type(dtype: str) -> str:
        if "int" in dtype or "float" in dtype:
            return "REAL"
        return "TEXT"

    def escape_col(c: Any) -> str:
        return '"' + str(c).replace('"', '""') + '"'

    col_defs = ", ".join(f"{escape_col(c)} {sql_type(t)}" for c, t in zip(columns, dtypes))
    cur.execute(f"CREATE TABLE raw_data ({col_defs})")
    placeholders = ", ".join("?" for _ in columns)
    col_names = ", ".join(escape_col(c) for c in columns)
    cur.executemany(f"INSERT INTO raw_data ({col_names}) VALUES ({placeholders})", rows)

    # Save to multi-dataset table
    ds_save(conn, dataset_id=dataset_id, name=name, df=df)

    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (datetime.now(timezone.utc).isoformat(),))
    if dataset_name:
        cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('dataset_name', ?)", (dataset_name,))
    conn.commit()
    conn.close()


def load_data(path: str, dataset_id: Optional[str] = None):
    if not os.path.exists(path):
        return None
    migrate_project(path)
    conn = sqlite3.connect(path)
    ds_data = ds_load(conn, dataset_id=dataset_id)
    conn.close()
    if ds_data is not None:
        return {
            "id": ds_data.get("id"),
            "dataset_name": ds_data.get("name"),
            "columns": ds_data.get("columns"),
            "rows": ds_data.get("rows"),
            "hash": ds_data.get("hash"),
            "column_metadata": ds_data.get("column_metadata"),
        }
    return None


def list_project_datasets(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    migrate_project(path)
    conn = sqlite3.connect(path)
    datasets = ds_list(conn)
    conn.close()
    return datasets


def delete_project_dataset(path: str, dataset_id: str) -> bool:
    if not os.path.exists(path):
        return False
    migrate_project(path)
    conn = sqlite3.connect(path)
    ok = ds_delete(conn, dataset_id)
    conn.close()
    return ok


def delete_data(path: str):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS raw_data")
    cur.execute("DELETE FROM metadata WHERE key='dataset_name'")
    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (datetime.now(timezone.utc).isoformat(),))
    conn.commit()
    conn.close()


def load_metadata(path: str):
    migrate_project(path)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT key, value FROM metadata")
    rows = cur.fetchall()
    conn.close()
    return dict(rows)


def add_recent_project(path: str):
    settings_io.add_recent("recent_projects", path)


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
    migrate_project(path)
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    now = datetime.now(timezone.utc).isoformat()
    spec_str = json.dumps(spec)
    layout_str = json.dumps(diagram_layout) if diagram_layout is not None else None
    key = model_id or "default"

    cur.execute("SELECT id FROM model_spec WHERE model_key = ?", (key,))
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE model_spec SET spec_json = ?, diagram_layout_json = ?, updated_at = ? WHERE id = ?",
            (spec_str, layout_str, now, row[0]),
        )
    else:
        cur.execute(
            "INSERT INTO model_spec (spec_json, diagram_layout_json, updated_at, model_key) VALUES (?, ?, ?, ?)",
            (spec_str, layout_str, now, key),
        )

    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (now,))
    conn.commit()
    conn.close()


def load_model_spec(path: str, model_id: str = None):
    if not os.path.exists(path):
        return None
    migrate_project(path)
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(model_spec)")
    cols = [r[1] for r in cur.fetchall()]

    row = None
    if model_id and "model_key" in cols:
        cur.execute("SELECT * FROM model_spec WHERE model_key = ?", (model_id,))
        row = cur.fetchone()

    if not row and not model_id:
        cur.execute("SELECT * FROM model_spec WHERE model_key = 'default'")
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
    init_project_schema(conn)
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

    try:
        add_recent_project(target_path)
    except Exception as e:
        print(f"Warning: could not add to recent projects: {e}")

    return {
        "status": "duplicated",
        "project_path": target_path,
        "name": new_name,
    }


def move_project(source_workspace_path: str, target_workspace_path: str, source_path: str, project_name: str = None):
    import shutil
    import workspace_io

    source_workspace_path = os.path.abspath(os.path.expanduser(source_workspace_path))
    target_workspace_path = os.path.abspath(os.path.expanduser(target_workspace_path))
    source_path = os.path.abspath(os.path.expanduser(source_path))

    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source study file not found: {source_path}")
    if not os.path.exists(target_workspace_path):
        raise FileNotFoundError(f"Target workspace folder not found: {target_workspace_path}")
    if source_workspace_path == target_workspace_path:
        raise ValueError("Source and target workspaces are the same")

    source_filename = os.path.basename(source_path)

    if not project_name:
        try:
            conn = sqlite3.connect(source_path)
            cur = conn.cursor()
            cur.execute("SELECT value FROM metadata WHERE key = 'name'")
            row = cur.fetchone()
            if row and row[0]:
                project_name = row[0]
            conn.close()
        except Exception:
            pass

    if not project_name:
        project_name = os.path.splitext(source_filename)[0]

    clean_name = "".join(c for c in project_name if c.isalnum() or c in (" ", "-", "_")).strip()
    if not clean_name:
        clean_name = "Untitled Study"

    base_filename = f"{clean_name}.pls"
    target_path = os.path.join(target_workspace_path, base_filename)
    counter = 1
    while os.path.exists(target_path):
        target_path = os.path.join(target_workspace_path, f"{clean_name} ({counter}).pls")
        counter += 1

    shutil.move(source_path, target_path)

    # Remove from source workspace.json
    try:
        workspace_io.remove_project_from_workspace(source_workspace_path, source_filename)
    except Exception as e:
        print(f"Warning: could not remove from source workspace: {e}")

    # Add to target workspace.json
    target_filename = os.path.basename(target_path)
    try:
        workspace_io.add_project_to_workspace(target_workspace_path, target_filename, project_name)
    except Exception as e:
        print(f"Warning: could not add to target workspace: {e}")

    # Update recent projects in settings
    try:
        settings_io.remove_recent("recent_projects", source_path)
        add_recent_project(target_path)
    except Exception as e:
        print(f"Warning: could not update recent projects: {e}")

    return {
        "status": "moved",
        "project_path": target_path,
        "name": project_name,
        "filename": target_filename,
    }


def save_results(
    path: str,
    algorithm: str,
    results_dict: dict,
    model_id: str = None,
    spec: dict = None,
    diagram_layout: dict = None,
    analysis_type: str = "pls",
    dataset_id: str = None,
    dataset_hash: str = None,
    params: dict = None,
):
    migrate_project(path)
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    def _json_default(obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    now = datetime.now(timezone.utc).isoformat()
    results_str = json.dumps(results_dict, default=_json_default)
    spec_str = json.dumps(spec, default=_json_default) if spec is not None else None
    layout_str = json.dumps(diagram_layout, default=_json_default) if diagram_layout is not None else None
    params_str = json.dumps(params, default=_json_default) if params is not None else None
    key = model_id or "default"
    s_hash = compute_spec_hash(spec)

    cur.execute("DELETE FROM results WHERE algorithm = ? AND model_key = ? AND (analysis_type = ? OR analysis_type IS NULL)", (algorithm, key, analysis_type))
    cur.execute(
        """
        INSERT INTO results (
            algorithm, analysis_type, results_json, created_at, model_key,
            spec_json, diagram_layout_json, dataset_id, dataset_hash, spec_hash, params_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            algorithm,
            analysis_type,
            results_str,
            now,
            key,
            spec_str,
            layout_str,
            dataset_id,
            dataset_hash,
            s_hash,
            params_str,
        ),
    )

    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (now,))
    conn.commit()
    conn.close()
    return {"status": "saved", "created_at": now}


def load_results(path: str, algorithm: str = "pls", model_id: str = None, analysis_type: str = None):
    if not os.path.exists(path):
        return None
    migrate_project(path)
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(results)")
    cols = [r[1] for r in cur.fetchall()]

    query = "SELECT * FROM results WHERE algorithm = ?"
    params_query = [algorithm]

    if model_id:
        query += " AND model_key = ?"
        params_query.append(model_id)
    else:
        query += " AND (model_key IS NULL OR model_key = '' OR model_key = 'default')"

    if analysis_type and "analysis_type" in cols:
        query += " AND analysis_type = ?"
        params_query.append(analysis_type)

    query += " ORDER BY id DESC LIMIT 1"
    cur.execute(query, tuple(params_query))
    row = cur.fetchone()

    # Fallback to any latest result for this model
    if not row and not analysis_type:
        cur.execute("SELECT * FROM results WHERE algorithm = ? ORDER BY id DESC LIMIT 1", (algorithm,))
        row = cur.fetchone()

    conn.close()
    if not row:
        return None

    row_dict = dict(zip(cols, row))
    spec_data = json.loads(row_dict["spec_json"]) if row_dict.get("spec_json") else None

    # Stale detection (P0-4)
    # Check if spec hash has changed
    current_spec_obj = load_model_spec(path, model_id)
    current_spec_hash = compute_spec_hash(current_spec_obj.get("spec")) if current_spec_obj else None
    saved_spec_hash = row_dict.get("spec_hash")
    stale = bool(saved_spec_hash and current_spec_hash and saved_spec_hash != current_spec_hash)

    return {
        "algorithm": algorithm,
        "analysis_type": row_dict.get("analysis_type", "pls"),
        "results": json.loads(row_dict["results_json"]) if row_dict.get("results_json") else None,
        "created_at": row_dict.get("created_at"),
        "spec": spec_data,
        "diagram_layout": json.loads(row_dict["diagram_layout_json"]) if row_dict.get("diagram_layout_json") else None,
        "model_key": row_dict.get("model_key"),
        "dataset_id": row_dict.get("dataset_id"),
        "dataset_hash": row_dict.get("dataset_hash"),
        "stale": stale,
        "params": json.loads(row_dict["params_json"]) if row_dict.get("params_json") else None,
    }


def save_snapshot(path: str, name: str, algorithm: str, results: dict, spec: dict, diagram_layout: dict, description: str = "", source_model_id: str = None) -> dict:
    import uuid
    if not os.path.exists(path):
        raise FileNotFoundError(f"Project not found: {path}")

    migrate_project(path)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
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
        ),
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
    migrate_project(path)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
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
    migrate_project(path)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
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
    migrate_project(path)
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
        "spec": spec,
    }


def rename_model(path: str, model_id: str, new_name: str) -> Dict[str, Any]:
    """Renames a model within the project file (PRJ-02)."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Project not found: {path}")
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("Model name cannot be empty")

    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT spec_json FROM model_spec WHERE model_key = ?", (model_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Model '{model_id}' not found")

    spec = json.loads(row[0]) if row[0] else {}
    spec["name"] = new_name
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        "UPDATE model_spec SET spec_json = ?, updated_at = ? WHERE model_key = ?",
        (json.dumps(spec), now, model_id),
    )
    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (now,))
    conn.commit()
    conn.close()
    return {"status": "renamed", "model_id": model_id, "new_name": new_name}


def rename_dataset(path: str, dataset_id: str, new_name: str) -> Dict[str, Any]:
    """Renames a dataset within the project (PRJ-02)."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Project not found: {path}")
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("Dataset name cannot be empty")

    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT id FROM datasets WHERE id = ?", (dataset_id,))
    if not cur.fetchone():
        conn.close()
        raise ValueError(f"Dataset '{dataset_id}' not found")

    cur.execute("UPDATE datasets SET name = ? WHERE id = ?", (new_name, dataset_id))
    now = datetime.now(timezone.utc).isoformat()
    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (now,))
    conn.commit()
    conn.close()
    return {"status": "renamed", "dataset_id": dataset_id, "new_name": new_name}


def rename_project(path: str, new_name: str, rename_file: bool = False) -> Dict[str, Any]:
    """Renames the project and optionally renames the .pls file (PRJ-02)."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Project not found: {path}")
    new_name = new_name.strip()
    if not new_name:
        raise ValueError("Project name cannot be empty")

    conn = sqlite3.connect(path)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('project_name', ?)", (new_name,))
    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (now,))
    conn.commit()
    conn.close()

    new_path = path
    if rename_file:
        folder = os.path.dirname(path)
        new_filename = f"{new_name}.pls" if not new_name.endswith(".pls") else new_name
        new_path = os.path.join(folder, new_filename)
        if new_path != path:
            if os.path.exists(new_path):
                raise FileExistsError(f"Target file already exists: {new_path}")
            os.rename(path, new_path)
            settings_io.remove_recent("recent_projects", path)
            settings_io.add_recent("recent_projects", new_path)

    return {"status": "renamed", "new_name": new_name, "path": new_path}


def get_project_tree(path: str) -> Dict[str, Any]:
    """
    Returns the complete explorer tree structure (PRJ-02):
    - Datasets with parent/child derived lineage
    - Models with bound dataset and stale results indicator
    - Snapshots
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Project not found: {path}")
    migrate_project(path)
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    # 1. Fetch datasets
    cur.execute("SELECT id, name, parent_id, kind, n_rows, n_cols, hash, created_at FROM datasets ORDER BY created_at ASC")
    ds_rows = cur.fetchall()
    datasets_by_id = {}
    for r in ds_rows:
        datasets_by_id[r[0]] = {
            "id": r[0],
            "name": r[1],
            "parent_id": r[2],
            "kind": r[3],
            "n_rows": r[4],
            "n_cols": r[5],
            "hash": r[6],
            "created_at": r[7],
            "children": [],
        }

    root_datasets = []
    for d_id, d_info in datasets_by_id.items():
        p_id = d_info["parent_id"]
        if p_id and p_id in datasets_by_id:
            datasets_by_id[p_id]["children"].append(d_info)
        else:
            root_datasets.append(d_info)

    # 2. Fetch models
    cur.execute("SELECT id, model_key, spec_json, updated_at FROM model_spec ORDER BY id ASC")
    model_rows = cur.fetchall()
    models = []
    for r in model_rows:
        m_key = r[1]
        spec_data = json.loads(r[2]) if r[2] else {}
        m_name = spec_data.get("name") or m_key or f"Model {r[0]}"
        m_dataset_id = spec_data.get("dataset_id")

        # Check results and staleness
        cur.execute("SELECT spec_hash FROM results WHERE model_key = ? ORDER BY id DESC LIMIT 1", (m_key,))
        res_row = cur.fetchone()
        has_results = res_row is not None
        stale = False
        if has_results:
            saved_spec_hash = res_row[0]
            curr_spec_hash = compute_spec_hash(spec_data)
            stale = bool(saved_spec_hash and curr_spec_hash and saved_spec_hash != curr_spec_hash)

        models.append({
            "id": m_key,
            "name": m_name,
            "dataset_id": m_dataset_id,
            "has_results": has_results,
            "stale": stale,
            "updated_at": r[3],
        })

    # 3. Fetch snapshots
    snapshots = list_snapshots(path)

    conn.close()
    return {
        "datasets": root_datasets,
        "models": models,
        "snapshots": snapshots,
    }


def bind_dataset_to_model(path: str, model_id: str, dataset_id: str) -> Dict[str, Any]:
    """
    Binds a model to a specific dataset (PRJ-05, PRJ-08).
    Verifies that all indicators in the model spec exist in the target dataset.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Project not found: {path}")
    migrate_project(path)
    conn = sqlite3.connect(path)

    # Verify dataset exists
    ds = ds_load(conn, dataset_id)
    if not ds:
        conn.close()
        raise ValueError(f"Dataset '{dataset_id}' not found")

    ds_cols = set(ds["columns"])

    # Load model spec
    model_data = load_model_spec(path, model_id)
    if not model_data or not model_data.get("spec"):
        conn.close()
        raise ValueError(f"Model '{model_id}' not found")

    spec = model_data["spec"]
    indicators = spec.get("indicators", [])
    missing_cols = []
    for ind in indicators:
        name = ind.get("name") if isinstance(ind, dict) else getattr(ind, "name", None)
        if name and name not in ds_cols:
            missing_cols.append(name)

    spec["dataset_id"] = dataset_id
    save_model_spec(path, spec, diagram_layout=model_data.get("diagram_layout"), model_id=model_id)
    conn.close()

    issues = []
    if missing_cols:
        issues.append({
            "code": "INDICATOR_NOT_IN_DATASET",
            "severity": "error",
            "message": f"Indicators {missing_cols} do not exist in dataset '{ds['name']}'.",
            "details": {"missing_indicators": missing_cols},
        })

    return {
        "status": "bound",
        "model_id": model_id,
        "dataset_id": dataset_id,
        "dataset_name": ds["name"],
        "ok": len(missing_cols) == 0,
        "issues": issues,
    }


def export_project_zip(project_path: str, out_zip_path: str, include_results: bool = True) -> str:
    """
    Exports project and all its datasets as a standalone .zip archive (PRJ-06).
    Archive contains:
    - manifest.json
    - <project_name>.pls
    - datasets/<name>.csv
    """
    import zipfile
    if not os.path.exists(project_path):
        raise FileNotFoundError(f"Project not found: {project_path}")

    migrate_project(project_path)
    conn = sqlite3.connect(project_path)
    meta = load_metadata(project_path)
    datasets = ds_list(conn)

    manifest = {
        "app_version": "1.0.0",
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_name": meta.get("project_name", os.path.basename(project_path)),
        "datasets_count": len(datasets),
    }

    with zipfile.ZipFile(out_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        pls_filename = os.path.basename(project_path)
        zf.write(project_path, pls_filename)

        # Export each dataset as CSV
        for d in datasets:
            ds_data = ds_load(conn, d["id"])
            if ds_data and "df" in ds_data:
                csv_bytes = ds_data["df"].to_csv(index=False).encode("utf-8")
                clean_name = "".join(c for c in d["name"] if c.isalnum() or c in (" ", "_", "-")).rstrip()
                zf.writestr(f"datasets/{clean_name}_{d['id']}.csv", csv_bytes)

    conn.close()
    return out_zip_path


def import_project_zip(zip_path: str, workspace_dir: str, on_conflict: str = "rename") -> str:
    """
    Safely imports a project from a .zip archive into workspace_dir (PRJ-06).
    Guards strictly against Zip-Slip attacks (path traversal).
    """
    import zipfile
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"Zip file not found: {zip_path}")
    if not os.path.exists(workspace_dir):
        os.makedirs(workspace_dir, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as zf:
        # Zip slip security guard
        for member in zf.namelist():
            if member.startswith("/") or member.startswith("\\") or ".." in member:
                raise ValueError(f"Unsafe zip archive entry: {member}")

        manifest_data = {}
        if "manifest.json" in zf.namelist():
            manifest_data = json.loads(zf.read("manifest.json").decode("utf-8"))

        # Find .pls file
        pls_entries = [m for m in zf.namelist() if m.endswith(".pls") and not m.startswith("__MACOSX")]
        if not pls_entries:
            raise ValueError("No .pls project file found inside zip archive")

        pls_entry = pls_entries[0]
        base_name = os.path.basename(pls_entry)

        target_path = os.path.join(workspace_dir, base_name)
        if os.path.exists(target_path):
            if on_conflict == "cancel":
                raise FileExistsError(f"Project '{base_name}' already exists in workspace")
            elif on_conflict == "rename":
                root, ext = os.path.splitext(base_name)
                i = 1
                while os.path.exists(target_path):
                    target_path = os.path.join(workspace_dir, f"{root}_{i}{ext}")
                    i += 1
            # If "overwrite", target_path stays as is

        with open(target_path, "wb") as f_out:
            f_out.write(zf.read(pls_entry))

    migrate_project(target_path)
    settings_io.add_recent("recent_projects", target_path)
    return target_path