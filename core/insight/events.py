"""Persist / update rows in insight.insight_events."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence

from core.insight.store import get_monitor_connection
from core.logging_setup import get_logger

log = get_logger("sqlmonitor.insight.events")

_ENSURE_EVIDENCE_SQL = """
IF COL_LENGTH(N'insight.insight_events', N'evidence_json') IS NULL
    ALTER TABLE insight.insight_events ADD evidence_json NVARCHAR(MAX) NULL;
"""

_UPSERT_SQL = """
MERGE insight.insight_events AS t
USING (SELECT ? AS dedupe_key) AS s
ON t.dedupe_key = s.dedupe_key
WHEN MATCHED THEN UPDATE SET
    last_seen_at = ?,
    severity = ?,
    title = ?,
    detail = ?,
    occurrence_count = ?,
    scope_label = COALESCE(?, t.scope_label),
    link_target = ?,
    evidence_json = COALESCE(?, t.evidence_json)
WHEN NOT MATCHED THEN INSERT (
    created_at, first_seen_at, last_seen_at,
    severity, rule_id, scope, scope_id, scope_label,
    title, detail, occurrence_count, dedupe_key, link_target, evidence_json
) VALUES (
    ?, ?, ?,
    ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?, ?
);
"""

_UPSERT_SQL_NO_EVIDENCE = """
MERGE insight.insight_events AS t
USING (SELECT ? AS dedupe_key) AS s
ON t.dedupe_key = s.dedupe_key
WHEN MATCHED THEN UPDATE SET
    last_seen_at = ?,
    severity = ?,
    title = ?,
    detail = ?,
    occurrence_count = ?,
    scope_label = COALESCE(?, t.scope_label),
    link_target = ?
WHEN NOT MATCHED THEN INSERT (
    created_at, first_seen_at, last_seen_at,
    severity, rule_id, scope, scope_id, scope_label,
    title, detail, occurrence_count, dedupe_key, link_target
) VALUES (
    ?, ?, ?,
    ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?
);
"""

_evidence_ready: Optional[bool] = None


def ensure_evidence_column() -> bool:
    """Try to add evidence_json if missing. Returns True when column is usable."""
    global _evidence_ready
    if _evidence_ready is not None:
        return _evidence_ready
    conn = get_monitor_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COL_LENGTH(N'insight.insight_events', N'evidence_json')"
        )
        if cur.fetchone()[0] is not None:
            _evidence_ready = True
            return True
        try:
            cur.execute(_ENSURE_EVIDENCE_SQL)
            conn.commit()
            _evidence_ready = True
            return True
        except Exception:
            log.warning(
                "evidence_json missing and ALTER denied — "
                "run phase2/queries/insight-evidence-json.sql as dbo"
            )
            _evidence_ready = False
            return False
    except Exception:
        log.exception("ensure_evidence_column failed")
        _evidence_ready = False
        return False
    finally:
        conn.close()


@dataclass
class InsightDraft:
    severity: str
    rule_id: str
    scope: str
    scope_id: str
    title: str
    detail: str
    occurrence_count: int = 1
    scope_label: Optional[str] = None
    link_target: Optional[str] = None
    dedupe_key: str = ""
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    evidence_json: Optional[str] = None


def upsert_insights(drafts: Sequence[InsightDraft]) -> int:
    if not drafts:
        return 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    has_evidence = ensure_evidence_column()
    conn = get_monitor_connection()
    try:
        cur = conn.cursor()
        n = 0
        for d in drafts:
            key = d.dedupe_key or f"{d.rule_id}:{d.scope}:{d.scope_id}:{now.strftime('%Y%m%d')}"
            first = d.first_seen_at or now
            last = d.last_seen_at or now
            if has_evidence:
                cur.execute(
                    _UPSERT_SQL,
                    key,
                    last,
                    d.severity,
                    d.title,
                    d.detail,
                    int(d.occurrence_count),
                    d.scope_label,
                    d.link_target,
                    d.evidence_json,
                    now,
                    first,
                    last,
                    d.severity,
                    d.rule_id,
                    d.scope,
                    d.scope_id,
                    d.scope_label,
                    d.title,
                    d.detail,
                    int(d.occurrence_count),
                    key,
                    d.link_target,
                    d.evidence_json,
                )
            else:
                # Keep detail as short summary; SQL/cause live in Metric Store + UI enrich
                cur.execute(
                    _UPSERT_SQL_NO_EVIDENCE,
                    key,
                    last,
                    d.severity,
                    d.title,
                    d.detail,
                    int(d.occurrence_count),
                    d.scope_label,
                    d.link_target,
                    now,
                    first,
                    last,
                    d.severity,
                    d.rule_id,
                    d.scope,
                    d.scope_id,
                    d.scope_label,
                    d.title,
                    d.detail,
                    int(d.occurrence_count),
                    key,
                    d.link_target,
                )
            n += 1
        conn.commit()
        return n
    finally:
        conn.close()


def _evidence_as_text(raw: str) -> str:
    import json
    try:
        data = json.loads(raw)
        rows = data.get("rows") or []
        lines = ["[snapshot]"]
        for r in rows[:6]:
            lines.append(
                f"• {r.get('blocker_session_id')} → {r.get('blocked_session_id')} | "
                f"{r.get('wait_ms')}ms | {r.get('blocked_login') or '—'} | "
                f"{r.get('database_name') or '—'} | {r.get('wait_type') or '—'}"
            )
        return "\n".join(lines)
    except Exception:
        return ""


def set_insight_feedback(insight_id: int, feedback: int) -> bool:
    """feedback: 0 = not important, 1 = important."""
    conn = get_monitor_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE insight.insight_events SET feedback = ? WHERE insight_id = ?",
            int(feedback),
            int(insight_id),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def fetch_todays_insights(include_dismissed: bool = False) -> list:
    has_evidence = ensure_evidence_column()
    conn = get_monitor_connection()
    try:
        cur = conn.cursor()
        evid_col = ", evidence_json" if has_evidence else ""
        sql = f"""
SET NOCOUNT ON;
DECLARE @day DATE = CAST(SYSUTCDATETIME() AS DATE);
SELECT
    insight_id, created_at, first_seen_at, last_seen_at,
    severity, rule_id, scope, scope_id, scope_label,
    title, detail, occurrence_count, dedupe_key, feedback, link_target
    {evid_col}
FROM insight.insight_events
WHERE CAST(created_at AS DATE) = @day
"""
        if not include_dismissed:
            sql += " AND (feedback IS NULL OR feedback <> 0)\n"
        sql += """
ORDER BY
    CASE severity
        WHEN 'critical' THEN 0
        WHEN 'warning' THEN 1
        ELSE 2
    END,
    last_seen_at DESC;
"""
        cur.execute(sql)
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        if not has_evidence:
            for r in rows:
                r["evidence_json"] = None
        return rows
    finally:
        conn.close()
