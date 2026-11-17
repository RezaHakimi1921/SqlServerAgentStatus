from datetime import datetime
from typing import Any, Literal

from modules.indexes.constants import (
    INDEX_CAP_MISSING,
    INDEX_CAP_UNUSED,
    INDEX_CAP_WRITE_HEAVY,
    INDEX_CONFIDENCE_SCRIPT_MIN,
    INDEX_HIGH_FRAG_MIN_PAGES,
    INDEX_HIGH_FRAG_PCT,
    INDEX_USAGE_MIN_UPTIME_DAYS,
    INDEX_WRITE_HEAVY_MIN_DIFF,
    INDEX_WRITE_HEAVY_MIN_RATIO,
    INDEX_WRITE_HEAVY_MIN_WRITES,
)

UsageClassification = Literal["unused", "write_heavy"] | None


def is_write_heavy(reads: int, writes: int) -> bool:
    reads = int(reads or 0)
    writes = int(writes or 0)
    if reads <= 0:
        return False
    if writes <= reads:
        return False
    if writes < INDEX_WRITE_HEAVY_MIN_WRITES:
        return False
    if (writes - reads) >= INDEX_WRITE_HEAVY_MIN_DIFF:
        return True
    return writes >= reads * INDEX_WRITE_HEAVY_MIN_RATIO


def classify_usage_row(row: dict) -> UsageClassification:
    if not row.get("eligible", True):
        return None
    reads = int(row.get("reads") or 0)
    writes = int(row.get("writes") or 0)
    if reads == 0:
        return "unused"
    if is_write_heavy(reads, writes):
        return "write_heavy"
    return None


ConfidenceLevel = Literal["high", "medium", "low"]


def assign_confidence(
    category: str,
    *,
    uptime_days: float,
    writes: int = 0,
) -> tuple[ConfidenceLevel, str, int]:
    """Return (level, reason, score 0-100). Copyable T-SQL only when score >= 70."""
    uptime_days = float(uptime_days or 0)
    writes = int(writes or 0)
    short_uptime = uptime_days < INDEX_USAGE_MIN_UPTIME_DAYS
    days_label = int(uptime_days) if uptime_days == int(uptime_days) else uptime_days

    def _level(s: int) -> ConfidenceLevel:
        if s < 40:
            return "low"
        if s < 70:
            return "medium"
        return "high"

    if category in ("duplicate", "heap"):
        return (
            "high",
            "Catalog metadata; not affected by DMV reset since restart.",
            90,
        )

    score = 100
    if short_uptime:
        score -= 40

    if category == "missing":
        # Optimizer hints never reach script threshold in v1
        score = 35 if short_uptime else 55
        reason = (
            f"Missing-index DMVs plus only {days_label} day(s) since restart — short collection window."
            if short_uptime
            else "Missing-index DMVs are optimizer hints; compare with existing indexes before acting."
        )
        return (_level(score), reason, score)

    if category == "unused":
        if writes < INDEX_WRITE_HEAVY_MIN_WRITES:
            score -= 35
        if short_uptime:
            reason = f"Usage stats reset at restart; only {days_label} day(s) of collection so far."
        elif writes >= INDEX_WRITE_HEAVY_MIN_WRITES:
            reason = (
                f"Zero reads with {writes:,} writes over {int(uptime_days)}+ days "
                "— strong usage signal."
            )
        else:
            reason = (
                f"Zero reads over {int(uptime_days)}+ days; write activity is low "
                "— confirm workload cycle."
            )
        return (_level(score), reason, max(0, min(100, score)))

    if category == "write_heavy":
        reason = (
            f"Usage stats reset at restart; only {days_label} day(s) of collection so far."
            if short_uptime
            else f"Write-heavy pattern observed over {int(uptime_days)}+ days since restart."
        )
        return (_level(score), reason, max(0, min(100, score)))

    return ("medium", "Limited evidence context for this category.", 55)


def _gated_scripts(score: int | float, scripts: list[dict]) -> tuple[list[dict], str | None]:
    """Attach copyable T-SQL only when confidence_score >= INDEX_CONFIDENCE_SCRIPT_MIN."""
    try:
        s = int(score)
    except (TypeError, ValueError):
        s = 0
    if s >= int(INDEX_CONFIDENCE_SCRIPT_MIN):
        return scripts, None
    if not scripts:
        return [], None
    return [], (
        f"Confidence {s} < {INDEX_CONFIDENCE_SCRIPT_MIN} — "
        "need more history/uptime before copying T-SQL."
    )


def _normalize_includes(include_cols: str | None) -> str:
    if not include_cols or not str(include_cols).strip():
        return ""
    parts = [p.strip() for p in str(include_cols).split(",") if p.strip()]
    return ",".join(sorted(parts))


def _duplicate_group_key(row: dict) -> tuple:
    return (
        row.get("object_id"),
        str(row.get("key_cols") or ""),
        _normalize_includes(row.get("include_cols")),
        str(row.get("filter_def") or ""),
    )


def group_exact_duplicates(inventory_rows: list[dict]) -> list[dict]:
    """Group indexes with identical keys, includes (order-insensitive), and filter."""
    buckets: dict[tuple, list[dict]] = {}
    for row in inventory_rows:
        key = _duplicate_group_key(row)
        buckets.setdefault(key, []).append(row)

    groups: list[dict] = []
    for key, members in buckets.items():
        if len(members) < 2:
            continue
        object_id, key_cols, includes, filter_def = key
        first = members[0]
        group_id = f"{object_id}:{key_cols}:{includes}:{filter_def}"
        groups.append(
            {
                "group_id": group_id,
                "schema": first.get("schema_name", ""),
                "table": first.get("table_name", ""),
                "members": members,
                "excess": members[1:],
            }
        )
    return groups


def quotename(ident: str) -> str:
    """SQL Server QUOTENAME equivalent for bracket-quoted identifiers."""
    name = str(ident or "")
    return f"[{name.replace(']', ']]')}]"


def build_disable_drop_script(
    schema: str,
    table: str,
    index_name: str,
    *,
    database: str | None = None,
    confidence_score: int | None = None,
    reasons: list[str] | None = None,
) -> str:
    """Copy-only DISABLE + DROP script for DBA review (never executed by the app)."""
    qualified = f"{quotename(schema)}.{quotename(table)}"
    idx = quotename(index_name)
    use = ""
    if database:
        use = f"USE {quotename(database)};\nGO\n"
    target = f"{quotename(database) + '.' if database else ''}{qualified}"
    conf_line = ""
    if confidence_score is not None:
        reason_txt = ", ".join(str(r) for r in (reasons or [])[:5]) or "—"
        conf_line = f"-- Confidence: {int(confidence_score)}/100   |  Reasons: {reason_txt}\n"
    return (
        use
        + "-- =========================================================================\n"
        + f"-- REVIEW ONLY — Target: {target}.{idx}\n"
        + conf_line
        + "-- SqlMonitor never executes this. Confirm uptime / AG role / business cycle\n"
        + "-- before DISABLE or DROP. Prefer DISABLE first when unsure.\n"
        + "-- =========================================================================\n"
        f"ALTER INDEX {idx} ON {qualified} DISABLE;\n"
        f"-- DROP INDEX {idx} ON {qualified};\n"
        f"-- Uncomment DROP only after DISABLE validation.\n"
        "GO\n"
    )


def build_create_missing_script(
    schema: str,
    table: str,
    index_name: str,
    key_cols: str,
    *,
    include_cols: str | None = None,
    filter_def: str | None = None,
    database: str | None = None,
    confidence_score: int | None = None,
    reasons: list[str] | None = None,
) -> str:
    """Suggested CREATE script for a missing-index hint (review only)."""
    qualified = f"{quotename(schema)}.{quotename(table)}"
    idx = quotename(index_name)
    include_clause = ""
    if include_cols and str(include_cols).strip():
        include_clause = f"\nINCLUDE ({include_cols})"
    filter_clause = ""
    if filter_def and str(filter_def).strip():
        filter_clause = f"\nWHERE {filter_def}"
    use = ""
    if database:
        use = f"USE {quotename(database)};\nGO\n"
    target = f"{quotename(database) + '.' if database else ''}{qualified}"
    conf_line = ""
    if confidence_score is not None:
        reason_txt = ", ".join(str(r) for r in (reasons or [])[:5]) or "—"
        conf_line = f"-- Confidence: {int(confidence_score)}/100   |  Reasons: {reason_txt}\n"
    return (
        use
        + "-- =========================================================================\n"
        + f"-- Optimization suggestion — Target: {target}\n"
        + conf_line
        + "-- REVIEW ONLY — not executed by SqlMonitor\n"
        + "-- =========================================================================\n"
        f"CREATE NONCLUSTERED INDEX {idx}\n"
        f"ON {qualified} ({key_cols}){include_clause}{filter_clause}\n"
        "WITH (\n"
        "    ONLINE = ON,           -- when edition supports\n"
        "    FILLFACTOR = 85\n"
        "    -- DATA_COMPRESSION / SORT_IN_TEMPDB / MAXDOP: set per workload\n"
        ");\n"
        "GO\n"
    )


def build_frag_maintenance_script(
    schema: str,
    table: str,
    index_name: str,
    frag_pct: float,
    *,
    database: str | None = None,
) -> str:
    """Copy-only REORGANIZE / REBUILD suggestion from frag bands (never executed)."""
    qualified = f"{quotename(schema)}.{quotename(table)}"
    idx = quotename(index_name)
    use = ""
    if database:
        use = f"USE {quotename(database)};\nGO\n"
    target = f"{quotename(database) + '.' if database else ''}{qualified}"
    try:
        pct = float(frag_pct)
    except (TypeError, ValueError):
        pct = 0.0
    if pct >= INDEX_HIGH_FRAG_PCT:
        action = "REBUILD"
        hint = "Critical band (>30%) — schedule offline/online rebuild per edition."
    elif pct >= 10.0:
        action = "REORGANIZE"
        hint = "Moderate band (10–30%) — online reorganize is usually enough."
    else:
        action = "REORGANIZE"
        hint = "Healthy band (<10%) — maintenance optional."
    return (
        use
        + "-- =========================================================================\n"
        + f"-- REVIEW ONLY — Target: {target}.{idx}\n"
        + f"-- Fragmentation: {pct:.1f}% · Suggested: {action}\n"
        + f"-- {hint}\n"
        + "-- SqlMonitor never executes this.\n"
        + "-- =========================================================================\n"
        f"ALTER INDEX {idx} ON {qualified} {action};\n"
        "GO\n"
    )


# --- Task 3: build_index_health assembly ---

_DISABLE_NOTE = (
    "Disabling is reversible but still requires workload validation before you rely on it."
)


def _parse_start_time(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _compute_uptime(sqlserver_start_time: Any) -> dict:
    start = _parse_start_time(sqlserver_start_time)
    if start is None:
        return {
            "sqlserver_start_time": None,
            "uptime_days": 0.0,
            "insufficient": True,
        }
    now = datetime.now(tz=start.tzinfo) if start.tzinfo else datetime.now()
    uptime_days = max(0.0, (now - start).total_seconds() / 86400.0)
    return {
        "sqlserver_start_time": start.isoformat(),
        "uptime_days": uptime_days,
        "insufficient": uptime_days < INDEX_USAGE_MIN_UPTIME_DAYS,
    }


def _sum_known_sizes(rows: list[dict], key: str = "size_mb") -> tuple[float, bool]:
    total = 0.0
    known = False
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        try:
            total += float(value)
            known = True
        except (TypeError, ValueError):
            continue
    return total, known


def _table_indexes_for(object_id: Any, inventory_rows: list[dict]) -> list[dict]:
    result = []
    for row in inventory_rows:
        if row.get("object_id") != object_id:
            continue
        result.append(
            {
                "name": row.get("index_name"),
                "keys": row.get("key_cols"),
                "includes": row.get("include_cols"),
                "filter": row.get("filter_def"),
                "is_unique": row.get("is_unique"),
                "type": row.get("type"),
            }
        )
    return result


def _usage_severity(writes: int) -> str:
    return "critical" if writes >= INDEX_WRITE_HEAVY_MIN_WRITES else "warn"


def _build_unused_write_heavy_findings(
    usage_rows: list[dict],
    *,
    database_name: str,
    uptime_days: float,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    unused_rows: list[dict] = []
    write_heavy_rows: list[dict] = []
    for row in usage_rows:
        category = classify_usage_row(row)
        if category == "unused":
            unused_rows.append(row)
        elif category == "write_heavy":
            write_heavy_rows.append(row)

    unused_rows.sort(
        key=lambda r: (int(r.get("writes") or 0), float(r.get("size_mb") or 0)),
        reverse=True,
    )
    write_heavy_rows.sort(
        key=lambda r: (
            int(r.get("writes") or 0) - int(r.get("reads") or 0),
            int(r.get("writes") or 0),
        ),
        reverse=True,
    )

    unused_findings = []
    for row in unused_rows[:INDEX_CAP_UNUSED]:
        reads = int(row.get("reads") or 0)
        writes = int(row.get("writes") or 0)
        schema = row.get("schema_name", "")
        table = row.get("table_name", "")
        index_name = row.get("index_name", "")
        confidence, reason, score = assign_confidence(
            "unused", uptime_days=uptime_days, writes=writes
        )
        scripts, blocked = _gated_scripts(
            score,
            [
                {
                    "label": "Copy DISABLE/DROP script for DBA review",
                    "tsql": build_disable_drop_script(
                        schema, table, index_name, confidence_score=score, reasons=[reason]
                    ),
                }
            ],
        )
        finding = {
                "category": "unused",
                "severity": _usage_severity(writes),
                "confidence": confidence,
                "confidence_score": score,
                "confidence_reason": reason,
                "confidence_reasons": [reason],
                "database_name": database_name,
                "schema_name": schema,
                "table_name": table,
                "index_name": index_name,
                "metrics": {
                    "usage": {
                        "reads": reads,
                        "writes": writes,
                        "write_read_ratio": None,
                    },
                    "storage": {"size_mb": row.get("size_mb")},
                },
                "title": f"Unused index {index_name} on {schema}.{table}",
                "recommendation": (
                    "No reads since last SQL Server start; still paying write/maintenance "
                    f"cost — review before drop; confirm a full business cycle. {_DISABLE_NOTE}"
                ),
                "scripts": scripts,
                "table_indexes": [],
                "duplicate_group_id": None,
            }
        if blocked:
            finding["script_blocked_reason"] = blocked
        unused_findings.append(finding)

    write_heavy_findings = []
    for row in write_heavy_rows[:INDEX_CAP_WRITE_HEAVY]:
        reads = int(row.get("reads") or 0)
        writes = int(row.get("writes") or 0)
        schema = row.get("schema_name", "")
        table = row.get("table_name", "")
        index_name = row.get("index_name", "")
        confidence, reason, score = assign_confidence(
            "write_heavy", uptime_days=uptime_days, writes=writes
        )
        scripts, blocked = _gated_scripts(
            score,
            [
                {
                    "label": "Copy DISABLE/DROP script for DBA review",
                    "tsql": build_disable_drop_script(
                        schema, table, index_name, confidence_score=score, reasons=[reason]
                    ),
                }
            ],
        )
        finding = {
                "category": "write_heavy",
                "severity": _usage_severity(writes),
                "confidence": confidence,
                "confidence_score": score,
                "confidence_reason": reason,
                "confidence_reasons": [reason],
                "database_name": database_name,
                "schema_name": schema,
                "table_name": table,
                "index_name": index_name,
                "metrics": {
                    "usage": {
                        "reads": reads,
                        "writes": writes,
                        "write_read_ratio": (writes / reads) if reads else None,
                    },
                    "storage": {"size_mb": row.get("size_mb")},
                },
                "title": f"Write-heavy index {index_name} on {schema}.{table}",
                "recommendation": (
                    "Used for reads but write cost dominates — check whether keys/filter "
                    f"still match workload. {_DISABLE_NOTE}"
                ),
                "scripts": scripts,
                "table_indexes": [],
                "duplicate_group_id": None,
            }
        if blocked:
            finding["script_blocked_reason"] = blocked
        write_heavy_findings.append(finding)

    return unused_findings, write_heavy_findings, unused_rows, write_heavy_rows


def _build_duplicate_findings(
    inventory_rows: list[dict],
    *,
    database_name: str,
    uptime_days: float,
) -> tuple[list[dict], list[dict]]:
    groups = group_exact_duplicates(inventory_rows)
    findings = []
    all_excess: list[dict] = []
    for group in groups:
        confidence, reason, score = assign_confidence("duplicate", uptime_days=uptime_days)
        excess = group["excess"]
        all_excess.extend(excess)
        raw_scripts = [
            {
                "label": f"Copy DISABLE/DROP script for {member.get('index_name')}",
                "tsql": build_disable_drop_script(
                    group["schema"], group["table"], member.get("index_name")
                ),
            }
            for member in excess
        ]
        scripts, blocked = _gated_scripts(score, raw_scripts)
        finding = {
                "category": "duplicate",
                "severity": "warn",
                "confidence": confidence,
                "confidence_score": score,
                "confidence_reason": reason,
                "confidence_reasons": [reason],
                "database_name": database_name,
                "schema_name": group["schema"],
                "table_name": group["table"],
                "index_name": None,
                "metrics": {},
                "title": f"Duplicate indexes on {group['schema']}.{group['table']}",
                "recommendation": (
                    "Same keys/includes/filter — keep one; drop excess only after "
                    "confirming uniqueness/FK needs."
                ),
                "scripts": scripts,
                "table_indexes": [
                    {
                        "name": m.get("index_name"),
                        "keys": m.get("key_cols"),
                        "includes": m.get("include_cols"),
                        "filter": m.get("filter_def"),
                        "is_unique": m.get("is_unique"),
                        "type": m.get("type"),
                    }
                    for m in group["members"]
                ],
                "duplicate_group_id": group["group_id"],
            }
        if blocked:
            finding["script_blocked_reason"] = blocked
        findings.append(finding)
    return findings, all_excess


def _build_heap_findings(
    heap_rows: list[dict],
    *,
    database_name: str,
    uptime_days: float,
) -> list[dict]:
    findings = []
    for row in heap_rows:
        confidence, reason, score = assign_confidence("heap", uptime_days=uptime_days)
        schema = row.get("schema_name", "")
        table = row.get("table_name", "")
        findings.append(
            {
                "category": "heap",
                "severity": "warn",
                "confidence": confidence,
                "confidence_score": score,
                "confidence_reason": reason,
                "confidence_reasons": [reason],
                "database_name": database_name,
                "schema_name": schema,
                "table_name": table,
                "index_name": None,
                "metrics": {"storage": {"size_mb": row.get("size_mb")}},
                "title": f"Heap table {schema}.{table}",
                "recommendation": (
                    "Heap — evaluate a clustered index (often PK) for lookups and "
                    "maintenance behavior."
                ),
                "scripts": [],
                "table_indexes": [],
                "duplicate_group_id": None,
            }
        )
    return findings


def _missing_key_cols(row: dict) -> str:
    equality = str(row.get("equality_columns") or "").strip()
    inequality = str(row.get("inequality_columns") or "").strip()
    parts = [p for p in (equality, inequality) if p]
    return ",".join(parts)


def _missing_impact_score(row: dict) -> float:
    if row.get("impact_score") is not None:
        try:
            return float(row["impact_score"])
        except (TypeError, ValueError):
            pass
    try:
        return float(row.get("avg_user_impact") or 0) * float(
            row.get("avg_total_user_cost") or 0
        ) * float(row.get("user_seeks") or 0)
    except (TypeError, ValueError):
        return 0.0


def _build_missing_findings(
    missing_rows: list[dict],
    inventory_rows: list[dict],
    *,
    database_name: str,
    uptime_days: float,
) -> tuple[list[dict], int]:
    missing_total = len(missing_rows)
    ranked = sorted(missing_rows, key=_missing_impact_score, reverse=True)
    capped = ranked[:INDEX_CAP_MISSING]

    capped_object_ids = {row.get("object_id") for row in capped}
    scoped_inventory = [
        row for row in inventory_rows if row.get("object_id") in capped_object_ids
    ]

    confidence, reason, score = assign_confidence("missing", uptime_days=uptime_days)

    findings = []
    for i, row in enumerate(capped, start=1):
        schema = row.get("schema_name", "")
        table = row.get("table_name", "")
        object_id = row.get("object_id")
        key_cols = _missing_key_cols(row)
        include_cols = row.get("included_columns")
        suggested_name = f"IX_{table}_Missing_{i}"
        scripts, blocked = _gated_scripts(
            score,
            [
                {
                    "label": "Copy suggested CREATE script for review",
                    "tsql": build_create_missing_script(
                        schema,
                        table,
                        suggested_name,
                        key_cols,
                        include_cols=include_cols,
                        confidence_score=score,
                        reasons=[reason],
                    ),
                }
            ],
        )
        finding = {
                "category": "missing",
                "severity": "info",
                "confidence": confidence,
                "confidence_score": score,
                "confidence_reason": reason,
                "confidence_reasons": [reason],
                "database_name": database_name,
                "schema_name": schema,
                "table_name": table,
                "index_name": None,
                "metrics": {
                    "missing": {
                        "user_seeks": row.get("user_seeks"),
                        "avg_user_impact": row.get("avg_user_impact"),
                        "avg_total_user_cost": row.get("avg_total_user_cost"),
                        "impact_score": _missing_impact_score(row),
                    }
                },
                "title": f"Missing index suggestion on {schema}.{table}",
                "recommendation": (
                    "Optimizer suggestion, not a recommendation — compare with existing "
                    "indexes before creating anything."
                ),
                "scripts": scripts,
                "table_indexes": _table_indexes_for(object_id, scoped_inventory),
                "duplicate_group_id": None,
            }
        if blocked:
            finding["script_blocked_reason"] = blocked
        findings.append(finding)
    return findings, missing_total


def build_index_health(raw: dict) -> dict:
    """Assemble the read-only Index Health payload from raw provider rows."""
    database_name = raw.get("database_name", "")
    usage_rows = raw.get("usage_rows") or []
    heap_rows = raw.get("heap_rows") or []
    inventory_rows = raw.get("inventory_rows") or []
    missing_rows = raw.get("missing_rows") or []
    errors = raw.get("errors") or {}

    uptime = _compute_uptime(raw.get("sqlserver_start_time"))
    uptime_days = uptime["uptime_days"]

    unused_findings, write_heavy_findings, unused_rows_all, write_heavy_rows_all = (
        _build_unused_write_heavy_findings(
            usage_rows, database_name=database_name, uptime_days=uptime_days
        )
    )
    duplicate_findings, duplicate_excess_rows = _build_duplicate_findings(
        inventory_rows, database_name=database_name, uptime_days=uptime_days
    )
    heap_findings = _build_heap_findings(
        heap_rows, database_name=database_name, uptime_days=uptime_days
    )
    missing_findings, missing_total = _build_missing_findings(
        missing_rows, inventory_rows, database_name=database_name, uptime_days=uptime_days
    )

    unused_size, unused_known = _sum_known_sizes(unused_rows_all)
    excess_size, excess_known = _sum_known_sizes(duplicate_excess_rows)
    if unused_known or excess_known:
        reviewable_index_space_mb: float | None = unused_size + excess_size
    else:
        reviewable_index_space_mb = None

    summary = {
        "unused": len(unused_rows_all),
        "write_heavy": len(write_heavy_rows_all),
        "duplicate_excess": len(duplicate_excess_rows),
        "heaps": len(heap_rows),
        "missing": len(missing_findings),
        "missing_total": missing_total,
        "reviewable_index_space_mb": reviewable_index_space_mb,
    }

    findings = (
        unused_findings + write_heavy_findings + duplicate_findings + heap_findings + missing_findings
    )

    return {
        "database_name": database_name,
        "uptime": uptime,
        "summary": summary,
        "findings": findings,
        "errors": errors,
    }


# --- v1.1 table-scoped tag glance ---------------------------------------------

PROBLEM_TAGS = ("Unused", "Write-heavy", "High frag", "Duplicate", "Disabled")
STRUCTURAL_TAGS = ("Filtered", "Unique")
ALL_SUMMARY_TAGS = (
    "Unused",
    "Write-heavy",
    "High frag",
    "Duplicate",
    "OK",
    "Filtered",
    "Unique",
    "Disabled",
)


def _dup_key_from_index(row: dict) -> tuple:
    return (
        str(row.get("key_cols") or ""),
        _normalize_includes(row.get("include_cols")),
        str(row.get("filter_def") or ""),
    )


def _duplicate_index_names(index_rows: list[dict]) -> set[str]:
    """Names of indexes that share an exact key/include/filter twin on the table."""
    buckets: dict[tuple, list[str]] = {}
    for row in index_rows:
        if int(row.get("index_id") or 0) <= 0:
            continue
        if row.get("is_hypothetical"):
            continue
        key = _dup_key_from_index(row)
        name = str(row.get("index_name") or "")
        if not name:
            continue
        buckets.setdefault(key, []).append(name)
    names: set[str] = set()
    for members in buckets.values():
        if len(members) >= 2:
            names.update(members)
    return names


def tag_index_row(row: dict, *, duplicate_names: set[str] | None = None) -> list[str]:
    """Return ordered tags for one index row on a selected table."""
    tags: list[str] = []
    duplicate_names = duplicate_names or set()
    index_id = int(row.get("index_id") or 0)
    is_nc = index_id > 1 or str(row.get("type_desc") or "").upper() == "NONCLUSTERED"
    is_pk = bool(row.get("is_primary_key"))
    is_unique_constraint = bool(row.get("is_unique_constraint"))
    is_unique = bool(row.get("is_unique")) or is_pk or is_unique_constraint
    is_disabled = bool(row.get("is_disabled"))
    has_filter = bool(row.get("has_filter")) or bool(str(row.get("filter_def") or "").strip())
    reads = int(row.get("reads") or 0)
    writes = int(row.get("writes") or 0)
    frag = row.get("avg_fragmentation_in_percent")
    pages = int(row.get("page_count") or 0)
    name = str(row.get("index_name") or "")

    # Usage problem tags (NC, not unique/PK)
    eligible_usage = is_nc and not is_pk and not is_unique_constraint and not is_unique
    if eligible_usage and not is_disabled:
        if reads == 0:
            tags.append("Unused")
        elif is_write_heavy(reads, writes):
            tags.append("Write-heavy")

    if frag is not None:
        try:
            frag_f = float(frag)
        except (TypeError, ValueError):
            frag_f = None
        if (
            frag_f is not None
            and frag_f >= INDEX_HIGH_FRAG_PCT
            and pages >= INDEX_HIGH_FRAG_MIN_PAGES
        ):
            tags.append("High frag")

    if name and name in duplicate_names:
        tags.append("Duplicate")

    if is_disabled:
        tags.append("Disabled")

    if has_filter:
        tags.append("Filtered")
    if is_unique:
        tags.append("Unique")

    problem = {t for t in tags if t in PROBLEM_TAGS}
    if not problem:
        tags.insert(0, "OK")

    return tags


def build_table_index_tags(raw: dict) -> dict:
    """Build tag-glance payload for one selected table.

    Raw contract (from get_table_index_snapshot):
      database_name, schema_name, table_name,
      sqlserver_start_time,
      index_rows: list with usage/size/frag/keys,
      missing_rows: optional,
      is_heap: bool,
      errors: dict
    """
    database_name = raw.get("database_name") or ""
    schema_name = raw.get("schema_name") or ""
    table_name = raw.get("table_name") or ""
    index_rows = list(raw.get("index_rows") or [])
    missing_rows = list(raw.get("missing_rows") or [])
    errors = dict(raw.get("errors") or {})
    is_heap = bool(raw.get("is_heap"))

    uptime = _compute_uptime(raw.get("sqlserver_start_time"))
    dup_names = _duplicate_index_names(index_rows)

    indexes_out: list[dict] = []
    summary_counts = {t: 0 for t in ALL_SUMMARY_TAGS}

    for row in index_rows:
        if int(row.get("index_id") or -1) == 0:
            # Heap placeholder row — skip; banner handles heap
            is_heap = True
            continue
        tags = tag_index_row(row, duplicate_names=dup_names)
        for t in tags:
            if t in summary_counts:
                summary_counts[t] += 1

        reads = int(row.get("reads") or 0)
        writes = int(row.get("writes") or 0)
        name = str(row.get("index_name") or "")
        scripts = []
        if "Unused" in tags or "Write-heavy" in tags or "Duplicate" in tags:
            scripts.append(
                {
                    "label": "Copy DISABLE/DROP script for DBA review",
                    "tsql": build_disable_drop_script(schema_name, table_name, name),
                }
            )
        frag_pct = row.get("avg_fragmentation_in_percent")
        try:
            frag_for_script = float(frag_pct) if frag_pct is not None else None
        except (TypeError, ValueError):
            frag_for_script = None
        if frag_for_script is not None and frag_for_script >= 10.0:
            scripts.append(
                {
                    "label": "Copy frag maintenance script for review",
                    "tsql": build_frag_maintenance_script(
                        schema_name,
                        table_name,
                        name,
                        frag_for_script,
                        database=database_name or None,
                    ),
                }
            )

        usage_note = None
        if uptime.get("insufficient") and ("Unused" in tags or "Write-heavy" in tags):
            usage_note = (
                f"Usage stats only cover ~{uptime['uptime_days']:.1f} day(s) since restart — "
                "treat Unused / Write-heavy with caution."
            )

        indexes_out.append(
            {
                "index_id": int(row.get("index_id") or 0),
                "index_name": name,
                "type_desc": row.get("type_desc") or "",
                "tags": tags,
                "metrics": {
                    "usage": {"reads": reads, "writes": writes},
                    "storage": {
                        "size_mb": row.get("size_mb"),
                        "page_count": int(row.get("page_count") or 0),
                    },
                    "frag_pct": row.get("avg_fragmentation_in_percent"),
                },
                "key_cols": row.get("key_cols") or "",
                "include_cols": row.get("include_cols") or "",
                "filter_def": row.get("filter_def") or "",
                "scripts": scripts,
                "usage_note": usage_note,
            }
        )

    # Sort: problem tags first, then name
    def _sort_key(item: dict):
        tags = item.get("tags") or []
        severity = 0 if any(t in PROBLEM_TAGS and t != "Disabled" for t in tags) else 1
        return (severity, (item.get("index_name") or "").lower())

    indexes_out.sort(key=_sort_key)

    missing_out = []
    for m in missing_rows[:INDEX_CAP_MISSING]:
        eq = m.get("equality_columns") or ""
        ineq = m.get("inequality_columns") or ""
        keys = ", ".join(p for p in (eq, ineq) if p)
        missing_out.append(
            {
                "impact_score": m.get("impact_score"),
                "user_seeks": m.get("user_seeks"),
                "equality_columns": eq,
                "inequality_columns": ineq,
                "included_columns": m.get("included_columns"),
                "tags": ["Missing"],
                "scripts": [
                    {
                        "label": "Copy suggested CREATE for review",
                        "tsql": build_create_missing_script(
                            schema_name,
                            table_name,
                            f"IX_missing_{table_name}",
                            keys or "/* columns */",
                            include_cols=m.get("included_columns"),
                        ),
                    }
                ],
            }
        )

    return {
        "database_name": database_name,
        "schema_name": schema_name,
        "table_name": table_name,
        "uptime": uptime,
        "is_heap": is_heap,
        "summary_tag_counts": summary_counts,
        "indexes": indexes_out,
        "missing": missing_out,
        "errors": errors,
        "permissions_hint": errors.get("permissions_hint"),
    }


def build_table_intelligence(raw: dict) -> dict:
    """Full Table Explorer payload: overview, inventory, relationships, missing, recommendations."""
    from modules.indexes import intelligence as intel

    base = build_table_index_tags(raw)
    schema = base["schema_name"]
    table = base["table_name"]
    # Prefer raw index rows (with key_cols) for relationship analysis
    index_rows = [
        r for r in (raw.get("index_rows") or []) if int(r.get("index_id") or 0) > 0
    ]
    # Merge tags from base onto rows by name
    tag_by_name = {i["index_name"]: i.get("tags") for i in base.get("indexes") or []}
    for r in index_rows:
        r = dict(r)
    inventory = []
    for i in base.get("indexes") or []:
        inventory.append(
            {
                **i,
                "key_cols": i.get("key_cols"),
                "include_cols": i.get("include_cols"),
                "filter_def": i.get("filter_def"),
            }
        )

    # Rebuild inventory from raw for analysis fields
    analysis_rows = []
    for r in raw.get("index_rows") or []:
        if int(r.get("index_id") or 0) <= 0:
            continue
        name = r.get("index_name")
        analysis_rows.append(
            {
                **r,
                "tags": tag_by_name.get(name) or [],
            }
        )

    relationships = intel.analyze_relationships(analysis_rows)
    missing_analyzed = intel.analyze_missing(
        raw.get("missing_rows") or [],
        analysis_rows,
        schema=schema,
        table=table,
    )
    uptime = base.get("uptime") or {}
    recommendations = intel.build_recommendations(
        analysis_rows,
        relationships,
        missing_analyzed,
        schema=schema,
        table=table,
        uptime_days=float(uptime.get("uptime_days") or 0),
        is_heap=bool(base.get("is_heap")),
    )
    health = intel.summarize_health(
        analysis_rows,
        relationships,
        missing_analyzed,
        is_heap=bool(base.get("is_heap")),
    )
    meta = raw.get("table_meta") or {}
    return {
        **base,
        "table_meta": meta,
        "health": health,
        "inventory": inventory,
        "relationships": relationships,
        "missing_intelligence": missing_analyzed,
        "recommendations": recommendations,
    }


def apply_frag_to_payload(payload: dict, frag_rows: list[dict]) -> dict:
    """Merge lazy frag results into inventory/tags/recommendations."""
    by_id = {int(r.get("index_id") or -1): r for r in frag_rows or []}
    schema_name = str(payload.get("schema_name") or "")
    table_name = str(payload.get("table_name") or "")
    database_name = str(payload.get("database_name") or "") or None

    def _merge(row: dict) -> None:
        iid = int(row.get("index_id") or -1)
        fr = by_id.get(iid)
        if not fr:
            return
        metrics = row.setdefault("metrics", {})
        metrics["frag_pct"] = fr.get("avg_fragmentation_in_percent")
        if fr.get("page_count") is not None:
            storage = metrics.setdefault("storage", {})
            storage["page_count"] = fr.get("page_count")
        tags = list(row.get("tags") or [])
        try:
            frag_f = float(fr.get("avg_fragmentation_in_percent"))
        except (TypeError, ValueError):
            frag_f = None
        pages = int(fr.get("page_count") or 0)
        if (
            frag_f is not None
            and frag_f >= INDEX_HIGH_FRAG_PCT
            and pages >= INDEX_HIGH_FRAG_MIN_PAGES
            and "High frag" not in tags
        ):
            if "OK" in tags:
                tags.remove("OK")
            tags.append("High frag")
            row["tags"] = tags
        if frag_f is not None and frag_f >= 10.0 and schema_name and table_name:
            name = str(row.get("index_name") or "")
            if name:
                scripts = list(row.get("scripts") or [])
                already = any("REBUILD" in (s.get("tsql") or "") or "REORGANIZE" in (s.get("tsql") or "") for s in scripts)
                if not already:
                    scripts.append(
                        {
                            "label": "Copy frag maintenance script for review",
                            "tsql": build_frag_maintenance_script(
                                schema_name,
                                table_name,
                                name,
                                frag_f,
                                database=database_name,
                            ),
                        }
                    )
                    row["scripts"] = scripts

    for row in payload.get("inventory") or []:
        _merge(row)
    for row in payload.get("indexes") or []:
        _merge(row)
    payload["frag_loaded"] = True
    return payload


def compute_overview_kpis(raw: dict) -> dict:
    """Pure Overview KPI cells for v1 strip (no Consolidation).

    Returns keys: missing_impact, high_frag, dead_unused_writes, duplicate_debt.
    Each cell has value, display ("int"|"dash"), sub_key, tone; unused also has writes.
    """
    totals = raw.get("totals") or {}
    sections = raw.get("sections") or {}
    unused = raw.get("unused") or sections.get("unused") or []
    write_heavy = raw.get("write_heavy") or sections.get("write_heavy") or []
    missing = raw.get("missing_by_table") or sections.get("missing_by_table") or []
    duplicates = raw.get("duplicates") or sections.get("duplicates") or []

    impact = 0.0
    peak_impact_pct = 0.0
    for row in missing:
        impact += float(_missing_impact_score(row) or 0)
        try:
            peak_impact_pct = max(peak_impact_pct, float(row.get("avg_user_impact") or 0))
        except (TypeError, ValueError):
            pass
    if missing:
        missing_value = int(round(impact))
    else:
        missing_value = int(totals.get("missing_suggestions") or 0)

    missing_cell = {
        "value": missing_value,
        "display": "int",
        "sub_key": "missing_sub",
        "tone": "is-warn" if missing_value or peak_impact_pct else "",
    }
    if peak_impact_pct > 0:
        missing_cell["peak_impact_pct"] = round(peak_impact_pct, 1)
        missing_cell["display_mode"] = "pct"

    frag_available = bool(raw.get("frag_available") or raw.get("frag_loaded"))
    if frag_available:
        high_frag_cell = {
            "value": int(totals.get("high_frag") or 0),
            "display": "int",
            "sub_key": "frag_sub",
            "tone": "is-warn" if int(totals.get("high_frag") or 0) else "",
        }
    else:
        high_frag_cell = {
            "value": None,
            "display": "dash",
            "sub_key": "frag_pending",
            "tone": "",
        }

    dead_rows = [r for r in unused if int(r.get("writes") or 0) > 0]
    dead_from_rows = len(dead_rows)
    dead_writes = sum(int(r.get("writes") or 0) for r in dead_rows)
    if "unused_with_writes" in totals:
        dead_n = int(totals.get("unused_with_writes") or 0)
        if "unused_write_ops" in totals:
            dead_writes = int(totals.get("unused_write_ops") or 0)
    else:
        dead_n = dead_from_rows

    wh_n = int(totals.get("write_heavy") or 0)
    if wh_n <= 0 and write_heavy:
        wh_n = len(write_heavy)
    wh_writes = sum(int(r.get("writes") or 0) for r in write_heavy)

    # Card aligns with triage write-tax findings: unused·wasted + write-heavy
    write_waste_n = dead_n + wh_n
    write_waste_ops = dead_writes + wh_writes

    dup_n = len(duplicates) if duplicates else 0
    if dup_n == 0:
        dup_n = int(totals.get("duplicates") or totals.get("duplicate_tables") or 0)

    return {
        "missing_impact": missing_cell,
        "high_frag": high_frag_cell,
        "dead_unused_writes": {
            "value": write_waste_n,
            "writes": write_waste_ops,
            "unused_with_writes": dead_n,
            "write_heavy": wh_n,
            "display": "int",
            "sub_key": "write_waste_sub",
            "tone": "is-warn" if write_waste_n else "",
        },
        "duplicate_debt": {
            "value": dup_n,
            "display": "int",
            "sub_key": "duplicate_sub",
            "tone": "is-warn" if dup_n else "",
        },
    }


def build_overview_payload(raw: dict) -> dict:
    """Shape environment overview for Health + Triage tabs."""
    from modules.indexes.triage import build_triage_findings

    uptime = _compute_uptime(raw.get("sqlserver_start_time"))
    totals = raw.get("totals") or {}
    # Preserve None for high_frag when absent so KPI can show dash (not fake zero).
    high_frag_raw = totals["high_frag"] if "high_frag" in totals else None
    payload = {
        "uptime": uptime,
        "databases_available": raw.get("databases_available") or 0,
        "databases_scanned": totals.get("databases_scanned") or 0,
        "databases_scanned_list": raw.get("databases_scanned_list") or [],
        "scan_mode": raw.get("scan_mode") or "quick",
        "source": raw.get("source") or "live",
        "advisor_meta": raw.get("advisor_meta") or {},
        "catalog": raw.get("catalog"),
        "frag_loaded": bool(raw.get("frag_loaded")),
        "frag_available": bool(raw.get("frag_available") or raw.get("frag_loaded")),
        "totals": {
            "indexes": totals.get("indexes") or 0,
            "need_review": totals.get("need_review") or 0,
            "unused": totals.get("unused") or 0,
            "unused_with_writes": int(totals.get("unused_with_writes") or 0),
            "unused_write_ops": int(totals.get("unused_write_ops") or 0),
            "write_heavy": totals.get("write_heavy") or 0,
            "heaps": totals.get("heaps") or 0,
            "high_frag": 0 if high_frag_raw is None else int(high_frag_raw or 0),
            "missing_suggestions": totals.get("missing_suggestions") or 0,
            "duplicates": int(totals.get("duplicates") or totals.get("duplicate_tables") or 0),
        },
        "sections": {
            "write_heavy": raw.get("write_heavy") or [],
            "unused": raw.get("unused") or [],
            "heaps": raw.get("heaps") or [],
            "missing_by_table": raw.get("missing_by_table") or [],
            "duplicates": raw.get("duplicates") or [],
        },
        "errors": raw.get("errors") or {},
        "permissions_hint": raw.get("permissions_hint"),
        "kpi_supplement": raw.get("kpi_supplement"),
    }
    payload["findings"] = build_triage_findings(payload)
    payload["kpis"] = compute_overview_kpis(
        {
            **raw,
            "unused": payload["sections"]["unused"],
            "write_heavy": payload["sections"]["write_heavy"],
            "missing_by_table": payload["sections"]["missing_by_table"],
            "duplicates": payload["sections"]["duplicates"],
            "frag_available": payload["frag_available"],
            "frag_loaded": payload["frag_loaded"],
            "totals": {
                **payload["totals"],
                # Keep availability separate from coerced display total
                "high_frag": high_frag_raw,
                "duplicates": payload["totals"]["duplicates"],
            },
            "source": payload.get("source"),
        }
    )
    return payload
