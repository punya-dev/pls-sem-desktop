from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Any, Dict, Set
import pandas as pd
import io
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
    dataset_cols = req.dataset_columns or req.columns
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
        saved_model = project_io.load_model_spec(req.project_path)
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

        # 5. Persist results in project file
        project_io.save_results(req.project_path, "pls", res)

        return {
            "status": "success",
            "algorithm": "pls",
            "results": res,
        }
    except Exception as e:
        return {"error": f"PLS-SEM calculation failed: {str(e)}"}


@app.get("/project/load-results")
def load_project_results(path: str, algorithm: str = "pls"):
    if not os.path.exists(path):
        return {"error": "Project file does not exist"}
    data = project_io.load_results(path, algorithm=algorithm)
    if data is None:
        return {"results": None}
    return data


# --- Phase 4: Bootstrapping & Live WebSocket Progress ---

active_bootstrap_jobs: Dict[str, Dict[str, Any]] = {}


def _broadcast_ws(job: dict, msg: dict):
    loop = job.get("loop")
    if not loop or loop.is_closed():
        return
    for ws in list(job.get("websockets", [])):
        try:
            asyncio.run_coroutine_threadsafe(ws.send_json(msg), loop)
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

            # Save full results with significance to project
            project_io.save_results(req.project_path, "pls", base_res)

            job["status"] = "completed"
            job["results"] = base_res
            job["elapsed_sec"] = round(time.time() - job["start_time"], 1)
            msg = {
                "type": "completed",
                "job_id": job_id,
                "results": base_res,
                "elapsed_sec": job["elapsed_sec"],
            }
            _broadcast_ws(job, msg)
        except InterruptedError:
            job["status"] = "cancelled"
            job["elapsed_sec"] = round(time.time() - job["start_time"], 1)
            msg = {"type": "cancelled", "job_id": job_id, "elapsed_sec": job["elapsed_sec"]}
            _broadcast_ws(job, msg)
        except Exception as exc:
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

    # Immediately send current state upon connection
    initial_type = "progress" if job["status"] == "running" else job["status"]
    await websocket.send_json({
        "type": initial_type,
        "job_id": job_id,
        "current": job["current"],
        "total": job["total"],
        "percent": job["percent"],
        "elapsed_sec": round(time.time() - job["start_time"], 1),
        "results": job.get("results"),
        "error": job.get("error"),
    })

    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict) and data.get("action") == "cancel":
                job["cancel_event"].set()
                job["status"] = "cancelled"
                _broadcast_ws(job, {"type": "cancelled", "job_id": job_id})
    except (WebSocketDisconnect, Exception):
        job["websockets"].discard(websocket)



