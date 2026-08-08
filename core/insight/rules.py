"""Conservative V2 rules over Metric Store → insight_events.

Only unambiguous signals. No email here — in-app Insights only.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from core.insight.collectors import capture_blocking_snapshot
from core.insight.events import InsightDraft, upsert_insights
from core.insight.store import get_monitor_connection
from core.logging_setup import get_logger

log = get_logger("sqlmonitor.insight.rules")

# Thresholds (conservative)
BLOCKING_WAIT_CRITICAL_MS = 5_000
BLOCKING_WAIT_WARNING_MS = 1_000


def _day_key(dt: Optional[datetime] = None) -> str:
    d = dt or datetime.now(timezone.utc)
    return d.strftime("%Y%m%d")


def _latest_server_metrics() -> Tuple[float, float, float]:
    """Latest blocking_session_count, blocking_wait_ms, head_blocker_count today."""
    conn = get_monitor_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
SET NOCOUNT ON;
DECLARE @day DATE = CAST(SYSUTCDATETIME() AS DATE);
;WITH latest AS (
    SELECT metric_name, value,
           ROW_NUMBER() OVER (PARTITION BY metric_name ORDER BY ts DESC, sample_id DESC) AS rn
    FROM insight.metric_samples
    WHERE CAST(ts AS DATE) = @day
      AND scope = 'server'
      AND metric_name IN ('blocking_session_count', 'blocking_wait_ms', 'head_blocker_count')
)
SELECT metric_name, value FROM latest WHERE rn = 1;
"""
        )
        vals = {r[0]: float(r[1] or 0) for r in cur.fetchall()}
        return (
            vals.get("blocking_session_count", 0.0),
            vals.get("blocking_wait_ms", 0.0),
            vals.get("head_blocker_count", 0.0),
        )
    finally:
        conn.close()


def _latest_blocking_edges(limit: int = 8) -> Tuple[List[dict], Optional[datetime]]:
    """Rebuild session evidence from latest blocking_edge (+ blocking_sql) batch."""
    conn = get_monitor_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
SET NOCOUNT ON;
DECLARE @day DATE = CAST(SYSUTCDATETIME() AS DATE);
DECLARE @ts DATETIME2(0) = (
    SELECT MAX(ts) FROM insight.metric_samples
    WHERE CAST(ts AS DATE) = @day AND metric_name = 'blocking_edge'
);
SELECT TOP ({limit})
    scope_id, scope_label, value, dims_json, ts
FROM insight.metric_samples
WHERE metric_name = 'blocking_edge'
  AND ts = @ts
ORDER BY value DESC, sample_id DESC;

SELECT scope_id, scope_label, dims_json
FROM insight.metric_samples
WHERE metric_name = 'blocking_sql'
  AND ts = @ts;
""".format(limit=max(1, min(int(limit), 20)))
        )
        edge_rows = cur.fetchall()
        if not edge_rows:
            return [], None
        captured = edge_rows[0][4]
        sql_map = {}
        if cur.nextset():
            for scope_id, label, dims_json in cur.fetchall():
                role = "blocked"
                if dims_json:
                    try:
                        role = (json.loads(dims_json) or {}).get("role") or role
                    except Exception:
                        pass
                key = str(scope_id)
                # scope_id like "833:157:h" or "833:157:b"
                if key.endswith(":h"):
                    pair = key[:-2]
                    sql_map.setdefault(pair, {})["blocker_sql"] = label or ""
                elif key.endswith(":b"):
                    pair = key[:-2]
                    sql_map.setdefault(pair, {})["blocked_sql"] = label or ""
                else:
                    sql_map.setdefault(key, {})[role + "_sql"] = label or ""

        out = []
        for scope_id, label, value, dims_json, ts in edge_rows:
            dims = {}
            if dims_json:
                try:
                    dims = json.loads(dims_json)
                except Exception:
                    dims = {}
            blocker = dims.get("b", dims.get("blocker"))
            if blocker is None and label and "→" in str(label):
                blocker = str(label).split("→", 1)[0]
            pair = f"{blocker}:{scope_id}"
            sqls = sql_map.get(pair) or {}
            out.append({
                "blocked_session_id": scope_id,
                "blocker_session_id": blocker,
                "is_head_blocker": int(dims.get("h", dims.get("head") or 0)),
                "wait_type": dims.get("w") or dims.get("wait"),
                "wait_resource": dims.get("r") or dims.get("res"),
                "wait_ms": int(value or 0),
                "chain_display": label or f"{blocker} → {scope_id}",
                "database_name": dims.get("db"),
                "blocked_login": dims.get("bl") or dims.get("blogin"),
                "blocked_host": dims.get("bh") or dims.get("bhost"),
                "blocked_program": dims.get("bp") or dims.get("bprog"),
                "blocked_command": dims.get("bc") or dims.get("bcmd"),
                "blocked_sql": sqls.get("blocked_sql") or dims.get("bs") or dims.get("bsql"),
                "blocker_login": dims.get("hl") or dims.get("hlogin"),
                "blocker_host": dims.get("hh") or dims.get("hhost"),
                "blocker_program": dims.get("hp") or dims.get("hprog"),
                "blocker_command": dims.get("hc") or dims.get("hcmd"),
                "blocker_sql": sqls.get("blocker_sql") or dims.get("hs") or dims.get("hsql"),
            })
            captured = ts or captured
        return out, captured
    except Exception:
        log.exception("load blocking_edge samples failed")
        return [], None
    finally:
        conn.close()


def blocking_cause_fa(row: dict) -> str:
    """One Persian sentence: why this blocking exists."""
    blocker = row.get("blocker_session_id") or "?"
    blocked = row.get("blocked_session_id") or "?"
    wait = row.get("wait_type") or "قفل"
    res = (row.get("wait_resource") or "").strip() or "منبع نامشخص"
    db = row.get("database_name") or "—"
    return (
        f"علت: نشست {blocker} کوئری خود را باز نگه داشته و با {wait} روی «{res}» "
        f"(دیتابیس {db}) قفل گرفته؛ نشست {blocked} منتظر آزاد شدن همان قفل است."
    )


def blocking_action_fa(row: dict) -> str:
    """Short ops guidance for a blocking edge."""
    blocker = row.get("blocker_session_id") or "?"
    cmd = (row.get("blocker_command") or "").strip().upper()
    open_tran = int(row.get("blocker_open_tran") or 0)
    wait = (row.get("wait_type") or "").upper()
    if open_tran > 0 and (not cmd or cmd in ("AWAITING COMMAND", "SLEEPING", "")):
        return (
            f"Head blocker = SPID {blocker}: تراکنش باز بدون کار فعال — "
            "اپ یا کاربر را پیدا کن؛ COMMIT/ROLLBACK یا در اضطرار Kill با احتیاط."
        )
    if wait.startswith("LCK_"):
        return (
            f"کوئری/تراکنش SPID {blocker} را در Session Lookup ببین؛ "
            "قفل را با اتمام تراکنش آزاد کن (نه Kill فوری مگر آخرین گزینه)."
        )
    return (
        f"SPID {blocker} را در Session Lookup باز کن و علت نگه‌داشتن منبع را رفع کن."
    )


def blocking_glance_fa(evidence_rows: list, detail: str = "") -> tuple[str, str]:
    """(problem, action) one-liners for insight card glance."""
    heads = [r for r in (evidence_rows or []) if int(r.get("is_head_blocker") or 0) == 1]
    sample = heads[0] if heads else ((evidence_rows or [None])[0])
    if sample:
        blocker = sample.get("blocker_session_id") or "?"
        blocked = sample.get("blocked_session_id") or "?"
        wait = sample.get("wait_type") or "lock"
        db = sample.get("database_name") or "—"
        problem = f"SPID {blocker} → {blocked} · {wait} · {db}"
        action = blocking_action_fa(sample)
        return problem, action
    problem = (detail or "Blocking روی سرور ثبت شده.").strip()
    action = "تب Activity → Blocking را باز کن و Head blocker را پیدا کن."
    return problem, action


def enrich_insight_rows(rows: list) -> list:
    """Attach structured blocking evidence (with SQL) for UI rendering."""
    if not rows:
        return rows
    edge_rows, edge_ts = _latest_blocking_edges(limit=12)
    # Prefer store edges; else try a live DMV snapshot while blocking still exists
    if not edge_rows:
        live = capture_blocking_snapshot(top=12)
        if live:
            edge_rows, edge_ts = live, datetime.now(timezone.utc).replace(tzinfo=None)

    payload = None
    if edge_rows:
        payload = _blocking_evidence_payload(
            edge_rows,
            captured_at=edge_ts or datetime.now(timezone.utc).replace(tzinfo=None),
        )

    out = []
    for r in rows:
        item = dict(r)
        if (item.get("rule_id") or "") == "blocking_active":
            existing = item.get("evidence_json")
            need = True
            if existing:
                try:
                    data = json.loads(existing) if isinstance(existing, str) else existing
                    rows_e = (data or {}).get("rows") or []
                    if rows_e and any((x.get("blocker_sql") or x.get("blocked_sql")) for x in rows_e):
                        need = False
                        for x in rows_e:
                            x.setdefault("cause_fa", blocking_cause_fa(x))
                        item["evidence_json"] = json.dumps(data, ensure_ascii=False)
                except Exception:
                    need = True
            if need and payload:
                data = json.loads(payload)
                for x in data.get("rows") or []:
                    x["cause_fa"] = blocking_cause_fa(x)
                item["evidence_json"] = json.dumps(data, ensure_ascii=False)
            detail = item.get("detail") or ""
            if "[snapshot]" in detail:
                item["detail"] = detail.split("[snapshot]", 1)[0].strip()
        out.append(item)
    return out


def _blocking_observation_count() -> int:
    """How many collector ticks today saw blocking_session_count > 0."""
    conn = get_monitor_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
SET NOCOUNT ON;
DECLARE @day DATE = CAST(SYSUTCDATETIME() AS DATE);
SELECT COUNT_BIG(*)
FROM insight.metric_samples
WHERE CAST(ts AS DATE) = @day
  AND metric_name = 'blocking_session_count'
  AND scope = 'server'
  AND value > 0;
"""
        )
        return int(cur.fetchone()[0] or 0)
    except Exception:
        return 0
    finally:
        conn.close()


def _job_failures_today() -> List[Tuple[str, str, int, datetime, datetime]]:
    """(job_id, label, count, first_ts, last_ts) for job_failed samples today."""
    conn = get_monitor_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
SET NOCOUNT ON;
DECLARE @day DATE = CAST(SYSUTCDATETIME() AS DATE);
SELECT
    scope_id,
    MAX(scope_label) AS scope_label,
    COUNT_BIG(*) AS cnt,
    MIN(ts) AS first_ts,
    MAX(ts) AS last_ts
FROM insight.metric_samples
WHERE CAST(ts AS DATE) = @day
  AND metric_name = 'job_failed'
  AND scope = 'job'
GROUP BY scope_id
ORDER BY cnt DESC;
"""
        )
        out = []
        for r in cur.fetchall():
            out.append((
                str(r[0]),
                (r[1] or str(r[0]))[:200],
                int(r[2] or 0),
                r[3],
                r[4],
            ))
        return out
    finally:
        conn.close()


def _blocking_evidence_payload(rows: List[dict], *, captured_at: datetime) -> Optional[str]:
    if not rows:
        return None
    payload = {
        "kind": "blocking_snapshot",
        "captured_at": (
            captured_at.strftime("%Y-%m-%d %H:%M:%S")
            if hasattr(captured_at, "strftime")
            else str(captured_at)[:19]
        ),
        "rows": rows,
    }
    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        log.exception("serialize blocking evidence failed")
        return None


def evaluate_rules() -> int:
    """Run V2 rules; upsert Today's Insights. Returns number of drafts written."""
    drafts: List[InsightDraft] = []
    day = _day_key()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        cnt, wait_ms, heads = _latest_server_metrics()
    except Exception:
        log.exception("rules: cannot read blocking metrics")
        cnt = wait_ms = heads = 0.0

    # Prefer live DMV snapshot; else rebuild from Metric Store edges
    snap_rows = capture_blocking_snapshot(top=12)
    captured_at = now
    if not snap_rows:
        snap_rows, edge_ts = _latest_blocking_edges(limit=12)
        if edge_ts:
            captured_at = edge_ts

    if cnt > 0 or snap_rows:
        if snap_rows:
            cnt = max(float(cnt), float(len(snap_rows)))
            wait_ms = max(float(wait_ms), float(max(int(r.get("wait_ms") or 0) for r in snap_rows)))
            heads = max(
                float(heads),
                float(sum(1 for r in snap_rows if int(r.get("is_head_blocker") or 0))),
            )

        if wait_ms >= BLOCKING_WAIT_CRITICAL_MS:
            sev = "critical"
            title = "Blocking فعال با انتظار بالا"
        elif wait_ms >= BLOCKING_WAIT_WARNING_MS or heads > 0:
            sev = "warning"
            title = "Blocking روی سرور دیده شد"
        else:
            sev = "info"
            title = "Blocking کوتاه‌مدت"

        detail = (
            f"{int(cnt)} نشست بلاک‌شده · max wait {int(wait_ms)} ms · "
            f"head blockerها: {int(heads)}"
        )
        evidence = _blocking_evidence_payload(snap_rows, captured_at=captured_at)
        if evidence and snap_rows:
            try:
                data = json.loads(evidence)
                for x in data.get("rows") or []:
                    x["cause_fa"] = blocking_cause_fa(x)
                evidence = json.dumps(data, ensure_ascii=False)
            except Exception:
                pass
        occ = max(1, _blocking_observation_count())

        drafts.append(InsightDraft(
            severity=sev,
            rule_id="blocking_active",
            scope="server",
            scope_id="_",
            title=title,
            detail=detail,
            occurrence_count=occ,
            link_target=None,
            dedupe_key=f"blocking_active:server:_:{day}",
            last_seen_at=captured_at if snap_rows else now,
            evidence_json=evidence,
        ))

    try:
        jobs = _job_failures_today()
    except Exception:
        log.exception("rules: cannot read job_failed metrics")
        jobs = []

    for job_id, label, n, first_ts, last_ts in jobs:
        sev = "critical" if n >= 3 else "warning"
        drafts.append(InsightDraft(
            severity=sev,
            rule_id="job_failed_today",
            scope="job",
            scope_id=job_id,
            scope_label=label,
            title=f"جاب با خطا: {label}",
            detail=f"امروز {n} بار step failure ثبت شده (از Metric Store).",
            occurrence_count=n,
            link_target="jobs",
            dedupe_key=f"job_failed_today:job:{job_id}:{day}",
            first_seen_at=first_ts or now,
            last_seen_at=last_ts or now,
        ))

    if not drafts:
        return 0
    try:
        n = upsert_insights(drafts)
        if n:
            log.info("rules upserted %s insight(s)", n)
        return n
    except Exception:
        log.exception("rules: upsert failed")
        return 0
