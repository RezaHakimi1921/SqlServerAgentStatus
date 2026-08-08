"""SQL Server DMV provider. No stored procedures."""
from __future__ import annotations

import time
from typing import Any, Dict, List

from core.connection import connect
from core.contracts import QueryResult
from core.logging_setup import get_logger
from core.permissions import (
    INDEX_PERMISSIONS_HINT,
    VIEW_SERVER_STATE_HINT,
    has_view_server_state,
    is_permission_error,
    permission_hint_for,
)
from core import severity as sev
from config import load_config
from modules.indexes.constants import (
    INDEX_CAP_MISSING,
    INDEX_CATALOG_REFRESH_PROC,
    INDEX_CATALOG_REFRESH_TIMEOUT_SEC,
    INDEX_CATALOG_SCHEMA,
    INDEX_DB_ALL,
    INDEX_FRAG_QUERY_TIMEOUT_SEC,
    INDEX_INVENTORY_MAX_MS,
    INDEX_INVENTORY_MAX_ROWS,
    INDEX_OVERVIEW_DB_TIMEOUT_SEC,
    INDEX_OVERVIEW_FINDING_ROWS,
    INDEX_OVERVIEW_MAX_DATABASES,
    INDEX_OVERVIEW_QUICK_MAX_DATABASES,
    INDEX_PREFERRED_DATABASE,
    INDEX_SNAPSHOT_QUERY_TIMEOUT_SEC,
    INDEX_TABLE_CACHE_CAP,
    INDEX_TABLE_LIST_CAP,
    INDEX_TABLE_SEARCH_CAP,
    INDEX_WRITE_HEAVY_MIN_DIFF,
    INDEX_WRITE_HEAVY_MIN_RATIO,
    INDEX_WRITE_HEAVY_MIN_WRITES,
)
from modules.tables.constants import (
    TABLES_DELTA_WINDOWS_DAYS,
    TABLES_LIVE_DB_CAP,
    TABLES_LIVE_DB_TIMEOUT_SEC,
    TABLES_QUERY_TIMEOUT_SEC,
)

log = get_logger("sqlmonitor.provider")

# Background / idle system waits — never useful in Running Now (sp_WhoIsActive-style).
_BENIGN_WAIT_SQL = """
N'SP_SERVER_DIAGNOSTICS_SLEEP',
N'XE_TIMER_EVENT',
N'XE_DISPATCHER_WAIT',
N'XE_DISPATCHER_JOIN',
N'LAZYWRITER_SLEEP',
N'LOGMGR_QUEUE',
N'CHECKPOINT_QUEUE',
N'CHKPT',
N'DIRTY_PAGE_POLL',
N'SLEEP_TASK',
N'SLEEP_SYSTEMTASK',
N'SLEEP_BPOOL_FLUSH',
N'SOS_WORK_DISPATCHER',
N'BROKER_EVENTHANDLER',
N'BROKER_RECEIVE_WAITFOR',
N'BROKER_TASK_STOP',
N'BROKER_TO_FLUSH',
N'BROKER_TRANSMITTER',
N'QDS_PERSIST_TASK_MAIN_LOOP_SLEEP',
N'QDS_ASYNC_QUEUE',
N'QDS_CLEANUP_STALE_QUERIES_TASK_MAIN_LOOP_SLEEP',
N'FT_IFTS_SCHEDULER_IDLE_WAIT',
N'HADR_FILESTREAM_IOMGR_IOCOMPLETION',
N'HADR_LOGCAPTURE_WAIT',
N'HADR_TIMER_TASK',
N'HADR_WORK_QUEUE',
N'REQUEST_FOR_DEADLOCK_SEARCH',
N'SQLTRACE_INCREMENTAL_FLUSH_SLEEP',
N'WAITFOR_TASKSHUTDOWN',
N'WAIT_XTP_OFFLINE_CKPT_NEW_LOG',
N'WAIT_XTP_HOST_WAIT'
"""

_RUNNING_SQL = """
SET NOCOUNT ON;
SELECT TOP ({top})
    s.session_id,
    COALESCE(r.status, s.status) AS status,
    r.command,
    r.wait_type,
    ISNULL(r.wait_time, 0) AS wait_time,
    ISNULL(r.blocking_session_id, 0) AS blocking_session_id,
    ISNULL(r.cpu_time, s.cpu_time) AS cpu_time,
    ISNULL(r.total_elapsed_time, 0) AS total_elapsed_time,
    ISNULL(r.reads, s.reads) AS reads,
    ISNULL(r.writes, s.writes) AS writes,
    ISNULL(r.logical_reads, s.logical_reads) AS logical_reads,
    ISNULL(DB_NAME(r.database_id), DB_NAME(s.database_id)) AS database_name,
    s.login_name,
    s.host_name,
    s.program_name,
    COALESCE(r.start_time, s.last_request_start_time) AS start_time,
    LEFT(CONVERT(nvarchar(400), st.text), 400) AS sql_text
FROM sys.dm_exec_sessions s
LEFT JOIN sys.dm_exec_requests r
    ON r.session_id = s.session_id
LEFT JOIN sys.dm_exec_connections c
    ON c.session_id = s.session_id
OUTER APPLY sys.dm_exec_sql_text(COALESCE(r.sql_handle, c.most_recent_sql_handle)) st
WHERE s.is_user_process = 1
  AND s.session_id <> @@SPID
  AND (
        r.session_id IS NOT NULL
        OR LOWER(CONVERT(varchar(20), s.status)) <> 'sleeping'
        OR s.open_transaction_count > 0
      )
  /* Hide SQL internal / always-on background noise (diagnostics, brokers, …) */
  AND (
        r.wait_type IS NULL
        OR r.wait_type NOT IN ({benign_waits})
      )
ORDER BY
    CASE WHEN ISNULL(r.blocking_session_id, 0) > 0 THEN 0 ELSE 1 END,
    ISNULL(r.total_elapsed_time, 0) DESC,
    s.session_id;
""".replace("{benign_waits}", _BENIGN_WAIT_SQL.strip())

_SESSION_BY_ID_SQL = """
SET NOCOUNT ON;
SELECT
    s.session_id,
    COALESCE(r.status, s.status) AS status,
    r.command,
    r.wait_type,
    ISNULL(r.wait_time, 0) AS wait_time,
    ISNULL(r.blocking_session_id, 0) AS blocking_session_id,
    ISNULL(r.cpu_time, s.cpu_time) AS cpu_time,
    ISNULL(r.total_elapsed_time, 0) AS total_elapsed_time,
    -- Wall-clock elapsed (matches what you see in SSMS / WhoIsActive better than total_elapsed_time alone)
    CASE
        WHEN r.start_time IS NOT NULL
            THEN DATEDIFF(MILLISECOND, r.start_time, SYSDATETIME())
        WHEN s.last_request_start_time IS NOT NULL
             AND (s.last_request_end_time IS NULL OR s.last_request_end_time < s.last_request_start_time)
            THEN DATEDIFF(MILLISECOND, s.last_request_start_time, SYSDATETIME())
        ELSE 0
    END AS elapsed_wall_ms,
    ISNULL(r.reads, s.reads) AS reads,
    ISNULL(r.writes, s.writes) AS writes,
    ISNULL(r.logical_reads, s.logical_reads) AS logical_reads,
    ISNULL(r.granted_query_memory, 0) AS granted_query_memory,
    ISNULL(r.open_transaction_count, s.open_transaction_count) AS open_tran_count,
    ISNULL(r.percent_complete, 0) AS percent_complete,
    ISNULL(DB_NAME(r.database_id), DB_NAME(s.database_id)) AS database_name,
    s.login_name,
    s.host_name,
    s.program_name,
    s.client_interface_name,
    s.login_time,
    s.last_request_start_time,
    s.last_request_end_time,
    r.start_time AS request_start_time,
    COALESCE(r.start_time, s.last_request_start_time) AS start_time,
    CASE WHEN r.session_id IS NOT NULL THEN 1 ELSE 0 END AS has_active_request,
    r.statement_start_offset,
    r.statement_end_offset,
    c.client_net_address,
    c.client_tcp_port,
    c.local_net_address,
    c.local_tcp_port,
    c.net_transport,
    c.encrypt_option,
    c.auth_scheme,
    /* Full batch / SP body — no 8k trim (modal scrolls). Cap only pathological size. */
    CASE
        WHEN st.text IS NULL THEN NULL
        WHEN DATALENGTH(st.text) > 1000000
            THEN LEFT(CONVERT(nvarchar(max), st.text), 500000)
        ELSE CONVERT(nvarchar(max), st.text)
    END AS sql_text,
    CASE
        WHEN st.text IS NULL OR r.statement_start_offset IS NULL THEN NULL
        ELSE CONVERT(nvarchar(max),
            SUBSTRING(
                st.text,
                (r.statement_start_offset / 2) + 1,
                (
                    (
                        CASE
                            WHEN r.statement_end_offset IS NULL OR r.statement_end_offset < 0
                                THEN DATALENGTH(st.text)
                            ELSE r.statement_end_offset
                        END
                        - r.statement_start_offset
                    ) / 2
                ) + 1
            )
        )
    END AS statement_text,
    OBJECT_SCHEMA_NAME(st.objectid, st.dbid) AS sql_object_schema,
    OBJECT_NAME(st.objectid, st.dbid) AS sql_object_name,
    CONVERT(nvarchar(128), SERVERPROPERTY('ServerName')) AS instance_name,
    CONVERT(nvarchar(128), SERVERPROPERTY('MachineName')) AS machine_name,
    /* How THIS monitor session is connected (not the looked-up SPID) */
    (
        SELECT TOP (1) c_mon.local_net_address
        FROM sys.dm_exec_connections c_mon
        WHERE c_mon.session_id = @@SPID
        ORDER BY c_mon.connect_time DESC
    ) AS monitor_local_address
FROM sys.dm_exec_sessions s
LEFT JOIN sys.dm_exec_requests r
    ON r.session_id = s.session_id
LEFT JOIN sys.dm_exec_connections c
    ON c.session_id = s.session_id
OUTER APPLY sys.dm_exec_sql_text(COALESCE(r.sql_handle, c.most_recent_sql_handle)) st
WHERE s.session_id = ?;
"""


_INDEX_START_TIME_SQL = """
SET NOCOUNT ON;
SELECT sqlserver_start_time FROM sys.dm_os_sys_info;
"""

# Eligible nonclustered indexes (not PK/unique/unique-constraint/disabled/hypothetical)
# on user tables, current DB only. Size via sys.dm_db_partition_stats — NEVER
# sys.dm_db_index_physical_stats (expensive; reserved for future fragmentation work).
_INDEX_USAGE_SQL = """
SET NOCOUNT ON;
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    i.name AS index_name,
    i.object_id,
    i.index_id,
    ISNULL(us.user_seeks, 0) + ISNULL(us.user_scans, 0) + ISNULL(us.user_lookups, 0) AS reads,
    ISNULL(us.user_updates, 0) AS writes,
    ps.size_mb,
    CAST(1 AS bit) AS eligible
FROM sys.indexes i
INNER JOIN sys.tables t ON t.object_id = i.object_id
INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
LEFT JOIN sys.dm_db_index_usage_stats us
    ON us.database_id = DB_ID()
    AND us.object_id = i.object_id
    AND us.index_id = i.index_id
LEFT JOIN (
    SELECT object_id, index_id, SUM(used_page_count) * 8.0 / 1024 AS size_mb
    FROM sys.dm_db_partition_stats
    GROUP BY object_id, index_id
) ps ON ps.object_id = i.object_id AND ps.index_id = i.index_id
WHERE t.is_ms_shipped = 0
  AND i.type_desc = N'NONCLUSTERED'
  AND i.is_primary_key = 0
  AND i.is_unique = 0
  AND i.is_unique_constraint = 0
  AND i.is_disabled = 0
  AND i.is_hypothetical = 0
ORDER BY writes DESC;
"""

# User tables that are heaps (no clustered index). Size via partition_stats.
_INDEX_HEAP_SQL = """
SET NOCOUNT ON;
SELECT
    s.name AS schema_name,
    t.name AS table_name,
    t.object_id,
    ps.size_mb
FROM sys.tables t
INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
INNER JOIN sys.indexes hi ON hi.object_id = t.object_id AND hi.index_id = 0
LEFT JOIN (
    SELECT object_id, SUM(used_page_count) * 8.0 / 1024 AS size_mb
    FROM sys.dm_db_partition_stats
    WHERE index_id IN (0, 1)
    GROUP BY object_id
) ps ON ps.object_id = t.object_id
WHERE t.is_ms_shipped = 0
  AND NOT EXISTS (
        SELECT 1 FROM sys.indexes ci WHERE ci.object_id = t.object_id AND ci.index_id = 1
      );
"""

# Missing-index DMVs, current DB only, ranked by impact. Fetch a safe upper bound
# (top 200) so the service layer can report "top N of M" before capping to
# INDEX_CAP_MISSING and attaching table context.
_INDEX_MISSING_SQL = """
SET NOCOUNT ON;
SELECT TOP (200)
    mid.object_id,
    OBJECT_SCHEMA_NAME(mid.object_id, mid.database_id) AS schema_name,
    OBJECT_NAME(mid.object_id, mid.database_id) AS table_name,
    mid.equality_columns,
    mid.inequality_columns,
    mid.included_columns,
    migs.user_seeks,
    migs.avg_user_impact,
    migs.avg_total_user_cost,
    migs.avg_total_user_cost * migs.avg_user_impact * migs.user_seeks AS impact_score
FROM sys.dm_db_missing_index_groups mig
INNER JOIN sys.dm_db_missing_index_group_stats migs ON migs.group_handle = mig.index_group_handle
INNER JOIN sys.dm_db_missing_index_details mid ON mig.index_handle = mid.index_handle
WHERE mid.database_id = DB_ID()
ORDER BY impact_score DESC;
"""

# Cheap pre-check (no STRING_AGG/FOR XML) used to decide whether the full-DB
# inventory scan is affordable before paying for it.
_INDEX_INVENTORY_COUNT_SQL = """
SET NOCOUNT ON;
SELECT COUNT(*)
FROM sys.indexes i
INNER JOIN sys.tables t ON t.object_id = i.object_id
WHERE t.is_ms_shipped = 0
  AND i.type_desc = N'NONCLUSTERED'
  AND i.name IS NOT NULL;
"""

# Key/include/filter inventory for duplicate detection + missing "table_indexes"
# context. {object_filter} is either empty (full-DB attempt) or "AND i.object_id
# IN (?,?,...)" for the touched-object fallback scope.
_INDEX_INVENTORY_SQL_TEMPLATE = """
SET NOCOUNT ON;
SELECT
    i.object_id,
    s.name AS schema_name,
    t.name AS table_name,
    i.name AS index_name,
    i.is_unique,
    i.type_desc AS type,
    i.filter_definition AS filter_def,
    ISNULL(STUFF((
        SELECT ',' + c.name
        FROM sys.index_columns ic
        INNER JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id AND ic.is_included_column = 0
        ORDER BY ic.key_ordinal
        FOR XML PATH(''), TYPE
    ).value('.', 'nvarchar(max)'), 1, 1, ''), '') AS key_cols,
    ISNULL(STUFF((
        SELECT ',' + c.name
        FROM sys.index_columns ic
        INNER JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id AND ic.is_included_column = 1
        ORDER BY c.name
        FOR XML PATH(''), TYPE
    ).value('.', 'nvarchar(max)'), 1, 1, ''), '') AS include_cols
FROM sys.indexes i
INNER JOIN sys.tables t ON t.object_id = i.object_id
INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
WHERE t.is_ms_shipped = 0
  AND i.type_desc = N'NONCLUSTERED'
  AND i.name IS NOT NULL
  {object_filter};
"""


def _rows_to_dicts(cursor) -> List[Dict[str, Any]]:
    cols = [c[0] for c in cursor.description]
    out = []
    for row in cursor.fetchall():
        item = {}
        for col, val in zip(cols, row):
            if hasattr(val, "isoformat"):
                item[col] = val.isoformat(sep=" ", timespec="seconds")
            else:
                item[col] = val
        out.append(item)
    return out


class SqlServerProvider:
    def get_running_requests(self, *, top: int = 100) -> QueryResult:
        top = max(1, min(int(top), 200))
        try:
            conn = connect()
            try:
                if not has_view_server_state(conn):
                    return QueryResult.error(
                        "VIEW SERVER STATE missing",
                        permission_denied=True,
                        hint=VIEW_SERVER_STATE_HINT,
                    )
                cur = conn.cursor()
                cur.execute(_RUNNING_SQL.format(top=top))
                rows = _rows_to_dicts(cur)
            finally:
                conn.close()
        except Exception as ex:
            log.exception("get_running_requests failed")
            return QueryResult.error(
                str(ex),
                permission_denied=is_permission_error(ex),
                hint=permission_hint_for(ex),
            )

        if not rows:
            return QueryResult.empty(
                summary={"running_requests": 0, "longest_wait_ms": 0},
                severity=sev.HEALTHY,
            )

        waits = [int(r.get("wait_time") or 0) for r in rows]
        longest = max(waits) if waits else 0
        blocked = sum(1 for r in rows if int(r.get("blocking_session_id") or 0) > 0)
        level = sev.classify_wait_ms(longest)
        if blocked:
            level = sev.worst(level, sev.IMPORTANT)

        for r in rows:
            r["severity"] = sev.classify_wait_ms(int(r.get("wait_time") or 0))
            if int(r.get("blocking_session_id") or 0) > 0:
                r["severity"] = sev.worst(r["severity"], sev.IMPORTANT)

        return QueryResult(
            status="ok",
            severity=level,
            summary={
                "running_requests": len(rows),
                "blocked_in_list": blocked,
                "longest_wait_ms": longest,
            },
            rows=rows,
            meta={"row_count": len(rows), "capped": len(rows) >= top, "hint": None},
        )

    def get_blocking(self, *, top: int = 200) -> QueryResult:
        top = max(1, min(int(top), 200))
        sql = f"""
SET NOCOUNT ON;
;WITH BlockingChain AS (
    SELECT
        r.session_id,
        r.blocking_session_id,
        r.wait_type,
        r.wait_resource,
        r.wait_time,
        r.status,
        r.command,
        r.start_time,
        0 AS lvl,
        CAST('|' + CAST(r.blocking_session_id AS VARCHAR(10))
          + '|' + CAST(r.session_id AS VARCHAR(10)) + '|' AS VARCHAR(MAX)) AS chain_path,
        CAST(CAST(r.blocking_session_id AS VARCHAR(10)) + ' -> '
          + CAST(r.session_id AS VARCHAR(10)) AS VARCHAR(MAX)) AS chain_display
    FROM sys.dm_exec_requests r
    WHERE r.blocking_session_id <> 0
      AND r.blocking_session_id <> r.session_id

    UNION ALL

    SELECT
        r.session_id,
        r.blocking_session_id,
        r.wait_type,
        r.wait_resource,
        r.wait_time,
        r.status,
        r.command,
        r.start_time,
        bc.lvl + 1,
        CAST('|' + CAST(r.blocking_session_id AS VARCHAR(10)) + bc.chain_path AS VARCHAR(MAX)),
        CAST(CAST(r.blocking_session_id AS VARCHAR(10)) + ' -> ' + bc.chain_display AS VARCHAR(MAX))
    FROM sys.dm_exec_requests r
    INNER JOIN BlockingChain bc ON r.session_id = bc.blocking_session_id
    WHERE bc.lvl < 50
      AND r.blocking_session_id <> 0
      AND r.blocking_session_id <> r.session_id
      AND bc.chain_path NOT LIKE '%|' + CAST(r.blocking_session_id AS VARCHAR(10)) + '|%'
)
SELECT TOP ({top})
    bc.lvl AS level_no,
    bc.session_id AS blocked_session_id,
    bc.blocking_session_id AS blocker_session_id,
    CASE
        WHEN NOT EXISTS (
            SELECT 1
            FROM sys.dm_exec_requests rx
            WHERE rx.session_id = bc.blocking_session_id
              AND rx.blocking_session_id <> 0
        ) THEN 1 ELSE 0
    END AS is_head_blocker,
    bc.wait_type,
    bc.wait_resource,
    bc.wait_time,
    CAST(bc.wait_time / 1000.0 AS DECIMAL(18, 2)) AS wait_seconds,
    DATEDIFF(SECOND, bc.start_time, GETDATE()) AS request_elapsed_sec,
    bc.chain_display,
    DB_NAME(r_blocked.database_id) AS database_name,
    s_blocked.login_name AS blocked_login,
    s_blocked.host_name AS blocked_host,
    s_blocked.program_name AS blocked_program,
    ISNULL(r_blocked.command, N'Sleeping') AS blocked_command,
    LEFT(CONVERT(nvarchar(max), st_blocked.text), 2000) AS blocked_sql,
    s_blocker.login_name AS blocker_login,
    s_blocker.host_name AS blocker_host,
    s_blocker.program_name AS blocker_program,
    ISNULL(r_blocker.command, N'Sleeping / open tran') AS blocker_command,
    LEFT(CONVERT(nvarchar(max), st_blocker.text), 2000) AS blocker_sql,
    tst.open_transaction_count AS blocker_open_tran
FROM BlockingChain bc
LEFT JOIN sys.dm_exec_sessions s_blocked ON bc.session_id = s_blocked.session_id
LEFT JOIN sys.dm_exec_requests r_blocked ON bc.session_id = r_blocked.session_id
OUTER APPLY sys.dm_exec_sql_text(r_blocked.sql_handle) st_blocked
LEFT JOIN sys.dm_exec_sessions s_blocker ON bc.blocking_session_id = s_blocker.session_id
LEFT JOIN sys.dm_exec_requests r_blocker ON bc.blocking_session_id = r_blocker.session_id
LEFT JOIN sys.dm_exec_connections c_blocker ON bc.blocking_session_id = c_blocker.session_id
OUTER APPLY sys.dm_exec_sql_text(c_blocker.most_recent_sql_handle) st_blocker
LEFT JOIN sys.dm_tran_session_transactions tst ON bc.blocking_session_id = tst.session_id
ORDER BY bc.lvl, bc.wait_time DESC, bc.session_id
OPTION (MAXRECURSION 200);
"""
        try:
            conn = connect()
            try:
                if not has_view_server_state(conn):
                    return QueryResult.error(
                        "VIEW SERVER STATE missing",
                        permission_denied=True,
                        hint=VIEW_SERVER_STATE_HINT,
                    )
                cur = conn.cursor()
                cur.execute(sql)
                rows = _rows_to_dicts(cur)
            finally:
                conn.close()
        except Exception as ex:
            log.exception("get_blocking failed")
            return QueryResult.error(
                str(ex),
                permission_denied=is_permission_error(ex),
                hint=permission_hint_for(ex),
            )

        if not rows:
            return QueryResult.empty(
                summary={
                    "head_blockers": 0,
                    "blocked_sessions": 0,
                    "longest_wait_ms": 0,
                },
                severity=sev.HEALTHY,
            )

        head_ids = {int(r["blocker_session_id"]) for r in rows if int(r.get("is_head_blocker") or 0) == 1}
        blocked_ids = {int(r["blocked_session_id"]) for r in rows}
        waits = [int(r.get("wait_time") or 0) for r in rows]
        longest = max(waits) if waits else 0
        level = sev.CRITICAL if head_ids else sev.classify_wait_ms(longest)
        if head_ids:
            level = sev.worst(level, sev.CRITICAL)
        elif blocked_ids:
            level = sev.worst(level, sev.IMPORTANT)

        for r in rows:
            if int(r.get("is_head_blocker") or 0) == 1:
                r["severity"] = sev.CRITICAL
                r["head_blocker_label"] = "بله — Head Blocker"
            else:
                r["severity"] = sev.classify_wait_ms(int(r.get("wait_time") or 0))
                r["head_blocker_label"] = ""

        return QueryResult(
            status="ok",
            severity=level,
            summary={
                "head_blockers": len(head_ids),
                "blocked_sessions": len(blocked_ids),
                "longest_wait_ms": longest,
                "chain_rows": len(rows),
            },
            rows=rows,
            meta={"row_count": len(rows), "capped": len(rows) >= top, "hint": None},
        )

    def get_index_health_snapshot(self) -> Dict[str, Any]:
        """Read-only Index Health raw snapshot for the current database (soft-fail per section).

        Never uses sys.dm_db_index_physical_stats — size comes from
        sys.dm_db_partition_stats only. Each DMV/catalog batch fails
        independently into `errors`; the caller (service.build_index_health)
        still gets a usable partial payload.
        """
        errors: Dict[str, str] = {}
        database_name = ""
        sqlserver_start_time = None
        usage_rows: List[Dict[str, Any]] = []
        heap_rows: List[Dict[str, Any]] = []
        inventory_rows: List[Dict[str, Any]] = []
        missing_rows: List[Dict[str, Any]] = []
        inventory_mode = "full"
        inventory_ms = 0.0

        try:
            conn = connect()
        except Exception as ex:
            log.exception("get_index_health_snapshot: connection failed")
            errors["connection"] = str(ex)
            return {
                "database_name": database_name,
                "sqlserver_start_time": sqlserver_start_time,
                "usage_rows": usage_rows,
                "heap_rows": heap_rows,
                "inventory_rows": inventory_rows,
                "missing_rows": missing_rows,
                "errors": errors,
                "inventory_mode": inventory_mode,
                "inventory_ms": inventory_ms,
                "inventory_rows_count": 0,
            }

        try:
            try:
                cur = conn.cursor()
                cur.execute("SELECT DB_NAME();")
                row = cur.fetchone()
                database_name = row[0] if row else ""
            except Exception as ex:
                log.exception("index_health: database_name lookup failed")
                errors["database_name"] = str(ex)

            try:
                cur = conn.cursor()
                cur.execute(_INDEX_START_TIME_SQL)
                row = cur.fetchone()
                sqlserver_start_time = row[0] if row else None
            except Exception as ex:
                log.debug("index_health: start_time lookup failed", exc_info=True)
                errors["start_time"] = str(ex)

            try:
                cur = conn.cursor()
                cur.execute(_INDEX_USAGE_SQL)
                usage_rows = _rows_to_dicts(cur)
            except Exception as ex:
                log.exception("index_health: usage query failed")
                errors["usage"] = str(ex)

            try:
                cur = conn.cursor()
                cur.execute(_INDEX_HEAP_SQL)
                heap_rows = _rows_to_dicts(cur)
            except Exception as ex:
                log.exception("index_health: heap query failed")
                errors["heaps"] = str(ex)

            try:
                cur = conn.cursor()
                cur.execute(_INDEX_MISSING_SQL)
                missing_rows = _rows_to_dicts(cur)
            except Exception as ex:
                log.exception("index_health: missing query failed")
                errors["missing"] = str(ex)

            try:
                inventory_rows, inventory_mode, inventory_ms = _fetch_index_inventory(
                    conn,
                    usage_rows=usage_rows,
                    heap_rows=heap_rows,
                    missing_rows=missing_rows,
                )
            except Exception as ex:
                log.exception("index_health: inventory query failed")
                errors["inventory"] = str(ex)
        finally:
            conn.close()

        return {
            "database_name": database_name,
            "sqlserver_start_time": sqlserver_start_time,
            "usage_rows": usage_rows,
            "heap_rows": heap_rows,
            "inventory_rows": inventory_rows,
            "missing_rows": missing_rows,
            "errors": errors,
            "inventory_mode": inventory_mode,
            "inventory_ms": inventory_ms,
            "inventory_rows_count": len(inventory_rows),
        }

    def list_user_databases(self) -> Dict[str, Any]:
        """User databases the login can access (Indexes DB dropdown)."""
        try:
            conn = connect()
            try:
                cur = conn.cursor()
                cur.execute(_LIST_USER_DATABASES_SQL)
                rows = _rows_to_dicts(cur)
            finally:
                conn.close()
        except Exception as ex:
            log.exception("list_user_databases failed")
            return {
                "databases": [],
                "errors": {"databases": str(ex)},
                "permissions_hint": INDEX_PERMISSIONS_HINT if is_permission_error(ex) else None,
            }
        names = [r.get("database_name") for r in rows if r.get("database_name")]
        return {"databases": names, "errors": {}, "permissions_hint": None}

    def list_tables(
        self,
        database: str,
        search: str | None = None,
        *,
        all_for_db: bool = False,
    ) -> Dict[str, Any]:
        """Searchable user tables in a database (Indexes table picker).

        Prefers insight.IdxCat_Table when the optional catalog is installed; otherwise live sys.tables.
        When all_for_db=True, prefetch up to INDEX_TABLE_CACHE_CAP rows for client-side typeahead.
        Pass database=\"__all__\" (INDEX_DB_ALL) to list across the catalog (catalog-only).
        """
        q = (search or "").strip() or None
        if all_for_db:
            top = int(INDEX_TABLE_CACHE_CAP)
            q = None
        else:
            top = int(INDEX_TABLE_SEARCH_CAP if q else INDEX_TABLE_LIST_CAP)
        catalog = self._list_tables_from_catalog(database, q, top, require_rows=not bool(q))
        if catalog is not None:
            return catalog
        if (database or "").strip() == INDEX_DB_ALL:
            return {
                "tables": [],
                "errors": {},
                "permissions_hint": None,
                "source": "catalog",
            }
        if top <= 0 and not all_for_db:
            return {"tables": [], "errors": {}, "permissions_hint": None, "source": "live"}
        try:
            conn = _connect_to_database(database)
            try:
                cur = conn.cursor()
                sql = _LIST_TABLES_SQL.format(top=top)
                cur.execute(sql, q, q or "", q or "", q or "")
                rows = _rows_to_dicts(cur)
            finally:
                conn.close()
        except Exception as ex:
            log.exception("list_tables failed db=%s", database)
            return {
                "tables": [],
                "errors": {"tables": str(ex)},
                "permissions_hint": INDEX_PERMISSIONS_HINT if is_permission_error(ex) else None,
                "source": "live",
            }
        for row in rows:
            row.setdefault("database_name", database)
        return {"tables": rows, "errors": {}, "permissions_hint": None, "source": "live"}

    def _index_catalog_present(self, cur) -> bool:
        cur.execute(
            """
            SELECT TOP (1) 1 AS ok
            FROM sys.tables t
            INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
            WHERE s.name = ? AND t.name = N'IdxCat_Table'
            """,
            INDEX_CATALOG_SCHEMA,
        )
        return bool(cur.fetchone())

    def _open_catalog_connection(self, *, timeout: int | None = None):
        """Open a connection where the index catalog lives.

        Prefer MONITOR_DATABASE (SmartMonitorDB). Fall back to the app default
        database if the catalog was installed there (e.g. msdb) for legacy setups.
        Returns (conn, database_name) or (None, None).
        """
        from core.insight.store import get_monitor_connection, monitor_database_name

        candidates: List[tuple[str, Any]] = []
        monitor = monitor_database_name()
        try:
            candidates.append((monitor, get_monitor_connection(timeout=timeout)))
        except Exception as ex:
            log.debug("monitor catalog connect failed: %s", ex)

        try:
            cfg = dict(load_config())
            default_db = (cfg.get("database") or "msdb").strip() or "msdb"
            if default_db.lower() != monitor.lower():
                if timeout is not None:
                    cfg["timeout"] = int(timeout)
                from db import get_connection

                candidates.append((default_db, get_connection(cfg)))
        except Exception as ex:
            log.debug("default catalog connect failed: %s", ex)

        for db_name, conn in candidates:
            try:
                cur = conn.cursor()
                if self._index_catalog_present(cur):
                    return conn, db_name
                conn.close()
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
        return None, None

    def get_index_catalog_status(self) -> Dict[str, Any]:
        """Last refresh + row counts from insight catalog (soft-fail if missing)."""
        try:
            conn, db_name = self._open_catalog_connection()
            if conn is None:
                return {"available": False, "reason": "catalog_missing"}
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT TOP (1)
                        refresh_id, database_name, started_at, finished_at, status, message,
                        tables_upserted, indexes_upserted
                    FROM insight.IdxCat_RefreshLog
                    ORDER BY refresh_id DESC
                    """
                )
                log_rows = _rows_to_dicts(cur)
                last = log_rows[0] if log_rows else None
                if last is not None:
                    try:
                        cur.execute(
                            """
                            SELECT TOP (1) refresh_parts
                            FROM insight.IdxCat_RefreshLog
                            ORDER BY refresh_id DESC
                            """
                        )
                        prow = cur.fetchone()
                        if prow is not None:
                            last["refresh_parts"] = prow[0]
                    except Exception:
                        pass
                cur.execute("SELECT COUNT(*) FROM insight.IdxCat_Table")
                table_count = int((cur.fetchone() or [0])[0] or 0)
                cur.execute("SELECT COUNT(*) FROM insight.IdxCat_Index")
                index_count = int((cur.fetchone() or [0])[0] or 0)
                cur.execute(
                    "SELECT COUNT(DISTINCT database_name) FROM insight.IdxCat_Table"
                )
                db_count = int((cur.fetchone() or [0])[0] or 0)
                return {
                    "available": True,
                    "catalog_database": db_name,
                    "last_refresh": last,
                    "table_count": table_count,
                    "index_count": index_count,
                    "database_count": db_count,
                    "ready": table_count > 0 and index_count > 0,
                }
            finally:
                conn.close()
        except Exception as ex:
            log.debug("index catalog status unavailable: %s", ex)
            return {"available": False, "reason": str(ex)}

    def refresh_index_catalog(
        self,
        database: str | None = None,
        *,
        tables: bool = True,
        index_defs: bool = True,
        index_stats: bool = True,
    ) -> Dict[str, Any]:
        """Refresh insight.IdxCat_* via USP_Insight_IndexCatalog_Refresh (selective parts)."""
        db = (database or "").strip() or None
        if not tables and not index_defs and not index_stats:
            return {"ok": False, "error": "Select at least one catalog part to refresh."}
        proc = f"{INDEX_CATALOG_SCHEMA}.{INDEX_CATALOG_REFRESH_PROC}"
        conn, catalog_db = self._open_catalog_connection(
            timeout=int(INDEX_CATALOG_REFRESH_TIMEOUT_SEC)
        )
        if conn is None:
            from core.insight.store import monitor_database_name

            mon = monitor_database_name()
            return {
                "ok": False,
                "error": (
                    f"Index catalog not found. Run scripts/sql/SqlMonitor_IndexCatalog.sql "
                    f"in [{mon}] (MONITOR_DATABASE)."
                ),
                "permissions_hint": INDEX_PERMISSIONS_HINT,
            }
        try:
            try:
                conn.timeout = int(INDEX_CATALOG_REFRESH_TIMEOUT_SEC)
            except Exception:
                pass
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*) FROM sys.parameters p
                INNER JOIN sys.objects o ON o.object_id = p.object_id
                INNER JOIN sys.schemas s ON s.schema_id = o.schema_id
                WHERE s.name = ? AND o.name = ?
                  AND p.name IN (N'@RefreshTables', N'@RefreshIndexDefs', N'@RefreshIndexStats')
                """,
                INDEX_CATALOG_SCHEMA,
                INDEX_CATALOG_REFRESH_PROC,
            )
            has_parts = int((cur.fetchone() or [0])[0] or 0) >= 3
            if has_parts:
                cur.execute(
                    f"""
                    EXEC {proc}
                        @DatabaseName = ?,
                        @RefreshTables = ?,
                        @RefreshIndexDefs = ?,
                        @RefreshIndexStats = ?
                    """,
                    db,
                    1 if tables else 0,
                    1 if index_defs else 0,
                    1 if index_stats else 0,
                )
            else:
                if db:
                    cur.execute(f"EXEC {proc} @DatabaseName = ?", db)
                else:
                    cur.execute(f"EXEC {proc}")
            conn.commit()
        except Exception as ex:
            log.exception("refresh_index_catalog failed")
            msg = str(ex)
            if "collation conflict" in msg.lower() or "468" in msg:
                msg = (
                    "Collation conflict while refreshing catalog "
                    "(databases use different Persian collations). "
                    "Re-run scripts/sql/SqlMonitor_IndexCatalog_FullInstall.sql "
                    "on SmartMonitorDB (includes COLLATE DATABASE_DEFAULT fixes)."
                )
            elif is_permission_error(ex) or "229" in msg or "EXECUTE permission" in msg:
                login_hint = ""
                try:
                    login_hint = (load_config().get("user") or "").strip()
                except Exception:
                    pass
                principal = login_hint or "YourAppLogin"
                msg = (
                    f"EXECUTE permission denied on {proc} in database [{catalog_db}]. "
                    f"Run as a sysadmin on [{catalog_db}]:\n"
                    f"GRANT EXECUTE ON {proc} TO [{principal}];"
                )
            return {
                "ok": False,
                "error": msg,
                "catalog_database": catalog_db,
                "permissions_hint": INDEX_PERMISSIONS_HINT if is_permission_error(ex) else None,
            }
        finally:
            try:
                conn.close()
            except Exception:
                pass
        status = self.get_index_catalog_status()
        return {
            "ok": True,
            "status": status,
            "database": db,
            "catalog_database": catalog_db,
            "parts": {
                "tables": bool(tables),
                "index_defs": bool(index_defs),
                "index_stats": bool(index_stats),
            },
        }

    def _objsize_history_present(self, cur) -> bool:
        cur.execute(
            """
            SELECT TOP (1) 1 AS ok
            FROM sys.tables t
            INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
            WHERE s.name = N'insight' AND t.name = N'ObjSize_History'
            """
        )
        return bool(cur.fetchone())

    def _open_monitor_connection(self, *, timeout: int | None = None):
        """Open MONITOR_DATABASE regardless of IdxCat presence."""
        from core.insight.store import get_monitor_connection, monitor_database_name

        try:
            conn = get_monitor_connection(timeout=timeout)
            return conn, monitor_database_name()
        except Exception as ex:
            log.debug("monitor connection failed: %s", ex)
            return None, None

    def _current_tables_from_catalog(self) -> Dict[str, Any] | None:
        try:
            conn, _db = self._open_catalog_connection(timeout=int(TABLES_QUERY_TIMEOUT_SEC))
            if conn is None:
                return None
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT
                        database_name, schema_name, table_name,
                        row_count, size_mb, is_heap, refreshed_at
                    FROM insight.IdxCat_Table
                    """
                )
                rows = _rows_to_dicts(cur)
                if not rows:
                    return None
                return {"tables": rows, "source": "catalog"}
            finally:
                conn.close()
        except Exception as ex:
            log.debug("tables from catalog failed: %s", ex)
            return None

    def _current_tables_live(self) -> Dict[str, Any]:
        db_info = self.list_user_databases()
        all_dbs = list(db_info.get("databases") or [])
        preferred = (INDEX_PREFERRED_DATABASE or "").strip()
        databases: List[str] = []
        if preferred and preferred in all_dbs:
            databases.append(preferred)
        for name in all_dbs:
            if name not in databases:
                databases.append(name)
            if len(databases) >= int(TABLES_LIVE_DB_CAP):
                break

        tables: List[Dict[str, Any]] = []
        errors: Dict[str, str] = {}
        for db in databases:
            try:
                conn = _connect_to_database(db)
                try:
                    try:
                        conn.timeout = int(TABLES_LIVE_DB_TIMEOUT_SEC)
                    except Exception:
                        pass
                    cur = conn.cursor()
                    cur.execute(_TABLE_SIZE_LIVE_SQL)
                    tables.extend(_rows_to_dicts(cur))
                finally:
                    conn.close()
            except Exception as ex:
                log.debug("live table size failed db=%s: %s", db, ex)
                errors[db] = str(ex)

        note = None
        if len(all_dbs) > len(databases):
            note = (
                f"Live path scanned {len(databases)} of {len(all_dbs)} databases "
                f"(cap {TABLES_LIVE_DB_CAP}). Install Index Catalog for full coverage."
            )
        return {
            "tables": tables,
            "source": "live",
            "errors": errors,
            "note": note,
            "permissions_hint": INDEX_PERMISSIONS_HINT if errors else None,
        }

    def _history_by_window(self, cur) -> Dict[str, List[dict]]:
        """Nearest prior day snapshot per window (1/7/30)."""
        out: Dict[str, List[dict]] = {}
        cur.execute("SELECT MAX(captured_date) FROM insight.ObjSize_History")
        latest = cur.fetchone()
        latest_date = latest[0] if latest else None
        if latest_date is None:
            return {str(d): [] for d in TABLES_DELTA_WINDOWS_DAYS}

        for days in TABLES_DELTA_WINDOWS_DAYS:
            cur.execute(
                """
                SELECT MAX(captured_date)
                FROM insight.ObjSize_History
                WHERE captured_date <= DATEADD(day, -?, ?)
                """,
                int(days),
                latest_date,
            )
            prior = (cur.fetchone() or [None])[0]
            if prior is None:
                out[str(days)] = []
                continue
            cur.execute(
                """
                SELECT
                    database_name, schema_name, table_name,
                    row_count, size_mb, is_heap, captured_date
                FROM insight.ObjSize_History
                WHERE captured_date = ?
                """,
                prior,
            )
            out[str(days)] = _rows_to_dicts(cur)
        return out

    def get_table_growth_snapshot(self) -> Dict[str, Any]:
        """Current table sizes (catalog-first) + optional ObjSize_History deltas."""
        errors: Dict[str, str] = {}
        catalog = self._current_tables_from_catalog()
        if catalog is not None:
            base = catalog
        else:
            base = self._current_tables_live()
            errors.update(base.get("errors") or {})

        history_available = False
        history_by_window: Dict[str, List[dict]] = {
            str(d): [] for d in TABLES_DELTA_WINDOWS_DAYS
        }
        latest_capture_date = None
        try:
            conn, _mon = self._open_monitor_connection(timeout=int(TABLES_QUERY_TIMEOUT_SEC))
            if conn is not None:
                try:
                    cur = conn.cursor()
                    if self._objsize_history_present(cur):
                        cur.execute(
                            "SELECT COUNT(*), MAX(captured_date) FROM insight.ObjSize_History"
                        )
                        cnt_row = cur.fetchone()
                        cnt = int((cnt_row[0] if cnt_row else 0) or 0)
                        latest_capture_date = cnt_row[1] if cnt_row else None
                        if hasattr(latest_capture_date, "isoformat"):
                            latest_capture_date = latest_capture_date.isoformat()
                        history_available = cnt > 0
                        if history_available:
                            history_by_window = self._history_by_window(cur)
                finally:
                    conn.close()
        except Exception as ex:
            log.debug("obj size history read failed: %s", ex)
            errors["history"] = str(ex)

        return {
            "tables": base.get("tables") or [],
            "source": base.get("source") or "live",
            "history_available": history_available,
            "history_by_window": history_by_window,
            "latest_capture_date": latest_capture_date,
            "errors": errors,
            "permissions_hint": base.get("permissions_hint"),
            "note": base.get("note"),
        }

    def capture_objsize_history(self, *, retention_days: int = 90) -> Dict[str, Any]:
        """Run insight.USP_Insight_ObjSize_Capture (soft-fail if missing)."""
        from core.insight.store import monitor_database_name

        conn, mon = self._open_monitor_connection(timeout=int(TABLES_QUERY_TIMEOUT_SEC))
        if conn is None:
            return {
                "ok": False,
                "error": (
                    f"Cannot connect to monitor database [{monitor_database_name()}]."
                ),
            }
        try:
            cur = conn.cursor()
            if not self._objsize_history_present(cur):
                return {
                    "ok": False,
                    "error": (
                        f"ObjSize_History not found. Run scripts/sql/SqlMonitor_ObjSizeHistory.sql "
                        f"in [{mon}]."
                    ),
                    "catalog_database": mon,
                }
            cur.execute(
                "EXEC insight.USP_Insight_ObjSize_Capture @RetentionDays = ?",
                int(retention_days),
            )
            result_rows = []
            try:
                result_rows = _rows_to_dicts(cur)
            except Exception:
                pass
            conn.commit()
            row = result_rows[0] if result_rows else {}
            return {
                "ok": True,
                "catalog_database": mon,
                "rows_captured": row.get("rows_captured"),
                "source": row.get("source"),
                "captured_date": row.get("captured_date"),
            }
        except Exception as ex:
            log.exception("capture_objsize_history failed")
            return {
                "ok": False,
                "error": str(ex),
                "catalog_database": mon,
                "permissions_hint": INDEX_PERMISSIONS_HINT if is_permission_error(ex) else None,
            }
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _list_tables_from_catalog(
        self,
        database: str,
        search: str | None,
        top: int,
        *,
        require_rows: bool = True,
    ) -> Dict[str, Any] | None:
        """Return catalog rows or None if catalog missing / empty for this DB."""
        if top <= 0 and not search:
            return None
        all_dbs = (database or "").strip() == INDEX_DB_ALL
        try:
            conn, _catalog_db = self._open_catalog_connection()
            if conn is None:
                return None
            try:
                cur = conn.cursor()
                db_filter = "" if all_dbs else "AND t.database_name = ?"
                order_by = (
                    "ORDER BY t.database_name, t.schema_name, t.table_name"
                    if all_dbs
                    else "ORDER BY t.schema_name, t.table_name"
                )
                select_cols = f"""
                        SELECT TOP ({int(top)})
                            t.database_name,
                            t.schema_name, t.table_name,
                            t.schema_name + N'.' + t.table_name AS full_name,
                            t.is_heap, t.row_count, t.size_mb,
                            (
                                SELECT COUNT(*)
                                FROM insight.IdxCat_Index i
                                WHERE i.database_name = t.database_name
                                  AND i.schema_name = t.schema_name
                                  AND i.table_name = t.table_name
                                  AND i.index_id > 0
                            ) AS index_count,
                            CONVERT(varchar(16), t.refreshed_at, 120) AS refreshed_at
                        FROM insight.IdxCat_Table t
                """
                if search:
                    params: list = []
                    if not all_dbs:
                        params.append(database)
                    params.extend([search, search, search])
                    cur.execute(
                        f"""
                        {select_cols}
                        WHERE 1 = 1
                          {db_filter}
                          AND (
                                t.schema_name + N'.' + t.table_name LIKE N'%' + ? + N'%'
                             OR t.table_name LIKE N'%' + ? + N'%'
                             OR t.database_name LIKE N'%' + ? + N'%'
                          )
                        {order_by}
                        """,
                        *params,
                    )
                else:
                    params = [] if all_dbs else [database]
                    cur.execute(
                        f"""
                        {select_cols}
                        WHERE 1 = 1
                          {db_filter}
                        {order_by}
                        """,
                        *params,
                    )
                rows = _rows_to_dicts(cur)
                if not rows and search:
                    return {"tables": [], "errors": {}, "permissions_hint": None, "source": "catalog"}
                if not rows and require_rows and not all_dbs:
                    return None
                return {"tables": rows, "errors": {}, "permissions_hint": None, "source": "catalog"}
            finally:
                conn.close()
        except Exception as ex:
            log.debug("index catalog table search unavailable: %s", ex)
            return None
    def get_table_index_snapshot(
        self, database: str, schema: str, table: str
    ) -> Dict[str, Any]:
        """Fast table index snapshot: catalog + usage + size + meta. No physical_stats."""
        schema = (schema or "dbo").strip()
        table = (table or "").strip()
        database = (database or "").strip()
        object_name = f"{schema}.{table}"
        errors: Dict[str, str] = {}
        index_rows: List[Dict[str, Any]] = []
        missing_rows: List[Dict[str, Any]] = []
        is_heap = False
        sqlserver_start_time = None
        table_meta: Dict[str, Any] = {}

        try:
            conn = _connect_to_database(database)
        except Exception as ex:
            log.exception("get_table_index_snapshot: connect failed")
            hint = INDEX_PERMISSIONS_HINT if is_permission_error(ex) else None
            return {
                "database_name": database,
                "schema_name": schema,
                "table_name": table,
                "sqlserver_start_time": None,
                "index_rows": [],
                "missing_rows": [],
                "is_heap": False,
                "table_meta": {},
                "errors": {"connection": str(ex)},
                "permissions_hint": hint,
            }

        try:
            try:
                conn.timeout = int(INDEX_SNAPSHOT_QUERY_TIMEOUT_SEC)
            except Exception:
                pass

            try:
                cur = conn.cursor()
                cur.execute(_INDEX_START_TIME_SQL)
                row = cur.fetchone()
                sqlserver_start_time = row[0] if row else None
            except Exception as ex:
                errors["start_time"] = str(ex)

            try:
                cur = conn.cursor()
                cur.execute(_TABLE_META_SQL, object_name)
                meta_rows = _rows_to_dicts(cur)
                table_meta = meta_rows[0] if meta_rows else {}
            except Exception as ex:
                errors["table_meta"] = str(ex)

            try:
                cur = conn.cursor()
                cur.execute(_TABLE_INDEX_SNAPSHOT_SQL, object_name)
                index_rows = _rows_to_dicts(cur)
            except Exception as ex:
                log.exception("table index snapshot failed")
                errors["indexes"] = str(ex)
                if is_permission_error(ex):
                    errors["permissions_hint"] = INDEX_PERMISSIONS_HINT

            try:
                cur = conn.cursor()
                cur.execute(_TABLE_IS_HEAP_SQL, object_name)
                row = cur.fetchone()
                is_heap = bool(row and row[0])
            except Exception as ex:
                errors["heap"] = str(ex)

            try:
                cur = conn.cursor()
                cur.execute(_TABLE_MISSING_SQL, object_name)
                missing_rows = _rows_to_dicts(cur)
            except Exception as ex:
                errors["missing"] = str(ex)
        finally:
            conn.close()

        return {
            "database_name": database,
            "schema_name": schema,
            "table_name": table,
            "sqlserver_start_time": sqlserver_start_time,
            "index_rows": index_rows,
            "missing_rows": missing_rows,
            "is_heap": is_heap,
            "table_meta": table_meta,
            "errors": errors,
            "permissions_hint": errors.get("permissions_hint"),
        }

    def get_table_index_frag(
        self, database: str, schema: str, table: str
    ) -> Dict[str, Any]:
        """Lazy LIMITED fragmentation for one table (manual button). Soft-fails on timeout."""
        object_name = f"{(schema or 'dbo').strip()}.{(table or '').strip()}"
        try:
            conn = _connect_to_database(database)
        except Exception as ex:
            return {"frag_rows": [], "errors": {"frag": str(ex)}}
        try:
            try:
                conn.timeout = int(INDEX_FRAG_QUERY_TIMEOUT_SEC)
            except Exception:
                pass
            cur = conn.cursor()
            cur.execute(_TABLE_FRAG_SQL, object_name)
            return {"frag_rows": _rows_to_dicts(cur), "errors": {}}
        except Exception as ex:
            log.warning("frag load failed %s: %s", object_name, ex)
            msg = str(ex)
            code = "timeout" if "timeout" in msg.lower() or "HYT00" in msg else "failed"
            return {
                "frag_rows": [],
                "errors": {"frag": code, "frag_detail": msg},
            }
        finally:
            conn.close()

    def get_index_overview_snapshot(self, *, deep: bool = False) -> Dict[str, Any]:
        """Finding-oriented environment health.

        Prefers insight.IdxCat_* when populated; otherwise live multi-DB DMV scan.
        Quick mode: preferred DB first, few DBs. Deep: more DBs from catalog/live.
        """
        catalog = self._get_index_overview_from_catalog(deep=deep)
        if catalog is not None:
            return catalog
        return self._get_index_overview_live(deep=deep)

    def _overview_database_scope(
        self, all_dbs: List[str], *, deep: bool
    ) -> List[str]:
        cap = int(INDEX_OVERVIEW_MAX_DATABASES if deep else INDEX_OVERVIEW_QUICK_MAX_DATABASES)
        databases: List[str] = []
        preferred = (INDEX_PREFERRED_DATABASE or "").strip()
        if preferred and preferred in all_dbs:
            databases.append(preferred)
        for name in all_dbs:
            if name not in databases:
                databases.append(name)
            if len(databases) >= cap:
                break
        return databases

    def _get_index_overview_from_catalog(self, *, deep: bool) -> Dict[str, Any] | None:
        row_cap = int(INDEX_OVERVIEW_FINDING_ROWS)
        wh_writes = int(INDEX_WRITE_HEAVY_MIN_WRITES)
        wh_diff = int(INDEX_WRITE_HEAVY_MIN_DIFF)
        wh_ratio = int(INDEX_WRITE_HEAVY_MIN_RATIO)
        try:
            conn, _catalog_db = self._open_catalog_connection()
            if conn is None:
                return None
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT COUNT(*) FROM insight.IdxCat_Index WHERE index_id > 0"
                )
                if int((cur.fetchone() or [0])[0] or 0) <= 0:
                    return None

                cur.execute(
                    """
                    SELECT DISTINCT database_name
                    FROM insight.IdxCat_Table
                    ORDER BY database_name
                    """
                )
                all_dbs = [r[0] for r in cur.fetchall() if r and r[0]]
                databases = self._overview_database_scope(all_dbs, deep=deep)
                if not databases:
                    return None

                placeholders = ",".join("?" for _ in databases)

                sqlserver_start_time = None
                try:
                    cur.execute(_INDEX_START_TIME_SQL)
                    row = cur.fetchone()
                    sqlserver_start_time = row[0] if row else None
                except Exception as ex:
                    log.debug("catalog overview start_time: %s", ex)

                cur.execute(
                    f"""
                    SELECT
                        COUNT(*) AS index_count,
                        COUNT(DISTINCT database_name) AS databases_scanned
                    FROM insight.IdxCat_Index
                    WHERE index_id > 0 AND database_name IN ({placeholders})
                    """,
                    *databases,
                )
                stats = cur.fetchone()
                index_count = int((stats[0] if stats else 0) or 0)
                db_scanned = int((stats[1] if stats else 0) or 0)

                cur.execute(
                    f"""
                    SELECT COUNT(*) FROM insight.IdxCat_Table
                    WHERE is_heap = 1 AND database_name IN ({placeholders})
                    """,
                    *databases,
                )
                heap_count = int((cur.fetchone() or [0])[0] or 0)

                cur.execute(
                    f"""
                    SELECT TOP ({row_cap})
                        database_name, schema_name, table_name, index_name,
                        ISNULL(writes, 0) AS writes,
                        size_mb
                    FROM insight.IdxCat_Index
                    WHERE database_name IN ({placeholders})
                      AND type_desc = N'NONCLUSTERED'
                      AND is_primary_key = 0 AND is_unique_constraint = 0 AND is_unique = 0
                      AND ISNULL(reads, 0) = 0
                      AND index_id > 0
                    ORDER BY ISNULL(writes, 0) DESC, ISNULL(size_mb, 0) DESC
                    """,
                    *databases,
                )
                unused_rows = _rows_to_dicts(cur)

                cur.execute(
                    f"""
                    SELECT TOP ({row_cap})
                        database_name, schema_name, table_name, index_name,
                        ISNULL(reads, 0) AS reads,
                        ISNULL(writes, 0) AS writes,
                        size_mb
                    FROM insight.IdxCat_Index
                    WHERE database_name IN ({placeholders})
                      AND type_desc = N'NONCLUSTERED'
                      AND is_primary_key = 0 AND is_unique_constraint = 0 AND is_unique = 0
                      AND ISNULL(reads, 0) > 0
                      AND ISNULL(writes, 0) > ISNULL(reads, 0)
                      AND ISNULL(writes, 0) >= {wh_writes}
                      AND (
                            ISNULL(writes, 0) - ISNULL(reads, 0) >= {wh_diff}
                         OR ISNULL(writes, 0) >= {wh_ratio} * ISNULL(reads, 0)
                      )
                      AND index_id > 0
                    ORDER BY (ISNULL(writes, 0) - ISNULL(reads, 0)) DESC
                    """,
                    *databases,
                )
                write_heavy_rows = _rows_to_dicts(cur)

                cur.execute(
                    f"""
                    SELECT TOP ({row_cap})
                        database_name, schema_name, table_name, row_count
                    FROM insight.IdxCat_Table
                    WHERE is_heap = 1 AND database_name IN ({placeholders})
                    ORDER BY ISNULL(row_count, 0) DESC
                    """,
                    *databases,
                )
                heap_rows = _rows_to_dicts(cur)

                # Missing-index DMVs are not stored in catalog — soft live peek preferred DB only
                missing_by_table: List[Dict[str, Any]] = []
                missing_count = 0
                peek_db = None
                preferred = (INDEX_PREFERRED_DATABASE or "").strip()
                if preferred and preferred in databases:
                    peek_db = preferred
                elif databases:
                    peek_db = databases[0]
                if peek_db:
                    try:
                        live = _connect_to_database(peek_db)
                        try:
                            try:
                                live.timeout = int(INDEX_OVERVIEW_DB_TIMEOUT_SEC)
                            except Exception:
                                pass
                            lcur = live.cursor()
                            lcur.execute(
                                _OVERVIEW_MISSING_SQL.format(top=row_cap)
                            )
                            for r in _rows_to_dicts(lcur):
                                r["database_name"] = peek_db
                                missing_by_table.append(r)
                            lcur.execute(
                                """
                                SELECT COUNT(*) FROM sys.dm_db_missing_index_details
                                WHERE database_id = DB_ID()
                                """
                            )
                            missing_count = int((lcur.fetchone() or [0])[0] or 0)
                        finally:
                            live.close()
                    except Exception as ex:
                        log.debug("catalog overview missing peek failed: %s", ex)

                totals = {
                    "databases_scanned": db_scanned or len(databases),
                    "indexes": index_count,
                    "unused": len(unused_rows),
                    "write_heavy": len(write_heavy_rows),
                    "heaps": heap_count,
                    "missing_suggestions": missing_count,
                    "need_review": len(unused_rows) + len(write_heavy_rows) + heap_count,
                }
                db_list = self.list_user_databases()
                return {
                    "sqlserver_start_time": sqlserver_start_time,
                    "databases_available": len(db_list.get("databases") or all_dbs),
                    "databases_scanned_list": databases,
                    "scan_mode": "deep" if deep else "quick",
                    "source": "catalog",
                    "totals": totals,
                    "write_heavy": write_heavy_rows[:row_cap],
                    "unused": unused_rows[:row_cap],
                    "heaps": heap_rows[:row_cap],
                    "missing_by_table": missing_by_table[:row_cap],
                    "errors": {},
                    "permissions_hint": db_list.get("permissions_hint"),
                }
            finally:
                conn.close()
        except Exception as ex:
            log.debug("index catalog overview unavailable: %s", ex)
            return None

    def _get_index_overview_live(self, *, deep: bool = False) -> Dict[str, Any]:
        """Live multi-DB DMV scan (fallback when catalog empty/missing)."""
        errors: Dict[str, str] = {}
        db_list = self.list_user_databases()
        all_dbs = list(db_list.get("databases") or [])
        databases = self._overview_database_scope(all_dbs, deep=deep)
        sqlserver_start_time = None
        try:
            conn = connect()
            try:
                cur = conn.cursor()
                cur.execute(_INDEX_START_TIME_SQL)
                row = cur.fetchone()
                sqlserver_start_time = row[0] if row else None
            finally:
                conn.close()
        except Exception as ex:
            errors["start_time"] = str(ex)

        totals = {
            "databases_scanned": 0,
            "indexes": 0,
            "unused": 0,
            "write_heavy": 0,
            "heaps": 0,
            "missing_suggestions": 0,
            "need_review": 0,
        }
        write_heavy_rows: List[Dict[str, Any]] = []
        unused_rows: List[Dict[str, Any]] = []
        heap_rows: List[Dict[str, Any]] = []
        missing_by_table: List[Dict[str, Any]] = []
        db_errors: Dict[str, str] = {}

        for db in databases:
            try:
                conn = _connect_to_database(db)
                try:
                    try:
                        conn.timeout = int(INDEX_OVERVIEW_DB_TIMEOUT_SEC)
                    except Exception:
                        pass
                    cur = conn.cursor()
                    cur.execute(_OVERVIEW_DB_STATS_SQL)
                    stats = _rows_to_dicts(cur)
                    if stats:
                        s = stats[0]
                        totals["indexes"] += int(s.get("index_count") or 0)
                        totals["heaps"] += int(s.get("heap_count") or 0)
                        totals["missing_suggestions"] += int(s.get("missing_count") or 0)

                    cur = conn.cursor()
                    cur.execute(
                        _OVERVIEW_UNUSED_SQL.format(top=int(INDEX_OVERVIEW_FINDING_ROWS))
                    )
                    for r in _rows_to_dicts(cur):
                        r["database_name"] = db
                        unused_rows.append(r)
                        totals["unused"] += 1

                    cur = conn.cursor()
                    cur.execute(
                        _OVERVIEW_WRITE_HEAVY_SQL.format(top=int(INDEX_OVERVIEW_FINDING_ROWS))
                    )
                    for r in _rows_to_dicts(cur):
                        r["database_name"] = db
                        write_heavy_rows.append(r)
                        totals["write_heavy"] += 1

                    cur = conn.cursor()
                    cur.execute(
                        _OVERVIEW_HEAPS_SQL.format(top=int(INDEX_OVERVIEW_FINDING_ROWS))
                    )
                    for r in _rows_to_dicts(cur):
                        r["database_name"] = db
                        heap_rows.append(r)

                    cur = conn.cursor()
                    cur.execute(
                        _OVERVIEW_MISSING_SQL.format(top=int(INDEX_OVERVIEW_FINDING_ROWS))
                    )
                    for r in _rows_to_dicts(cur):
                        r["database_name"] = db
                        missing_by_table.append(r)

                    totals["databases_scanned"] += 1
                finally:
                    conn.close()
            except Exception as ex:
                log.warning("overview scan failed db=%s: %s", db, ex)
                db_errors[db] = str(ex)

        unused_rows.sort(key=lambda r: int(r.get("writes") or 0), reverse=True)
        write_heavy_rows.sort(
            key=lambda r: int(r.get("writes") or 0) - int(r.get("reads") or 0),
            reverse=True,
        )
        missing_by_table.sort(key=lambda r: float(r.get("suggestion_count") or 0), reverse=True)
        row_cap = int(INDEX_OVERVIEW_FINDING_ROWS)
        totals["need_review"] = (
            len(unused_rows) + len(write_heavy_rows) + totals["heaps"]
        )
        return {
            "sqlserver_start_time": sqlserver_start_time,
            "databases_available": len(db_list.get("databases") or []),
            "databases_scanned_list": databases,
            "scan_mode": "deep" if deep else "quick",
            "source": "live",
            "totals": totals,
            "write_heavy": write_heavy_rows[:row_cap],
            "unused": unused_rows[:row_cap],
            "heaps": heap_rows[:row_cap],
            "missing_by_table": missing_by_table[:row_cap],
            "errors": {**errors, **({"databases": db_errors} if db_errors else {})},
            "permissions_hint": db_list.get("permissions_hint"),
        }

    def get_sessions(self, *, top: int = 200) -> QueryResult:
        # Wave 1b / Wave 2 — stub extension point
        return QueryResult.empty(summary={"sessions": 0})

    def get_session_by_id(self, session_id: int) -> QueryResult:
        try:
            sid = int(session_id)
        except (TypeError, ValueError):
            return QueryResult.error("SessionId must be an integer", hint="Enter a numeric SessionId.")
        if sid <= 0:
            return QueryResult.error("SessionId must be > 0", hint="Enter a positive SessionId.")

        try:
            conn = connect()
            try:
                if not has_view_server_state(conn):
                    return QueryResult.error(
                        "VIEW SERVER STATE missing",
                        permission_denied=True,
                        hint=VIEW_SERVER_STATE_HINT,
                    )
                cur = conn.cursor()
                cur.execute(_SESSION_BY_ID_SQL, sid)
                rows = _rows_to_dicts(cur)
            finally:
                conn.close()
        except Exception as ex:
            log.exception("get_session_by_id failed")
            return QueryResult.error(
                str(ex),
                permission_denied=is_permission_error(ex),
                hint=permission_hint_for(ex),
            )

        if not rows:
            return QueryResult.empty(
                summary={"session_id": sid, "found": 0},
                severity=sev.HEALTHY,
            )

        row = rows[0]
        wait_ms = int(row.get("wait_time") or 0)
        level = sev.classify_wait_ms(wait_ms)
        if int(row.get("blocking_session_id") or 0) > 0:
            level = sev.worst(level, sev.IMPORTANT)
        row["severity"] = level

        # Fallback statement extract if SQL SUBSTRING returned empty
        stmt = (row.get("statement_text") or "").strip()
        batch = row.get("sql_text") or ""
        if not stmt and batch and row.get("statement_start_offset") is not None:
            try:
                start = max(0, int(row.get("statement_start_offset") or 0) // 2)
                end_off = row.get("statement_end_offset")
                if end_off is None or int(end_off) < 0:
                    end = len(batch)
                else:
                    end = max(start, int(end_off) // 2)
                stmt = batch[start:end].strip()
                row["statement_text"] = stmt[:4000]
            except Exception:
                pass

        # Live progress (query profiles) + optional PRINT/RAISERROR message history
        progress = _fetch_session_progress(sid)
        row["progress"] = progress

        return QueryResult(
            status="ok",
            severity=level,
            summary={
                "session_id": sid,
                "found": 1,
                "status": row.get("status"),
                "wait_ms": wait_ms,
                "elapsed_wall_ms": int(row.get("elapsed_wall_ms") or 0),
                "blocking_session_id": int(row.get("blocking_session_id") or 0),
                "has_active_request": int(row.get("has_active_request") or 0),
                "percent_complete": row.get("percent_complete"),
                "progress_rows_done": progress.get("rows_done"),
                "progress_rows_est": progress.get("rows_est"),
                "progress_message_count": len(progress.get("messages") or []),
            },
            rows=rows,
            meta={"row_count": 1, "capped": False, "hint": None},
        )

    def get_server_resource_pulse(self) -> QueryResult:
        """Lightweight instance health sample for Session Lookup sparklines."""
        sql = """
SET NOCOUNT ON;
DECLARE @cpu INT = NULL;
;WITH rb AS (
    SELECT CAST(record AS xml) AS rec
    FROM sys.dm_os_ring_buffers
    WHERE ring_buffer_type = N'RING_BUFFER_SCHEDULER_MONITOR'
      AND record LIKE N'%<SystemHealth>%'
)
SELECT TOP (1)
    @cpu = 100 - rec.value('(./Record/SchedulerMonitorEvent/SystemHealth/SystemIdle)[1]', 'int')
FROM rb;

SELECT
    @cpu AS cpu_pct,
    MAX(CASE WHEN counter_name = N'Page reads/sec' THEN cntr_value END) AS page_reads_sec,
    MAX(CASE WHEN counter_name = N'Page writes/sec' THEN cntr_value END) AS page_writes_sec,
    MAX(CASE
            WHEN counter_name = N'Page life expectancy'
             AND (instance_name IS NULL OR instance_name = N'')
            THEN cntr_value
        END) AS page_life_expectancy
FROM sys.dm_os_performance_counters
WHERE object_name LIKE N'%:Buffer Manager%'
  AND counter_name IN (N'Page reads/sec', N'Page writes/sec', N'Page life expectancy');
"""
        try:
            conn = connect()
            try:
                if not has_view_server_state(conn):
                    return QueryResult.error(
                        "VIEW SERVER STATE missing",
                        permission_denied=True,
                        hint=VIEW_SERVER_STATE_HINT,
                    )
                cur = conn.cursor()
                cur.execute(sql)
                # Skip intermediate resultsets if any; last set has the counters
                rows = []
                while True:
                    if cur.description:
                        rows = _rows_to_dicts(cur)
                    if not cur.nextset():
                        break
            finally:
                conn.close()
        except Exception as ex:
            log.exception("get_server_resource_pulse failed")
            return QueryResult.error(str(ex), permission_denied=is_permission_error(ex))

        row = rows[0] if rows else {}
        return QueryResult(
            status="ok",
            severity=sev.HEALTHY,
            summary={
                "cpu_pct": row.get("cpu_pct"),
                "page_reads_sec": row.get("page_reads_sec"),
                "page_writes_sec": row.get("page_writes_sec"),
                "page_life_expectancy": row.get("page_life_expectancy"),
            },
            rows=[row] if row else [],
            meta={"row_count": 1 if row else 0, "capped": False, "hint": None},
        )


def _fetch_session_progress(session_id: int) -> dict:
    """Row progress from dm_exec_query_profiles + optional PRINT messages via XE."""
    out: Dict[str, Any] = {
        "operators": 0,
        "rows_done": 0,
        "rows_est": 0,
        "messages": [],
        "messages_source": None,
        "messages_hint": None,
    }
    try:
        conn = connect()
    except Exception:
        return out
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
SET NOCOUNT ON;
SELECT
    COUNT_BIG(*) AS operators,
    ISNULL(SUM(CAST(row_count AS bigint)), 0) AS rows_done,
    ISNULL(SUM(CAST(estimate_row_count AS bigint)), 0) AS rows_est
FROM sys.dm_exec_query_profiles
WHERE session_id = ?;
""",
                int(session_id),
            )
            prow = cur.fetchone()
            if prow:
                out["operators"] = int(prow[0] or 0)
                out["rows_done"] = int(prow[1] or 0)
                out["rows_est"] = int(prow[2] or 0)
        except Exception:
            log.debug("query_profiles unavailable for session %s", session_id, exc_info=True)

        msgs, source, hint = _read_print_messages(cur, int(session_id))
        out["messages"] = msgs
        out["messages_source"] = source
        out["messages_hint"] = hint
    finally:
        conn.close()
    return out


def _read_print_messages(cur, session_id: int) -> tuple[list, str | None, str | None]:
    """
    Read recent PRINT / low-severity messages for a SPID from optional XE session
    SqlMonitor_PrintMessages (ring_buffer). Soft-fails if session missing.
    """
    hint = (
        "PRINT history is unavailable without Extended Events "
        "(deferred — not enabled on this server). Row progress still comes from query profiles."
    )
    try:
        cur.execute(
            "SELECT 1 FROM sys.dm_xe_sessions WHERE name = N'SqlMonitor_PrintMessages'"
        )
        if not cur.fetchone():
            return [], None, hint

        cur.execute(
            """
SET NOCOUNT ON;
;WITH tgt AS (
    SELECT CAST(st.target_data AS xml) AS x
    FROM sys.dm_xe_session_targets st
    INNER JOIN sys.dm_xe_sessions s ON s.address = st.event_session_address
    WHERE s.name = N'SqlMonitor_PrintMessages'
      AND st.target_name = N'ring_buffer'
)
SELECT TOP (40)
    ev.value('(@timestamp)[1]', 'datetime2') AS ts,
    COALESCE(
        ev.value('(data[@name="message"]/value)[1]', 'nvarchar(4000)'),
        ev.value('(data[@name="message"]/text)[1]', 'nvarchar(4000)')
    ) AS message
FROM tgt
CROSS APPLY x.nodes('/RingBufferTarget/event') AS q(ev)
WHERE ev.value('(action[@name="session_id"]/value)[1]', 'int') = ?
ORDER BY ev.value('(@timestamp)[1]', 'datetime2') DESC;
""",
            session_id,
        )
        rows = _rows_to_dicts(cur)
    except Exception:
        log.debug("print message XE read failed for session %s", session_id, exc_info=True)
        return [], None, hint

    messages = []
    for r in rows or []:
        msg = (r.get("message") or "").strip()
        if not msg:
            continue
        messages.append({"ts": r.get("ts"), "message": msg[:2000]})
    messages.reverse()  # chronological
    if not messages:
        return [], "xe", hint
    return messages, "xe", None


def _touched_object_ids(
    usage_rows: List[Dict[str, Any]],
    heap_rows: List[Dict[str, Any]],
    missing_rows: List[Dict[str, Any]],
) -> List[Any]:
    """Distinct object_ids from usage + heaps + top INDEX_CAP_MISSING missing by score."""
    ids: set = set()
    for row in usage_rows:
        oid = row.get("object_id")
        if oid is not None:
            ids.add(oid)
    for row in heap_rows:
        oid = row.get("object_id")
        if oid is not None:
            ids.add(oid)

    def _score(row: Dict[str, Any]) -> float:
        try:
            return float(row.get("impact_score") or 0)
        except (TypeError, ValueError):
            return 0.0

    ranked_missing = sorted(missing_rows, key=_score, reverse=True)
    for row in ranked_missing[:INDEX_CAP_MISSING]:
        oid = row.get("object_id")
        if oid is not None:
            ids.add(oid)
    return list(ids)


def _fetch_index_inventory(
    conn,
    *,
    usage_rows: List[Dict[str, Any]],
    heap_rows: List[Dict[str, Any]],
    missing_rows: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], str, float]:
    """Duplicate-detection index inventory (v1 strategy, see index-health design spec).

    1. Cheap COUNT of eligible NC indexes decides whether a full-DB inventory
       scan (STRING_AGG/FOR XML) is affordable.
    2. Below INDEX_INVENTORY_MAX_ROWS: run it, log duration + row count.
       Above it: skip straight to a scoped inventory for touched object_ids
       only (usage + heaps + capped missing) — may miss duplicates on cold
       tables, an accepted MVP trade-off vs. scanning the whole DB.
    """
    cur = conn.cursor()
    cur.execute(_INDEX_INVENTORY_COUNT_SQL)
    row = cur.fetchone()
    nc_count = int(row[0]) if row and row[0] is not None else 0

    if nc_count <= INDEX_INVENTORY_MAX_ROWS:
        started = time.perf_counter()
        cur = conn.cursor()
        cur.execute(_INDEX_INVENTORY_SQL_TEMPLATE.format(object_filter=""))
        rows = _rows_to_dicts(cur)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        log.info(
            "index_health.inventory_ms=%.1f index_health.inventory_rows=%d mode=full nc_count=%d",
            elapsed_ms, len(rows), nc_count,
        )
        if elapsed_ms > INDEX_INVENTORY_MAX_MS:
            log.warning(
                "index_health: full inventory took %.1fms (> %dms guideline) — "
                "consider lowering INDEX_INVENTORY_MAX_ROWS",
                elapsed_ms, INDEX_INVENTORY_MAX_MS,
            )
        return rows, "full", elapsed_ms

    log.info(
        "index_health: skipping full inventory (nc_count=%d > INDEX_INVENTORY_MAX_ROWS=%d) "
        "— using touched-object fallback",
        nc_count, INDEX_INVENTORY_MAX_ROWS,
    )
    touched_ids = _touched_object_ids(usage_rows, heap_rows, missing_rows)
    if not touched_ids:
        return [], "touched", 0.0

    started = time.perf_counter()
    placeholders = ",".join("?" for _ in touched_ids)
    sql = _INDEX_INVENTORY_SQL_TEMPLATE.format(
        object_filter=f"AND i.object_id IN ({placeholders})"
    )
    cur = conn.cursor()
    cur.execute(sql, *touched_ids)
    rows = _rows_to_dicts(cur)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    log.info(
        "index_health.inventory_ms=%.1f index_health.inventory_rows=%d mode=touched "
        "touched_object_ids=%d",
        elapsed_ms, len(rows), len(touched_ids),
    )
    return rows, "touched", elapsed_ms


def _connect_to_database(database: str):
    """Open a connection with DATABASE overridden (Indexes DB picker)."""
    cfg = dict(load_config())
    cfg["database"] = (database or cfg.get("database") or "master").strip()
    return connect(cfg)


_LIST_USER_DATABASES_SQL = """
SET NOCOUNT ON;
SELECT d.name AS database_name
FROM sys.databases d
WHERE d.state = 0
  AND d.database_id > 4
  AND HAS_DBACCESS(d.name) = 1
ORDER BY d.name;
"""

_LIST_TABLES_SQL = """
SET NOCOUNT ON;
SELECT TOP ({top})
    s.name AS schema_name,
    t.name AS table_name,
    s.name + N'.' + t.name AS full_name
FROM sys.tables t
INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
WHERE t.is_ms_shipped = 0
  AND (
        ? IS NULL
        OR ? = N''
        OR s.name + N'.' + t.name LIKE N'%' + ? + N'%'
        OR t.name LIKE N'%' + ? + N'%'
      )
ORDER BY s.name, t.name;
"""

# Parameters: OBJECT_ID(?) with N'schema.table' — fast path (no physical_stats)
_TABLE_INDEX_SNAPSHOT_SQL = """
SET NOCOUNT ON;
DECLARE @oid INT = OBJECT_ID(?);
IF @oid IS NULL
BEGIN
    SELECT CAST(NULL AS INT) AS index_id WHERE 1 = 0;
    RETURN;
END;

SELECT
    i.index_id,
    i.name AS index_name,
    i.type_desc,
    CAST(i.is_unique AS bit) AS is_unique,
    CAST(i.is_primary_key AS bit) AS is_primary_key,
    CAST(i.is_unique_constraint AS bit) AS is_unique_constraint,
    CAST(i.is_disabled AS bit) AS is_disabled,
    CAST(i.is_hypothetical AS bit) AS is_hypothetical,
    CAST(i.has_filter AS bit) AS has_filter,
    ISNULL(i.filter_definition, N'') AS filter_def,
    ISNULL(us.user_seeks, 0) + ISNULL(us.user_scans, 0) + ISNULL(us.user_lookups, 0) AS reads,
    ISNULL(us.user_updates, 0) AS writes,
    CAST(ISNULL(ps.used_page_count, 0) * 8.0 / 1024.0 AS float) AS size_mb,
    ISNULL(ps.used_page_count, 0) AS page_count,
    CAST(NULL AS float) AS avg_fragmentation_in_percent,
    ISNULL(keys.key_cols, N'') AS key_cols,
    ISNULL(incs.include_cols, N'') AS include_cols
FROM sys.indexes i
LEFT JOIN sys.dm_db_index_usage_stats us
    ON us.database_id = DB_ID()
   AND us.object_id = i.object_id
   AND us.index_id = i.index_id
LEFT JOIN (
    SELECT object_id, index_id, SUM(used_page_count) AS used_page_count
    FROM sys.dm_db_partition_stats
    WHERE object_id = @oid
    GROUP BY object_id, index_id
) ps ON ps.object_id = i.object_id AND ps.index_id = i.index_id
OUTER APPLY (
    SELECT STUFF((
        SELECT N',' + c.name
        FROM sys.index_columns ic
        INNER JOIN sys.columns c
            ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE ic.object_id = i.object_id
          AND ic.index_id = i.index_id
          AND ic.is_included_column = 0
        ORDER BY ic.key_ordinal
        FOR XML PATH(N''), TYPE
    ).value(N'.', N'nvarchar(max)'), 1, 1, N'') AS key_cols
) keys
OUTER APPLY (
    SELECT STUFF((
        SELECT N',' + c.name
        FROM sys.index_columns ic
        INNER JOIN sys.columns c
            ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE ic.object_id = i.object_id
          AND ic.index_id = i.index_id
          AND ic.is_included_column = 1
        ORDER BY ic.index_column_id
        FOR XML PATH(N''), TYPE
    ).value(N'.', N'nvarchar(max)'), 1, 1, N'') AS include_cols
) incs
WHERE i.object_id = @oid
  AND i.is_hypothetical = 0
ORDER BY i.index_id;
"""

# Optional — can be slow on huge tables; run with short query timeout and soft-fail
_TABLE_FRAG_SQL = """
SET NOCOUNT ON;
DECLARE @oid INT = OBJECT_ID(?);
SELECT
    frag.index_id,
    frag.avg_fragmentation_in_percent,
    frag.page_count
FROM sys.dm_db_index_physical_stats(DB_ID(), @oid, NULL, NULL, N'LIMITED') frag
WHERE frag.alloc_unit_type_desc = N'IN_ROW_DATA';
"""

_TABLE_MISSING_SQL = """
SET NOCOUNT ON;
DECLARE @oid INT = OBJECT_ID(?);
SELECT TOP (25)
    mid.object_id,
    mid.equality_columns,
    mid.inequality_columns,
    mid.included_columns,
    migs.user_seeks,
    migs.avg_user_impact,
    migs.avg_total_user_cost,
    (migs.avg_total_user_cost * migs.avg_user_impact * migs.user_seeks) AS impact_score
FROM sys.dm_db_missing_index_details mid
INNER JOIN sys.dm_db_missing_index_groups mig ON mig.index_handle = mid.index_handle
INNER JOIN sys.dm_db_missing_index_group_stats migs ON migs.group_handle = mig.index_group_handle
WHERE mid.database_id = DB_ID()
  AND mid.object_id = @oid
ORDER BY impact_score DESC;
"""

_TABLE_IS_HEAP_SQL = """
SET NOCOUNT ON;
DECLARE @oid INT = OBJECT_ID(?);
SELECT CASE
    WHEN EXISTS (
        SELECT 1 FROM sys.indexes i
        WHERE i.object_id = @oid AND i.index_id = 0
    ) AND NOT EXISTS (
        SELECT 1 FROM sys.indexes i
        WHERE i.object_id = @oid AND i.index_id = 1
    ) THEN 1 ELSE 0 END AS is_heap;
"""

_TABLE_META_SQL = """
SET NOCOUNT ON;
DECLARE @oid INT = OBJECT_ID(?);
SELECT
    OBJECT_SCHEMA_NAME(@oid) AS schema_name,
    OBJECT_NAME(@oid) AS table_name,
    (SELECT SUM(p.rows) FROM sys.partitions p WHERE p.object_id = @oid AND p.index_id IN (0, 1)) AS row_count,
    CAST((
        SELECT SUM(ps.used_page_count) * 8.0 / 1024.0
        FROM sys.dm_db_partition_stats ps
        WHERE ps.object_id = @oid
    ) AS float) AS size_mb,
    (
        SELECT TOP (1) i.name
        FROM sys.indexes i
        WHERE i.object_id = @oid AND i.type = 1
        ORDER BY i.index_id
    ) AS clustered_index_name,
    (
        SELECT TOP (1) i.name
        FROM sys.indexes i
        WHERE i.object_id = @oid AND i.is_primary_key = 1
        ORDER BY i.index_id
    ) AS primary_key_name,
    (
        SELECT COUNT(*)
        FROM sys.indexes i
        WHERE i.object_id = @oid AND i.index_id > 0 AND i.is_hypothetical = 0
    ) AS index_count;
"""

_OVERVIEW_DB_STATS_SQL = """
SET NOCOUNT ON;
SELECT
    (SELECT COUNT(*) FROM sys.indexes i
     INNER JOIN sys.tables t ON t.object_id = i.object_id
     WHERE t.is_ms_shipped = 0 AND i.index_id > 0 AND i.is_hypothetical = 0) AS index_count,
    (SELECT COUNT(*) FROM sys.tables t
     WHERE t.is_ms_shipped = 0
       AND EXISTS (SELECT 1 FROM sys.indexes i WHERE i.object_id = t.object_id AND i.index_id = 0)
       AND NOT EXISTS (SELECT 1 FROM sys.indexes i WHERE i.object_id = t.object_id AND i.index_id = 1)
    ) AS heap_count,
    (SELECT COUNT(*) FROM sys.dm_db_missing_index_details mid
     WHERE mid.database_id = DB_ID()) AS missing_count;
"""

_OVERVIEW_UNUSED_SQL = """
SET NOCOUNT ON;
SELECT TOP ({top})
    SCHEMA_NAME(o.schema_id) AS schema_name,
    o.name AS table_name,
    i.name AS index_name,
    ISNULL(us.user_updates, 0) AS writes,
    CAST(ISNULL(ps.used_page_count, 0) * 8.0 / 1024.0 AS float) AS size_mb
FROM sys.indexes i
INNER JOIN sys.objects o ON o.object_id = i.object_id
LEFT JOIN sys.dm_db_index_usage_stats us
    ON us.database_id = DB_ID() AND us.object_id = i.object_id AND us.index_id = i.index_id
LEFT JOIN (
    SELECT object_id, index_id, SUM(used_page_count) AS used_page_count
    FROM sys.dm_db_partition_stats GROUP BY object_id, index_id
) ps ON ps.object_id = i.object_id AND ps.index_id = i.index_id
WHERE o.type = 'U'
  AND i.type_desc = N'NONCLUSTERED'
  AND i.is_primary_key = 0 AND i.is_unique_constraint = 0 AND i.is_unique = 0
  AND i.is_disabled = 0 AND i.is_hypothetical = 0
  AND ISNULL(us.user_seeks, 0) + ISNULL(us.user_scans, 0) + ISNULL(us.user_lookups, 0) = 0
ORDER BY ISNULL(us.user_updates, 0) DESC, ISNULL(ps.used_page_count, 0) DESC;
"""

_OVERVIEW_WRITE_HEAVY_SQL = """
SET NOCOUNT ON;
SELECT TOP ({top})
    SCHEMA_NAME(o.schema_id) AS schema_name,
    o.name AS table_name,
    i.name AS index_name,
    ISNULL(us.user_seeks, 0) + ISNULL(us.user_scans, 0) + ISNULL(us.user_lookups, 0) AS reads,
    ISNULL(us.user_updates, 0) AS writes,
    CAST(ISNULL(ps.used_page_count, 0) * 8.0 / 1024.0 AS float) AS size_mb
FROM sys.indexes i
INNER JOIN sys.objects o ON o.object_id = i.object_id
INNER JOIN sys.dm_db_index_usage_stats us
    ON us.database_id = DB_ID() AND us.object_id = i.object_id AND us.index_id = i.index_id
LEFT JOIN (
    SELECT object_id, index_id, SUM(used_page_count) AS used_page_count
    FROM sys.dm_db_partition_stats GROUP BY object_id, index_id
) ps ON ps.object_id = i.object_id AND ps.index_id = i.index_id
WHERE o.type = 'U'
  AND i.type_desc = N'NONCLUSTERED'
  AND i.is_primary_key = 0 AND i.is_unique_constraint = 0 AND i.is_unique = 0
  AND i.is_disabled = 0 AND i.is_hypothetical = 0
  AND (ISNULL(us.user_seeks, 0) + ISNULL(us.user_scans, 0) + ISNULL(us.user_lookups, 0)) > 0
  AND us.user_updates > (ISNULL(us.user_seeks, 0) + ISNULL(us.user_scans, 0) + ISNULL(us.user_lookups, 0))
  AND us.user_updates >= 1000
  AND (
        us.user_updates - (ISNULL(us.user_seeks, 0) + ISNULL(us.user_scans, 0) + ISNULL(us.user_lookups, 0)) >= 10000
     OR us.user_updates >= 10 * (ISNULL(us.user_seeks, 0) + ISNULL(us.user_scans, 0) + ISNULL(us.user_lookups, 0))
  )
ORDER BY (us.user_updates - (ISNULL(us.user_seeks, 0) + ISNULL(us.user_scans, 0) + ISNULL(us.user_lookups, 0))) DESC;
"""

_OVERVIEW_HEAPS_SQL = """
SET NOCOUNT ON;
SELECT TOP ({top})
    SCHEMA_NAME(t.schema_id) AS schema_name,
    t.name AS table_name,
    (SELECT SUM(p.rows) FROM sys.partitions p WHERE p.object_id = t.object_id AND p.index_id = 0) AS row_count
FROM sys.tables t
WHERE t.is_ms_shipped = 0
  AND EXISTS (SELECT 1 FROM sys.indexes i WHERE i.object_id = t.object_id AND i.index_id = 0)
  AND NOT EXISTS (SELECT 1 FROM sys.indexes i WHERE i.object_id = t.object_id AND i.index_id = 1)
ORDER BY row_count DESC;
"""

_OVERVIEW_MISSING_SQL = """
SET NOCOUNT ON;
SELECT TOP ({top})
    OBJECT_SCHEMA_NAME(mid.object_id) AS schema_name,
    OBJECT_NAME(mid.object_id) AS table_name,
    COUNT(*) AS suggestion_count,
    SUM(migs.user_seeks) AS user_seeks
FROM sys.dm_db_missing_index_details mid
INNER JOIN sys.dm_db_missing_index_groups mig ON mig.index_handle = mid.index_handle
INNER JOIN sys.dm_db_missing_index_group_stats migs ON migs.group_handle = mig.index_group_handle
WHERE mid.database_id = DB_ID()
GROUP BY mid.object_id
ORDER BY COUNT(*) DESC, SUM(migs.user_seeks) DESC;
"""


_TABLE_SIZE_LIVE_SQL = """
SET NOCOUNT ON;
SELECT
    DB_NAME() AS database_name,
    s.name AS schema_name,
    t.name AS table_name,
    (SELECT SUM(p.rows) FROM sys.partitions p
     WHERE p.object_id = t.object_id AND p.index_id IN (0,1)) AS row_count,
    CAST((
        SELECT SUM(ps.used_page_count) * 8.0 / 1024.0
        FROM sys.dm_db_partition_stats ps
        WHERE ps.object_id = t.object_id
    ) AS float) AS size_mb,
    CASE WHEN EXISTS (
        SELECT 1 FROM sys.indexes i WHERE i.object_id = t.object_id AND i.index_id = 0
    ) AND NOT EXISTS (
        SELECT 1 FROM sys.indexes i WHERE i.object_id = t.object_id AND i.index_id = 1
    ) THEN CAST(1 AS bit) ELSE CAST(0 AS bit) END AS is_heap
FROM sys.tables t
INNER JOIN sys.schemas s ON s.schema_id = t.schema_id
WHERE t.is_ms_shipped = 0;
"""


def get_provider() -> SqlServerProvider:
    return SqlServerProvider()
