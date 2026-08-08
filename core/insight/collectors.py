"""Lightweight metric collectors — keep queries tiny (load-sensitive)."""
from __future__ import annotations

from typing import List, Optional, Tuple

from core.connection import connect
from core.insight.store import MetricSample
from core.logging_setup import get_logger

log = get_logger("sqlmonitor.insight.collect")

# Watermark for job failures: (run_date, run_time) last seen — process-local
_job_fail_watermark: Optional[Tuple[int, int]] = None

_BLOCKING_SQL = """
SET NOCOUNT ON;
SELECT
    COUNT_BIG(*) AS blocking_session_count,
    ISNULL(MAX(r.wait_time), 0) AS blocking_wait_ms,
    (
        SELECT COUNT_BIG(DISTINCT r2.blocking_session_id)
        FROM sys.dm_exec_requests r2
        WHERE r2.blocking_session_id <> 0
          AND r2.blocking_session_id <> r2.session_id
          AND NOT EXISTS (
              SELECT 1
              FROM sys.dm_exec_requests rx
              WHERE rx.session_id = r2.blocking_session_id
                AND rx.blocking_session_id <> 0
          )
    ) AS head_blocker_count
FROM sys.dm_exec_requests r
WHERE r.blocking_session_id <> 0
  AND r.blocking_session_id <> r.session_id;
"""

# Only brand-new step failures since watermark (today). Very selective.
_JOB_FAILED_SQL = """
SET NOCOUNT ON;
DECLARE @today INT = CONVERT(INT, CONVERT(VARCHAR(8), GETDATE(), 112));
SELECT TOP (40)
    CONVERT(VARCHAR(36), jh.job_id) AS job_id,
    j.name AS job_name,
    jh.run_date,
    jh.run_time,
    jh.step_id
FROM msdb.dbo.sysjobhistory jh
INNER JOIN msdb.dbo.sysjobs j ON j.job_id = jh.job_id
WHERE jh.run_status = 0
  AND jh.step_id > 0
  AND jh.run_date = @today
  AND (
        jh.run_date > ?
        OR (jh.run_date = ? AND jh.run_time > ?)
      )
ORDER BY jh.run_date, jh.run_time;
"""


def collect_blocking_metrics() -> List[MetricSample]:
    """~10s metrics: aggregate + optional per-edge samples for Insight evidence."""
    import json
    from datetime import datetime, timezone

    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(_BLOCKING_SQL)
        row = cur.fetchone()
        if not row:
            cnt = wait_ms = heads = 0
        else:
            cnt = int(row[0] or 0)
            wait_ms = int(row[1] or 0)
            heads = int(row[2] or 0)
    finally:
        conn.close()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    samples = [
        MetricSample("server", "_", "blocking_session_count", float(cnt), ts=now),
        MetricSample("server", "_", "blocking_wait_ms", float(wait_ms), ts=now),
        MetricSample("server", "_", "head_blocker_count", float(heads), ts=now),
    ]

    # Persist edges + SQL snippets so Insights keep cause after Live clears
    if cnt > 0:
        for r in capture_blocking_snapshot(top=8):
            blocker = r.get("blocker_session_id")
            blocked = r.get("blocked_session_id")
            blocker_sql = (r.get("blocker_sql") or "").strip()
            blocked_sql = (r.get("blocked_sql") or "").strip()
            # Metadata edge — prioritize SQL inside 400-char dims
            dims = {
                "b": blocker,
                "h": int(r.get("is_head_blocker") or 0),
                "w": (r.get("wait_type") or "")[:20],
                "db": (r.get("database_name") or "")[:20],
                "bl": (r.get("blocked_login") or "")[:20],
                "hl": (r.get("blocker_login") or "")[:20],
                "bs": blocked_sql[:140],
                "hs": blocker_sql[:140],
                "r": (r.get("wait_resource") or "")[:36],
            }
            try:
                dims_json = json.dumps(dims, ensure_ascii=False, separators=(",", ":"))
                while len(dims_json) > 400 and (dims.get("bs") or dims.get("hs")):
                    dims["bs"] = (dims.get("bs") or "")[:-15]
                    dims["hs"] = (dims.get("hs") or "")[:-15]
                    dims_json = json.dumps(dims, ensure_ascii=False, separators=(",", ":"))
                if len(dims_json) > 400:
                    dims_json = None
            except Exception:
                dims_json = None
            samples.append(MetricSample(
                scope="session",
                scope_id=str(blocked),
                metric_name="blocking_edge",
                value=float(r.get("wait_ms") or 0),
                dims_json=dims_json,
                scope_label=f"{blocker}→{blocked}"[:200],
                ts=now,
            ))
            # Fuller SQL in scope_label (200 chars) — separate from dims
            if blocker_sql:
                samples.append(MetricSample(
                    scope="session",
                    scope_id=f"{blocker}:{blocked}:h",
                    metric_name="blocking_sql",
                    value=float(r.get("wait_ms") or 0),
                    dims_json='{"role":"blocker"}',
                    scope_label=blocker_sql[:200],
                    ts=now,
                ))
            if blocked_sql:
                samples.append(MetricSample(
                    scope="session",
                    scope_id=f"{blocker}:{blocked}:b",
                    metric_name="blocking_sql",
                    value=float(r.get("wait_ms") or 0),
                    dims_json='{"role":"blocked"}',
                    scope_label=blocked_sql[:200],
                    ts=now,
                ))

    return samples


# Compact chain for Insight evidence (not Live). Truncated SQL — no full text in Metric Store.
_BLOCKING_SNAPSHOT_SQL = """
SET NOCOUNT ON;
SELECT TOP ({top})
    r.session_id AS blocked_session_id,
    r.blocking_session_id AS blocker_session_id,
    CASE
        WHEN NOT EXISTS (
            SELECT 1 FROM sys.dm_exec_requests rx
            WHERE rx.session_id = r.blocking_session_id
              AND rx.blocking_session_id <> 0
        ) THEN 1 ELSE 0
    END AS is_head_blocker,
    r.wait_type,
    LEFT(ISNULL(r.wait_resource, N''), 120) AS wait_resource,
    r.wait_time AS wait_ms,
    CAST(r.blocking_session_id AS VARCHAR(20)) + N' → ' + CAST(r.session_id AS VARCHAR(20)) AS chain_display,
    DB_NAME(r.database_id) AS database_name,
    s_blocked.login_name AS blocked_login,
    s_blocked.host_name AS blocked_host,
    LEFT(ISNULL(s_blocked.program_name, N''), 80) AS blocked_program,
    ISNULL(r.command, N'Sleeping') AS blocked_command,
    LEFT(CONVERT(nvarchar(max), st_blocked.text), 400) AS blocked_sql,
    s_blocker.login_name AS blocker_login,
    s_blocker.host_name AS blocker_host,
    LEFT(ISNULL(s_blocker.program_name, N''), 80) AS blocker_program,
    ISNULL(r_blocker.command, N'Sleeping / open tran') AS blocker_command,
    LEFT(CONVERT(nvarchar(max), st_blocker.text), 400) AS blocker_sql
FROM sys.dm_exec_requests r
LEFT JOIN sys.dm_exec_sessions s_blocked ON r.session_id = s_blocked.session_id
OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) st_blocked
LEFT JOIN sys.dm_exec_sessions s_blocker ON r.blocking_session_id = s_blocker.session_id
LEFT JOIN sys.dm_exec_requests r_blocker ON r.blocking_session_id = r_blocker.session_id
LEFT JOIN sys.dm_exec_connections c_blocker ON r.blocking_session_id = c_blocker.session_id
OUTER APPLY sys.dm_exec_sql_text(ISNULL(r_blocker.sql_handle, c_blocker.most_recent_sql_handle)) st_blocker
WHERE r.blocking_session_id <> 0
  AND r.blocking_session_id <> r.session_id
ORDER BY r.wait_time DESC, r.session_id;
"""


def capture_blocking_snapshot(*, top: int = 8) -> List[dict]:
    """Session-level blocking evidence for Today's Insights (not Live Monitor)."""
    import pyodbc

    top = max(1, min(int(top), 20))
    try:
        conn = connect()
    except Exception as ex:
        log.warning("capture_blocking_snapshot: connect failed (%s)", ex)
        return []
    try:
        cur = conn.cursor()
        cur.execute(_BLOCKING_SNAPSHOT_SQL.format(top=top))
        cols = [c[0] for c in cur.description]
        out = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            for k, v in list(d.items()):
                if v is None:
                    d[k] = None
                elif isinstance(v, (bytes, bytearray)):
                    d[k] = None
                else:
                    d[k] = v if isinstance(v, (int, float)) else str(v)
            out.append(d)
        return out
    except pyodbc.Error as ex:
        # Transient TCP drops (08S01 / 10053) are common under load — don't spam traceback
        code = ""
        try:
            code = str(ex.args[0]) if ex.args else ""
        except Exception:
            pass
        if code == "08S01" or "10053" in str(ex) or "Communication link" in str(ex):
            log.warning("capture_blocking_snapshot: connection dropped (%s)", code or ex)
        else:
            log.exception("capture_blocking_snapshot failed")
        return []
    except Exception:
        log.exception("capture_blocking_snapshot failed")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def collect_job_failed_metrics() -> List[MetricSample]:
    """~60s metric: only new msdb step failures since last watermark."""
    global _job_fail_watermark

    # First poll: seed watermark to "now" so we do not backfill today's history
    if _job_fail_watermark is None:
        from datetime import datetime
        now = datetime.now()
        _job_fail_watermark = (
            int(now.strftime("%Y%m%d")),
            now.hour * 10000 + now.minute * 100 + now.second,
        )
        return []

    wd, wt = _job_fail_watermark

    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(_JOB_FAILED_SQL, wd, wd, wt)
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    samples: List[MetricSample] = []
    max_d, max_t = wd, wt
    for r in rows:
        job_id = str(r[0])
        name = r[1] or job_id
        run_date = int(r[2] or 0)
        run_time = int(r[3] or 0)
        step_id = int(r[4] or 0)
        samples.append(MetricSample(
            scope="job",
            scope_id=job_id,
            metric_name="job_failed",
            value=1.0,
            dims_json=f'{{"step":"{step_id}"}}',
            scope_label=str(name)[:200],
        ))
        if run_date > max_d or (run_date == max_d and run_time > max_t):
            max_d, max_t = run_date, run_time

    _job_fail_watermark = (max_d, max_t)
    return samples
