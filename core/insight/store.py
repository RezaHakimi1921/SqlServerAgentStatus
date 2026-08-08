"""Write metric samples into SmartMonitorDB (insight.metric_samples)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Sequence

import pyodbc

from config import build_conn_str, load_config
from core.logging_setup import get_logger

log = get_logger("sqlmonitor.insight.store")

_INSERT_SQL = """
INSERT INTO insight.metric_samples
    (ts, scope, scope_id, metric_name, value, dims_json, scope_label)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""


@dataclass
class MetricSample:
    scope: str
    scope_id: str
    metric_name: str
    value: float
    dims_json: Optional[str] = None
    scope_label: Optional[str] = None
    ts: Optional[datetime] = None


def monitor_database_name() -> str:
    cfg = load_config()
    return (cfg.get("monitor_database") or "SmartMonitorDB").strip() or "SmartMonitorDB"


def get_monitor_connection(*, timeout: int | None = None):
    """Same server/login as Live Monitor; database = MONITOR_DATABASE / SmartMonitorDB."""
    cfg = dict(load_config())
    cfg["database"] = monitor_database_name()
    if timeout is None:
        timeout = min(int(cfg.get("timeout") or 10), 8)
    else:
        timeout = int(timeout)
    cfg["timeout"] = timeout
    return pyodbc.connect(build_conn_str(cfg), timeout=timeout)


def insert_samples(samples: Sequence[MetricSample]) -> int:
    if not samples:
        return 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = []
    for s in samples:
        rows.append((
            s.ts or now,
            s.scope,
            s.scope_id,
            s.metric_name,
            float(s.value),
            s.dims_json,
            s.scope_label,
        ))
    conn = get_monitor_connection()
    try:
        cur = conn.cursor()
        cur.fast_executemany = True
        cur.executemany(_INSERT_SQL, rows)
        conn.commit()
        return len(rows)
    finally:
        conn.close()
