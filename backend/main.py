from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Any
import pandas as pd
import io
from scipy import stats
import numpy as np
import project_io
import os
import workspace_io
import settings_io
from model_spec import ModelSpec, ValidateModelRequest, SaveModelRequest
from model_validator import validate_model_spec, ValidationResult



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


@app.post("/data/import")
async def import_data(
    file: UploadFile = File(...),
    missing_value: Optional[str] = None,
    treatment: Optional[str] = None,
):
    contents = await file.read()
    try:
        mv_list = [v.strip() for v in missing_value.split(",") if v.strip()] if missing_value else None
        df = read_uploaded_file(file.filename, contents, missing_values=mv_list)
        df = apply_missing_treatment(df, treatment)
    except ValueError as e:
        return {"error": str(e)}

    preview_df = df.head(20).astype(object).where(pd.notnull(df.head(20)), None)


    return {
        "columns": list(df.columns),
        "dtypes": df.dtypes.astype(str).to_dict(),
        "row_count": len(df),
        "preview": preview_df.to_dict(orient="records"),
    }

@app.get("/project/diagnostics")
def project_diagnostics(path: str):
    data = project_io.load_data(path)
    if data is None:
        return {"error": "No data found in this project"}

    df = pd.DataFrame(data["rows"], columns=data["columns"])
    numeric_df = df.select_dtypes(include=[np.number])

    stats_report = {}
    for col in numeric_df.columns:
        series = numeric_df[col].dropna()
        skew = stats.skew(series)
        kurt = stats.kurtosis(series)
        stats_report[col] = {
            "mean": float(series.mean()),
            "std": float(series.std()),
            "min": float(series.min()),
            "max": float(series.max()),
            "skewness": float(skew),
            "kurtosis": float(kurt),
            "non_normal_flag": bool(abs(skew) > 2 or abs(kurt) > 7),
        }

    missing_report = {}
    total_rows = len(df)
    for col in df.columns:
        missing_count = int(df[col].isna().sum())
        missing_report[col] = {
            "missing_count": missing_count,
            "missing_pct": round((missing_count / total_rows) * 100, 2),
        }

    return {
        "row_count": total_rows,
        "descriptive_stats": stats_report,
        "missing_report": missing_report,
    }


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


@app.post("/workspace/delete")
def delete_workspace(folder_path: str):
    try:
        res = workspace_io.delete_workspace(folder_path)
        return res
    except Exception as e:
        return {"error": str(e)}


@app.post("/model/validate")
def validate_model(req: ValidateModelRequest):
    dataset_cols = req.dataset_columns
    if dataset_cols is None and req.project_path:
        project_data = project_io.load_data(req.project_path)
        if project_data and "columns" in project_data:
            dataset_cols = project_data["columns"]

    result = validate_model_spec(req.spec, dataset_columns=dataset_cols)
    return result.model_dump()


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
        )
        return {
            "status": "saved",
            "validation": validation.model_dump(),
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/project/load-model")
def load_project_model(path: str):
    if not os.path.exists(path):
        return {"error": "Project file does not exist"}

    model_data = project_io.load_model_spec(path)
    if model_data is None or model_data.get("spec") is None:
        return {"spec": None, "diagram_layout": None, "updated_at": None}

    return model_data


