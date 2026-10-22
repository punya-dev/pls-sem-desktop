from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Any, Dict, Set
import pandas as pd
import io
import json
import asyncio
import uuid
import threading
import time
from scipy import stats
import numpy as np
import project_io
import os
import workspace_io
import settings_io
from model_spec import ModelSpec, ValidateModelRequest, SaveModelRequest, RunPlsRequest, BootstrapStartRequest
from model_validator import validate_model_spec, ValidationResult
from engine.pls.algorithm import PLSAlgorithm, run_pls
import smartpls_importer
import sqlite3
from data.importer import (
    ImportSettings,
    raw_file_preview,
    parse_dataframe,
    preview_import_data,
)
from data.datasets import (
    save_dataset as ds_save,
    load_dataset as ds_load,
    list_datasets as ds_list,
    delete_dataset as ds_delete,
    update_column_metadata as ds_update_col,
)
from data.screening import (
    analyze_missing_data,
    detect_suspicious_patterns,
    detect_outliers,
    assess_distributions,
    calculate_histogram,
    reverse_code_column,
    assess_directionality,
)
from data.derived import (
    create_derived_dataset,
    split_by_group,
)
from core.jobs import default_job_manager
from engine.pls.blindfolding import run_blindfolding
from engine.pls.mediation import analyze_mediation
from engine.pls.moderation import analyze_moderation
from engine.pls.quadratic import analyze_quadratic_effect
from engine.pls.ipma import analyze_ipma
from engine.pls.hcm import analyze_hcm
from engine.pls.cta import run_cta_pls
from engine.pls.micom import run_micom
from engine.pls.mga import analyze_mga
from engine.pls.fimix import analyze_fimix
from engine.pls.pos import analyze_pos
from engine.pls.otg import run_otg_analysis
from engine.pls.ex_post import (
    compute_crosstab_overlap,
    run_logistic_segment_regression,
    compare_explanatory_groups_with_pos,
)
from data.groups import (
    generate_categorical_groups,
    append_column_to_dataset,
    seed_corporate_reputation_project,
)
from engine.pls.power import (
    calculate_ten_times_rule,
    compute_statistical_power,
    solve_minimum_sample_size,
    get_cohen_appendix_c_table,
    evaluate_model_power,
)
from engine.pls.copula import analyze_gaussian_copula
from engine.pls.nca import analyze_nca
from engine.pls.predict import run_pls_predict
from reporting.tables import TABLE_EXTRACTORS, export_table_to_format
from reporting.narrative import generate_narrative_report
from reporting.pdf_export import generate_pdf_report



app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SaveDataJsonRequest(BaseModel):
    path: str
    dataset_name: Optional[str] = None
    columns: List[str]
    rows: List[List[Any]]
    dtypes: Optional[List[str]] = None
    missing_value: Optional[str] = None
    treatment: Optional[str] = None


class RenameModelRequest(BaseModel):
    path: str
    model_id: str
    new_name: str


class RenameDatasetRequest(BaseModel):
    path: str
    dataset_id: str
    new_name: str


class RenameProjectRequest(BaseModel):
    path: str
    new_name: str
    rename_file: bool = False


class CreateModelRequest(BaseModel):
    path: str
    name: Optional[str] = None
    dataset_id: Optional[str] = None


class CopyModelRequest(BaseModel):
    path: str
    model_id: str
    include_results: bool = False


class BindDatasetRequest(BaseModel):
    path: str
    model_id: str
    dataset_id: str


class DeleteDatasetRequest(BaseModel):
    path: str
    dataset_id: str
    force: bool = False


class ExportZipRequest(BaseModel):
    path: str
    out_path: str
    include_results: bool = True


class ImportZipRequest(BaseModel):
    zip_path: str
    workspace_dir: str
    on_conflict: str = "rename"


class DeriveDatasetRequest(BaseModel):
    path: str
    parent_id: str
    name: str
    operation: str
    params: Dict[str, Any]


class SplitGroupsRequest(BaseModel):
    path: str
    parent_id: str
    group_column: str


class ColumnRoleRequest(BaseModel):
    path: str
    dataset_id: str
    column: str
    role: Optional[str] = None
    scale_min: Optional[float] = None
    scale_max: Optional[float] = None
    reverse_coded: Optional[bool] = None
    label: Optional[str] = None


class ReverseCodeRequest(BaseModel):
    path: str
    dataset_id: str
    columns: List[str]
    scale_min: Optional[float] = None
    scale_max: Optional[float] = None
    in_place: bool = False
    new_dataset_name: Optional[str] = None


class RemoveFlaggedCasesRequest(BaseModel):
    path: str
    dataset_id: str
    rule: str = "missing_gt_15"
    new_dataset_name: Optional[str] = None


def read_uploaded_file(filename: str, contents: bytes, missing_values: Optional[List[str]] = None) -> pd.DataFrame:
    na_vals = ["", "NA", "N/A", "nan", "NaN", "null", "NULL", "None"]
    if missing_values:
        for mv in missing_values:
            mv_str = str(mv).strip()
            if mv_str and mv_str not in na_vals:
                na_vals.append(mv_str)

    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(contents), sep=None, engine='python', na_values=na_vals, keep_default_na=True)
    elif filename.endswith((".xls", ".xlsx")):
        df = pd.read_excel(io.BytesIO(contents), na_values=na_vals, keep_default_na=True)
    else:
        raise ValueError("Unsupported file type")

    if missing_values:
        for mv in missing_values:
            mv_str = str(mv).strip()
            if not mv_str:
                continue
            df = df.replace(mv_str, np.nan)
            try:
                val_num = float(mv_str)
                df = df.replace(val_num, np.nan)
                if val_num.is_integer():
                    df = df.replace(int(val_num), np.nan)
            except ValueError:
                pass

    return df


def apply_missing_treatment(df: pd.DataFrame, treatment: Optional[str]) -> pd.DataFrame:
    if treatment == "listwise":
        return df.dropna()
    elif treatment == "mean":
        cleaned_df = df.copy()
        for col in cleaned_df.columns:
            converted = pd.to_numeric(cleaned_df[col], errors='coerce')
            if converted.notnull().sum() > 0 and converted.isna().sum() < len(converted):
                cleaned_df[col] = converted
        numeric_cols = cleaned_df.select_dtypes(include=[np.number]).columns
        cleaned_df[numeric_cols] = cleaned_df[numeric_cols].fillna(cleaned_df[numeric_cols].mean())
        return cleaned_df
    return df


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"message": "PLS-SEM backend running"}


@app.post("/data/raw-preview")
async def data_raw_preview(file: UploadFile = File(...), n_lines: int = 50, encoding: Optional[str] = None):
    contents = await file.read()
    return raw_file_preview(contents, n_lines=n_lines, encoding=encoding)


@app.post("/data/preview-import")
async def data_preview_import(
    file: UploadFile = File(...),
    delimiter: Optional[str] = "auto",
    decimal: str = ".",
    thousands: Optional[str] = None,
    encoding: str = "utf-8",
    header: bool = True,
    skip_rows: int = 0,
    missing_codes: Optional[str] = None,
    treat_dot_as_missing: bool = True,
    sheet: Optional[str] = "0",
):
    contents = await file.read()
    mv_list = [v.strip() for v in missing_codes.split(",") if v.strip()] if missing_codes else ["-99", "NA", "null", "."]
    sheet_val: Any = sheet
    if sheet is not None:
        try:
            sheet_val = int(sheet)
        except ValueError:
            sheet_val = sheet

    settings = ImportSettings(
        delimiter=delimiter,
        decimal=decimal,
        thousands=thousands,
        encoding=encoding,
        header=header,
        skip_rows=skip_rows,
        missing_codes=mv_list,
        treat_dot_as_missing=treat_dot_as_missing,
        sheet=sheet_val,
    )
    return preview_import_data(contents, file.filename, settings=settings)


@app.post("/data/import")
async def import_data(
    file: UploadFile = File(...),
    missing_value: Optional[str] = None,
    treatment: Optional[str] = None,
    path: Optional[str] = None,
    dataset_name: Optional[str] = None,
    mode: str = "new",  # "new" or "replace"
    delimiter: Optional[str] = "auto",
    decimal: str = ".",
    thousands: Optional[str] = None,
    encoding: str = "utf-8",
    header: bool = True,
    skip_rows: int = 0,
    treat_dot_as_missing: bool = True,
    sheet: Optional[str] = "0",
):
    contents = await file.read()
    mv_list = [v.strip() for v in missing_value.split(",") if v.strip()] if missing_value else ["-99", "NA", "null", "."]
    sheet_val: Any = sheet
    if sheet is not None:
        try:
            sheet_val = int(sheet)
        except ValueError:
            sheet_val = sheet

    settings = ImportSettings(
        delimiter=delimiter,
        decimal=decimal,
        thousands=thousands,
        encoding=encoding,
        header=header,
        skip_rows=skip_rows,
        missing_codes=mv_list,
        treat_dot_as_missing=treat_dot_as_missing,
        sheet=sheet_val,
    )
    df, col_meta, issues, used_settings = parse_dataframe(contents, file.filename, settings)
    if treatment:
        df = apply_missing_treatment(df, treatment)

    ds_name = dataset_name or file.filename or "Imported Data"

    # If project path is given, save to SQLite multi-dataset table
    saved_meta = None
    if path and os.path.exists(path):
        conn = sqlite3.connect(path)
        existing = ds_list(conn)
        dataset_id = "1" if mode == "replace" and len(existing) > 0 else str(len(existing) + 1)
        while mode != "replace" and any(d["id"] == dataset_id for d in existing):
            dataset_id = f"{dataset_id}_1"

        saved_meta = ds_save(
            conn=conn,
            dataset_id=dataset_id,
            name=ds_name,
            df=df,
            column_roles=col_meta,
            settings=used_settings,
        )
        conn.close()

    preview_df = df.head(20).astype(object).where(pd.notnull(df.head(20)), None)
    return {
        "columns": list(df.columns),
        "dtypes": df.dtypes.astype(str).to_dict(),
        "row_count": len(df),
        "preview": preview_df.to_dict(orient="records"),
        "issues": issues,
        "dataset": saved_meta,
    }


@app.get("/project/diagnostics")
def project_diagnostics(path: str, dataset_id: Optional[str] = None):
    if not os.path.exists(path):
        return {"error": "Project file not found"}

    conn = sqlite3.connect(path)
    ds = ds_load(conn, dataset_id)
    conn.close()

    if not ds:
        # Fallback to legacy
        data = project_io.load_data(path)
        if data is None:
            return {"error": "No data found in this project"}
        df = pd.DataFrame(data["rows"], columns=data["columns"])
    else:
        df = ds["df"]

    total_rows, total_cols = df.shape
    numeric_df = df.select_dtypes(include=[np.number])

    stats_report = {}
    for col in numeric_df.columns:
        series = numeric_df[col].dropna()
        n_valid = len(series)
        if n_valid == 0:
            continue
        vals = series.values.astype(float)
        skew = float(stats.skew(vals)) if n_valid > 2 else 0.0
        kurt = float(stats.kurtosis(vals)) if n_valid > 3 else 0.0
        q1 = float(np.percentile(vals, 25))
        q3 = float(np.percentile(vals, 75))
        iqr = q3 - q1
        mode_val = float(stats.mode(vals, keepdims=False)[0]) if n_valid > 0 else None

        stats_report[col] = {
            "mean": float(np.mean(vals)),
            "std": float(np.std(vals, ddof=1)) if n_valid > 1 else 0.0,
            "median": float(np.median(vals)),
            "min": float(np.min(vals)),
            "max": float(np.max(vals)),
            "q1": q1,
            "q3": q3,
            "iqr": iqr,
            "mode": mode_val,
            "n_valid": n_valid,
            "unique_count": len(np.unique(vals)),
            "skewness": round(skew, 4),
            "kurtosis": round(kurt, 4),
            "non_normal_flag": bool(abs(skew) > 1 or abs(kurt) > 1),
        }

    missing_report = {}
    for col in df.columns:
        missing_count = int(df[col].isna().sum())
        missing_report[col] = {
            "missing_count": missing_count,
            "missing_pct": round((missing_count / total_rows) * 100, 2) if total_rows > 0 else 0.0,
        }

    total_cells = total_rows * total_cols
    total_missing = int(df.isna().sum().sum())
    cases_any_missing = int((df.isna().sum(axis=1) > 0).sum())

    return {
        "row_count": total_rows,
        "column_count": total_cols,
        "total_missing": total_missing,
        "n_cases_with_any_missing": cases_any_missing,
        "pct_cells_missing": round(total_missing / total_cells * 100, 2) if total_cells > 0 else 0.0,
        "descriptive_stats": stats_report,
        "missing_report": missing_report,
    }


@app.get("/data/correlations")
def get_data_correlations(
    path: str,
    dataset_id: Optional[str] = None,
    method: str = "pearson",
    missing: str = "pairwise",
    columns: Optional[str] = None,
):
    if not os.path.exists(path):
        return {"error": "Project not found"}
    conn = sqlite3.connect(path)
    ds = ds_load(conn, dataset_id)
    conn.close()
    if not ds:
        return {"error": "Dataset not found"}

    df = ds["df"]
    col_list = [c.strip() for c in columns.split(",") if c.strip()] if columns else list(df.select_dtypes(include=[np.number]).columns)
    col_list = [c for c in col_list if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]

    if len(col_list) > 300:
        return {"error": "Too many columns requested (maximum 300)."}

    sub_df = df[col_list]
    if missing == "listwise":
        sub_df = sub_df.dropna()

    if method == "spearman":
        corr_matrix = sub_df.corr(method="spearman").values
    else:
        corr_matrix = sub_df.corr(method="pearson").values

    # Pairwise N matrix
    p = len(col_list)
    n_matrix = np.zeros((p, p), dtype=int)
    for i in range(p):
        for j in range(p):
            n_matrix[i, j] = int((~sub_df[col_list[i]].isna() & ~sub_df[col_list[j]].isna()).sum())

    # Collinearity flags (|r| >= 0.90)
    flags = []
    for i in range(p):
        for j in range(i + 1, p):
            val = float(corr_matrix[i, j])
            if not np.isnan(val) and abs(val) >= 0.90:
                flags.append({
                    "col1": col_list[i],
                    "col2": col_list[j],
                    "r": round(val, 4),
                    "warning": "Potential collinearity (|r| >= 0.90)",
                })

    return {
        "columns": col_list,
        "matrix": np.nan_to_num(corr_matrix, nan=0.0).tolist(),
        "n_matrix": n_matrix.tolist(),
        "flags": flags,
    }


@app.post("/data/derive")
def derive_dataset(req: DeriveDatasetRequest):
    if not os.path.exists(req.path):
        return {"error": "Project not found"}
    conn = sqlite3.connect(req.path)
    try:
        new_ds = create_derived_dataset(
            conn,
            parent_id=req.parent_id,
            name=req.name,
            operation=req.operation,
            params=req.params,
        )
        return {"status": "created", "dataset": new_ds}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


@app.post("/data/split-groups")
def split_dataset_groups(req: SplitGroupsRequest):
    if not os.path.exists(req.path):
        return {"error": "Project not found"}
    conn = sqlite3.connect(req.path)
    try:
        results = split_by_group(conn, parent_id=req.parent_id, group_column=req.group_column)
        return {"status": "split", "created_datasets": results}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


@app.patch("/data/column-role")
def update_column_role(req: ColumnRoleRequest):
    if not os.path.exists(req.path):
        return {"error": "Project not found"}
    conn = sqlite3.connect(req.path)
    try:
        updated = ds_update_col(
            conn=conn,
            dataset_id=req.dataset_id,
            column=req.column,
            role=req.role,
            scale_min=req.scale_min,
            scale_max=req.scale_max,
            reverse_coded=req.reverse_coded,
            label=req.label,
        )
        return {"status": "updated", "column": updated}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


@app.post("/data/reverse-code")
def reverse_code_data(req: ReverseCodeRequest):
    if not os.path.exists(req.path):
        return {"error": "Project not found"}
    conn = sqlite3.connect(req.path)
    ds = ds_load(conn, req.dataset_id)
    if not ds:
        conn.close()
        return {"error": "Dataset not found"}

    df = ds["df"].copy()
    for col in req.columns:
        if col in df.columns:
            rev_s, s_min, s_max = reverse_code_column(df[col], scale_min=req.scale_min, scale_max=req.scale_max)
            df[col] = rev_s
            ds_update_col(conn, req.dataset_id, col, reverse_coded=True, scale_min=s_min, scale_max=s_max)

    if req.new_dataset_name:
        existing = ds_list(conn)
        new_id = str(len(existing) + 1)
        res_meta = ds_save(
            conn,
            dataset_id=new_id,
            name=req.new_dataset_name,
            df=df,
            parent_id=req.dataset_id,
            kind="derived",
            derivation={"operation": "reverse_code", "columns": req.columns},
        )
        conn.close()
        return {"status": "created_derived", "dataset": res_meta}
    else:
        ds_save(conn, req.dataset_id, ds["name"], df, parent_id=ds.get("parent_id"), kind=ds.get("kind", "imported"))
        conn.close()
        return {"status": "updated_in_place", "columns": req.columns}


# --- Data Groups & Template Endpoints (A18-DAT-01 to A18-DAT-05, A18-CON-01) ---

class GenerateGroupsRequest(BaseModel):
    path: str
    dataset_id: Optional[str] = None
    column: str
    min_size: int = 10
    max_paths_predictors: int = 2


class AppendColumnRequest(BaseModel):
    path: str
    dataset_id: str
    column_name: str
    values: List[Any]
    role: str = "group"
    label: Optional[str] = None


class LoadTemplateRequest(BaseModel):
    path: str


@app.post("/data/groups/generate")
def api_generate_groups(req: GenerateGroupsRequest):
    if not os.path.exists(req.path):
        return {"error": "Project not found"}
    conn = sqlite3.connect(req.path)
    try:
        ds = ds_load(conn, req.dataset_id)
        if not ds:
            return {"error": "Dataset not found"}
        res = generate_categorical_groups(
            df=ds["df"],
            column=req.column,
            min_size=req.min_size,
            max_paths_predictors=req.max_paths_predictors,
        )
        return {"status": "success", "groups_info": res}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


@app.post("/data/append-column")
def api_append_column(req: AppendColumnRequest):
    if not os.path.exists(req.path):
        return {"error": "Project not found"}
    conn = sqlite3.connect(req.path)
    try:
        res = append_column_to_dataset(
            conn=conn,
            dataset_id=req.dataset_id,
            column_name=req.column_name,
            values=req.values,
            role=req.role,
            label=req.label,
        )
        return res
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


@app.post("/project/load-template/corporate-reputation")
def api_load_corporate_reputation_template(req: LoadTemplateRequest):
    try:
        res = seed_corporate_reputation_project(req.path)
        return res
    except Exception as e:
        return {"error": str(e)}



# --- Screening Endpoints (SCR-01 to SCR-10) ---

@app.get("/screening/missing")
def screening_missing(
    path: str,
    dataset_id: Optional[str] = None,
    model_id: Optional[str] = None,
    case_threshold: float = 15.0,
    indicator_threshold: float = 5.0,
):
    if not os.path.exists(path):
        return {"error": "Project not found"}
    conn = sqlite3.connect(path)
    ds = ds_load(conn, dataset_id)
    conn.close()
    if not ds:
        return {"error": "Dataset not found"}

    spec_obj = None
    if model_id:
        m_data = project_io.load_model_spec(path, model_id)
        if m_data and m_data.get("spec"):
            spec_obj = ModelSpec.model_validate(m_data["spec"])

    return analyze_missing_data(
        ds["df"],
        model_spec=spec_obj,
        case_threshold_pct=case_threshold,
        indicator_threshold_pct=indicator_threshold,
    )


@app.post("/screening/remove-flagged-cases")
def screening_remove_flagged_cases(req: RemoveFlaggedCasesRequest):
    if not os.path.exists(req.path):
        return {"error": "Project not found"}
    conn = sqlite3.connect(req.path)
    ds = ds_load(conn, req.dataset_id)
    if not ds:
        conn.close()
        return {"error": "Dataset not found"}

    analysis = analyze_missing_data(ds["df"])
    flagged_rows = analysis.get("flagged_cases", [])
    if not flagged_rows:
        conn.close()
        return {"status": "no_flagged_cases", "message": "No cases exceeded missing threshold."}

    new_name = req.new_dataset_name or f"{ds['name']} (clean cases)"
    derived = create_derived_dataset(
        conn,
        parent_id=req.dataset_id,
        name=new_name,
        operation="remove_cases",
        params={"row_indices": flagged_rows},
    )
    conn.close()
    return {"status": "created", "dataset": derived, "removed_count": len(flagged_rows)}


@app.get("/screening/patterns")
def screening_patterns(path: str, dataset_id: Optional[str] = None, model_id: Optional[str] = None):
    if not os.path.exists(path):
        return {"error": "Project not found"}
    conn = sqlite3.connect(path)
    ds = ds_load(conn, dataset_id)
    conn.close()
    if not ds:
        return {"error": "Dataset not found"}

    spec_obj = None
    if model_id:
        m_data = project_io.load_model_spec(path, model_id)
        if m_data and m_data.get("spec"):
            spec_obj = ModelSpec.model_validate(m_data["spec"])

    return detect_suspicious_patterns(ds["df"], model_spec=spec_obj)


@app.get("/screening/outliers")
def screening_outliers(path: str, dataset_id: Optional[str] = None, columns: Optional[str] = None):
    if not os.path.exists(path):
        return {"error": "Project not found"}
    conn = sqlite3.connect(path)
    ds = ds_load(conn, dataset_id)
    conn.close()
    if not ds:
        return {"error": "Dataset not found"}

    col_list = [c.strip() for c in columns.split(",") if c.strip()] if columns else None
    return detect_outliers(ds["df"], columns=col_list)


@app.get("/screening/distributions")
def screening_distributions(path: str, dataset_id: Optional[str] = None, rule_set: str = "textbook"):
    if not os.path.exists(path):
        return {"error": "Project not found"}
    conn = sqlite3.connect(path)
    ds = ds_load(conn, dataset_id)
    conn.close()
    if not ds:
        return {"error": "Dataset not found"}

    return assess_distributions(ds["df"], rule_set=rule_set)


@app.get("/screening/histogram")
def screening_histogram(path: str, column: str, dataset_id: Optional[str] = None, bins: str = "auto"):
    if not os.path.exists(path):
        return {"error": "Project not found"}
    conn = sqlite3.connect(path)
    ds = ds_load(conn, dataset_id)
    conn.close()
    if not ds:
        return {"error": "Dataset not found"}

    bin_arg: Any = bins
    if bins != "auto":
        try:
            bin_arg = int(bins)
        except ValueError:
            bin_arg = "auto"

    return calculate_histogram(ds["df"], column=column, bins=bin_arg)


@app.get("/screening/directionality")
def screening_directionality(path: str, model_id: str, dataset_id: Optional[str] = None):
    if not os.path.exists(path):
        return {"error": "Project not found"}
    conn = sqlite3.connect(path)
    ds = ds_load(conn, dataset_id)
    conn.close()
    if not ds:
        return {"error": "Dataset not found"}

    m_data = project_io.load_model_spec(path, model_id)
    if not m_data or not m_data.get("spec"):
        return {"error": f"Model '{model_id}' not found"}

    spec_obj = ModelSpec.model_validate(m_data["spec"])
    return assess_directionality(ds["df"], model_spec=spec_obj)


# --- Project Explorer & Management Endpoints (PRJ-01 to PRJ-09) ---

@app.get("/project/tree")
def project_tree(path: str):
    try:
        return project_io.get_project_tree(path)
    except Exception as e:
        return {"error": str(e)}


@app.post("/project/create-model")
def project_create_model(req: CreateModelRequest):
    try:
        existing = project_io.list_models(req.path)
        m_id = str(uuid.uuid4())[:8]
        m_name = req.name or f"Model {len(existing) + 1}"
        new_spec = ModelSpec(constructs=[], indicators=[], paths=[], dataset_id=req.dataset_id)
        spec_dict = new_spec.model_dump(by_alias=True)
        spec_dict["name"] = m_name
        project_io.save_model_spec(req.path, spec_dict, model_id=m_id)
        return {"status": "created", "model_id": m_id, "name": m_name, "dataset_id": req.dataset_id}
    except Exception as e:
        return {"error": str(e)}


@app.post("/project/copy-model")
def project_copy_model(req: CopyModelRequest):
    try:
        m_data = project_io.load_model_spec(req.path, req.model_id)
        if not m_data or not m_data.get("spec"):
            return {"error": f"Model '{req.model_id}' not found"}

        new_id = str(uuid.uuid4())[:8]
        spec_copy = json.loads(json.dumps(m_data["spec"]))
        old_name = spec_copy.get("name", "Model")
        spec_copy["name"] = f"{old_name} (copy)"
        project_io.save_model_spec(req.path, spec_copy, diagram_layout=m_data.get("diagram_layout"), model_id=new_id)

        if req.include_results:
            res_data = project_io.load_results(req.path, model_id=req.model_id)
            if res_data and res_data.get("results"):
                project_io.save_results(
                    req.path,
                    res_data.get("algorithm", "pls"),
                    res_data["results"],
                    model_id=new_id,
                    spec=spec_copy,
                    diagram_layout=m_data.get("diagram_layout"),
                )

        return {"status": "copied", "source_model_id": req.model_id, "new_model_id": new_id, "name": spec_copy["name"]}
    except Exception as e:
        return {"error": str(e)}


@app.post("/project/rename-model")
def project_rename_model(req: RenameModelRequest):
    try:
        return project_io.rename_model(req.path, req.model_id, req.new_name)
    except Exception as e:
        return {"error": str(e)}


@app.post("/project/rename-dataset")
def project_rename_dataset(req: RenameDatasetRequest):
    try:
        return project_io.rename_dataset(req.path, req.dataset_id, req.new_name)
    except Exception as e:
        return {"error": str(e)}


@app.post("/project/rename")
def project_rename(req: RenameProjectRequest):
    try:
        return project_io.rename_project(req.path, req.new_name, rename_file=req.rename_file)
    except Exception as e:
        return {"error": str(e)}


@app.post("/project/bind-dataset")
def project_bind_dataset(req: BindDatasetRequest):
    try:
        return project_io.bind_dataset_to_model(req.path, req.model_id, req.dataset_id)
    except Exception as e:
        return {"error": str(e)}


@app.post("/project/delete-dataset")
def project_delete_dataset(req: DeleteDatasetRequest):
    try:
        conn = sqlite3.connect(req.path)
        models = project_io.list_models(req.path)
        bound_models = []
        for m in models:
            spec = m.get("spec", {})
            if spec.get("dataset_id") == req.dataset_id:
                bound_models.append(m["model_id"])

        if bound_models and not req.force:
            conn.close()
            return {
                "error": "Dataset is currently bound to active models.",
                "bound_models": bound_models,
            }

        res = ds_delete(conn, req.dataset_id)
        conn.close()
        return {"status": "deleted", "dataset_id": req.dataset_id}
    except Exception as e:
        return {"error": str(e)}


@app.get("/project/datasets")
def project_get_datasets(path: str):
    if not os.path.exists(path):
        return {"error": "Project not found"}
    conn = sqlite3.connect(path)
    datasets = ds_list(conn)
    conn.close()
    return {"datasets": datasets}


@app.post("/project/export-zip")
def project_export_zip(req: ExportZipRequest):
    try:
        zip_path = project_io.export_project_zip(req.path, req.out_path, include_results=req.include_results)
        return {"status": "exported", "zip_path": zip_path}
    except Exception as e:
        return {"error": str(e)}


@app.post("/project/import-zip")
def project_import_zip(req: ImportZipRequest):
    try:
        proj_path = project_io.import_project_zip(req.zip_path, req.workspace_dir, on_conflict=req.on_conflict)
        return {"status": "imported", "project_path": proj_path}
    except Exception as e:
        return {"error": str(e)}



@app.post("/project/treat-missing")
def project_treat_missing(path: str, method: str = "listwise", missing_value: Optional[str] = None):
    data = project_io.load_data(path)
    if data is None:
        return {"error": "No data found in this project"}

    df = pd.DataFrame(data["rows"], columns=data["columns"])
    original_rows = len(df)

    if missing_value:
        mv_list = [v.strip() for v in missing_value.split(",") if v.strip()]
        for mv in mv_list:
            df = df.replace(mv, np.nan)
            try:
                num = float(mv)
                df = df.replace(num, np.nan)
                if num.is_integer():
                    df = df.replace(int(num), np.nan)
            except ValueError:
                pass

    cleaned_df = apply_missing_treatment(df, method)
    cleaned_clean = cleaned_df.astype(object).where(pd.notnull(cleaned_df), None)
    project_io.save_data(path, cleaned_clean.values.tolist(), list(cleaned_df.columns), list(cleaned_df.dtypes.astype(str)), dataset_name=data.get("dataset_name"))

    return {
        "status": "updated",
        "method": method,
        "original_row_count": original_rows,
        "cleaned_row_count": len(cleaned_df),
        "rows_dropped": original_rows - len(cleaned_df),
    }


@app.post("/project/open")
def open_project(path: str):
    if not os.path.exists(path):
        return {"error": "Project file does not exist"}
    project_io.add_recent_project(path)
    return {"status": "opened", "path": path}


@app.post("/project/save-data")
async def save_project_data(
    path: str,
    file: UploadFile = File(...),
    missing_value: Optional[str] = None,
    treatment: Optional[str] = None,
):
    contents = await file.read()
    mv_list = [v.strip() for v in missing_value.split(",") if v.strip()] if missing_value else None
    df = read_uploaded_file(file.filename, contents, missing_values=mv_list)
    df = apply_missing_treatment(df, treatment)

    df_clean = df.astype(object).where(pd.notnull(df), None)
    project_io.save_data(path, df_clean.values.tolist(), list(df.columns), list(df.dtypes.astype(str)), dataset_name=file.filename)
    return {"status": "saved", "row_count": len(df), "dataset_name": file.filename}


@app.post("/project/save-data-json")
def save_project_data_json(req: SaveDataJsonRequest):
    try:
        df = pd.DataFrame(req.rows, columns=req.columns)
        if req.missing_value:
            mv_list = [v.strip() for v in req.missing_value.split(",") if v.strip()]
            for mv in mv_list:
                df = df.replace(mv, np.nan)
                try:
                    num = float(mv)
                    df = df.replace(num, np.nan)
                    if num.is_integer():
                        df = df.replace(int(num), np.nan)
                except ValueError:
                    pass
        if req.treatment:
            df = apply_missing_treatment(df, req.treatment)

        df_clean = df.astype(object).where(pd.notnull(df), None)
        dtypes = req.dtypes
        if not dtypes:
            dtypes = list(df.dtypes.astype(str))
        project_io.save_data(req.path, df_clean.values.tolist(), list(df.columns), dtypes, dataset_name=req.dataset_name)
        return {"status": "saved", "row_count": len(df), "dataset_name": req.dataset_name}
    except Exception as e:
        return {"error": str(e)}


@app.post("/project/delete-data")
def delete_project_data(path: str):
    try:
        project_io.delete_data(path)
        return {"status": "deleted"}
    except Exception as e:
        return {"error": str(e)}


@app.get("/project/load-data")
def load_project_data(path: str):
    data = project_io.load_data(path)
    if data is None:
        return {"error": "No data found in this project"}
    return data


@app.get("/project/metadata")
def get_project_metadata(path: str):
    return project_io.load_metadata(path)


@app.get("/project/recent")
def recent_projects():
    return project_io.get_recent_projects()


@app.post("/workspace/create")
def create_workspace(folder_path: str, name: str):
    try:
        ws = workspace_io.create_workspace(folder_path, name)
        workspace_io.add_recent_workspace(folder_path)
        return {"status": "created", "path": folder_path, "workspace": ws}
    except FileExistsError as e:
        return {"error": str(e)}


@app.post("/workspace/open")
def open_workspace(folder_path: str):
    ws = workspace_io.load_workspace(folder_path)
    if ws is None:
        return {"error": "Not a valid workspace"}
    workspace_io.add_recent_workspace(folder_path)
    
    return {"status": "opened", "path": folder_path, "workspace": ws}


@app.get("/workspace/recent")
def recent_workspaces():
    return workspace_io.get_recent_workspaces()


@app.post("/workspace/add-project")
def add_project(folder_path: str, project_name: str):
    try:
        project_filename = f"{project_name}.pls"
        full_project_path = os.path.join(folder_path, project_filename)

        project_io.create_project(full_project_path, project_name)
        project_io.add_recent_project(full_project_path)
        ws = workspace_io.add_project_to_workspace(folder_path, project_filename, project_name)

        return {"status": "created", "project_path": full_project_path, "workspace": ws}
    except Exception as e:
        return {"error": str(e)}


@app.post("/workspace/remove-project")
def remove_project_from_ws(folder_path: str, project_filename: str):
    try:
        ws = workspace_io.remove_project_from_workspace(folder_path, project_filename)
        return {"status": "removed", "workspace": ws}
    except Exception as e:
        return {"error": str(e)}


@app.post("/workspace/delete-project")
def delete_project_from_ws(folder_path: str, project_filename: str):
    try:
        full_project_path = os.path.join(folder_path, project_filename)
        if os.path.exists(full_project_path):
            os.remove(full_project_path)
        ws = workspace_io.remove_project_from_workspace(folder_path, project_filename)
        settings_io.remove_recent("recent_projects", full_project_path)
        return {"status": "deleted", "workspace": ws}
    except Exception as e:
        return {"error": str(e)}


class SmartPlsDetectRequest(BaseModel):
    folder_path: str


class SmartPlsImportRequest(BaseModel):
    folder_path: str
    target_workspace_folder: Optional[str] = None
    workspace_name: Optional[str] = None


@app.post("/project/smartpls/detect")
def detect_smartpls(req: SmartPlsDetectRequest):
    try:
        return smartpls_importer.detect_smartpls_folder(req.folder_path)
    except Exception as e:
        return {"valid": False, "error": str(e)}


@app.post("/project/smartpls/import")
def import_smartpls(req: SmartPlsImportRequest):
    try:
        return smartpls_importer.import_smartpls_folder(
            req.folder_path,
            target_workspace_folder=req.target_workspace_folder,
            workspace_name=req.workspace_name,
        )
    except Exception as e:
        return {"error": str(e)}


class FolderDetectRequest(BaseModel):
    folder_path: str


class SmartPlsWorkspaceImportRequest(BaseModel):
    folder_path: str


@app.post("/workspace/detect_folder")
def detect_folder(req: FolderDetectRequest):
    try:
        return smartpls_importer.detect_folder_type(req.folder_path)
    except Exception as e:
        return {"kind": "error", "error": str(e)}


@app.post("/workspace/smartpls/import")
def import_smartpls_ws(req: SmartPlsWorkspaceImportRequest):
    try:
        return smartpls_importer.import_smartpls_workspace(req.folder_path)
    except Exception as e:
        return {"error": str(e)}







@app.post("/workspace/delete")
def delete_workspace(folder_path: str):
    try:
        res = workspace_io.delete_workspace(folder_path)
        return res
    except Exception as e:
        return {"error": str(e)}


@app.post("/model/validate")
def validate_model(req: ValidateModelRequest):
    dataset_cols = req.dataset_columns or req.columns
    if dataset_cols is None and req.project_path:
        project_data = project_io.load_data(req.project_path)
        if project_data and "columns" in project_data:
            dataset_cols = project_data["columns"]

    result = validate_model_spec(req.spec, dataset_columns=dataset_cols)
    return result.model_dump()


class DuplicateModelRequest(BaseModel):
    project_path: str
    source_model_id: str
    new_model_id: str

class DuplicateProjectRequest(BaseModel):
    folder_path: str
    source_path: str
    new_name: str
    model_id_map: Optional[Dict[str, str]] = None

class MoveProjectRequest(BaseModel):
    source_workspace_path: str
    target_workspace_path: str
    source_path: str
    project_name: Optional[str] = None

class RemapModelIdsRequest(BaseModel):
    project_path: str
    model_id_map: Dict[str, str]

class DuplicateWorkspaceRequest(BaseModel):
    source_folder_path: str
    new_name: str

class SaveSnapshotRequest(BaseModel):
    project_path: str
    name: str
    description: Optional[str] = ""
    algorithm: Optional[str] = "pls"
    results: dict
    spec: dict
    diagram_layout: dict
    source_model_id: Optional[str] = None

class CreateModelFromSnapshotRequest(BaseModel):
    project_path: str
    snapshot_id: str
    new_model_id: str
    new_model_name: str

class DeleteSnapshotRequest(BaseModel):
    project_path: str
    snapshot_id: str

@app.post("/project/save-snapshot")
def save_snapshot_endpoint(req: SaveSnapshotRequest):
    if not os.path.exists(req.project_path):
        return {"error": "Project file does not exist"}
    try:
        res = project_io.save_snapshot(
            req.project_path,
            name=req.name,
            algorithm=req.algorithm,
            results=req.results,
            spec=req.spec,
            diagram_layout=req.diagram_layout,
            description=req.description,
            source_model_id=req.source_model_id,
        )
        return res
    except Exception as e:
        return {"error": str(e)}

@app.get("/project/list-snapshots")
def list_snapshots_endpoint(path: str):
    if not os.path.exists(path):
        return {"error": "Project file does not exist"}
    try:
        return project_io.list_snapshots(path)
    except Exception as e:
        return {"error": str(e)}

@app.get("/project/get-snapshot")
def get_snapshot_endpoint(path: str, snapshot_id: str):
    if not os.path.exists(path):
        return {"error": "Project file does not exist"}
    try:
        snap = project_io.get_snapshot(path, snapshot_id)
        if not snap:
            return {"error": "Snapshot not found"}
        return snap
    except Exception as e:
        return {"error": str(e)}

@app.post("/project/delete-snapshot")
def delete_snapshot_endpoint(req: DeleteSnapshotRequest):
    if not os.path.exists(req.project_path):
        return {"error": "Project file does not exist"}
    try:
        ok = project_io.delete_snapshot(req.project_path, req.snapshot_id)
        return {"status": "deleted" if ok else "not_found"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/project/create-model-from-snapshot")
def create_model_from_snapshot_endpoint(req: CreateModelFromSnapshotRequest):
    if not os.path.exists(req.project_path):
        return {"error": "Project file does not exist"}
    try:
        return project_io.create_model_from_snapshot(
            req.project_path,
            snapshot_id=req.snapshot_id,
            new_model_id=req.new_model_id,
            new_model_name=req.new_model_name,
        )
    except Exception as e:
        return {"error": str(e)}

@app.post("/project/save-model")
def save_project_model(req: SaveModelRequest):
    if not os.path.exists(req.project_path):
        return {"error": "Project file does not exist"}

    project_data = project_io.load_data(req.project_path)
    dataset_cols = project_data["columns"] if (project_data and "columns" in project_data) else None

    validation = validate_model_spec(req.spec, dataset_columns=dataset_cols)

    try:
        project_io.save_model_spec(
            req.project_path,
            req.spec.model_dump(by_alias=True),
            diagram_layout=req.diagram_layout,
            model_id=req.model_id,
        )
        return {
            "status": "saved",
            "validation": validation.model_dump(),
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/project/load-model")
def load_project_model(path: str, model_id: Optional[str] = None):
    if not os.path.exists(path):
        return {"error": "Project file does not exist"}

    model_data = project_io.load_model_spec(path, model_id=model_id)
    if model_data is None or model_data.get("spec") is None:
        return {"spec": None, "diagram_layout": None, "updated_at": None, "model_key": model_id}

    return model_data


@app.post("/project/duplicate-model")
def duplicate_project_model(req: DuplicateModelRequest):
    if not os.path.exists(req.project_path):
        return {"error": "Project file does not exist"}
    try:
        res = project_io.duplicate_model_spec(req.project_path, req.source_model_id, req.new_model_id)
        return res
    except Exception as e:
        return {"error": str(e)}


@app.post("/project/duplicate")
@app.post("/study/duplicate")
def duplicate_project_file(req: DuplicateProjectRequest):
    try:
        res = project_io.duplicate_project(req.folder_path, req.source_path, req.new_name, req.model_id_map)
        return res
    except Exception as e:
        return {"error": str(e)}


@app.post("/project/move")
@app.post("/study/move")
def move_project_file(req: MoveProjectRequest):
    try:
        res = project_io.move_project(
            req.source_workspace_path,
            req.target_workspace_path,
            req.source_path,
            req.project_name
        )
        return res
    except Exception as e:
        return {"error": str(e)}


@app.post("/project/remap-model-ids")
def remap_project_model_ids(req: RemapModelIdsRequest):
    if not os.path.exists(req.project_path):
        return {"error": "Project file does not exist"}
    try:
        import sqlite3
        conn = sqlite3.connect(req.project_path)
        cur = conn.cursor()
        for old_id, new_id in req.model_id_map.items():
            cur.execute("UPDATE model_spec SET model_key = ? WHERE model_key = ?", (new_id, old_id))
            cur.execute("UPDATE results SET model_key = ? WHERE model_key = ?", (new_id, old_id))
            cur.execute("UPDATE snapshots SET source_model_id = ? WHERE source_model_id = ?", (new_id, old_id))
        conn.commit()
        conn.close()
        return {"status": "remapped"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/workspace/duplicate")
def duplicate_workspace_folder(req: DuplicateWorkspaceRequest):
    try:
        res = workspace_io.duplicate_workspace(req.source_folder_path, req.new_name)
        return res
    except Exception as e:
        return {"error": str(e)}


@app.post("/project/run-pls")
def run_project_pls(req: RunPlsRequest):
    if not os.path.exists(req.project_path):
        return {"error": "Project file does not exist"}

    # 1. Load project data
    data_dict = project_io.load_data(req.project_path)
    if (not data_dict or not data_dict.get("rows")) and req.columns and req.rows:
        try:
            df_temp = pd.DataFrame(req.rows, columns=req.columns)
            df_clean = df_temp.astype(object).where(pd.notnull(df_temp), None)
            dtypes = list(df_clean.dtypes.astype(str))
            project_io.save_data(req.project_path, df_clean.values.tolist(), list(df_clean.columns), dtypes, dataset_name=req.dataset_name)
            data_dict = {"columns": list(df_clean.columns), "rows": df_clean.values.tolist(), "dataset_name": req.dataset_name}
        except Exception as e:
            print(f"Failed to auto-save dataset in run_project_pls: {e}")

    if not data_dict or not data_dict.get("rows"):
        return {"error": "No dataset found in project. Please import data first."}

    df = pd.DataFrame(data_dict["rows"], columns=data_dict["columns"])
    # Convert numeric columns where possible
    for col in df.columns:
        converted = pd.to_numeric(df[col], errors='coerce')
        if converted.notnull().sum() > 0:
            df[col] = converted

    # 2. Resolve Model spec
    spec = req.spec
    if spec is None:
        saved_model = project_io.load_model_spec(req.project_path, req.model_id)
        if not saved_model or not saved_model.get("spec"):
            return {"error": "No path model found. Please draw or save a model first."}
        try:
            spec = ModelSpec.model_validate(saved_model["spec"])
        except Exception as e:
            return {"error": f"Invalid saved model specification: {str(e)}"}

    # 3. Validate model spec against dataset columns
    validation = validate_model_spec(spec, dataset_columns=list(df.columns))
    if not validation.is_valid:
        return {
            "error": "Model validation failed",
            "validation": validation.model_dump(),
        }

    # 4. Execute PLS algorithm
    try:
        algo = PLSAlgorithm(
            scheme=req.scheme,
            max_iter=req.max_iter,
            tol=req.tol,
            missing_treatment=req.missing_treatment or "mean",
            missing_values=req.missing_values,
        )
        res = algo.fit(df, spec)
        if req.bootstrap:
            res["significance"] = algo.bootstrap(df, spec, n_boot=req.n_boot)

        # 5. Persist results in project file scoped to model_id
        spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else None)
        project_io.save_results(
            req.project_path,
            "pls",
            res,
            model_id=req.model_id,
            spec=spec_dict,
            diagram_layout=req.diagram_layout,
        )

        return {
            "status": "success",
            "algorithm": "pls",
            "results": res,
        }
    except Exception as e:
        return {"error": f"PLS-SEM calculation failed: {str(e)}"}


@app.get("/project/load-results")
def load_project_results(path: str, algorithm: str = "pls", model_id: Optional[str] = None):
    if not os.path.exists(path):
        return {"error": "Project file does not exist"}
    data = project_io.load_results(path, algorithm=algorithm, model_id=model_id)
    if data is None:
        return {"results": None}
    return data


# --- Phase 4: Bootstrapping & Live WebSocket Progress ---

active_bootstrap_jobs: Dict[str, Dict[str, Any]] = {}


def _ws_json_default(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, (np.floating, float)):
        return float(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    return str(obj)


def _broadcast_ws(job: dict, msg: dict):
    loop = job.get("loop")
    if not loop or loop.is_closed():
        return
    try:
        payload = json.dumps(msg, default=_ws_json_default)
    except Exception as e:
        print(f"Error serializing bootstrap WS message: {e}")
        return

    for ws in list(job.get("websockets", [])):
        try:
            asyncio.run_coroutine_threadsafe(ws.send_text(payload), loop)
        except Exception:
            pass


@app.post("/project/bootstrap-start")
async def start_bootstrap_job(req: BootstrapStartRequest):
    if not os.path.exists(req.project_path):
        return {"error": "Project file does not exist"}

    # 1. Load or persist project data
    data_dict = project_io.load_data(req.project_path)
    if (not data_dict or not data_dict.get("rows")) and req.columns and req.rows:
        try:
            df_temp = pd.DataFrame(req.rows, columns=req.columns)
            df_clean = df_temp.astype(object).where(pd.notnull(df_temp), None)
            dtypes = list(df_clean.dtypes.astype(str))
            project_io.save_data(req.project_path, df_clean.values.tolist(), list(df_clean.columns), dtypes, dataset_name=req.dataset_name)
            data_dict = {"columns": list(df_clean.columns), "rows": df_clean.values.tolist(), "dataset_name": req.dataset_name}
        except Exception as e:
            print(f"Failed to auto-save dataset in start_bootstrap_job: {e}")

    if not data_dict or not data_dict.get("rows"):
        return {"error": "No dataset found in project. Please import data first."}

    df = pd.DataFrame(data_dict["rows"], columns=data_dict["columns"])
    for col in df.columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notnull().sum() > 0:
            df[col] = converted

    # 2. Resolve Model Spec
    spec = req.spec
    if spec is None:
        saved_model = project_io.load_model_spec(req.project_path)
        if not saved_model or not saved_model.get("spec"):
            return {"error": "No path model found. Please draw or save a model first."}
        try:
            spec = ModelSpec.model_validate(saved_model["spec"])
        except Exception as e:
            return {"error": f"Invalid saved model specification: {str(e)}"}

    # 3. Validate spec
    validation = validate_model_spec(spec, dataset_columns=list(df.columns))
    if not validation.is_valid:
        return {
            "error": "Model validation failed",
            "validation": validation.model_dump(),
        }

    job_id = uuid.uuid4().hex
    cancel_event = threading.Event()
    loop = asyncio.get_running_loop()

    job: Dict[str, Any] = {
        "job_id": job_id,
        "project_path": req.project_path,
        "cancel_event": cancel_event,
        "status": "running",
        "current": 0,
        "total": req.n_boot,
        "percent": 0.0,
        "start_time": time.time(),
        "elapsed_sec": 0.0,
        "results": None,
        "error": None,
        "websockets": set(),
        "loop": loop,
    }
    active_bootstrap_jobs[job_id] = job

    def _worker():
        try:
            def on_progress(cur: int, tot: int):
                job["current"] = cur
                job["total"] = tot
                job["percent"] = round((cur / tot) * 100, 1)
                job["elapsed_sec"] = round(time.time() - job["start_time"], 1)
                msg = {
                    "type": "progress",
                    "job_id": job_id,
                    "current": cur,
                    "total": tot,
                    "percent": job["percent"],
                    "elapsed_sec": job["elapsed_sec"],
                }
                _broadcast_ws(job, msg)

            algo = PLSAlgorithm(
                scheme=req.scheme,
                max_iter=req.max_iter,
                tol=req.tol,
                sign_alignment=req.sign_alignment,
                missing_treatment=req.missing_treatment or "mean",
                missing_values=req.missing_values,
            )

            # Fit base model
            base_res = algo.fit(df, spec)
            # Run parallel bootstrap
            boot_res = algo.bootstrap(
                df,
                spec,
                n_boot=req.n_boot,
                seed=req.seed,
                progress_callback=on_progress,
                cancel_event=cancel_event,
            )
            base_res["significance"] = boot_res

            # Save full results with significance to project scoped to model_id
            spec_dict = spec.model_dump(mode="json", by_alias=True) if hasattr(spec, "model_dump") else (spec if isinstance(spec, dict) else None)
            project_io.save_results(
                req.project_path,
                "pls",
                base_res,
                model_id=getattr(req, "model_id", None),
                spec=spec_dict,
                diagram_layout=getattr(req, "diagram_layout", None),
            )

            clean_res = json.loads(json.dumps(base_res, default=_ws_json_default))
            job["status"] = "completed"
            job["results"] = clean_res
            job["elapsed_sec"] = round(time.time() - job["start_time"], 1)
            msg = {
                "type": "completed",
                "job_id": job_id,
                "results": clean_res,
                "elapsed_sec": job["elapsed_sec"],
            }
            _broadcast_ws(job, msg)
        except InterruptedError:
            job["status"] = "cancelled"
            job["elapsed_sec"] = round(time.time() - job["start_time"], 1)
            msg = {"type": "cancelled", "job_id": job_id, "elapsed_sec": job["elapsed_sec"]}
            _broadcast_ws(job, msg)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            job["status"] = "failed"
            job["error"] = str(exc)
            job["elapsed_sec"] = round(time.time() - job["start_time"], 1)
            msg = {"type": "failed", "job_id": job_id, "error": str(exc), "elapsed_sec": job["elapsed_sec"]}
            _broadcast_ws(job, msg)

    threading.Thread(target=_worker, daemon=True).start()

    return {
        "status": "started",
        "job_id": job_id,
        "n_boot": req.n_boot,
    }


@app.post("/project/bootstrap-cancel")
def cancel_bootstrap_job(job_id: str):
    job = active_bootstrap_jobs.get(job_id)
    if not job:
        return {"error": "Job not found"}
    job["cancel_event"].set()
    job["status"] = "cancelled"
    _broadcast_ws(job, {"type": "cancelled", "job_id": job_id})
    return {"status": "cancelled", "job_id": job_id}


@app.get("/project/bootstrap-status")
def get_bootstrap_status(job_id: str):
    job = active_bootstrap_jobs.get(job_id)
    if not job:
        return {"error": "Job not found"}
    return {
        "job_id": job_id,
        "status": job["status"],
        "current": job["current"],
        "total": job["total"],
        "percent": job["percent"],
        "elapsed_sec": job.get("elapsed_sec", 0.0),
        "results": job.get("results"),
        "error": job.get("error"),
    }


@app.websocket("/ws/bootstrap-progress/{job_id}")
async def ws_bootstrap_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()
    job = active_bootstrap_jobs.get(job_id)
    if not job:
        await websocket.send_json({"type": "error", "message": "Job not found"})
        await websocket.close()
        return

    job["websockets"].add(websocket)

    initial_type = (
        "completed"
        if job["status"] == "completed"
        else ("failed" if job["status"] == "failed" else ("cancelled" if job["status"] == "cancelled" else "progress"))
    )

    # Immediately send current state upon connection
    initial_payload = json.dumps({
        "type": initial_type,
        "job_id": job_id,
        "current": job["current"],
        "total": job["total"],
        "percent": job["percent"],
        "elapsed_sec": round(time.time() - job["start_time"], 1),
        "results": job.get("results"),
        "error": job.get("error"),
    }, default=_ws_json_default)
    await websocket.send_text(initial_payload)

    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict) and data.get("action") == "cancel":
                job["cancel_event"].set()
                job["status"] = "cancelled"
                _broadcast_ws(job, {"type": "cancelled", "job_id": job_id})
    except (WebSocketDisconnect, Exception):
        job["websockets"].discard(websocket)


class ContrastRequest(BaseModel):
    project_path: str
    model_id: Optional[str] = None
    contrast: Dict[str, float]
    ci_method: str = "percentile"
    alpha: float = 0.05
    tails: str = "two"


@app.get("/bootstrap/samples")
def get_bootstrap_samples(path: str, model_id: Optional[str] = None, parameter: Optional[str] = None):
    res_data = project_io.load_results(path, algorithm="pls", model_id=model_id)
    if not res_data or not res_data.get("results"):
        return {"error": "No results found for model."}
    
    results = res_data["results"]
    significance = results.get("significance", {})
    samples_matrix = significance.get("samples_matrix", {})
    
    if not samples_matrix:
        return {"error": "No raw bootstrap samples saved in results."}
    
    if parameter:
        if parameter not in samples_matrix:
            return {"error": f"Parameter '{parameter}' not found in bootstrap samples."}
        return {"parameter": parameter, "samples": samples_matrix[parameter]}
    
    return {"samples_matrix": samples_matrix}


@app.get("/bootstrap/histogram")
def get_bootstrap_histogram(path: str, parameter: str, model_id: Optional[str] = None, bins: int = 30):
    res_data = project_io.load_results(path, algorithm="pls", model_id=model_id)
    if not res_data or not res_data.get("results"):
        return {"error": "No results found for model."}
    
    significance = res_data["results"].get("significance", {})
    samples_matrix = significance.get("samples_matrix", {})
    if parameter not in samples_matrix:
        return {"error": f"Parameter '{parameter}' not found in bootstrap samples."}
    
    arr = np.array(samples_matrix[parameter], dtype=float)
    counts, edges = np.histogram(arr, bins=bins)
    mean_v = float(np.mean(arr))
    std_v = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    
    normal_curve = []
    if std_v > 1e-9:
        x_grid = np.linspace(float(edges[0]), float(edges[-1]), 60)
        bin_width = float(edges[1] - edges[0])
        y_pdf = stats.norm.pdf(x_grid, mean_v, std_v) * len(arr) * bin_width
        normal_curve = [{"x": float(x), "y": float(y)} for x, y in zip(x_grid, y_pdf)]
        
    return {
        "parameter": parameter,
        "n_samples": len(arr),
        "mean": mean_v,
        "std": std_v,
        "edges": [float(e) for e in edges],
        "counts": [int(c) for c in counts],
        "normal_curve": normal_curve,
    }


@app.post("/structural/contrast")
def calculate_structural_contrast(req: ContrastRequest):
    res_data = project_io.load_results(req.project_path, algorithm="pls", model_id=req.model_id)
    if not res_data or not res_data.get("results"):
        return {"error": "No estimation results found."}
        
    results = res_data["results"]
    significance = results.get("significance", {})
    samples_matrix = significance.get("samples_matrix", {})
    params_summary = significance.get("parameters", {})
    
    if not samples_matrix:
        return {"error": "Raw bootstrap samples required for contrast analysis."}
        
    from engine.pls.contrast import compute_contrast
    original_params = {k: v.get("original", 0.0) for k, v in params_summary.items()}
    
    try:
        contrast_res = compute_contrast(
            original_parameters=original_params,
            samples_matrix=samples_matrix,
            contrast_coefficients=req.contrast,
            alpha=req.alpha,
            tails=req.tails,
            ci_method=req.ci_method,
        )
        return {"status": "success", "contrast": contrast_res}
    except Exception as e:
        return {"error": str(e)}


# --- Generic Job Manager Endpoints (P0-3) ---

@app.get("/jobs/{job_id}")
def get_generic_job(job_id: str):
    job = default_job_manager.get_job(job_id)
    if not job:
        return {"error": f"Job '{job_id}' not found"}
    return job.to_dict()


@app.post("/jobs/{job_id}/cancel")
def cancel_generic_job(job_id: str):
    success = default_job_manager.cancel(job_id)
    return {"status": "cancelled" if success else "failed", "job_id": job_id}


@app.get("/jobs")
def list_generic_jobs():
    return {"jobs": default_job_manager.list_jobs()}


@app.websocket("/ws/jobs/{job_id}")
async def ws_generic_jobs(websocket: WebSocket, job_id: str):
    await websocket.accept()
    job = default_job_manager.get_job(job_id)
    if not job:
        await websocket.send_json({"type": "error", "message": "Job not found"})
        await websocket.close()
        return

    q = default_job_manager.subscribe(job_id)
    await websocket.send_json({"type": "status", "job": job.to_dict()})
    try:
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=1.0)
                await websocket.send_json(msg)
            except asyncio.TimeoutError:
                pass
    except (WebSocketDisconnect, Exception):
        default_job_manager.unsubscribe(job_id, q)


# --- Phase 4 Advanced Analysis Endpoints ---

class BaseAnalysisRequest(BaseModel):
    project_path: str
    model_id: str = "default"
    dataset_id: Optional[str] = None
    spec: Optional[Dict[str, Any]] = None
    columns: Optional[List[str]] = None
    rows: Optional[List[List[Any]]] = None


class BlindfoldingRunRequest(BaseAnalysisRequest):
    omission_distance: int = 7
    compute_q2_effects: bool = True


class MediationAnalysisRequest(BaseAnalysisRequest):
    source: str
    target: str
    n_boot: int = 500
    seed: Optional[int] = 42
    alpha: float = 0.05
    include_sobel: bool = False


class ModerationAnalysisRequest(BaseAnalysisRequest):
    source: str
    moderator: str
    target: str
    method: str = "two_stage"
    n_boot: int = 500
    seed: Optional[int] = 42
    alpha: float = 0.05


class QuadraticAnalysisRequest(BaseAnalysisRequest):
    source: str
    target: str
    n_boot: int = 500
    seed: Optional[int] = 42
    alpha: float = 0.05


class IPMAAnalysisRequest(BaseAnalysisRequest):
    target: str
    scale_bounds: Optional[Dict[str, Any]] = None
    level: str = "both"


class HCMAnalysisRequest(BaseAnalysisRequest):
    hoc_id: str
    loc_ids: List[str]
    hoc_type: str = "RR"
    approach: str = "repeated_indicators"


def _load_data_and_spec(
    project_path: str,
    model_id: str = "default",
    dataset_id: Optional[str] = None,
    spec: Optional[Dict[str, Any]] = None,
    columns: Optional[List[str]] = None,
    rows: Optional[List[List[Any]]] = None,
):
    if not os.path.exists(project_path):
        raise ValueError(f"Project file '{project_path}' does not exist")

    df = None
    if columns and rows:
        try:
            df = pd.DataFrame(rows, columns=columns)
        except Exception:
            df = None

    if df is None:
        data_dict = project_io.load_data(project_path, dataset_id=dataset_id)
        if not data_dict or not data_dict.get("rows"):
            raise ValueError("No dataset found in project.")
        df = pd.DataFrame(data_dict["rows"], columns=data_dict["columns"])

    for col in df.columns:
        converted = pd.to_numeric(df[col], errors='coerce')
        if converted.notnull().sum() > 0:
            df[col] = converted

    resolved_spec = spec
    if not resolved_spec or not resolved_spec.get("constructs"):
        saved_model = project_io.load_model_spec(project_path, model_id)
        if saved_model and saved_model.get("spec") and saved_model["spec"].get("constructs"):
            resolved_spec = saved_model["spec"]
        else:
            # Fallback: check all models in project file
            try:
                conn = sqlite3.connect(project_path)
                cur = conn.cursor()
                cur.execute("SELECT spec_json FROM model_spec WHERE spec_json IS NOT NULL")
                for r in cur.fetchall():
                    try:
                        cand = json.loads(r[0])
                        if cand.get("constructs") and len(cand["constructs"]) > 0:
                            resolved_spec = cand
                            break
                    except Exception:
                        pass
                conn.close()
            except Exception:
                pass

    if not resolved_spec or not resolved_spec.get("constructs"):
        raise ValueError(f"No path model found for model '{model_id}'.")
    return df, resolved_spec


@app.post("/blindfolding/run")
def api_run_blindfolding(req: BlindfoldingRunRequest):
    try:
        df, spec = _load_data_and_spec(req.project_path, req.model_id, req.dataset_id, req.spec, req.columns, req.rows)
        res = run_blindfolding(
            df=df,
            spec=spec,
            omission_distance=req.omission_distance,
            compute_q2_effects=req.compute_q2_effects,
        )
        project_io.save_results(
            path=req.project_path,
            algorithm="pls",
            results_dict=res,
            model_id=req.model_id,
            analysis_type="blindfolding",
            dataset_id=req.dataset_id,
            params={"omission_distance": req.omission_distance},
        )
        return {"status": "success", "results": res}
    except Exception as e:
        return {"error": str(e)}


@app.post("/analysis/mediation")
def api_analyze_mediation(req: MediationAnalysisRequest):
    try:
        df, spec = _load_data_and_spec(req.project_path, req.model_id, req.dataset_id, req.spec, req.columns, req.rows)
        res = analyze_mediation(
            df=df,
            spec=spec,
            source_construct=req.source,
            target_construct=req.target,
            n_boot=req.n_boot,
            seed=req.seed,
            alpha=req.alpha,
            include_sobel=req.include_sobel,
        )
        project_io.save_results(
            path=req.project_path,
            algorithm="pls",
            results_dict=res,
            model_id=req.model_id,
            analysis_type="mediation",
            dataset_id=req.dataset_id,
            params={"source": req.source, "target": req.target, "n_boot": req.n_boot},
        )
        return {"status": "success", "results": res}
    except Exception as e:
        return {"error": str(e)}


@app.post("/analysis/moderation")
def api_analyze_moderation(req: ModerationAnalysisRequest):
    try:
        df, spec = _load_data_and_spec(req.project_path, req.model_id, req.dataset_id, req.spec, req.columns, req.rows)
        res = analyze_moderation(
            df=df,
            spec=spec,
            source=req.source,
            moderator=req.moderator,
            target=req.target,
            method=req.method,
            n_boot=req.n_boot,
            seed=req.seed,
            alpha=req.alpha,
        )
        project_io.save_results(
            path=req.project_path,
            algorithm="pls",
            results_dict=res,
            model_id=req.model_id,
            analysis_type="moderation",
            dataset_id=req.dataset_id,
            params={"source": req.source, "moderator": req.moderator, "target": req.target, "method": req.method},
        )
        return {"status": "success", "results": res}
    except Exception as e:
        return {"error": str(e)}


@app.post("/analysis/quadratic")
def api_analyze_quadratic(req: QuadraticAnalysisRequest):
    try:
        df, spec = _load_data_and_spec(req.project_path, req.model_id, req.dataset_id, req.spec, req.columns, req.rows)
        res = analyze_quadratic_effect(
            df=df,
            spec=spec,
            source=req.source,
            target=req.target,
            n_boot=req.n_boot,
            seed=req.seed,
            alpha=req.alpha,
        )
        project_io.save_results(
            path=req.project_path,
            algorithm="pls",
            results_dict=res,
            model_id=req.model_id,
            analysis_type="quadratic",
            dataset_id=req.dataset_id,
            params={"source": req.source, "target": req.target},
        )
        return {"status": "success", "results": res}
    except Exception as e:
        return {"error": str(e)}


@app.post("/analysis/ipma")
def api_analyze_ipma(req: IPMAAnalysisRequest):
    try:
        df, spec = _load_data_and_spec(req.project_path, req.model_id, req.dataset_id, req.spec, req.columns, req.rows)
        res = analyze_ipma(
            df=df,
            spec=spec,
            target_construct=req.target,
            scale_bounds=req.scale_bounds,
            level=req.level,
        )
        project_io.save_results(
            path=req.project_path,
            algorithm="pls",
            results_dict=res,
            model_id=req.model_id,
            analysis_type="ipma",
            dataset_id=req.dataset_id,
            params={"target": req.target, "level": req.level},
        )
        return {"status": "success", "results": res}
    except Exception as e:
        return {"error": str(e)}


@app.post("/analysis/hcm")
def api_analyze_hcm(req: HCMAnalysisRequest):
    try:
        df, spec = _load_data_and_spec(req.project_path, req.model_id, req.dataset_id, req.spec, req.columns, req.rows)
        res = analyze_hcm(
            df=df,
            spec=spec,
            hoc_id=req.hoc_id,
            loc_ids=req.loc_ids,
            hoc_type=req.hoc_type,
            approach=req.approach,
        )
        project_io.save_results(
            path=req.project_path,
            algorithm="pls",
            results_dict=res,
            model_id=req.model_id,
            analysis_type="hcm",
            dataset_id=req.dataset_id,
            params={"hoc_id": req.hoc_id, "hoc_type": req.hoc_type, "approach": req.approach},
        )
        return {"status": "success", "results": res}
    except Exception as e:
        return {"error": str(e)}


# --- Phase 5 Multi-Group, Invariance, and Latent Class Endpoints ---

class CTAAnalysisRequest(BaseAnalysisRequest):
    construct_id: Optional[str] = None
    n_boot: int = 500
    seed: Optional[int] = 42
    alpha: float = 0.05


class MICOMAnalysisRequest(BaseAnalysisRequest):
    group_col: str
    group_values: Optional[List[Any]] = None
    n_permutations: int = 500
    alpha: float = 0.05
    seed: Optional[int] = 42


class MGAAnalysisRequest(BaseAnalysisRequest):
    group_col: str
    group_values: Optional[List[Any]] = None
    n_boot: int = 500
    n_permutations: int = 500
    seed: Optional[int] = 42
    alpha: float = 0.05


class FIMIXAnalysisRequest(BaseAnalysisRequest):
    min_segments: int = 1
    max_segments: int = 4
    seed: Optional[int] = 42


class POSAnalysisRequest(BaseAnalysisRequest):
    n_segments: int = 2
    max_iter: int = 50
    min_segment_size: int = 15
    seed: Optional[int] = 42


class OTGAnalysisRequest(BaseAnalysisRequest):
    group_col: str
    group_values: Optional[List[Any]] = None
    n_boot: int = 500
    n_permutations: int = 1000
    seed: Optional[int] = 42
    alpha: float = 0.05


class ExPostAnalysisRequest(BaseAnalysisRequest):
    segment_col: str
    explanatory_cols: List[str]
    crosstab_cat_col: Optional[str] = None
    run_pos_comparison: bool = True
    min_sample_size: int = 54



@app.post("/analysis/cta")
def api_analyze_cta(req: CTAAnalysisRequest):
    try:
        df, spec = _load_data_and_spec(req.project_path, req.model_id, req.dataset_id, req.spec, req.columns, req.rows)
        res = run_cta_pls(
            df=df,
            spec=spec,
            construct_id=req.construct_id,
            n_boot=req.n_boot,
            seed=req.seed,
            alpha=req.alpha,
        )
        project_io.save_results(
            path=req.project_path,
            algorithm="pls",
            results_dict=res,
            model_id=req.model_id,
            analysis_type="cta",
            dataset_id=req.dataset_id,
            params={"construct_id": req.construct_id, "n_boot": req.n_boot},
        )
        return {"status": "success", "results": res}
    except Exception as e:
        return {"error": str(e)}


@app.post("/analysis/micom")
def api_analyze_micom(req: MICOMAnalysisRequest):
    try:
        df, spec = _load_data_and_spec(req.project_path, req.model_id, req.dataset_id, req.spec, req.columns, req.rows)
        g_vals = tuple(req.group_values) if req.group_values and len(req.group_values) == 2 else None
        res = run_micom(
            df=df,
            spec=spec,
            group_col=req.group_col,
            group_values=g_vals,
            n_permutations=req.n_permutations,
            alpha=req.alpha,
            seed=req.seed,
        )
        project_io.save_results(
            path=req.project_path,
            algorithm="pls",
            results_dict=res,
            model_id=req.model_id,
            analysis_type="micom",
            dataset_id=req.dataset_id,
            params={"group_col": req.group_col, "n_permutations": req.n_permutations},
        )
        return {"status": "success", "results": res}
    except Exception as e:
        return {"error": str(e)}


@app.post("/analysis/mga")
def api_analyze_mga(req: MGAAnalysisRequest):
    try:
        df, spec = _load_data_and_spec(req.project_path, req.model_id, req.dataset_id, req.spec, req.columns, req.rows)
        g_vals = tuple(req.group_values) if req.group_values and len(req.group_values) == 2 else None
        res = analyze_mga(
            df=df,
            spec=spec,
            group_col=req.group_col,
            group_values=g_vals,
            n_boot=req.n_boot,
            n_permutations=req.n_permutations,
            seed=req.seed,
            alpha=req.alpha,
        )
        project_io.save_results(
            path=req.project_path,
            algorithm="pls",
            results_dict=res,
            model_id=req.model_id,
            analysis_type="mga",
            dataset_id=req.dataset_id,
            params={"group_col": req.group_col, "n_boot": req.n_boot, "n_permutations": req.n_permutations},
        )
        return {"status": "success", "results": res}
    except Exception as e:
        return {"error": str(e)}


@app.post("/analysis/fimix")
def api_analyze_fimix(req: FIMIXAnalysisRequest):
    try:
        df, spec = _load_data_and_spec(req.project_path, req.model_id, req.dataset_id, req.spec, req.columns, req.rows)
        res = analyze_fimix(
            df=df,
            spec=spec,
            min_segments=req.min_segments,
            max_segments=req.max_segments,
            seed=req.seed,
        )
        project_io.save_results(
            path=req.project_path,
            algorithm="pls",
            results_dict=res,
            model_id=req.model_id,
            analysis_type="fimix",
            dataset_id=req.dataset_id,
            params={"min_segments": req.min_segments, "max_segments": req.max_segments},
        )
        return {"status": "success", "results": res}
    except Exception as e:
        return {"error": str(e)}


@app.post("/analysis/pos")
def api_analyze_pos(req: POSAnalysisRequest):
    try:
        df, spec = _load_data_and_spec(req.project_path, req.model_id, req.dataset_id, req.spec, req.columns, req.rows)
        res = analyze_pos(
            df=df,
            spec=spec,
            n_segments=req.n_segments,
            max_iter=req.max_iter,
            min_segment_size=req.min_segment_size,
            seed=req.seed,
        )
        project_io.save_results(
            path=req.project_path,
            algorithm="pls",
            results_dict=res,
            model_id=req.model_id,
            analysis_type="pos",
            dataset_id=req.dataset_id,
            params={"n_segments": req.n_segments, "max_iter": req.max_iter},
        )
        return {"status": "success", "results": res}
    except Exception as e:
        return {"error": str(e)}


@app.post("/analysis/otg")
def api_analyze_otg(req: OTGAnalysisRequest):
    try:
        df, spec = _load_data_and_spec(req.project_path, req.model_id, req.dataset_id, req.spec, req.columns, req.rows)
        res = run_otg_analysis(
            df=df,
            spec=spec,
            group_col=req.group_col,
            group_values=req.group_values,
            n_boot=req.n_boot,
            n_permutations=req.n_permutations,
            seed=req.seed,
            alpha=req.alpha,
        )
        project_io.save_results(
            path=req.project_path,
            algorithm="pls",
            results_dict=res,
            model_id=req.model_id,
            analysis_type="otg",
            dataset_id=req.dataset_id,
            params={"group_col": req.group_col, "n_boot": req.n_boot, "n_permutations": req.n_permutations},
        )
        return {"status": "success", "results": res}
    except Exception as e:
        return {"error": str(e)}


@app.post("/analysis/ex-post")
def api_analyze_ex_post(req: ExPostAnalysisRequest):
    try:
        df, spec = _load_data_and_spec(req.project_path, req.model_id, req.dataset_id, req.spec, req.columns, req.rows)
        if req.segment_col not in df.columns:
            return {"error": f"Segment column '{req.segment_col}' not found in dataset."}

        segment_vals = df[req.segment_col]
        results: Dict[str, Any] = {
            "segment_col": req.segment_col,
            "explanatory_cols": req.explanatory_cols,
        }

        # 1. Crosstab & Overlap
        crosstab_col = req.crosstab_cat_col or (req.explanatory_cols[0] if req.explanatory_cols else None)
        if crosstab_col and crosstab_col in df.columns:
            crosstab_res = compute_crosstab_overlap(segment_vals, df[crosstab_col])
            results["crosstab_analysis"] = crosstab_res

        # 2. Logistic Regression
        if req.explanatory_cols:
            valid_expl = [c for c in req.explanatory_cols if c in df.columns]
            if valid_expl:
                logit_res = run_logistic_segment_regression(segment_vals, df[valid_expl])
                results["logistic_regression"] = logit_res

        # 3. Explanatory group comparison with POS
        if req.run_pos_comparison and crosstab_col and crosstab_col in df.columns:
            pos_res = analyze_pos(df=df, spec=spec, n_segments=2)
            pos_comp = compare_explanatory_groups_with_pos(
                df=df,
                spec=spec,
                explanatory_col=crosstab_col,
                pos_results=pos_res,
                min_sample_size=req.min_sample_size,
            )
            results["pos_comparison"] = pos_comp

        project_io.save_results(
            path=req.project_path,
            algorithm="pls",
            results_dict=results,
            model_id=req.model_id,
            analysis_type="ex_post",
            dataset_id=req.dataset_id,
            params={"segment_col": req.segment_col, "explanatory_cols": req.explanatory_cols},
        )
        return {"status": "success", "results": results}
    except Exception as e:
        return {"error": str(e)}



# --- Phase 6: Power, Copula, NCA, PLSpredict, and Reporting Endpoints ---

class PowerCalculationRequest(BaseModel):
    n_samples: Optional[int] = 100
    n_predictors: Optional[int] = 2
    r_squared: Optional[float] = 0.25
    effect_size_f2: Optional[float] = None
    target_power: Optional[float] = 0.80
    alpha: Optional[float] = 0.05
    max_formative_indicators: Optional[int] = 1
    max_paths_into_construct: Optional[int] = 1


class CopulaAnalysisRequest(BaseAnalysisRequest):
    candidate_predictor: str
    target_construct: str
    n_boot: Optional[int] = 200
    seed: Optional[int] = 42
    alpha: Optional[float] = 0.05


class NcaAnalysisRequest(BaseAnalysisRequest):
    predictor: str
    outcome: str
    n_permutations: Optional[int] = 500
    seed: Optional[int] = 42
    alpha: Optional[float] = 0.05


class PlsPredictRequest(BaseAnalysisRequest):
    k_folds: Optional[int] = 10
    repetitions: Optional[int] = 10
    seed: Optional[int] = 42
    antecedents: Optional[str] = "direct"


class PdfReportRequest(BaseModel):
    project_path: str
    model_id: Optional[str] = None
    dataset_id: Optional[str] = None
    project_name: Optional[str] = "PLS-SEM Project"
    dataset_name: Optional[str] = "Analysis Dataset"
    model_name: Optional[str] = "Path Model"
    author: Optional[str] = "Antigravity PLS-SEM Engine"


@app.post("/power/calculate")
def api_calculate_power(req: PowerCalculationRequest):
    try:
        ten_times = calculate_ten_times_rule(
            max_formative_indicators=req.max_formative_indicators or 1,
            max_paths_into_construct=req.max_paths_into_construct or 1,
        )
        achieved_power = compute_statistical_power(
            n_samples=req.n_samples or 100,
            n_predictors=req.n_predictors or 2,
            r_squared=req.r_squared,
            effect_size_f2=req.effect_size_f2,
            alpha=req.alpha or 0.05,
        )
        min_n_required = solve_minimum_sample_size(
            n_predictors=req.n_predictors or 2,
            r_squared=req.r_squared,
            effect_size_f2=req.effect_size_f2,
            target_power=req.target_power or 0.80,
            alpha=req.alpha or 0.05,
        )
        return {
            "status": "success",
            "achieved_power": round(achieved_power, 4),
            "adequate_power": achieved_power >= (req.target_power or 0.80),
            "minimum_sample_size_required": min_n_required,
            "ten_times_rule": ten_times,
            "parameters": {
                "n_samples": req.n_samples,
                "n_predictors": req.n_predictors,
                "r_squared": req.r_squared,
                "target_power": req.target_power,
                "alpha": req.alpha,
            },
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/power/table")
def api_get_power_table(target_power: float = 0.80, alpha: float = 0.05):
    try:
        tbl = get_cohen_appendix_c_table(target_power=target_power, alpha=alpha)
        return {"status": "success", "results": tbl}
    except Exception as e:
        return {"error": str(e)}


@app.post("/analysis/copula")
def api_analyze_copula(req: CopulaAnalysisRequest):
    try:
        df, spec = _load_data_and_spec(req.project_path, req.model_id, req.dataset_id, req.spec, req.columns, req.rows)
        res = analyze_gaussian_copula(
            df=df,
            spec=spec,
            candidate_predictor=req.candidate_predictor,
            target_construct=req.target_construct,
            n_boot=req.n_boot or 200,
            seed=req.seed,
            alpha=req.alpha or 0.05,
        )
        project_io.save_results(
            path=req.project_path,
            algorithm="pls",
            results_dict=res,
            model_id=req.model_id,
            analysis_type="copula",
            dataset_id=req.dataset_id,
            params={"candidate": req.candidate_predictor, "target": req.target_construct},
        )
        return {"status": "success", "results": res}
    except Exception as e:
        return {"error": str(e)}


@app.post("/analysis/nca")
def api_analyze_nca(req: NcaAnalysisRequest):
    try:
        df, spec = _load_data_and_spec(req.project_path, req.model_id, req.dataset_id, req.spec, req.columns, req.rows)
        res = analyze_nca(
            df=df,
            spec=spec,
            predictor=req.predictor,
            outcome=req.outcome,
            n_permutations=req.n_permutations or 500,
            seed=req.seed,
            alpha=req.alpha or 0.05,
        )
        project_io.save_results(
            path=req.project_path,
            algorithm="pls",
            results_dict=res,
            model_id=req.model_id,
            analysis_type="nca",
            dataset_id=req.dataset_id,
            params={"predictor": req.predictor, "outcome": req.outcome},
        )
        return {"status": "success", "results": res}
    except Exception as e:
        return {"error": str(e)}


@app.post("/analysis/predict")
def api_analyze_predict(req: PlsPredictRequest):
    try:
        df, spec = _load_data_and_spec(req.project_path, req.model_id, req.dataset_id, req.spec, req.columns, req.rows)
        res = run_pls_predict(
            df=df,
            model_spec=spec,
            k_folds=req.k_folds or 10,
            repetitions=req.repetitions or 10,
            seed=req.seed,
            antecedents=req.antecedents or "direct",
        )
        project_io.save_results(
            path=req.project_path,
            algorithm="pls",
            results_dict=res,
            model_id=req.model_id,
            analysis_type="predict",
            dataset_id=req.dataset_id,
            params={"k_folds": req.k_folds, "repetitions": req.repetitions},
        )
        return {"status": "success", "results": res}
    except Exception as e:
        return {"error": str(e)}


@app.get("/export/table")
def api_export_table(
    project_path: str,
    table_name: str,
    format: str = "csv",
    decimals: int = 3,
    model_id: Optional[str] = None,
):
    try:
        if not os.path.exists(project_path):
            return {"error": f"Project file '{project_path}' does not exist"}

        res_data = project_io.load_results(project_path, algorithm="pls", model_id=model_id)
        if not res_data or not res_data.get("results"):
            return {"error": "No PLS results found in project. Please run analysis first."}

        results = res_data["results"]
        extractor = TABLE_EXTRACTORS.get(table_name)
        if not extractor:
            return {
                "error": f"Table '{table_name}' not found. Available tables: {list(TABLE_EXTRACTORS.keys())}"
            }

        table_dict = extractor(results, decimals=decimals)
        content_bytes, media_type, filename = export_table_to_format(table_dict, export_format=format)

        return Response(
            content=content_bytes,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        return {"error": str(e)}


@app.post("/export/report-pdf")
def api_export_report_pdf(req: PdfReportRequest):
    try:
        if not os.path.exists(req.project_path):
            return {"error": f"Project file '{req.project_path}' does not exist"}

        res_data = project_io.load_results(req.project_path, algorithm="pls", model_id=req.model_id)
        if not res_data or not res_data.get("results"):
            return {"error": "No PLS results found in project. Please run analysis first."}

        results = res_data["results"]
        pdf_bytes = generate_pdf_report(
            results=results,
            project_name=req.project_name or "PLS-SEM Project",
            dataset_name=req.dataset_name or "Analysis Dataset",
            model_name=req.model_name or "Path Model",
            author=req.author,
        )

        filename = f"{req.model_name.lower().replace(' ', '_')}_report.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        return {"error": str(e)}






