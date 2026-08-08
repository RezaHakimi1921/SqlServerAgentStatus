"""Pure Index Intelligence analysis — relationships, missing compare, recommendations.

No Dash / SQL. Operates on normalized index row dicts from the provider/service.
"""
from __future__ import annotations

from typing import Any

from modules.indexes.constants import (
    INDEX_HIGH_FRAG_MIN_PAGES,
    INDEX_HIGH_FRAG_PCT,
    INDEX_USAGE_MIN_UPTIME_DAYS,
    INDEX_WRITE_HEAVY_MIN_WRITES,
)
from modules.indexes.service import is_write_heavy


def _scripts():
    from modules.indexes.service import (
        build_create_missing_script,
        build_disable_drop_script,
        quotename,
    )
    return build_create_missing_script, build_disable_drop_script, quotename


def _split_cols(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    return [p.strip() for p in str(raw).split(",") if p.strip()]


def _norm_includes(raw: str | None) -> frozenset[str]:
    return frozenset(_split_cols(raw))


def _keys(row: dict) -> list[str]:
    return _split_cols(row.get("key_cols"))


def _is_nc_drop_candidate(row: dict) -> bool:
    iid = int(row.get("index_id") or 0)
    if iid <= 1:
        return False
    if row.get("is_primary_key") or row.get("is_unique_constraint") or row.get("is_unique"):
        return False
    if row.get("is_disabled") or row.get("is_hypothetical"):
        return False
    return True


def analyze_relationships(indexes: list[dict]) -> list[dict]:
    """Exact duplicate, covered-by, and prefix-overlap pairs (non-heap indexes)."""
    rows = [r for r in indexes if int(r.get("index_id") or 0) > 0]
    findings: list[dict] = []

    # Exact duplicates
    buckets: dict[tuple, list[dict]] = {}
    for r in rows:
        key = (
            tuple(_keys(r)),
            frozenset(_norm_includes(r.get("include_cols"))),
            str(r.get("filter_def") or "").strip(),
        )
        buckets.setdefault(key, []).append(r)
    for members in buckets.values():
        if len(members) < 2:
            continue
        keep = members[0]
        for excess in members[1:]:
            findings.append(
                {
                    "kind": "exact_duplicate",
                    "severity": "warn",
                    "index_a": keep.get("index_name"),
                    "index_b": excess.get("index_name"),
                    "title": "Exact duplicate indexes",
                    "analysis": (
                        f"{excess.get('index_name')} is structurally identical to "
                        f"{keep.get('index_name')} (same keys, includes, and filter)."
                    ),
                    "recommendation": (
                        f"Review removing {excess.get('index_name')} after confirming "
                        "no unique/FK dependency relies on it."
                    ),
                }
            )

    # Covered-by / prefix (pairwise among NC)
    n = len(rows)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            a, b = rows[i], rows[j]
            ka, kb = _keys(a), _keys(b)
            if not ka or not kb:
                continue
            # B covered by A: same keys, includes(B) ⊆ includes(A), A has more/equal includes
            if ka == kb:
                inc_a = _norm_includes(a.get("include_cols"))
                inc_b = _norm_includes(b.get("include_cols"))
                filt_a = str(a.get("filter_def") or "").strip()
                filt_b = str(b.get("filter_def") or "").strip()
                if filt_a != filt_b:
                    continue
                if inc_b < inc_a:  # strict subset
                    findings.append(
                        {
                            "kind": "covered_by",
                            "severity": "warn",
                            "index_a": a.get("index_name"),
                            "index_b": b.get("index_name"),
                            "title": "Index covered by a wider include list",
                            "analysis": (
                                f"{b.get('index_name')} has the same keys as "
                                f"{a.get('index_name')} but a smaller INCLUDE set. "
                                f"Queries using {b.get('index_name')} are likely satisfiable by "
                                f"{a.get('index_name')}."
                            ),
                            "recommendation": (
                                f"Review consolidating by removing {b.get('index_name')} "
                                f"if {a.get('index_name')} covers the workload."
                            ),
                        }
                    )
            # Prefix: kb is strict prefix of ka → shorter may be redundant
            if len(kb) < len(ka) and ka[: len(kb)] == kb:
                if a.get("is_unique") or a.get("is_primary_key") or b.get("is_unique") or b.get("is_primary_key"):
                    # still report investigate, never strong remove on unique
                    risk = "high"
                else:
                    risk = "medium"
                findings.append(
                    {
                        "kind": "prefix_overlap",
                        "severity": "info",
                        "index_a": a.get("index_name"),  # longer
                        "index_b": b.get("index_name"),  # shorter prefix
                        "title": "Left-prefix overlap",
                        "analysis": (
                            f"{b.get('index_name')} keys are a left-prefix of "
                            f"{a.get('index_name')}. Seeks on the shorter key set may use the longer index."
                        ),
                        "recommendation": (
                            f"Validate whether {b.get('index_name')} is still needed; "
                            f"if workload allows, keep {a.get('index_name')} only."
                        ),
                        "risk": risk,
                    }
                )

    # Dedupe identical pairs
    seen = set()
    out = []
    for f in findings:
        sig = (f["kind"], f.get("index_a"), f.get("index_b"))
        if sig in seen:
            continue
        seen.add(sig)
        out.append(f)
    return out


def analyze_missing(missing_rows: list[dict], indexes: list[dict], *, schema: str, table: str) -> list[dict]:
    """Compare missing-index DMV rows to existing indexes."""
    existing = [r for r in indexes if int(r.get("index_id") or 0) > 0]
    results = []
    for m in missing_rows:
        eq = _split_cols(m.get("equality_columns"))
        ineq = _split_cols(m.get("inequality_columns"))
        suggested_keys = eq + ineq
        suggested_inc = _norm_includes(m.get("included_columns"))
        action = "create_new"
        related = None
        analysis = "No closely related existing index found for this pattern."
        recommendation = (
            "Optimizer suggestion only — compare with query plans before creating anything."
        )

        best = None
        best_score = -1
        for ex in existing:
            keys = _keys(ex)
            if not suggested_keys or not keys:
                continue
            # leading key match length
            match = 0
            for a, b in zip(keys, suggested_keys):
                if a.lower() == b.lower().strip("[]"):
                    match += 1
                else:
                    break
            if match == 0:
                continue
            score = match * 10
            inc = _norm_includes(ex.get("include_cols"))
            if suggested_inc and suggested_inc <= inc:
                score += 5
            if match == len(suggested_keys) and keys[: len(suggested_keys)] == suggested_keys:
                score += 20
            if score > best_score:
                best_score = score
                best = ex

        if best is not None:
            related = best.get("index_name")
            bkeys = _keys(best)
            binc = _norm_includes(best.get("include_cols"))
            if (
                len(bkeys) >= len(suggested_keys)
                and [k.lower() for k in bkeys[: len(suggested_keys)]]
                == [k.lower().strip("[]") for k in suggested_keys]
                and suggested_inc
                and not suggested_inc <= binc
            ):
                action = "extend_existing"
                missing_inc = sorted(suggested_inc - binc)
                analysis = (
                    f"Suggestion overlaps {related}. Keys already align; "
                    f"INCLUDE is missing: {', '.join(missing_inc) or '(none)'}."
                )
                recommendation = (
                    f"Do not create a new index first — consider extending {related} "
                    f"with INCLUDE ({', '.join(missing_inc)}) after validating workload."
                )
            elif (
                len(bkeys) >= len(suggested_keys)
                and [k.lower() for k in bkeys[: len(suggested_keys)]]
                == [k.lower().strip("[]") for k in suggested_keys]
                and (not suggested_inc or suggested_inc <= binc)
            ):
                action = "ignore_near_duplicate"
                analysis = (
                    f"Existing {related} already covers this key pattern "
                    f"(and INCLUDE overlap). Creating another index is likely redundant."
                )
                recommendation = f"Prefer ignoring this suggestion; investigate plans using {related}."
            else:
                action = "create_new"
                analysis = f"Closest existing index is {related}, but keys/includes differ enough that a new index may still be considered."
                recommendation = "Compare plans; prefer extending an existing index when possible."

        key_sql = ", ".join(suggested_keys) if suggested_keys else "/* columns */"
        inc_sql = ", ".join(sorted(suggested_inc)) if suggested_inc else None
        scripts = []
        build_create_missing_script, _, quotename = _scripts()
        if action == "create_new":
            scripts.append(
                {
                    "label": "Copy suggested CREATE for review",
                    "tsql": build_create_missing_script(
                        schema, table, f"IX_{table}_missing", key_sql, include_cols=inc_sql
                    ),
                }
            )
        elif action == "extend_existing" and related:
            scripts.append(
                {
                    "label": "Copy note for DBA review",
                    "tsql": (
                        "-- REVIEW ONLY — not executed by SqlMonitor\n"
                        f"-- Consider extending {quotename(related)} on "
                        f"{quotename(schema)}.{quotename(table)}\n"
                        f"-- Suggested INCLUDE add: {inc_sql or ''}\n"
                        "-- Prefer DROP+CREATE or online rebuild strategy in SSMS after validation.\n"
                    ),
                }
            )

        results.append(
            {
                "equality_columns": m.get("equality_columns"),
                "inequality_columns": m.get("inequality_columns"),
                "included_columns": m.get("included_columns"),
                "user_seeks": m.get("user_seeks"),
                "impact_score": m.get("impact_score"),
                "action": action,
                "related_index": related,
                "analysis": analysis,
                "recommendation": recommendation,
                "scripts": scripts,
            }
        )
    return results


def build_recommendations(
    indexes: list[dict],
    relationships: list[dict],
    missing_analyzed: list[dict],
    *,
    schema: str,
    table: str,
    uptime_days: float,
    is_heap: bool,
) -> list[dict]:
    """Categorized recommendations with problem / why / evidence / action / risk."""
    recs: list[dict] = []
    insufficient = float(uptime_days or 0) < INDEX_USAGE_MIN_UPTIME_DAYS
    _, build_disable_drop_script, _ = _scripts()

    if is_heap:
        recs.append(
            {
                "category": "INVESTIGATE",
                "severity": "warn",
                "problem": f"{schema}.{table} is a heap (no clustered index).",
                "why": "Heaps can cause forwarding lookups and unpredictable I/O for large tables.",
                "evidence": {"heap": True},
                "suggested_action": "Evaluate a clustered index (often on the PK) for this table.",
                "risk": "Medium — clustering large tables needs maintenance window planning.",
                "scripts": [],
                "index_name": None,
            }
        )

    for row in indexes:
        if int(row.get("index_id") or 0) <= 0:
            continue
        name = row.get("index_name") or ""
        reads = int(row.get("reads") or 0)
        writes = int(row.get("writes") or 0)
        size_mb = row.get("size_mb")
        frag = row.get("avg_fragmentation_in_percent")
        pages = int(row.get("page_count") or 0)

        if _is_nc_drop_candidate(row) and reads == 0:
            cat = "INVESTIGATE" if insufficient else "REMOVE_CANDIDATE"
            recs.append(
                {
                    "category": cat,
                    "severity": "warn" if not insufficient else "info",
                    "problem": f"{name} has zero reads since restart.",
                    "why": (
                        "The index still incurs write and storage cost with no observed seek/scan/lookup benefit "
                        "in the current usage window."
                        + (" Usage window may be too short after restart." if insufficient else "")
                    ),
                    "evidence": {"reads": reads, "writes": writes, "size_mb": size_mb},
                    "suggested_action": (
                        "Validate a full business cycle, then consider DISABLE → monitor → DROP in SSMS."
                    ),
                    "risk": "High if monthly/quarterly reports need this index.",
                    "scripts": [
                        {
                            "label": "Copy DISABLE/DROP for review",
                            "tsql": build_disable_drop_script(schema, table, name),
                        }
                    ],
                    "index_name": name,
                }
            )
        elif _is_nc_drop_candidate(row) and is_write_heavy(reads, writes):
            recs.append(
                {
                    "category": "INVESTIGATE",
                    "severity": "warn",
                    "problem": f"{name} is write-heavy relative to reads.",
                    "why": "Maintenance cost dominates; the index may still help some queries but amplifies writes.",
                    "evidence": {"reads": reads, "writes": writes, "size_mb": size_mb},
                    "suggested_action": "Review whether keys/includes still match critical queries; consider consolidation.",
                    "risk": "Medium — dropping may regress specific seeks.",
                    "scripts": [
                        {
                            "label": "Copy DISABLE/DROP for review",
                            "tsql": build_disable_drop_script(schema, table, name),
                        }
                    ],
                    "index_name": name,
                }
            )

        if (
            frag is not None
            and float(frag) >= INDEX_HIGH_FRAG_PCT
            and pages >= INDEX_HIGH_FRAG_MIN_PAGES
        ):
            recs.append(
                {
                    "category": "INVESTIGATE",
                    "severity": "info",
                    "problem": f"{name} shows high fragmentation ({float(frag):.1f}%).",
                    "why": "Fragmentation can increase scan cost; rebuild/reorganize needs workload context.",
                    "evidence": {"frag_pct": float(frag), "page_count": pages},
                    "suggested_action": "Investigate in maintenance windows — do not rebuild blindly.",
                    "risk": "Medium — rebuilds can lock/block and stress TempDB.",
                    "scripts": [],
                    "index_name": name,
                }
            )

    for rel in relationships:
        if rel["kind"] == "exact_duplicate":
            recs.append(
                {
                    "category": "REMOVE_CANDIDATE",
                    "severity": "warn",
                    "problem": f"Exact duplicate: {rel.get('index_b')} vs {rel.get('index_a')}.",
                    "why": rel.get("analysis"),
                    "evidence": {"kind": "exact_duplicate"},
                    "suggested_action": rel.get("recommendation"),
                    "risk": "Medium — confirm uniqueness constraints.",
                    "scripts": [
                        {
                            "label": "Copy DROP for review",
                            "tsql": build_disable_drop_script(schema, table, rel.get("index_b") or ""),
                        }
                    ],
                    "index_name": rel.get("index_b"),
                }
            )
        elif rel["kind"] in ("covered_by", "prefix_overlap"):
            recs.append(
                {
                    "category": "CONSOLIDATE",
                    "severity": "warn" if rel["kind"] == "covered_by" else "info",
                    "problem": rel.get("title"),
                    "why": rel.get("analysis"),
                    "evidence": {"kind": rel["kind"], "a": rel.get("index_a"), "b": rel.get("index_b")},
                    "suggested_action": rel.get("recommendation"),
                    "risk": rel.get("risk") or "Medium",
                    "scripts": [],
                    "index_name": rel.get("index_b"),
                }
            )

    for m in missing_analyzed:
        if m.get("action") == "extend_existing":
            recs.append(
                {
                    "category": "IMPROVE_EXISTING",
                    "severity": "info",
                    "problem": "Missing-index suggestion overlaps an existing index.",
                    "why": m.get("analysis"),
                    "evidence": {
                        "impact_score": m.get("impact_score"),
                        "user_seeks": m.get("user_seeks"),
                        "related_index": m.get("related_index"),
                    },
                    "suggested_action": m.get("recommendation"),
                    "risk": "Low–Medium — extending INCLUDE widens the index and write cost.",
                    "scripts": m.get("scripts") or [],
                    "index_name": m.get("related_index"),
                }
            )
        elif m.get("action") == "ignore_near_duplicate":
            recs.append(
                {
                    "category": "INVESTIGATE",
                    "severity": "info",
                    "problem": "Missing suggestion likely redundant with an existing index.",
                    "why": m.get("analysis"),
                    "evidence": {"impact_score": m.get("impact_score"), "related_index": m.get("related_index")},
                    "suggested_action": m.get("recommendation"),
                    "risk": "Low",
                    "scripts": [],
                    "index_name": m.get("related_index"),
                }
            )

    # Prefer actionable categories first
    order = {"REMOVE_CANDIDATE": 0, "CONSOLIDATE": 1, "IMPROVE_EXISTING": 2, "INVESTIGATE": 3}
    recs.sort(key=lambda r: (order.get(r.get("category"), 9), r.get("problem") or ""))
    return recs


def summarize_health(indexes: list[dict], relationships: list[dict], missing_analyzed: list[dict], *, is_heap: bool) -> dict[str, Any]:
    unused = write_heavy = 0
    for row in indexes:
        if int(row.get("index_id") or 0) <= 0:
            continue
        if not _is_nc_drop_candidate(row) and not (
            int(row.get("index_id") or 0) > 1
            and not row.get("is_primary_key")
            and not row.get("is_unique_constraint")
        ):
            # still count write-heavy on unique? plan: usage tags for NC non-unique primarily
            pass
        reads = int(row.get("reads") or 0)
        writes = int(row.get("writes") or 0)
        if _is_nc_drop_candidate(row) and reads == 0:
            unused += 1
        elif _is_nc_drop_candidate(row) and is_write_heavy(reads, writes):
            write_heavy += 1
    exact = sum(1 for r in relationships if r["kind"] == "exact_duplicate")
    consolidate = sum(1 for r in relationships if r["kind"] in ("covered_by", "prefix_overlap"))
    extend = sum(1 for m in missing_analyzed if m.get("action") == "extend_existing")
    need_review = unused + write_heavy + exact + consolidate + extend + (1 if is_heap else 0)
    return {
        "indexes": len([r for r in indexes if int(r.get("index_id") or 0) > 0]),
        "unused": unused,
        "write_heavy": write_heavy,
        "duplicate": exact,
        "possible_consolidation": consolidate,
        "missing_patterns": len(missing_analyzed),
        "need_review": need_review,
        "is_heap": is_heap,
        "health": "needs_optimization" if need_review else "ok",
    }
