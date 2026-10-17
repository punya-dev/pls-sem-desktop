"""
Derived Datasets and Lineage Module (DAT-10).
Supports creating derived datasets with lineage tracking:
- filter_rows
- select_columns
- casewise_deletion
- remove_cases
- mean_replace
- imputation (EM or kNN)
- group_split
- median_split / mean_split
"""

import sqlite3
import json
from typing import List, Dict, Any, Optional, Tuple, Union
import pandas as pd
import numpy as np

from data.datasets import load_dataset, save_dataset, list_datasets
from data.imputation import mean_imputation, em_imputation, knn_imputation


def apply_derivation(
    df: pd.DataFrame,
    operation: str,
    params: Dict[str, Any],
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Applies a transformation operation to a DataFrame and returns (derived_df, execution_meta).
    """
    op = operation.lower()
    df_result = df.copy()
    meta: Dict[str, Any] = {"operation": op, "params": params}

    if op == "filter_rows":
        filters = params.get("filters", [])
        for f in filters:
            col = f["column"]
            val = f["value"]
            operator = f.get("op", "==")
            if col not in df_result.columns:
                continue

            s = df_result[col]
            if operator == "==":
                df_result = df_result[s == val]
            elif operator == "!=":
                df_result = df_result[s != val]
            elif operator == ">":
                df_result = df_result[pd.to_numeric(s, errors="coerce") > float(val)]
            elif operator == ">=":
                df_result = df_result[pd.to_numeric(s, errors="coerce") >= float(val)]
            elif operator == "<":
                df_result = df_result[pd.to_numeric(s, errors="coerce") < float(val)]
            elif operator == "<=":
                df_result = df_result[pd.to_numeric(s, errors="coerce") <= float(val)]
            elif operator == "in":
                val_list = val if isinstance(val, list) else [val]
                df_result = df_result[s.isin(val_list)]
            elif operator == "not_in":
                val_list = val if isinstance(val, list) else [val]
                df_result = df_result[~s.isin(val_list)]
        df_result = df_result.reset_index(drop=True)

    elif op == "select_columns":
        cols = [c for c in params.get("columns", []) if c in df_result.columns]
        if cols:
            df_result = df_result[cols].copy()

    elif op == "casewise_deletion":
        cols = [c for c in params.get("columns", list(df_result.columns)) if c in df_result.columns]
        max_missing_pct = float(params.get("max_missing_pct", 0.0))
        if max_missing_pct == 0.0:
            df_result = df_result.dropna(subset=cols).reset_index(drop=True)
        else:
            missing_share = df_result[cols].isna().mean(axis=1) * 100.0
            df_result = df_result[missing_share <= max_missing_pct].reset_index(drop=True)

    elif op == "remove_cases":
        row_indices = params.get("row_indices", [])
        valid_indices = [idx for idx in row_indices if idx in df_result.index]
        df_result = df_result.drop(index=valid_indices).reset_index(drop=True)

    elif op == "mean_replace":
        cols = params.get("columns", None)
        df_result, n_imputed = mean_imputation(df_result, columns=cols)
        meta["cells_imputed"] = n_imputed

    elif op == "em_impute":
        cols = params.get("columns", None)
        max_iter = int(params.get("max_iter", 100))
        tol = float(params.get("tol", 1e-4))
        df_result, n_imputed, iters = em_imputation(df_result, columns=cols, max_iter=max_iter, tol=tol)
        meta["cells_imputed"] = n_imputed
        meta["iterations"] = iters

    elif op == "knn_impute":
        cols = params.get("columns", None)
        k = int(params.get("k", 5))
        df_result, n_imputed = knn_imputation(df_result, columns=cols, k=k)
        meta["cells_imputed"] = n_imputed

    elif op == "median_split" or op == "mean_split":
        col = params.get("column")
        if col not in df_result.columns:
            raise ValueError(f"Column '{col}' not found for split.")
        s = pd.to_numeric(df_result[col], errors="coerce")
        split_val = float(s.median() if op == "median_split" else s.mean())
        target_group = params.get("group", "high")  # 'high' or 'low'
        if target_group == "high":
            df_result = df_result[s >= split_val].reset_index(drop=True)
        else:
            df_result = df_result[s < split_val].reset_index(drop=True)
        meta["split_value"] = split_val
        meta["selected_group"] = target_group

    else:
        raise ValueError(f"Unsupported derivation operation: '{operation}'")

    meta["initial_rows"] = len(df)
    meta["final_rows"] = len(df_result)
    return df_result, meta


def create_derived_dataset(
    conn: sqlite3.Connection,
    parent_id: str,
    name: str,
    operation: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Loads parent dataset, applies derivation operation, and saves as a new derived dataset.
    """
    parent_ds = load_dataset(conn, dataset_id=parent_id)
    if not parent_ds:
        raise ValueError(f"Parent dataset '{parent_id}' not found.")

    parent_df = parent_ds["df"]
    derived_df, meta = apply_derivation(parent_df, operation, params)

    # Generate unique dataset id
    existing = list_datasets(conn)
    new_id = str(len(existing) + 1)
    while any(d["id"] == new_id for d in existing):
        new_id = f"{new_id}_1"

    # Carry forward column metadata from parent
    parent_meta = parent_ds.get("column_metadata", {})
    col_roles = {c: parent_meta.get(c, {}) for c in derived_df.columns if c in parent_meta}

    saved_meta = save_dataset(
        conn=conn,
        dataset_id=new_id,
        name=name,
        df=derived_df,
        parent_id=parent_id,
        kind="derived",
        derivation={"operation": operation, "params": params, "meta": meta},
        column_roles=col_roles,
    )
    return saved_meta


def split_by_group(
    conn: sqlite3.Connection,
    parent_id: str,
    group_column: str,
) -> List[Dict[str, Any]]:
    """
    Splits a dataset into multiple derived datasets based on unique values of group_column.
    """
    parent_ds = load_dataset(conn, dataset_id=parent_id)
    if not parent_ds:
        raise ValueError(f"Parent dataset '{parent_id}' not found.")

    parent_df = parent_ds["df"]
    if group_column not in parent_df.columns:
        raise ValueError(f"Group column '{group_column}' not found.")

    groups = parent_df[group_column].dropna().unique()
    created_datasets = []

    for g_val in groups:
        sub_name = f"{parent_ds['name']} - {group_column}={g_val}"
        ds_info = create_derived_dataset(
            conn=conn,
            parent_id=parent_id,
            name=sub_name,
            operation="filter_rows",
            params={"filters": [{"column": group_column, "op": "==", "value": g_val}]},
        )
        created_datasets.append(ds_info)

    return created_datasets
