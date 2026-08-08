"""Background catalog refresh so Dash UI stays responsive."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from core.logging_setup import get_logger
from core.providers.sqlserver_provider import get_provider

log = get_logger("sqlmonitor.indexes.catalog_jobs")

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}


def start_catalog_refresh(
    database: str | None,
    *,
    tables: bool,
    index_defs: bool,
    index_stats: bool,
) -> str:
    job_id = uuid.uuid4().hex
    with _LOCK:
        _JOBS[job_id] = {
            "status": "running",
            "started_at": time.time(),
            "error": None,
            "result": None,
        }

    def _run():
        try:
            result = get_provider().refresh_index_catalog(
                database,
                tables=tables,
                index_defs=index_defs,
                index_stats=index_stats,
            )
            with _LOCK:
                _JOBS[job_id] = {
                    "status": "done" if result.get("ok") else "error",
                    "started_at": _JOBS.get(job_id, {}).get("started_at"),
                    "finished_at": time.time(),
                    "error": None if result.get("ok") else (result.get("error") or "Catalog refresh failed"),
                    "result": result,
                }
        except Exception as ex:
            log.exception("background catalog refresh failed")
            with _LOCK:
                _JOBS[job_id] = {
                    "status": "error",
                    "started_at": _JOBS.get(job_id, {}).get("started_at"),
                    "finished_at": time.time(),
                    "error": str(ex),
                    "result": None,
                }

    threading.Thread(target=_run, name=f"catalog-refresh-{job_id[:8]}", daemon=True).start()
    return job_id


def get_catalog_job(job_id: str | None) -> dict[str, Any] | None:
    if not job_id:
        return None
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None
