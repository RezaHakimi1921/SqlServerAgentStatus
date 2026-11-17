"""Background table intelligence loads so Dash UI stays responsive."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from core.logging_setup import get_logger
from core.providers.factory import get_provider
from modules.indexes.service import build_table_intelligence

log = get_logger("sqlmonitor.indexes.table_jobs")

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}


def start_table_intelligence(database: str, schema: str, table: str) -> str:
    job_id = uuid.uuid4().hex
    with _LOCK:
        _JOBS[job_id] = {
            "status": "running",
            "started_at": time.time(),
            "error": None,
            "payload": None,
            "sel": {"database": database, "schema": schema, "table": table},
        }

    def _run():
        try:
            raw = get_provider().get_table_index_snapshot(database, schema, table)
            payload = build_table_intelligence(raw)
            with _LOCK:
                _JOBS[job_id] = {
                    "status": "done",
                    "started_at": _JOBS.get(job_id, {}).get("started_at"),
                    "finished_at": time.time(),
                    "error": None,
                    "payload": payload,
                    "sel": {"database": database, "schema": schema, "table": table},
                }
        except Exception as ex:
            log.exception("background table intelligence failed")
            with _LOCK:
                _JOBS[job_id] = {
                    "status": "error",
                    "started_at": _JOBS.get(job_id, {}).get("started_at"),
                    "finished_at": time.time(),
                    "error": str(ex),
                    "payload": None,
                    "sel": {"database": database, "schema": schema, "table": table},
                }

    threading.Thread(target=_run, name=f"table-intel-{job_id[:8]}", daemon=True).start()
    return job_id


def get_table_job(job_id: str | None) -> dict[str, Any] | None:
    if not job_id:
        return None
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None
