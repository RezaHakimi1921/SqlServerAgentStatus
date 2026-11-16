"""Read-only SQL Server collector prototype for capacity and index insight.

This module collects snapshots only. It never executes DDL or writes to the
monitored SQL Server. Use a least-privilege account and review the permission
requirements for the SQL Server versions in your environment.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional


ConnectionFactory = Callable[[], Any]


@dataclass(frozen=True)
class SqlServerCollectorConfig:
    """Non-secret identity for a monitored database."""

    instance_id: str
    database_name: str
    command_timeout_seconds: int = 30


# FILEPROPERTY('SpaceUsed') is meaningful for data files. It may return NULL
# for log files, so the collector preserves NULL instead of inventing free space.
FILE_CAPACITY_SQL = r"""
SET NOCOUNT ON;
SELECT
    DB_NAME() AS database_name,
    df.file_id,
    df.name AS logical_name,
    df.type_desc AS file_type,
    df.physical_name,
    CONVERT(bigint, df.size) * 8192 AS allocated_bytes,
    CASE WHEN df.type = 0 AND FILEPROPERTY(df.name, 'SpaceUsed') IS NOT NULL
         THEN CONVERT(bigint, FILEPROPERTY(df.name, 'SpaceUsed')) * 8192
         ELSE NULL END AS used_bytes,
    CASE WHEN df.type = 0 AND FILEPROPERTY(df.name, 'SpaceUsed') IS NOT NULL
         THEN CONVERT(bigint, df.size - FILEPROPERTY(df.name, 'SpaceUsed')) * 8192
         ELSE NULL END AS free_inside_file_bytes,
    CASE WHEN df.max_size = -1 THEN NULL
         ELSE CONVERT(bigint, df.max_size) * 8192 END AS max_size_bytes,
    df.growth AS growth_raw,
    df.is_percent_growth
FROM sys.database_files AS df
ORDER BY df.file_id;
"""

# One record per table. Row count is taken from the heap/clustered index only;
# summing row_count across nonclustered indexes would count rows repeatedly.
TABLE_SIZE_SQL = r"""
SET NOCOUNT ON;
SELECT
    DB_NAME() AS database_name,
    s.name AS schema_name,
    t.name AS table_name,
    p.object_id,
    SUM(CASE WHEN p.index_id IN (0, 1) THEN p.row_count ELSE 0 END) AS row_count_approx,
    SUM(p.used_page_count) AS total_used_pages,
    SUM(p.reserved_page_count) AS total_reserved_pages,
    SUM(CASE WHEN p.index_id IN (0, 1) THEN p.used_page_count ELSE 0 END) AS base_used_pages,
    SUM(CASE WHEN p.index_id > 1 THEN p.used_page_count ELSE 0 END) AS nonclustered_used_pages
FROM sys.dm_db_partition_stats AS p
JOIN sys.tables AS t ON t.object_id = p.object_id
JOIN sys.schemas AS s ON s.schema_id = t.schema_id
WHERE t.is_ms_shipped = 0
GROUP BY s.name, t.name, p.object_id
ORDER BY s.name, t.name;
"""

# Index sizes are aggregated by partition before joining to key-column metadata.
# The result repeats size values per column; _shape_index_rows folds those rows.
INDEX_DETAIL_SQL = r"""
SET NOCOUNT ON;
WITH index_space AS (
    SELECT
        object_id,
        index_id,
        SUM(used_page_count) AS used_pages,
        SUM(reserved_page_count) AS reserved_pages
    FROM sys.dm_db_partition_stats
    GROUP BY object_id, index_id
)
SELECT
    DB_NAME() AS database_name,
    s.name AS schema_name,
    t.name AS table_name,
    i.object_id,
    i.index_id,
    i.name AS index_name,
    i.type_desc AS index_type,
    i.is_unique,
    i.is_primary_key,
    i.is_unique_constraint,
    i.is_disabled,
    i.has_filter,
    i.filter_definition,
    ic.key_ordinal,
    ic.is_included_column,
    ic.is_descending_key,
    c.name AS column_name,
    COALESCE(sp.used_pages, 0) AS used_pages,
    COALESCE(sp.reserved_pages, 0) AS reserved_pages
FROM sys.indexes AS i
JOIN sys.tables AS t ON t.object_id = i.object_id
JOIN sys.schemas AS s ON s.schema_id = t.schema_id
LEFT JOIN index_space AS sp ON sp.object_id = i.object_id AND sp.index_id = i.index_id
LEFT JOIN sys.index_columns AS ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
LEFT JOIN sys.columns AS c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE t.is_ms_shipped = 0
ORDER BY s.name, t.name, i.index_id, ic.is_included_column, ic.key_ordinal, ic.index_column_id;
"""

# Usage counters are cumulative since engine start/reset. The startup timestamp
# is returned with every observation so downstream code can reject invalid deltas.
INDEX_USAGE_SQL = r"""
SET NOCOUNT ON;
SELECT
    DB_NAME() AS database_name,
    s.name AS schema_name,
    t.name AS table_name,
    i.object_id,
    i.index_id,
    i.name AS index_name,
    COALESCE(us.user_seeks, 0) AS user_seeks,
    COALESCE(us.user_scans, 0) AS user_scans,
    COALESCE(us.user_lookups, 0) AS user_lookups,
    COALESCE(us.user_updates, 0) AS user_updates,
    us.last_user_seek,
    us.last_user_scan,
    us.last_user_lookup,
    us.last_user_update,
    osi.sqlserver_start_time
FROM sys.indexes AS i
JOIN sys.tables AS t ON t.object_id = i.object_id
JOIN sys.schemas AS s ON s.schema_id = t.schema_id
CROSS JOIN sys.dm_os_sys_info AS osi
LEFT JOIN sys.dm_db_index_usage_stats AS us
  ON us.database_id = DB_ID()
 AND us.object_id = i.object_id
 AND us.index_id = i.index_id
WHERE t.is_ms_shipped = 0
ORDER BY s.name, t.name, i.index_id;
"""


class SqlServerCollector:
    """Collect capacity and index snapshots through an injected connection factory.

    The factory must connect directly to ``config.database_name``. Injecting it
    keeps this module testable and avoids embedding credentials in collector code.
    The connection/cursor are closed even when a query fails.
    """

    def __init__(
        self,
        config: SqlServerCollectorConfig,
        connection_factory: ConnectionFactory,
    ) -> None:
        if not config.instance_id.strip():
            raise ValueError("instance_id must not be empty")
        if not config.database_name.strip():
            raise ValueError("database_name must not be empty")
        if config.command_timeout_seconds < 1:
            raise ValueError("command_timeout_seconds must be positive")
        self.config = config
        self._connection_factory = connection_factory

    def _query(self, sql: str) -> List[Dict[str, Any]]:
        conn = self._connection_factory()
        try:
            cursor = conn.cursor()
            try:
                cursor.timeout = self.config.command_timeout_seconds
                cursor.execute(sql)
                if cursor.description is None:
                    return []
                columns = [column[0] for column in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            finally:
                cursor.close()
        finally:
            conn.close()

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        return None if value is None else int(value)

    def collect_file_capacity(self) -> List[Dict[str, Any]]:
        observed_at = datetime.now(timezone.utc).isoformat()
        rows = self._query(FILE_CAPACITY_SQL)
        result = []
        for row in rows:
            result.append({
                "instance_id": self.config.instance_id,
                "database_name": row["database_name"],
                "file_id": int(row["file_id"]),
                "logical_name": row["logical_name"],
                "file_type": row["file_type"],
                "physical_name": row["physical_name"],
                "allocated_bytes": int(row["allocated_bytes"]),
                "used_bytes": self._to_int(row["used_bytes"]),
                "free_inside_file_bytes": self._to_int(row["free_inside_file_bytes"]),
                "max_size_bytes": self._to_int(row["max_size_bytes"]),
                "growth_raw": int(row["growth_raw"]),
                "is_percent_growth": bool(row["is_percent_growth"]),
                "observed_at_utc": observed_at,
                "quality": "ok" if row["used_bytes"] is not None or row["file_type"] != "ROWS" else "partial",
            })
        return result

    def collect_table_sizes(self) -> List[Dict[str, Any]]:
        observed_at = datetime.now(timezone.utc).isoformat()
        rows = self._query(TABLE_SIZE_SQL)
        result = []
        for row in rows:
            result.append({
                "instance_id": self.config.instance_id,
                "database_name": row["database_name"],
                "schema_name": row["schema_name"],
                "table_name": row["table_name"],
                "object_id": int(row["object_id"]),
                "row_count_approx": int(row["row_count_approx"]),
                "total_used_bytes": int(row["total_used_pages"]) * 8192,
                "total_reserved_bytes": int(row["total_reserved_pages"]) * 8192,
                "base_used_bytes": int(row["base_used_pages"]) * 8192,
                "nonclustered_used_bytes": int(row["nonclustered_used_pages"]) * 8192,
                "observed_at_utc": observed_at,
                "quality": "approximate",
            })
        return result

    def collect_index_details(self) -> List[Dict[str, Any]]:
        observed_at = datetime.now(timezone.utc).isoformat()
        rows = self._query(INDEX_DETAIL_SQL)
        return self._shape_index_rows(rows, observed_at)

    def collect_index_usage(self) -> List[Dict[str, Any]]:
        observed_at = datetime.now(timezone.utc).isoformat()
        rows = self._query(INDEX_USAGE_SQL)
        result = []
        for row in rows:
            result.append({
                "instance_id": self.config.instance_id,
                "database_name": row["database_name"],
                "schema_name": row["schema_name"],
                "table_name": row["table_name"],
                "object_id": int(row["object_id"]),
                "index_id": int(row["index_id"]),
                "index_name": row["index_name"],
                "user_seeks": int(row["user_seeks"]),
                "user_scans": int(row["user_scans"]),
                "user_lookups": int(row["user_lookups"]),
                "user_updates": int(row["user_updates"]),
                "last_user_seek": row["last_user_seek"],
                "last_user_scan": row["last_user_scan"],
                "last_user_lookup": row["last_user_lookup"],
                "last_user_update": row["last_user_update"],
                "sqlserver_start_time": row["sqlserver_start_time"],
                "observed_at_utc": observed_at,
                "quality": "ok" if row["sqlserver_start_time"] is not None else "partial",
            })
        return result

    def collect_snapshot(self) -> Dict[str, Any]:
        """Collect one sequential snapshot; caller persists it in its repository."""
        started_at = datetime.now(timezone.utc).isoformat()
        return {
            "instance_id": self.config.instance_id,
            "database_name": self.config.database_name,
            "started_at_utc": started_at,
            "file_capacity": self.collect_file_capacity(),
            "table_sizes": self.collect_table_sizes(),
            "index_details": self.collect_index_details(),
            "index_usage": self.collect_index_usage(),
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "collector_version": "0.1.0",
        }

    def _shape_index_rows(
        self, rows: Iterable[Dict[str, Any]], observed_at: str
    ) -> List[Dict[str, Any]]:
        grouped: Dict[tuple, Dict[str, Any]] = {}
        for row in rows:
            key = (row["object_id"], row["index_id"])
            item = grouped.get(key)
            if item is None:
                item = {
                    "instance_id": self.config.instance_id,
                    "database_name": row["database_name"],
                    "schema_name": row["schema_name"],
                    "table_name": row["table_name"],
                    "object_id": int(row["object_id"]),
                    "index_id": int(row["index_id"]),
                    "index_name": row["index_name"],
                    "index_type": row["index_type"],
                    "is_unique": bool(row["is_unique"]),
                    "is_primary_key": bool(row["is_primary_key"]),
                    "is_unique_constraint": bool(row["is_unique_constraint"]),
                    "is_disabled": bool(row["is_disabled"]),
                    "has_filter": bool(row["has_filter"]),
                    "filter_definition": row["filter_definition"],
                    "used_bytes": int(row["used_pages"]) * 8192,
                    "reserved_bytes": int(row["reserved_pages"]) * 8192,
                    "key_columns": [],
                    "included_columns": [],
                    "observed_at_utc": observed_at,
                    "quality": "metadata_snapshot",
                }
                grouped[key] = item
            column_name = row["column_name"]
            if column_name is None:
                continue
            if bool(row["is_included_column"]):
                item["included_columns"].append(column_name)
            elif row["key_ordinal"] is not None and int(row["key_ordinal"]) > 0:
                item["key_columns"].append({
                    "ordinal": int(row["key_ordinal"]),
                    "name": column_name,
                    "descending": bool(row["is_descending_key"]),
                })
        result = list(grouped.values())
        for item in result:
            item["key_columns"].sort(key=lambda column: column["ordinal"])
            item["included_columns"] = sorted(set(item["included_columns"]))
        return result


def build_default_connection_factory(database_name: str) -> ConnectionFactory:
    """Build a factory using the project's existing connection configuration.

    Call this from the repository root after the app's SQL connection settings
    have been configured. The database name is escaped by the existing ODBC
    connection-string builder. This creates a fresh short-lived connection per
    collector query; the prototype intentionally does not pool connections.
    """
    from config import build_conn_str, load_config
    import pyodbc

    config = load_config()
    config["database"] = database_name
    timeout = config.get("timeout", 10)
    connection_string = build_conn_str(config)

    def connect():
        return pyodbc.connect(connection_string, timeout=timeout)

    return connect
