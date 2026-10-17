"""
Generic Background Job & WebSocket Progress Manager for Long-Running Tasks.
Supports cooperative cancellation, thread/process execution, live progress broadcasting,
and job status queries.
"""

import asyncio
import json
import os
import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional, Set, List
import numpy as np
from fastapi import WebSocket, WebSocketDisconnect


class Job:
    def __init__(self, job_id: str, job_type: str, params: Optional[Dict[str, Any]] = None):
        self.job_id = job_id
        self.job_type = job_type
        self.params = params or {}
        self.status = "pending"  # pending, running, completed, cancelled, failed
        self.current = 0
        self.total = 100
        self.percent = 0.0
        self.start_time = time.time()
        self.elapsed_sec = 0.0
        self.results: Optional[Any] = None
        self.error: Optional[str] = None
        self.cancel_event = threading.Event()
        self.websockets: Set[WebSocket] = set()
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def update_progress(self, current: int, total: int):
        self.current = current
        self.total = total
        self.percent = round((current / total) * 100, 1) if total > 0 else 0.0
        self.elapsed_sec = round(time.time() - self.start_time, 1)
        msg = {
            "type": "progress",
            "job_id": self.job_id,
            "job_type": self.job_type,
            "current": self.current,
            "total": self.total,
            "percent": self.percent,
            "elapsed_sec": self.elapsed_sec,
        }
        self.broadcast(msg)

    def complete(self, results: Any):
        self.status = "completed"
        self.results = results
        self.elapsed_sec = round(time.time() - self.start_time, 1)
        msg = {
            "type": "completed",
            "job_id": self.job_id,
            "job_type": self.job_type,
            "results": self.results,
            "elapsed_sec": self.elapsed_sec,
        }
        self.broadcast(msg)

    def fail(self, error: str):
        self.status = "failed"
        self.error = error
        self.elapsed_sec = round(time.time() - self.start_time, 1)
        msg = {
            "type": "failed",
            "job_id": self.job_id,
            "job_type": self.job_type,
            "error": self.error,
            "elapsed_sec": self.elapsed_sec,
        }
        self.broadcast(msg)

    def cancel(self):
        self.cancel_event.set()
        self.status = "cancelled"
        self.elapsed_sec = round(time.time() - self.start_time, 1)
        msg = {
            "type": "cancelled",
            "job_id": self.job_id,
            "job_type": self.job_type,
            "elapsed_sec": self.elapsed_sec,
        }
        self.broadcast(msg)

    def broadcast(self, msg: Dict[str, Any]):
        if not self.loop or self.loop.is_closed():
            return

        def _json_default(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, (np.floating, float)):
                return float(obj)
            if isinstance(obj, (np.integer, int)):
                return int(obj)
            if isinstance(obj, (np.bool_, bool)):
                return bool(obj)
            return str(obj)

        try:
            payload = json.dumps(msg, default=_json_default)
        except Exception:
            return

        for ws in list(self.websockets):
            try:
                asyncio.run_coroutine_threadsafe(ws.send_text(payload), self.loop)
            except Exception:
                pass

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status,
            "current": self.current,
            "total": self.total,
            "percent": self.percent,
            "elapsed_sec": self.elapsed_sec,
            "results": self.results,
            "error": self.error,
        }


class JobManager:
    def __init__(self):
        self.jobs: Dict[str, Job] = {}

    def create_job(self, job_type: str, params: Optional[Dict[str, Any]] = None, loop: Optional[asyncio.AbstractEventLoop] = None) -> Job:
        job_id = uuid.uuid4().hex
        job = Job(job_id=job_id, job_type=job_type, params=params)
        job.loop = loop
        self.jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job:
            return False
        job.cancel()
        return True

    def list_jobs(self) -> List[Dict[str, Any]]:
        return [job.to_dict() for job in self.jobs.values()]

    def cancel(self, job_id: str) -> bool:
        return self.cancel_job(job_id)

    def submit(
        self,
        job_type: str,
        worker_fn: Callable[[Job], Any],
        params: Optional[Dict[str, Any]] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> Job:
        job = self.create_job(job_type=job_type, params=params, loop=loop)

        def _runner():
            job.status = "running"
            try:
                res = worker_fn(job)
                if not job.cancel_event.is_set():
                    job.complete(res)
            except InterruptedError:
                job.cancel()
            except Exception as e:
                job.fail(str(e))

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        return job


# Global singleton instance
job_manager = JobManager()
default_job_manager = job_manager
