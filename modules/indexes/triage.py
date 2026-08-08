"""Enrich Overview sections into Triage findings shaped for the mockup UI."""
from __future__ import annotations

from typing import Any

from core.formatters import fmt_compact, fmt_size_mb
from modules.indexes.constants import (
    INDEX_CAP_MISSING,
    INDEX_CAP_UNUSED,
    INDEX_CAP_WRITE_HEAVY,
    INDEX_OVERVIEW_FINDING_ROWS,
    INDEX_WRITE_HEAVY_MIN_WRITES,
)
from modules.indexes.service import (
    build_create_missing_script,
    build_disable_drop_script,
)

_SEVERITY_RANK = {"critical": 0, "warning": 1, "watch": 2, "ok": 3}

_CATEGORY_LABEL = {
    "unused": "Unused",
    "write_heavy": "Write-heavy",
    "heap": "Heap",
    "missing": "Missing index",
}

_ACTION_LABEL = {
    "unused": "→ Disable unused index after workload validation",
    "write_heavy": "→ Drop or rebuild with filtered index",
    "heap": "→ Evaluate clustered index (often PK)",
    "missing": "→ Review missing index DMV suggestion",
}


def _clamp_score(value: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(100.0, v))


def _norm_severity(raw: str | None, *, writes: int = 0) -> str:
    s = (raw or "").lower().strip()
    if s in ("critical", "warning", "watch", "ok"):
        return s
    if s in ("warn", "warning"):
        return "critical" if writes >= INDEX_WRITE_HEAVY_MIN_WRITES else "warning"
    if s in ("info", "information"):
        return "watch"
    if writes >= INDEX_WRITE_HEAVY_MIN_WRITES:
        return "critical"
    return "warning"


def _finding_id(
    category: str,
    database: str,
    schema: str,
    table: str,
    index_name: str | None,
) -> str:
    return f"{category}|{database}|{schema}|{table}|{index_name or ''}"


def _unused_score(row: dict) -> float:
    writes = int(row.get("writes") or 0)
    try:
        size = float(row.get("size_mb") or 0)
    except (TypeError, ValueError):
        size = 0.0
    base = min(85.0, (writes / max(INDEX_WRITE_HEAVY_MIN_WRITES, 1)) * 40.0)
    return _clamp_score(base + min(15.0, size / 50.0))


def _write_heavy_score(row: dict) -> float:
    reads = max(int(row.get("reads") or 0), 1)
    writes = int(row.get("writes") or 0)
    if writes <= 0:
        return 0.0
    delta_ratio = (writes - reads) / max(writes, 1)
    volume = min(40.0, writes / max(INDEX_WRITE_HEAVY_MIN_WRITES, 1) * 20.0)
    return _clamp_score(delta_ratio * 60.0 + volume)


def _heap_score(row: dict) -> float:
    try:
        rows = float(row.get("row_count") or 0)
    except (TypeError, ValueError):
        rows = 0.0
    try:
        size = float(row.get("size_mb") or 0)
    except (TypeError, ValueError):
        size = 0.0
    if rows <= 0 and size <= 0:
        return 45.0
    return _clamp_score(min(90.0, (rows / 100_000.0) * 40.0 + (size / 100.0) * 20.0 + 30.0))


def _missing_score(row: dict) -> float:
    if row.get("impact_score") is not None:
        try:
            return _clamp_score(float(row["impact_score"]))
        except (TypeError, ValueError):
            pass
    if row.get("avg_user_impact") is not None:
        try:
            impact = float(row.get("avg_user_impact") or 0)
            seeks = float(row.get("user_seeks") or row.get("suggestion_count") or 1)
            return _clamp_score(min(100.0, impact * 0.7 + min(30.0, seeks / 100.0)))
        except (TypeError, ValueError):
            pass
    try:
        return _clamp_score(min(80.0, float(row.get("suggestion_count") or 1) * 8.0))
    except (TypeError, ValueError):
        return 40.0


def _object_path(row: dict) -> str:
    return f"{row.get('schema_name') or 'dbo'}.{row.get('table_name') or ''}"


def _wr_label(reads: int, writes: int) -> str | None:
    if reads <= 0:
        return None
    ratio = writes / reads
    if ratio >= 10:
        return f"{int(round(ratio))}:1 W/R"
    return f"{ratio:.1f}:1 W/R"


def _verify_usage_script(db: str, schema: str, table: str, index_name: str) -> str:
    use = f"USE [{str(db or '').replace(']', ']]')}];\nGO\n" if db else ""
    return (
        use
        + "-- Verify impact before dropping\n"
        "SELECT user_seeks, user_scans, user_lookups, user_updates\n"
        "FROM sys.dm_db_index_usage_stats\n"
        f"WHERE database_id = DB_ID(N'{db}')\n"
        f"  AND object_id = OBJECT_ID(N'{schema}.{table}')\n"
        f"  AND index_id = (\n"
        f"      SELECT index_id FROM sys.indexes\n"
        f"      WHERE object_id = OBJECT_ID(N'{schema}.{table}')\n"
        f"        AND name = N'{index_name}'\n"
        "  );\n"
    )


def _missing_review_script(db: str) -> str:
    use = f"USE [{str(db or '').replace(']', ']]')}];\nGO\n" if db else ""
    return (
        use
        + "-- Review missing index suggestion\n"
        "SELECT mid.*, migs.avg_total_user_cost * migs.avg_user_impact AS benefit\n"
        "FROM sys.dm_db_missing_index_details mid\n"
        "JOIN sys.dm_db_missing_index_groups mig ON mid.index_handle = mig.index_handle\n"
        "JOIN sys.dm_db_missing_index_group_stats migs ON mig.index_group_handle = migs.group_handle\n"
        f"WHERE mid.database_id = DB_ID(N'{db}')\n"
        "ORDER BY benefit DESC;\n"
    )


def recoverable_mb(findings: list[dict] | None) -> float:
    total = 0.0
    for f in findings or []:
        if f.get("category") not in ("unused", "write_heavy"):
            continue
        try:
            total += float((f.get("metrics") or {}).get("size_mb") or 0)
        except (TypeError, ValueError):
            continue
    return total


def per_database_summary(findings: list[dict] | None) -> list[dict]:
    buckets: dict[str, dict] = {}
    for f in findings or []:
        db = f.get("database_name") or "—"
        b = buckets.setdefault(
            db,
            {"database_name": db, "critical": 0, "warning": 0, "watch": 0, "size_mb": 0.0},
        )
        sev = f.get("severity") or ""
        if sev in b:
            b[sev] += 1
        try:
            b["size_mb"] += float((f.get("metrics") or {}).get("size_mb") or 0)
        except (TypeError, ValueError):
            pass
    rows = list(buckets.values())
    rows.sort(key=lambda r: (-(r["critical"]), -(r["warning"]), r["database_name"]))
    return rows


def build_triage_findings(overview_payload: dict | None) -> list[dict[str, Any]]:
    """Flatten Overview sections into ranked Triage findings."""
    if not overview_payload:
        return []
    sections = overview_payload.get("sections") or {}
    uptime = overview_payload.get("uptime") or {}
    insufficient = bool(uptime.get("insufficient"))
    cap = int(INDEX_OVERVIEW_FINDING_ROWS)
    findings: list[dict[str, Any]] = []

    for row in (sections.get("unused") or [])[: max(cap, INDEX_CAP_UNUSED)]:
        writes = int(row.get("writes") or 0)
        db = row.get("database_name") or ""
        schema = row.get("schema_name") or "dbo"
        table = row.get("table_name") or ""
        index_name = row.get("index_name") or ""
        size = row.get("size_mb")
        severity = _norm_severity(None, writes=writes)
        bullets = [
            {"tone": "critical", "text": f"{fmt_compact(writes)} writes vs 0 reads — unused since restart"},
            {"tone": "critical", "text": "Every INSERT/UPDATE/DELETE still pays maintenance overhead"},
        ]
        if size:
            bullets.append({"tone": "warning", "text": f"{fmt_size_mb(size)} — candidate reclaimable space"})
        if insufficient:
            bullets.append({"tone": "watch", "text": "Short uptime — confirm a full business cycle before drop"})
        drop = build_disable_drop_script(schema, table, index_name)
        findings.append(
            {
                "id": _finding_id("unused", db, schema, table, index_name),
                "category": "unused",
                "category_label": _CATEGORY_LABEL["unused"],
                "severity": severity,
                "impact_score": round(_unused_score(row)),
                "title": index_name or f"{schema}.{table}",
                "display_title": index_name or "HEAP",
                "card_icon": "unused",
                "database_name": db,
                "schema_name": schema,
                "table_name": table,
                "index_name": index_name,
                "object_path": _object_path(row),
                "why": "No reads since last SQL Server start; still paying write/maintenance cost.",
                "why_bullets": bullets,
                "metrics": {"reads": 0, "writes": writes, "size_mb": size, "write_read_ratio_label": None},
                "action": "review_drop",
                "action_label": _ACTION_LABEL["unused"],
                "scripts": [
                    {
                        "label": "Copy",
                        "tsql": _verify_usage_script(db, schema, table, index_name)
                        + "\n-- Drop when confirmed:\n"
                        + drop,
                    }
                ],
            }
        )

    for row in (sections.get("write_heavy") or [])[: max(cap, INDEX_CAP_WRITE_HEAVY)]:
        reads = int(row.get("reads") or 0)
        writes = int(row.get("writes") or 0)
        db = row.get("database_name") or ""
        schema = row.get("schema_name") or "dbo"
        table = row.get("table_name") or ""
        index_name = row.get("index_name") or ""
        size = row.get("size_mb")
        severity = _norm_severity(None, writes=writes)
        wr = _wr_label(reads, writes)
        bullets = [
            {
                "tone": "critical",
                "text": f"{fmt_compact(writes)} writes vs {fmt_compact(reads)} reads"
                + (f" — {wr}" if wr else ""),
            },
            {
                "tone": "critical",
                "text": "Every INSERT/UPDATE/DELETE pays maintenance overhead on this index",
            },
        ]
        if size:
            bullets.append({"tone": "warning", "text": f"{fmt_size_mb(size)} — significant buffer pool pressure"})
        drop = build_disable_drop_script(schema, table, index_name)
        findings.append(
            {
                "id": _finding_id("write_heavy", db, schema, table, index_name),
                "category": "write_heavy",
                "category_label": _CATEGORY_LABEL["write_heavy"],
                "severity": severity,
                "impact_score": round(_write_heavy_score(row)),
                "title": index_name,
                "display_title": index_name,
                "card_icon": "write_heavy",
                "database_name": db,
                "schema_name": schema,
                "table_name": table,
                "index_name": index_name,
                "object_path": _object_path(row),
                "why": "Write cost dominates reads — review keys/filter against workload.",
                "why_bullets": bullets,
                "metrics": {
                    "reads": reads,
                    "writes": writes,
                    "write_read_ratio": (writes / reads) if reads else None,
                    "write_read_ratio_label": wr,
                    "size_mb": size,
                },
                "action": "investigate",
                "action_label": _ACTION_LABEL["write_heavy"],
                "scripts": [
                    {
                        "label": "Copy",
                        "tsql": _verify_usage_script(db, schema, table, index_name)
                        + "\n-- Drop when confirmed:\n"
                        + drop,
                    }
                ],
            }
        )

    for row in (sections.get("heaps") or [])[:cap]:
        db = row.get("database_name") or ""
        schema = row.get("schema_name") or "dbo"
        table = row.get("table_name") or ""
        findings.append(
            {
                "id": _finding_id("heap", db, schema, table, None),
                "category": "heap",
                "category_label": _CATEGORY_LABEL["heap"],
                "severity": "warning",
                "impact_score": round(_heap_score(row)),
                "title": f"{schema}.{table}",
                "display_title": "HEAP",
                "card_icon": "heap",
                "database_name": db,
                "schema_name": schema,
                "table_name": table,
                "index_name": None,
                "object_path": _object_path(row),
                "why": "Table has no clustered index — evaluate a clustered index for lookups.",
                "why_bullets": [
                    {"tone": "warning", "text": "Heap — no clustered index for lookups / range scans"},
                    {"tone": "watch", "text": "Forwarded records and scans can grow with updates"},
                ],
                "metrics": {
                    "reads": None,
                    "writes": None,
                    "row_count": row.get("row_count"),
                    "size_mb": row.get("size_mb"),
                    "write_read_ratio_label": None,
                },
                "action": "investigate",
                "action_label": _ACTION_LABEL["heap"],
                "scripts": [],
            }
        )

    for i, row in enumerate(
        (sections.get("missing_by_table") or [])[: max(cap, INDEX_CAP_MISSING)], start=1
    ):
        db = row.get("database_name") or ""
        schema = row.get("schema_name") or "dbo"
        table = row.get("table_name") or ""
        equality = str(row.get("equality_columns") or "").strip()
        inequality = str(row.get("inequality_columns") or "").strip()
        key_parts = [p for p in (equality, inequality) if p]
        key_cols = ",".join(key_parts) if key_parts else ""
        include_cols = row.get("included_columns")
        suggested = f"IX_{table}_Missing_{i}"
        tsql = _missing_review_script(db)
        if key_cols:
            tsql += "\n-- Suggested CREATE (review only):\n" + build_create_missing_script(
                schema,
                table,
                suggested,
                key_cols,
                include_cols=include_cols,
                database=db,
            )
        findings.append(
            {
                "id": _finding_id("missing", db, schema, table, f"sugg:{i}"),
                "category": "missing",
                "category_label": _CATEGORY_LABEL["missing"],
                "severity": "watch",
                "impact_score": round(_missing_score(row)),
                "title": suggested,
                "display_title": f"+? {suggested}",
                "card_icon": "missing",
                "database_name": db,
                "schema_name": schema,
                "table_name": table,
                "index_name": suggested,
                "object_path": _object_path(row),
                "why": "Optimizer suggestion — compare with existing indexes before creating.",
                "why_bullets": [
                    {"tone": "watch", "text": "Optimizer is recommending this index based on query plans"},
                    {
                        "tone": "watch",
                        "text": "Review execution plans before creating — may overlap with existing",
                    },
                ],
                "metrics": {
                    "reads": 0,
                    "writes": 0,
                    "suggestion_count": row.get("suggestion_count"),
                    "avg_user_impact": row.get("avg_user_impact"),
                    "user_seeks": row.get("user_seeks"),
                    "write_read_ratio_label": None,
                    "size_mb": None,
                },
                "action": "add_index",
                "action_label": _ACTION_LABEL["missing"],
                "scripts": [{"label": "Copy", "tsql": tsql}],
            }
        )

    findings.sort(
        key=lambda f: (
            _SEVERITY_RANK.get(f.get("severity") or "ok", 9),
            -float(f.get("impact_score") or 0),
        )
    )
    return findings


def filter_triage_findings(
    findings: list[dict] | None,
    filter_key: str | None,
) -> list[dict]:
    rows = findings or []
    key = (filter_key or "all").lower().strip()
    if key in ("", "all"):
        return list(rows)
    if key in _SEVERITY_RANK:
        return [f for f in rows if (f.get("severity") or "") == key]
    return [f for f in rows if (f.get("category") or "") == key]


def triage_filter_counts(findings: list[dict] | None) -> dict[str, int]:
    rows = findings or []
    counts = {
        "all": len(rows),
        "critical": 0,
        "warning": 0,
        "watch": 0,
        "ok": 0,
        "unused": 0,
        "write_heavy": 0,
        "heap": 0,
        "missing": 0,
    }
    for f in rows:
        sev = f.get("severity") or ""
        cat = f.get("category") or ""
        if sev in counts:
            counts[sev] += 1
        if cat in counts:
            counts[cat] += 1
    return counts
