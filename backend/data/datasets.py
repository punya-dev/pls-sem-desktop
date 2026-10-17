"""
Multi-Dataset Storage and Management Module (Task P0-5 & Section 1/2).
Supports multiple datasets within a single SQLite .pls project file:
- Primary datasets (imported)
- Derived datasets (subsets, casewise deletion, group splits, imputed)
- Lineage tracking (parent_id, derivation_json)
- Column metadata (role, scale_min, scale_max, reverse_coded, label)
- Safe migration from legacy single-table 'raw_data'
"""

import hashlib
import json
import sqlite3
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np


def compute_dataframe_hash(df: pd.DataFrame) -> str:
    """Computes SHA-256 hash of a dataframe's values and column names."""
    hasher = hashlib.sha256()
    hasher.update(",".join(str(c) for c in df.columns).encode("utf-8"))
    # Hash first 100 and last 100 rows + shape for performance
    head_tail = pd.concat([df.head(100), df.tail(100)])
    hasher.update(pd.util.hash_pandas_object(head_tail).values.tobytes())
    hasher.update(str(df.shape).encode("utf-8"))
    return hasher.hexdigest()[:16]


def sanitize_table_name(dataset_id: str) -> str:
    """Sanitizes dataset_id into a safe SQLite table suffix."""
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", str(dataset_id))
    return f"data_{clean}"


def init_datasets_schema(conn: sqlite3.Connection):
    """Creates the multi-dataset tables in SQLite if they don't already exist."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS datasets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            parent_id TEXT,
            kind TEXT NOT NULL DEFAULT 'imported', -- 'imported' or 'derived'
            derivation_json TEXT,
            n_rows INTEGER NOT NULL,
            n_cols INTEGER NOT NULL,
            hash TEXT NOT NULL,
            settings_json TEXT,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS dataset_columns (
            dataset_id TEXT NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'indicator', -- 'indicator', 'group', 'weight', 'id', 'ignore'
            scale_min REAL,
            scale_max REAL,
            reverse_coded INTEGER NOT NULL DEFAULT 0,
            label TEXT,
            PRIMARY KEY (dataset_id, name)
        )
    """)
    conn.commit()


def migrate_legacy_raw_data(conn: sqlite3.Connection) -> Optional[str]:
    """
    Migrates legacy single 'raw_data' table to the multi-dataset schema.
    If 'raw_data' exists and datasets table is empty, imports it as dataset '1'.
    """
    init_datasets_schema(conn)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM datasets")
    count = cur.fetchone()[0]
    if count > 0:
        return None  # Already has multi-dataset records

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='raw_data'")
    if cur.fetchone() is None:
        return None  # No legacy raw_data

    cur.execute("PRAGMA table_info(raw_data)")
    cols = [r[1] for r in cur.fetchall()]
    if not cols:
        return None

    cur.execute("SELECT * FROM raw_data")
    rows = cur.fetchall()

    df = pd.DataFrame(rows, columns=cols)
    cur.execute("SELECT value FROM metadata WHERE key='dataset_name'")
    ds_name_row = cur.fetchone()
    ds_name = ds_name_row[0] if ds_name_row and ds_name_row[0] else "Imported data"

    dataset_id = "1"
    save_dataset(
        conn=conn,
        dataset_id=dataset_id,
        name=ds_name,
        df=df,
        kind="imported",
    )
    return dataset_id


def save_dataset(
    conn: sqlite3.Connection,
    dataset_id: str,
    name: str,
    df: pd.DataFrame,
    parent_id: Optional[str] = None,
    kind: str = "imported",
    derivation: Optional[Dict[str, Any]] = None,
    settings: Optional[Dict[str, Any]] = None,
    column_roles: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Saves a dataframe as a named dataset in the SQLite project."""
    init_datasets_schema(conn)
    cur = conn.cursor()

    table_name = sanitize_table_name(dataset_id)
    n_rows, n_cols = df.shape
    df_hash = compute_dataframe_hash(df)
    now = datetime.now(timezone.utc).isoformat()

    # Drop old data table if exists
    cur.execute(f"DROP TABLE IF EXISTS {table_name}")

    # Determine column types
    def sql_type(col_name: str) -> str:
        s = df[col_name]
        if pd.api.types.is_numeric_dtype(s):
            return "REAL"
        return "TEXT"

    col_defs = ", ".join(f'"{c}" {sql_type(c)}' for c in df.columns)
    cur.execute(f"CREATE TABLE {table_name} ({col_defs})")

    # Insert rows
    placeholders = ", ".join("?" for _ in df.columns)
    col_names_quoted = ", ".join(f'"{c}"' for c in df.columns)
    clean_records = df.astype(object).where(pd.notnull(df), None).values.tolist()
    cur.executemany(f"INSERT INTO {table_name} ({col_names_quoted}) VALUES ({placeholders})", clean_records)

    # Upsert dataset metadata
    cur.execute(
        """
        INSERT OR REPLACE INTO datasets (id, name, parent_id, kind, derivation_json, n_rows, n_cols, hash, settings_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dataset_id,
            name,
            parent_id,
            kind,
            json.dumps(derivation) if derivation else None,
            n_rows,
            n_cols,
            df_hash,
            json.dumps(settings) if settings else None,
            now,
        ),
    )

    # Populate dataset_columns
    cur.execute("DELETE FROM dataset_columns WHERE dataset_id = ?", (dataset_id,))
    for col in df.columns:
        role_info = (column_roles or {}).get(col, {})
        role = role_info.get("role", "indicator")
        scale_min = role_info.get("scale_min", None)
        scale_max = role_info.get("scale_max", None)
        reverse = 1 if role_info.get("reverse_coded") else 0
        label = role_info.get("label", None)

        # Auto-detect observed min/max if numeric
        if pd.api.types.is_numeric_dtype(df[col]):
            s_valid = df[col].dropna()
            if len(s_valid) > 0:
                if scale_min is None:
                    scale_min = float(s_valid.min())
                if scale_max is None:
                    scale_max = float(s_valid.max())

        cur.execute(
            """
            INSERT INTO dataset_columns (dataset_id, name, role, scale_min, scale_max, reverse_coded, label)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (dataset_id, col, role, scale_min, scale_max, reverse, label),
        )

    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (now,))
    conn.commit()

    return {
        "id": dataset_id,
        "name": name,
        "parent_id": parent_id,
        "kind": kind,
        "n_rows": n_rows,
        "n_cols": n_cols,
        "hash": df_hash,
        "created_at": now,
    }


def load_dataset(conn: sqlite3.Connection, dataset_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Loads a dataset by id, or loads the first available dataset if dataset_id is None."""
    init_datasets_schema(conn)
    cur = conn.cursor()

    if dataset_id is None:
        cur.execute("SELECT id FROM datasets ORDER BY created_at ASC LIMIT 1")
        row = cur.fetchone()
        if not row:
            # Try legacy migration
            migrated_id = migrate_legacy_raw_data(conn)
            if not migrated_id:
                return None
            dataset_id = migrated_id
        else:
            dataset_id = row[0]

    cur.execute("SELECT id, name, parent_id, kind, derivation_json, n_rows, n_cols, hash, settings_json, created_at FROM datasets WHERE id = ?", (dataset_id,))
    meta_row = cur.fetchone()
    if not meta_row:
        return None

    table_name = sanitize_table_name(dataset_id)
    cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
    if cur.fetchone() is None:
        return None

    cur.execute(f"PRAGMA table_info({table_name})")
    cols = [r[1] for r in cur.fetchall()]

    cur.execute(f"SELECT * FROM {table_name}")
    rows = cur.fetchall()

    # Load column roles
    cur.execute("SELECT name, role, scale_min, scale_max, reverse_coded, label FROM dataset_columns WHERE dataset_id = ?", (dataset_id,))
    col_rows = cur.fetchall()
    col_meta = {
        r[0]: {
            "role": r[1],
            "scale_min": r[2],
            "scale_max": r[3],
            "reverse_coded": bool(r[4]),
            "label": r[5],
        }
        for r in col_rows
    }

    return {
        "id": meta_row[0],
        "name": meta_row[1],
        "parent_id": meta_row[2],
        "kind": meta_row[3],
        "derivation": json.loads(meta_row[4]) if meta_row[4] else None,
        "n_rows": meta_row[5],
        "n_cols": meta_row[6],
        "hash": meta_row[7],
        "settings": json.loads(meta_row[8]) if meta_row[8] else None,
        "created_at": meta_row[9],
        "columns": cols,
        "rows": [list(r) for r in rows],
        "df": pd.DataFrame(rows, columns=cols),
        "column_metadata": col_meta,
    }


def list_datasets(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Returns a list of all datasets in the project."""
    init_datasets_schema(conn)
    migrate_legacy_raw_data(conn)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, parent_id, kind, n_rows, n_cols, hash, created_at
        FROM datasets
        ORDER BY created_at ASC
    """)
    rows = cur.fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "parent_id": r[2],
            "kind": r[3],
            "n_rows": r[4],
            "n_cols": r[5],
            "hash": r[6],
            "created_at": r[7],
        }
        for r in rows
    ]


def delete_dataset(conn: sqlite3.Connection, dataset_id: str) -> bool:
    """Deletes a dataset and drops its table."""
    init_datasets_schema(conn)
    cur = conn.cursor()
    table_name = sanitize_table_name(dataset_id)
    cur.execute(f"DROP TABLE IF EXISTS {table_name}")
    cur.execute("DELETE FROM datasets WHERE id = ?", (dataset_id,))
    cur.execute("DELETE FROM dataset_columns WHERE dataset_id = ?", (dataset_id,))
    now = datetime.now(timezone.utc).isoformat()
    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (now,))
    conn.commit()
    return True


def update_column_metadata(
    conn: sqlite3.Connection,
    dataset_id: str,
    column: str,
    role: Optional[str] = None,
    scale_min: Optional[float] = None,
    scale_max: Optional[float] = None,
    reverse_coded: Optional[bool] = None,
    label: Optional[str] = None,
) -> Dict[str, Any]:
    """Updates metadata (role, scale ranges, reverse coding, label) for a column (DAT-12, SCR-09)."""
    init_datasets_schema(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT role, scale_min, scale_max, reverse_coded, label FROM dataset_columns WHERE dataset_id = ? AND name = ?",
        (dataset_id, column),
    )
    row = cur.fetchone()
    if not row:
        cur.execute(
            """
            INSERT INTO dataset_columns (dataset_id, name, role, scale_min, scale_max, reverse_coded, label)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dataset_id,
                column,
                role or "indicator",
                scale_min,
                scale_max,
                1 if reverse_coded else 0,
                label,
            ),
        )
    else:
        new_role = role if role is not None else row[0]
        new_min = scale_min if scale_min is not None else row[1]
        new_max = scale_max if scale_max is not None else row[2]
        new_rev = (1 if reverse_coded else 0) if reverse_coded is not None else row[3]
        new_label = label if label is not None else row[4]
        cur.execute(
            """
            UPDATE dataset_columns
            SET role = ?, scale_min = ?, scale_max = ?, reverse_coded = ?, label = ?
            WHERE dataset_id = ? AND name = ?
            """,
            (new_role, new_min, new_max, new_rev, new_label, dataset_id, column),
        )

    now = datetime.now(timezone.utc).isoformat()
    cur.execute("UPDATE metadata SET value = ? WHERE key = 'modified_at'", (now,))
    conn.commit()

    return {
        "dataset_id": dataset_id,
        "name": column,
        "role": role if role is not None else (row[0] if row else "indicator"),
        "scale_min": scale_min if scale_min is not None else (row[1] if row else None),
        "scale_max": scale_max if scale_max is not None else (row[2] if row else None),
        "reverse_coded": reverse_coded if reverse_coded is not None else (bool(row[3]) if row else False),
        "label": label if label is not None else (row[4] if row else None),
    }

