"""Persist per-metric capture intervals in SmartMonitorDB."""
from __future__ import annotations

from typing import Dict, List, Optional

from core.insight.registry import DEFAULT_METRICS, MetricSpec
from core.insight.store import get_monitor_connection
from core.logging_setup import get_logger

log = get_logger("sqlmonitor.insight.schedule")

_ENSURE_SQL = """
IF OBJECT_ID(N'insight.metric_schedule', N'U') IS NULL
BEGIN
    CREATE TABLE insight.metric_schedule
    (
        metric_name   VARCHAR(64) NOT NULL
            CONSTRAINT PK_insight_metric_schedule PRIMARY KEY,
        interval_sec  INT NOT NULL,
        enabled       BIT NOT NULL
            CONSTRAINT DF_insight_metric_schedule_en DEFAULT (1),
        updated_at    DATETIME2(0) NOT NULL
            CONSTRAINT DF_insight_metric_schedule_ts DEFAULT (SYSUTCDATETIME())
    );
END
"""

_UPSERT_SQL = """
MERGE insight.metric_schedule AS t
USING (SELECT ? AS metric_name) AS s
ON t.metric_name = s.metric_name
WHEN MATCHED THEN UPDATE SET
    interval_sec = ?,
    enabled = ?,
    updated_at = SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT (metric_name, interval_sec, enabled)
VALUES (?, ?, ?);
"""

# In-process cache so scheduler does not hit DB every 10s
_cache: Optional[Dict[str, dict]] = None


def ensure_schedule_table() -> None:
    """Create table if missing. May fail without DDL rights — caller handles."""
    conn = get_monitor_connection()
    try:
        cur = conn.cursor()
        cur.execute(_ENSURE_SQL)
        cur.execute("SELECT COUNT(*) FROM insight.metric_schedule")
        n = int(cur.fetchone()[0] or 0)
        if n == 0:
            for m in DEFAULT_METRICS:
                cur.execute(
                    "INSERT INTO insight.metric_schedule (metric_name, interval_sec, enabled) VALUES (?, ?, ?)",
                    m.name,
                    int(m.interval_sec),
                    1 if m.enabled else 0,
                )
        conn.commit()
    finally:
        conn.close()


def table_exists() -> bool:
    try:
        conn = get_monitor_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM sys.tables t "
                "INNER JOIN sys.schemas s ON s.schema_id = t.schema_id "
                "WHERE s.name = 'insight' AND t.name = 'metric_schedule'"
            )
            return cur.fetchone() is not None
        finally:
            conn.close()
    except Exception:
        return False


def invalidate_schedule_cache() -> None:
    global _cache
    _cache = None


def load_schedule(use_cache: bool = True) -> Dict[str, dict]:
    """Return {metric_name: {interval_sec, enabled}} merged with defaults."""
    global _cache
    if use_cache and _cache is not None:
        return dict(_cache)

    result = {
        m.name: {
            "interval_sec": m.interval_sec,
            "enabled": m.enabled,
            "description": m.description,
            "scope": m.scope,
        }
        for m in DEFAULT_METRICS
    }
    try:
        if not table_exists():
            try:
                ensure_schedule_table()
            except Exception:
                log.warning(
                    "insight.metric_schedule missing and CREATE denied — "
                    "run phase2/queries/insight-metric-schedule.sql as dbo, then GRANT"
                )
                _cache = dict(result)
                return result

        conn = get_monitor_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM insight.metric_schedule")
            if int(cur.fetchone()[0] or 0) == 0:
                for m in DEFAULT_METRICS:
                    cur.execute(
                        "INSERT INTO insight.metric_schedule (metric_name, interval_sec, enabled) VALUES (?, ?, ?)",
                        m.name,
                        int(m.interval_sec),
                        1 if m.enabled else 0,
                    )
                conn.commit()

            cur.execute(
                "SELECT metric_name, interval_sec, enabled FROM insight.metric_schedule"
            )
            for name, interval, enabled in cur.fetchall():
                key = str(name)
                if key not in result:
                    result[key] = {
                        "interval_sec": int(interval),
                        "enabled": bool(enabled),
                        "description": "",
                        "scope": "server",
                    }
                else:
                    result[key]["interval_sec"] = max(10, int(interval or 10))
                    result[key]["enabled"] = bool(enabled)
        finally:
            conn.close()
    except Exception:
        log.exception("load_schedule failed — using defaults")

    _cache = dict(result)
    return result


def save_schedule(updates: Dict[str, dict]) -> int:
    """updates: {metric_name: {interval_sec, enabled}}"""
    if not table_exists():
        try:
            ensure_schedule_table()
        except Exception as e:
            raise RuntimeError(
                "جدول insight.metric_schedule وجود ندارد. "
                "اسکریپت phase2/queries/insight-metric-schedule.sql را با کاربر dbo اجرا کنید."
            ) from e

    conn = get_monitor_connection()
    try:
        cur = conn.cursor()
        n = 0
        for name, cfg in updates.items():
            interval = max(10, int(cfg.get("interval_sec") or 10))
            enabled = 1 if cfg.get("enabled", True) else 0
            cur.execute(
                _UPSERT_SQL,
                name,
                interval,
                enabled,
                name,
                interval,
                enabled,
            )
            n += 1
        conn.commit()
        invalidate_schedule_cache()
        return n
    finally:
        conn.close()


def reset_schedule_to_defaults() -> int:
    updates = {
        m.name: {"interval_sec": m.interval_sec, "enabled": m.enabled}
        for m in DEFAULT_METRICS
    }
    return save_schedule(updates)


def schedule_as_specs() -> List[MetricSpec]:
    sched = load_schedule()
    out: List[MetricSpec] = []
    for m in DEFAULT_METRICS:
        row = sched.get(m.name) or {}
        if not row.get("enabled", True):
            continue
        out.append(MetricSpec(
            name=m.name,
            interval_sec=max(10, int(row.get("interval_sec") or m.interval_sec)),
            scope=m.scope,
            description=m.description,
            enabled=True,
        ))
    return out
