from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import io
from scipy import stats
import numpy as np
import project_io
import os


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "tauri://localhost"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def read_uploaded_file(filename: str, contents: bytes) -> pd.DataFrame:
    if filename.endswith(".csv"):
        return pd.read_csv(io.BytesIO(contents), sep=None, engine='python')
    elif filename.endswith((".xls", ".xlsx")):
        return pd.read_excel(io.BytesIO(contents))
    else:
        raise ValueError("Unsupported file type")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"message": "PLS-SEM backend running"}


@app.post("/data/import")
async def import_data(file: UploadFile = File(...)):
    contents = await file.read()
    try:
        df = read_uploaded_file(file.filename, contents)
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
def project_treat_missing(path: str, method: str = "listwise"):
    data = project_io.load_data(path)
    if data is None:
        return {"error": "No data found in this project"}

    df = pd.DataFrame(data["rows"], columns=data["columns"])
    original_rows = len(df)

    if method == "listwise":
        cleaned_df = df.dropna()
    elif method == "mean":
        cleaned_df = df.copy()
        numeric_cols = cleaned_df.select_dtypes(include=[np.number]).columns
        cleaned_df[numeric_cols] = cleaned_df[numeric_cols].fillna(cleaned_df[numeric_cols].mean())
    else:
        return {"error": f"Unknown method: {method}"}

    cleaned_clean = cleaned_df.astype(object).where(pd.notnull(cleaned_df), None)
    project_io.save_data(path, cleaned_clean.values.tolist(), list(cleaned_df.columns),list(cleaned_df.dtypes.astype(str)))

    return {
        "status": "updated",
        "method": method,
        "original_row_count": original_rows,
        "cleaned_row_count": len(cleaned_df),
        "rows_dropped": original_rows - len(cleaned_df),
    }


@app.post("/project/create")
def create_project(path: str, name: str):
    try:
        project_io.create_project(path, name)
        project_io.add_recent_project(path)
        return {"status": "created", "path": path}
    except FileExistsError:
        return {"error": "A project already exists at this path"}


@app.post("/project/open")
def open_project(path: str):
    if not os.path.exists(path):
        return {"error": "Project file does not exist"}
    project_io.add_recent_project(path)
    return {"status": "opened", "path": path}


@app.post("/project/save-data")
async def save_project_data(path: str, file: UploadFile = File(...)):
    contents = await file.read()
    df = read_uploaded_file(file.filename, contents)
    df_clean = df.astype(object).where(pd.notnull(df), None)

    project_io.save_data(path, df_clean.values.tolist(), list(df.columns),list(df.dtypes.astype(str)))
    return {"status": "saved", "row_count": len(df)}


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
