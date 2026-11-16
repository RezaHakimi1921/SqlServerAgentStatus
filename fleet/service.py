"""Fleet health probes for registered SQL Server instances.

Probes execute a small read-only SELECT with a connection timeout and persist
only sanitized results. They do not collect Job/Query Store or host metrics.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from fleet.store import MonitoringStore


ConnectionFactoryBuilder = Callable[[Dict[str, Any]], Callable[[], Any]]


def _classify_connection_error(exc: Exception) -> tuple[str, str]:
    """Map driver errors to safe categories without returning raw driver text."""
    state = ""
    try:
        args = getattr(exc, "args", ())
        if args:
            state = str(args[0]).upper()
    except Exception:
        pass
    if state.startswith("28"):
        return "authentication_failed", "SQL Server rejected the configured credentials."
    if state.startswith("08") or state in {"IM002", "HYT00", "HYT01"}:
        return "connection_failed", "SQL Server could not be reached within the configured timeout."
    if state.startswith("42"):
        return "permission_or_query_error", "The health query was rejected by SQL Server permissions or compatibility."
    return "connection_error", "The SQL Server health check failed; inspect sanitized application diagnostics."


def default_connection_factory_builder(instance: Dict[str, Any]) -> Callable[[], Any]:
    """Create a pyodbc connection factory from registry metadata and OS keyring."""
    import pyodbc
    from config import build_conn_str
    from secrets_store import get_sql_password

    password = get_sql_password(instance["server"], instance["user_name"])
    if not password:
        raise RuntimeError("credential_not_configured")
    cfg = {
        "server": instance["server"],
        "database": instance["database_name"],
        "user": instance["user_name"],
        "password": password,
        "driver": instance["driver"],
        "timeout": instance["timeout_seconds"],
        "encrypt": "no",
        "trust_cert": "yes",
    }
    conn_string = build_conn_str(cfg)
    return lambda: pyodbc.connect(conn_string, timeout=instance["timeout_seconds"])


class FleetService:
    def __init__(self, store: MonitoringStore,
                 connection_factory_builder: ConnectionFactoryBuilder = default_connection_factory_builder,
                 credential_setter: Optional[Callable[[str, str, str], None]] = None,
                 unreachable_failure_threshold: int = 3) -> None:
        self.store = store
        self.connection_factory_builder = connection_factory_builder
        self.credential_setter = credential_setter
        self.unreachable_failure_threshold = max(1, int(unreachable_failure_threshold))

    def set_credential(self, instance_id: str, password: str) -> None:
        if not password:
            raise ValueError("password must not be empty")
        instance = next((row for row in self.store.list_instances()
                         if row["instance_id"] == instance_id), None)
        if instance is None:
            raise KeyError("instance not found")
        setter = self.credential_setter
        if setter is None:
            from secrets_store import set_sql_password
            setter = set_sql_password
        setter(instance["server"], instance["user_name"], password)

    def probe_instance(self, instance_id: str) -> Dict[str, Any]:
        matches = [row for row in self.store.list_instances() if row["instance_id"] == instance_id]
        if not matches:
            raise KeyError("instance not found")
        instance = matches[0]
        if not instance["enabled"]:
            self.store.record_health(instance_id, status="disabled")
            return {"instance_id": instance_id, "status": "disabled"}

        started = time.monotonic()
        conn = None
        try:
            factory = self.connection_factory_builder(instance)
            conn = factory()
            cursor = conn.cursor()
            try:
                cursor.timeout = min(max(int(instance["timeout_seconds"]), 1), 300)
                cursor.execute("""
                    SET NOCOUNT ON;
                    SELECT @@SERVERNAME AS server_name,
                           CONVERT(nvarchar(128), SERVERPROPERTY('ProductVersion')) AS product_version,
                           DB_NAME() AS database_name;
                """)
                row = cursor.fetchone()
            finally:
                cursor.close()
            duration_ms = int((time.monotonic() - started) * 1000)
            server_name = row[0] if row else None
            product_version = row[1] if row else None
            self.store.record_health(
                instance_id, status="healthy", server_name=server_name,
                product_version=product_version, duration_ms=duration_ms,
            )
            return {"instance_id": instance_id, "status": "healthy",
                    "server_name": server_name, "product_version": product_version,
                    "duration_ms": duration_ms}
        except Exception as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            if str(exc) == "credential_not_configured":
                code, summary = "credential_not_configured", "No credential is configured in the OS secret store."
                status = "degraded"
            else:
                code, summary = _classify_connection_error(exc)
                status = "degraded"
                if code == "connection_failed":
                    previous = self.store.list_health_checks(
                        instance_id, limit=max(0, self.unreachable_failure_threshold - 1)
                    )
                    consecutive_failures = 0
                    for check in previous:
                        if check["error_code"] != "connection_failed":
                            break
                        consecutive_failures += 1
                    if consecutive_failures >= self.unreachable_failure_threshold - 1:
                        status = "unreachable"
            self.store.record_health(
                instance_id, status=status, error_code=code,
                error_summary=summary, duration_ms=duration_ms,
            )
            return {"instance_id": instance_id, "status": status,
                    "error_code": code, "error_summary": summary,
                    "duration_ms": duration_ms}
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def probe_enabled_instances(self) -> List[Dict[str, Any]]:
        """Probe every enabled instance independently; one failure never aborts the fleet."""
        results = []
        for instance in self.store.list_instances(enabled_only=True):
            try:
                results.append(self.probe_instance(instance["instance_id"]))
            except Exception:
                # A persistence or unexpected per-instance error is sanitized and isolated.
                results.append({"instance_id": instance["instance_id"],
                                "status": "degraded", "error_code": "probe_internal_error",
                                "error_summary": "The probe failed internally; check application diagnostics."})
        return results
