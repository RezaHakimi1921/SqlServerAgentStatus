"""Local durable metadata store for Fleet and alerting foundations.

This store is separate from monitored SQL Server databases. It contains no
passwords or webhook signing keys; those belong in an OS-backed secret store.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


HEALTH_STATES = {"healthy", "degraded", "unreachable", "disabled", "unknown"}
ALERT_SEVERITIES = {"critical", "high", "warning", "info"}
ALERT_STATUSES = {"new", "acknowledged", "investigating", "resolved", "suppressed"}
TARGET_CHANNELS = {"email", "webhook"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_store_path() -> Path:
    configured = os.environ.get("SQLMONITOR_STATE_DB", "").strip()
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SqlServerAgentStatus"
    else:
        root = Path.home() / ".local" / "share" / "SqlServerAgentStatus"
    return root / "monitoring.sqlite3"


class MonitoringStore:
    """SQLite repository for local/single-user Fleet and alerting MVP."""

    def __init__(self, path: Optional[Union[os.PathLike, str]] = None) -> None:
        self._managed_data_dir = path is None
        self.path = Path(path).expanduser() if path else default_store_path()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._initialize()
        if self._managed_data_dir and os.name != "nt":
            try:
                self.path.parent.chmod(0o700)
            except OSError:
                pass

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS monitored_instance (
                    instance_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    server TEXT NOT NULL,
                    database_name TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    driver TEXT NOT NULL,
                    timeout_seconds INTEGER NOT NULL DEFAULT 10,
                    environment TEXT NOT NULL DEFAULT 'unspecified',
                    group_name TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS instance_health (
                    instance_id TEXT PRIMARY KEY REFERENCES monitored_instance(instance_id),
                    status TEXT NOT NULL,
                    checked_at_utc TEXT NOT NULL,
                    last_success_at_utc TEXT,
                    error_code TEXT,
                    error_summary TEXT,
                    server_name TEXT,
                    product_version TEXT,
                    duration_ms INTEGER
                );
                CREATE TABLE IF NOT EXISTS instance_health_check (
                    check_id TEXT PRIMARY KEY,
                    instance_id TEXT NOT NULL REFERENCES monitored_instance(instance_id),
                    status TEXT NOT NULL,
                    checked_at_utc TEXT NOT NULL,
                    error_code TEXT,
                    error_summary TEXT,
                    server_name TEXT,
                    product_version TEXT,
                    duration_ms INTEGER
                );
                CREATE INDEX IF NOT EXISTS ix_health_check_instance_time
                    ON instance_health_check(instance_id, checked_at_utc DESC);
                CREATE TABLE IF NOT EXISTS alert_event (
                    event_id TEXT PRIMARY KEY,
                    dedup_key TEXT NOT NULL,
                    instance_id TEXT REFERENCES monitored_instance(instance_id),
                    rule_id TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    first_seen_utc TEXT NOT NULL,
                    last_seen_utc TEXT NOT NULL,
                    occurrences INTEGER NOT NULL DEFAULT 1,
                    acknowledged_by TEXT,
                    acknowledged_at_utc TEXT,
                    resolved_at_utc TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_alert_status_severity
                    ON alert_event(status, severity, last_seen_utc);
                CREATE UNIQUE INDEX IF NOT EXISTS ux_alert_open_dedup
                    ON alert_event(dedup_key)
                    WHERE status IN ('new', 'acknowledged', 'investigating');
                CREATE TABLE IF NOT EXISTS notification_target (
                    target_id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    name TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notification_outbox (
                    delivery_id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL REFERENCES alert_event(event_id),
                    target_id TEXT NOT NULL REFERENCES notification_target(target_id),
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at_utc TEXT NOT NULL,
                    last_error TEXT,
                    created_at_utc TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    UNIQUE(event_id, target_id)
                );
                CREATE INDEX IF NOT EXISTS ix_outbox_pending
                    ON notification_outbox(status, next_attempt_at_utc);
                CREATE TABLE IF NOT EXISTS notification_attempt (
                    attempt_id TEXT PRIMARY KEY,
                    delivery_id TEXT NOT NULL REFERENCES notification_outbox(delivery_id),
                    attempt_number INTEGER NOT NULL,
                    started_at_utc TEXT NOT NULL,
                    completed_at_utc TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    status_code INTEGER,
                    sanitized_error TEXT,
                    UNIQUE(delivery_id, attempt_number)
                );
            """)
        if os.name != "nt":
            try:
                self.path.chmod(0o600)
            except OSError:
                pass

    @staticmethod
    def _dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
        return dict(row) if row is not None else None

    def add_instance(
        self,
        *,
        display_name: str,
        server: str,
        database_name: str,
        user_name: str,
        driver: str = "17",
        timeout_seconds: int = 10,
        environment: str = "unspecified",
        group_name: str = "",
        instance_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        fields = [display_name, server, database_name, user_name, driver]
        if any(not str(value).strip() for value in fields):
            raise ValueError("display_name, server, database_name, user_name and driver are required")
        if int(timeout_seconds) < 1 or int(timeout_seconds) > 300:
            raise ValueError("timeout_seconds must be between 1 and 300")
        now, identifier = utc_now(), instance_id or str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO monitored_instance (
                    instance_id, display_name, server, database_name, user_name,
                    driver, timeout_seconds, environment, group_name, enabled,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (identifier, display_name.strip(), server.strip(), database_name.strip(),
                  user_name.strip(), str(driver).strip(), int(timeout_seconds),
                  (environment or "unspecified").strip(), (group_name or "").strip(), now, now))
            row = conn.execute("SELECT * FROM monitored_instance WHERE instance_id=?", (identifier,)).fetchone()
        return self._dict(row) or {}

    def list_instances(self, *, enabled_only: bool = False) -> List[Dict[str, Any]]:
        where = "WHERE i.enabled = 1" if enabled_only else ""
        with self._connect() as conn:
            rows = conn.execute(f"""
                SELECT i.*, h.status AS health_status, h.checked_at_utc,
                       h.last_success_at_utc, h.error_code, h.error_summary,
                       h.server_name, h.product_version, h.duration_ms
                FROM monitored_instance AS i
                LEFT JOIN instance_health AS h ON h.instance_id = i.instance_id
                {where}
                ORDER BY i.environment, i.group_name, i.display_name
            """).fetchall()
        return [dict(row) for row in rows]

    def set_instance_enabled(self, instance_id: str, enabled: bool) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE monitored_instance SET enabled=?, updated_at_utc=? WHERE instance_id=?",
                (int(bool(enabled)), utc_now(), instance_id),
            )
            return cursor.rowcount > 0

    def record_health(
        self,
        instance_id: str,
        *,
        status: str,
        error_code: Optional[str] = None,
        error_summary: Optional[str] = None,
        server_name: Optional[str] = None,
        product_version: Optional[str] = None,
        duration_ms: Optional[int] = None,
        checked_at_utc: Optional[str] = None,
    ) -> None:
        if status not in HEALTH_STATES:
            raise ValueError(f"unsupported health status: {status}")
        checked = checked_at_utc or utc_now()
        with self._connect() as conn:
            if status == "healthy":
                conn.execute("""
                    INSERT INTO instance_health (
                        instance_id, status, checked_at_utc, last_success_at_utc,
                        error_code, error_summary, server_name, product_version, duration_ms
                    ) VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?)
                    ON CONFLICT(instance_id) DO UPDATE SET
                        status=excluded.status,
                        checked_at_utc=excluded.checked_at_utc,
                        last_success_at_utc=excluded.last_success_at_utc,
                        error_code=NULL, error_summary=NULL,
                        server_name=excluded.server_name,
                        product_version=excluded.product_version,
                        duration_ms=excluded.duration_ms
                """, (instance_id, status, checked, checked, server_name, product_version, duration_ms))
            else:
                conn.execute("""
                    INSERT INTO instance_health (
                        instance_id, status, checked_at_utc, error_code,
                        error_summary, duration_ms
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(instance_id) DO UPDATE SET
                        status=excluded.status,
                        checked_at_utc=excluded.checked_at_utc,
                        error_code=excluded.error_code,
                        error_summary=excluded.error_summary,
                        duration_ms=excluded.duration_ms
                """, (instance_id, status, checked, error_code, error_summary, duration_ms))
            conn.execute("""
                INSERT INTO instance_health_check (
                    check_id, instance_id, status, checked_at_utc, error_code,
                    error_summary, server_name, product_version, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), instance_id, status, checked, error_code,
                  error_summary, server_name if status == "healthy" else None,
                  product_version if status == "healthy" else None, duration_ms))

    def list_health_checks(self, instance_id: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        limit = min(max(int(limit), 1), 500)
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM instance_health_check
                WHERE instance_id=? ORDER BY checked_at_utc DESC LIMIT ?
            """, (instance_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def fleet_summary(self) -> Dict[str, Any]:
        with self._connect() as conn:
            counts = {state: 0 for state in HEALTH_STATES}
            for row in conn.execute("""
                SELECT CASE WHEN i.enabled=0 THEN 'disabled'
                            ELSE COALESCE(h.status, 'unknown') END AS state, COUNT(*) AS n
                FROM monitored_instance i
                LEFT JOIN instance_health h ON h.instance_id=i.instance_id
                GROUP BY state
            """):
                counts[row["state"]] = row["n"]
            alerts = {severity: 0 for severity in ALERT_SEVERITIES}
            for row in conn.execute("""
                SELECT severity, COUNT(*) AS n FROM alert_event
                WHERE status IN ('new','acknowledged','investigating') GROUP BY severity
            """):
                alerts[row["severity"]] = row["n"]
        return {"instances": counts, "open_alerts": alerts, "generated_at_utc": utc_now()}

    def upsert_alert(
        self,
        *,
        dedup_key: str,
        rule_id: str,
        severity: str,
        title: str,
        summary: str,
        evidence: Optional[Dict[str, Any]] = None,
        instance_id: Optional[str] = None,
        observed_at_utc: Optional[str] = None,
    ) -> Dict[str, Any]:
        if severity not in ALERT_SEVERITIES:
            raise ValueError(f"unsupported severity: {severity}")
        if not dedup_key.strip() or not rule_id.strip() or not title.strip():
            raise ValueError("dedup_key, rule_id and title are required")
        now = observed_at_utc or utc_now()
        evidence_json = json.dumps(evidence or {}, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("""
                SELECT * FROM alert_event WHERE dedup_key=?
                  AND status IN ('new','acknowledged','investigating')
            """, (dedup_key,)).fetchone()
            if row:
                conn.execute("""
                    UPDATE alert_event SET last_seen_utc=?, occurrences=occurrences+1,
                        severity=?, title=?, summary=?, evidence_json=?
                    WHERE event_id=?
                """, (now, severity, title, summary, evidence_json, row["event_id"]))
                event_id = row["event_id"]
            else:
                event_id = str(uuid.uuid4())
                conn.execute("""
                    INSERT INTO alert_event (
                        event_id, dedup_key, instance_id, rule_id, severity, status,
                        title, summary, evidence_json, first_seen_utc, last_seen_utc
                    ) VALUES (?, ?, ?, ?, ?, 'new', ?, ?, ?, ?, ?)
                """, (event_id, dedup_key, instance_id, rule_id, severity, title,
                      summary, evidence_json, now, now))
            saved = conn.execute("SELECT * FROM alert_event WHERE event_id=?", (event_id,)).fetchone()
        return self._alert_dict(saved)

    @staticmethod
    def _alert_dict(row: sqlite3.Row) -> Dict[str, Any]:
        result = dict(row)
        result["evidence"] = json.loads(result.pop("evidence_json"))
        return result

    def get_alert(self, event_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM alert_event WHERE event_id=?", (event_id,)).fetchone()
        return self._alert_dict(row) if row else None

    def list_alerts(self, *, status: Optional[str] = None, severity: Optional[str] = None,
                    limit: int = 100) -> List[Dict[str, Any]]:
        limit = min(max(int(limit), 1), 500)
        clauses, values = [], []
        if status:
            if status not in ALERT_STATUSES:
                raise ValueError("unsupported alert status")
            clauses.append("status=?")
            values.append(status)
        if severity:
            if severity not in ALERT_SEVERITIES:
                raise ValueError("unsupported severity")
            clauses.append("severity=?")
            values.append(severity)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM alert_event {where} ORDER BY last_seen_utc DESC LIMIT ?",
                (*values, limit),
            ).fetchall()
        return [self._alert_dict(row) for row in rows]

    def acknowledge_alert(self, event_id: str, actor: str, *, investigating: bool = False) -> bool:
        if not actor.strip():
            raise ValueError("actor is required")
        status = "investigating" if investigating else "acknowledged"
        with self._connect() as conn:
            cursor = conn.execute("""
                UPDATE alert_event SET status=?, acknowledged_by=?, acknowledged_at_utc=?
                WHERE event_id=? AND status IN ('new','acknowledged','investigating')
            """, (status, actor.strip(), utc_now(), event_id))
            return cursor.rowcount > 0

    def resolve_alert(self, event_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("""
                UPDATE alert_event SET status='resolved', resolved_at_utc=?
                WHERE event_id=? AND status IN ('new','acknowledged','investigating')
            """, (utc_now(), event_id))
            return cursor.rowcount > 0

    def add_notification_target(self, *, channel: str, name: str,
                                config: Dict[str, Any], target_id: Optional[str] = None) -> Dict[str, Any]:
        if channel not in TARGET_CHANNELS:
            raise ValueError("channel must be email or webhook")
        if not name.strip():
            raise ValueError("target name is required")
        if not isinstance(config, dict):
            raise ValueError("target config must be a dictionary")
        forbidden = ("password", "secret", "token", "api_key", "hmac_key", "credential")

        def contains_secret_key(value: Any) -> bool:
            if isinstance(value, dict):
                return any(any(part in str(key).lower() for part in forbidden)
                           or contains_secret_key(item) for key, item in value.items())
            if isinstance(value, (list, tuple)):
                return any(contains_secret_key(item) for item in value)
            return False

        if contains_secret_key(config):
            raise ValueError("secrets must be stored in the OS secret store, not target config")
        if channel == "webhook":
            parsed = urllib.parse.urlsplit(str(config.get("url", "")))
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                    or parsed.password or parsed.query):
                raise ValueError("webhook target must be HTTPS without embedded credentials or query parameters")
        identifier, now = target_id or str(uuid.uuid4()), utc_now()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO notification_target
                    (target_id, channel, name, config_json, enabled, created_at_utc, updated_at_utc)
                VALUES (?, ?, ?, ?, 1, ?, ?)
            """, (identifier, channel, name.strip(),
                  json.dumps(config, ensure_ascii=False, sort_keys=True), now, now))
        return {"target_id": identifier, "channel": channel, "name": name.strip(),
                "config": config, "enabled": True}

    def list_notification_targets(self, *, enabled_only: bool = False) -> List[Dict[str, Any]]:
        where = "WHERE enabled=1" if enabled_only else ""
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM notification_target {where} ORDER BY name").fetchall()
        return [{**dict(row), "config": json.loads(row["config_json"])} for row in rows]

    def get_notification_target(self, target_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM notification_target WHERE target_id=?", (target_id,)).fetchone()
        return ({**dict(row), "config": json.loads(row["config_json"]) } if row else None)

    def enqueue_alert_for_targets(self, event_id: str) -> int:
        event = self.get_alert(event_id)
        if not event:
            raise KeyError("alert event not found")
        enqueued = 0
        for target in self.list_notification_targets(enabled_only=True):
            severities = target["config"].get("severities")
            if severities and event["severity"] not in severities:
                continue
            if self.enqueue_notification(event_id, target["target_id"]):
                enqueued += 1
        return enqueued

    def enqueue_notification(self, event_id: str, target_id: str) -> bool:
        now, delivery_id = utc_now(), str(uuid.uuid4())
        with self._connect() as conn:
            cursor = conn.execute("""
                INSERT OR IGNORE INTO notification_outbox (
                    delivery_id, event_id, target_id, status, next_attempt_at_utc,
                    created_at_utc, updated_at_utc
                ) VALUES (?, ?, ?, 'pending', ?, ?, ?)
            """, (delivery_id, event_id, target_id, now, now, now))
            return cursor.rowcount > 0

    def claim_notifications(self, *, limit: int = 20, now_utc: Optional[str] = None) -> List[Dict[str, Any]]:
        now, limit = now_utc or utc_now(), min(max(int(limit), 1), 100)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute("""
                SELECT o.*, t.channel, t.name AS target_name, t.config_json,
                       e.event_id AS event_id_value
                FROM notification_outbox o
                JOIN notification_target t ON t.target_id=o.target_id AND t.enabled=1
                JOIN alert_event e ON e.event_id=o.event_id
                WHERE o.status IN ('pending','retry') AND o.next_attempt_at_utc <= ?
                ORDER BY o.created_at_utc LIMIT ?
            """, (now, limit)).fetchall()
            ids = [row["delivery_id"] for row in rows]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                conn.execute(
                    f"UPDATE notification_outbox SET status='sending', updated_at_utc=? WHERE delivery_id IN ({placeholders})",
                    (now, *ids),
                )
        results = []
        for row in rows:
            item = {**dict(row), "config": json.loads(row["config_json"])}
            item["status"] = "sending"
            item["updated_at_utc"] = now
            results.append(item)
        return results

    def record_delivery_attempt(self, delivery_id: str, *, success: bool,
                                status_code: Optional[int] = None,
                                sanitized_error: Optional[str] = None,
                                max_attempts: int = 5,
                                started_at_utc: Optional[str] = None,
                                now: Optional[datetime] = None) -> Dict[str, Any]:
        current = now or datetime.now(timezone.utc)
        completed = current.astimezone(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM notification_outbox WHERE delivery_id=?", (delivery_id,)).fetchone()
            if row is None:
                raise KeyError("delivery not found")
            attempt = int(row["attempt_count"]) + 1
            outcome = "delivered" if success else ("dead" if attempt >= max_attempts else "retry")
            delay_seconds = min(30 * (2 ** max(0, attempt - 1)), 3600)
            next_attempt = (current + timedelta(seconds=delay_seconds)).astimezone(timezone.utc).isoformat()
            conn.execute("""
                INSERT INTO notification_attempt (
                    attempt_id, delivery_id, attempt_number, started_at_utc,
                    completed_at_utc, outcome, status_code, sanitized_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), delivery_id, attempt, started_at_utc or completed, completed,
                  outcome, status_code, None if success else (sanitized_error or "delivery failed")[:500]))
            conn.execute("""
                UPDATE notification_outbox SET status=?, attempt_count=?,
                    next_attempt_at_utc=?, last_error=?, updated_at_utc=?
                WHERE delivery_id=?
            """, (outcome, attempt, next_attempt,
                  None if success else (sanitized_error or "delivery failed")[:500], completed, delivery_id))
        return {"delivery_id": delivery_id, "status": outcome,
                "attempt_count": attempt, "next_attempt_at_utc": next_attempt}

    def recover_stale_sending(self, *, stale_before_utc: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute("""
                UPDATE notification_outbox SET status='retry', next_attempt_at_utc=?,
                    updated_at_utc=?, last_error='recovered stale in-progress delivery'
                WHERE status='sending' AND updated_at_utc < ?
            """, (utc_now(), utc_now(), stale_before_utc))
            return cursor.rowcount
