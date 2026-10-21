"""
Data Groups and Segmentation Management Module (A18-DAT-01 to A18-DAT-05).
Source of truth: Hair et al. (2018) Chapters 4 & 5.

Implements:
1. Persistent group definitions & auto-generation from categorical variables.
2. Group sample size validation (Ng >= 10 mandatory, 10-times rule & Cohen power warnings).
3. Group summary statistics: sample size, %, missing counts.
4. Appending cluster/group assignments to dataset SQLite table.
5. Seeding the Corporate Reputation benchmark case study project (344/336 data + models).
"""

from typing import List, Dict, Any, Optional, Tuple, Union
import os
import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from data.datasets import (
    load_dataset,
    save_dataset,
    init_datasets_schema,
    update_column_metadata,
)
from data.derived import create_derived_dataset


def generate_categorical_groups(
    df: pd.DataFrame,
    column: str,
    min_size: int = 10,
    max_paths_predictors: int = 2,
    alpha: float = 0.05,
) -> Dict[str, Any]:
    """
    Auto-generates groups from categorical column with validation checks (A18-DAT-01, A18-DAT-02, A18-DAT-03, A18-DAT-05).
    """
    if column not in df.columns:
        raise ValueError(f"Column '{column}' not found in dataset.")

    s = df[column]
    total_n = len(s)
    missing_n = int(s.isna().sum()) + int((s == -99).sum() if pd.api.types.is_numeric_dtype(s) else 0)

    # Valid values
    valid_s = s.dropna()
    if pd.api.types.is_numeric_dtype(valid_s):
        valid_s = valid_s[valid_s != -99]

    val_counts = valid_s.value_counts(sort=False).to_dict()
    unique_vals = sorted(list(val_counts.keys()))

    ten_times_threshold = max_paths_predictors * 10
    # Cohen (1992) recommendation for 80% power at 5% alpha, R2=0.25 is approx 54 for 2 predictors
    cohen_power_threshold = 54

    groups_list = []
    has_critical_error = False
    critical_errors = []
    power_warnings = []

    for v in unique_vals:
        count = int(val_counts[v])
        pct = round((count / total_n) * 100.0, 2)
        valid_pct = round((count / len(valid_s)) * 100.0, 2) if len(valid_s) > 0 else 0.0

        is_below_min = count < min_size
        is_below_ten_times = count < ten_times_threshold
        is_below_cohen = count < cohen_power_threshold

        if is_below_min:
            has_critical_error = True
            critical_errors.append(
                f"Group '{v}' has only {count} observations (minimum required is {min_size})."
            )
        elif is_below_ten_times:
            power_warnings.append(
                f"Group '{v}' has {count} cases, below 10-times rule threshold ({ten_times_threshold})."
            )
        elif is_below_cohen:
            power_warnings.append(
                f"Group '{v}' has {count} cases, below Cohen (1992) 80% statistical power threshold ({cohen_power_threshold})."
            )

        groups_list.append({
            "name": f"{column}={v}",
            "value": v if not (isinstance(v, np.generic)) else v.item(),
            "count": count,
            "percentage": pct,
            "valid_percentage": valid_pct,
            "filter_expression": f"df['{column}'] == {repr(v)}",
            "is_valid_size": not is_below_min,
            "power_status": "adequate" if not is_below_cohen else ("caution" if not is_below_ten_times else "low_power"),
        })

    return {
        "column": column,
        "total_observations": total_n,
        "total_samples": total_n,
        "valid_observations": len(valid_s),
        "missing_count": missing_n,
        "n_groups": len(unique_vals),
        "groups": groups_list,
        "has_critical_error": has_critical_error,
        "critical_errors": critical_errors,
        "power_warnings": power_warnings,
        "ten_times_threshold": ten_times_threshold,
        "cohen_threshold": cohen_power_threshold,
    }


def append_column_to_dataset(
    conn: sqlite3.Connection,
    dataset_id: str,
    column_name: str,
    values: List[Any],
    role: str = "group",
    label: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Appends or updates a column in a SQLite dataset table (A18-DAT-04).
    Used for appending cluster solutions (FIMIX, POS) or custom grouping columns.
    """
    ds = load_dataset(conn, dataset_id)
    if not ds:
        raise ValueError(f"Dataset with ID '{dataset_id}' not found.")

    df = ds["df"].copy()
    if len(values) != len(df):
        raise ValueError(
            f"Length mismatch: provided {len(values)} values, but dataset has {len(df)} rows."
        )

    df[column_name] = values
    col_roles = ds.get("column_metadata", {})
    col_roles[column_name] = {
        "role": role,
        "label": label or f"Segment / Group: {column_name}",
        "reverse_coded": False,
    }

    # Save back updated dataset
    updated_meta = save_dataset(
        conn=conn,
        dataset_id=dataset_id,
        name=ds["name"],
        df=df,
        parent_id=ds.get("parent_id"),
        kind=ds.get("kind", "imported"),
        derivation=ds.get("derivation"),
        settings=ds.get("settings"),
        column_roles=col_roles,
    )

    return {
        "status": "success",
        "dataset_id": dataset_id,
        "appended_column": column_name,
        "n_rows": len(df),
        "n_cols": len(df.columns),
        "columns": list(df.columns),
    }


def seed_corporate_reputation_project(
    project_path: str,
    data_csv_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Seeds a project with the authentic Corporate Reputation benchmark case study
    from Hair et al. (2018) Advanced Issues in PLS-SEM (A18-CON-01, A18-CON-02).
    Includes:
    - Primary dataset (344 cases, 41 columns)
    - Casewise deletion derived dataset (336 cases, missing codes -99 excluded)
    - Simple Model (COMP, LIKE -> CUSA -> CUSL)
    - Extended Model (QUAL, PERF, CSOR, ATTR -> COMP, LIKE -> CUSA -> CUSL)
    - Higher-Order Construct Model (Corporate Reputation HOC with LOCs COMP & LIKE)
    """
    if data_csv_path is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_csv_path = os.path.join(base_dir, "tests", "data", "Corporate reputation data.csv")

    if not os.path.exists(data_csv_path):
        raise FileNotFoundError(f"Corporate reputation CSV not found at '{data_csv_path}'.")

    # Read CSV
    df_raw = pd.read_csv(data_csv_path, sep=";")

    db_file = project_path
    if os.path.isdir(project_path) or not os.path.splitext(project_path)[1]:
        db_file = os.path.join(project_path, "corporate_reputation.sqlite")

    os.makedirs(os.path.dirname(os.path.abspath(db_file)), exist_ok=True)
    conn = sqlite3.connect(db_file)

    try:
        cur = conn.cursor()
        # Initialize project tables if new
        cur.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS models (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                spec_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                modified_at TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id TEXT PRIMARY KEY,
                algorithm TEXT NOT NULL,
                results_json TEXT NOT NULL,
                model_id TEXT,
                dataset_id TEXT,
                analysis_type TEXT,
                params_json TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

        # Metadata
        now = datetime.now(timezone.utc).isoformat()
        cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('name', 'Corporate Reputation Case Study')")
        cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('description', 'Benchmark study from Hair, Sarstedt, Ringle & Gudergan (2018) Advanced Issues in PLS-SEM')")
        cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('created_at', ?)", (now,))
        cur.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('modified_at', ?)", (now,))
        conn.commit()

        # Column roles configuration
        col_roles = {}
        for c in df_raw.columns:
            if c in ["serviceprovider", "servicetype"]:
                col_roles[c] = {"role": "group", "label": f"Grouping: {c}"}
            else:
                col_roles[c] = {"role": "indicator", "scale_min": 1.0, "scale_max": 7.0}

        # 1. Save Primary Dataset (344 rows)
        ds1 = save_dataset(
            conn=conn,
            dataset_id="corp_rep_344",
            name="Corporate Reputation (Full N=344)",
            df=df_raw,
            parent_id=None,
            kind="imported",
            settings={"missing_treatment": "casewise", "missing_codes": [-99, "-99"]},
            column_roles=col_roles,
        )

        # 2. Save Casewise Clean Dataset (336 rows)
        # Exclude rows containing -99
        clean_mask = ~(df_raw == -99).any(axis=1)
        df_clean = df_raw[clean_mask].copy().reset_index(drop=True)

        ds2 = save_dataset(
            conn=conn,
            dataset_id="corp_rep_336",
            name="Corporate Reputation (Casewise Deletion N=336)",
            df=df_clean,
            parent_id="corp_rep_344",
            kind="derived",
            derivation={"operation": "casewise_deletion", "removed_rows": int((~clean_mask).sum())},
            settings={"missing_treatment": "casewise"},
            column_roles=col_roles,
        )

        # 3. Model 1: Simple Model
        simple_spec = {
            "constructs": [
                {"id": "COMP", "name": "Competence", "type": "reflective", "indicators": ["comp_1", "comp_2", "comp_3"]},
                {"id": "LIKE", "name": "Likeability", "type": "reflective", "indicators": ["like_1", "like_2", "like_3"]},
                {"id": "CUSA", "name": "Customer Satisfaction", "type": "reflective", "indicators": ["cusa"]},
                {"id": "CUSL", "name": "Customer Loyalty", "type": "reflective", "indicators": ["cusl_1", "cusl_2", "cusl_3"]},
            ],
            "paths": [
                {"from": "COMP", "to": "CUSA"},
                {"from": "LIKE", "to": "CUSA"},
                {"from": "COMP", "to": "CUSL"},
                {"from": "LIKE", "to": "CUSL"},
                {"from": "CUSA", "to": "CUSL"},
            ],
        }

        # Model 2: Extended Formative Model
        extended_spec = {
            "constructs": [
                {"id": "QUAL", "name": "Quality", "type": "formative", "indicators": ["qual_1", "qual_2", "qual_3", "qual_4", "qual_5", "qual_6", "qual_7", "qual_8"]},
                {"id": "PERF", "name": "Performance", "type": "formative", "indicators": ["perf_1", "perf_2", "perf_3", "perf_4", "perf_5"]},
                {"id": "CSOR", "name": "Corporate Social Responsibility", "type": "formative", "indicators": ["csor_1", "csor_2", "csor_3", "csor_4", "csor_5"]},
                {"id": "ATTR", "name": "Attractiveness", "type": "formative", "indicators": ["attr_1", "attr_2", "attr_3"]},
                {"id": "COMP", "name": "Competence", "type": "reflective", "indicators": ["comp_1", "comp_2", "comp_3"]},
                {"id": "LIKE", "name": "Likeability", "type": "reflective", "indicators": ["like_1", "like_2", "like_3"]},
                {"id": "CUSA", "name": "Customer Satisfaction", "type": "reflective", "indicators": ["cusa"]},
                {"id": "CUSL", "name": "Customer Loyalty", "type": "reflective", "indicators": ["cusl_1", "cusl_2", "cusl_3"]},
            ],
            "paths": [
                {"from": "QUAL", "to": "COMP"},
                {"from": "PERF", "to": "COMP"},
                {"from": "CSOR", "to": "COMP"},
                {"from": "ATTR", "to": "COMP"},
                {"from": "QUAL", "to": "LIKE"},
                {"from": "PERF", "to": "LIKE"},
                {"from": "CSOR", "to": "LIKE"},
                {"from": "ATTR", "to": "LIKE"},
                {"from": "COMP", "to": "CUSA"},
                {"from": "LIKE", "to": "CUSA"},
                {"from": "COMP", "to": "CUSL"},
                {"from": "LIKE", "to": "CUSL"},
                {"from": "CUSA", "to": "CUSL"},
            ],
        }

        # Model 3: Higher-Order Construct Model (Corporate Reputation HCM)
        hcm_spec = {
            "constructs": [
                {"id": "COMP", "name": "Competence", "type": "reflective", "indicators": ["comp_1", "comp_2", "comp_3"]},
                {"id": "LIKE", "name": "Likeability", "type": "reflective", "indicators": ["like_1", "like_2", "like_3"]},
                {
                    "id": "CORP_REP",
                    "name": "Corporate Reputation (HOC)",
                    "type": "reflective",
                    "level": "hoc",
                    "hoc_type": "reflective-reflective",
                    "approach": "repeated_indicators",
                    "locs": ["COMP", "LIKE"],
                    "indicators": ["comp_1", "comp_2", "comp_3", "like_1", "like_2", "like_3"],
                },
                {"id": "CUSA", "name": "Customer Satisfaction", "type": "reflective", "indicators": ["cusa"]},
                {"id": "CUSL", "name": "Customer Loyalty", "type": "reflective", "indicators": ["cusl_1", "cusl_2", "cusl_3"]},
            ],
            "paths": [
                {"from": "CORP_REP", "to": "CUSA"},
                {"from": "CORP_REP", "to": "CUSL"},
                {"from": "CUSA", "to": "CUSL"},
            ],
        }

        for m_id, m_name, m_spec in [
            ("model_simple", "Simple Model (Hair et al. 2017/2018)", simple_spec),
            ("model_extended", "Extended Model with Formative Drivers (Ch. 2-5)", extended_spec),
            ("model_hcm", "Higher-Order Construct Model (Ch. 2)", hcm_spec),
        ]:
            cur.execute(
                """
                INSERT OR REPLACE INTO models (id, name, spec_json, created_at, modified_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (m_id, m_name, json.dumps(m_spec), now, now),
            )

        conn.commit()

        return {
            "status": "success",
            "success": True,
            "project_path": project_path,
            "row_count": len(df_raw),
            "column_count": len(df_raw.columns),
            "dataset_id": ds1["id"],
            "model_id": "model_extended",
            "datasets": [ds1, ds2],
            "models": ["model_simple", "model_extended", "model_hcm"],
            "description": "Seeded Corporate Reputation benchmark case study.",
        }

    finally:
        conn.close()
