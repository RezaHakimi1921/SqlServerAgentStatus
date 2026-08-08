"""Tables & Growth — pure composition (no Dash, no SQL)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from modules.tables.constants import (
    TABLES_DELTA_WINDOWS_DAYS,
    TABLES_GROWERS_N,
    TABLES_TOP_N,
)


def _key(row: dict) -> Tuple[str, str, str]:
    return (
        str(row.get("database_name") or ""),
        str(row.get("schema_name") or ""),
        str(row.get("table_name") or ""),
    )


def _num(v: Any) -> float:
    try:
        if v is None:
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _int(v: Any) -> int:
    try:
        if v is None:
            return 0
        return int(v)
    except (TypeError, ValueError):
        return 0


def rollup_databases(tables: List[dict]) -> List[dict]:
    by_db: Dict[str, dict] = {}
    for t in tables:
        db = str(t.get("database_name") or "")
        if not db:
            continue
        bucket = by_db.setdefault(
            db,
            {
                "database_name": db,
                "table_count": 0,
                "total_size_mb": 0.0,
                "total_rows": 0,
                "heap_count": 0,
            },
        )
        bucket["table_count"] += 1
        bucket["total_size_mb"] += _num(t.get("size_mb"))
        bucket["total_rows"] += _int(t.get("row_count"))
        if t.get("is_heap"):
            bucket["heap_count"] += 1
    out = list(by_db.values())
    out.sort(key=lambda r: r["total_size_mb"], reverse=True)
    return out


def attach_deltas(
    current: List[dict],
    history_by_window: Dict[int, Dict[Tuple[str, str, str], dict]],
) -> List[dict]:
    """Attach delta_mb_Nd / delta_rows_Nd for each window in history_by_window."""
    out: List[dict] = []
    for row in current:
        item = dict(row)
        k = _key(row)
        cur_mb = _num(row.get("size_mb"))
        cur_rows = _int(row.get("row_count"))
        for days, prior_map in history_by_window.items():
            prior = prior_map.get(k)
            if prior is None:
                item[f"delta_mb_{days}d"] = None
                item[f"delta_rows_{days}d"] = None
            else:
                item[f"delta_mb_{days}d"] = cur_mb - _num(prior.get("size_mb"))
                item[f"delta_rows_{days}d"] = cur_rows - _int(prior.get("row_count"))
        out.append(item)
    return out


def pick_top_tables(tables: List[dict], *, top: int = TABLES_TOP_N) -> List[dict]:
    ranked = sorted(tables, key=lambda r: _num(r.get("size_mb")), reverse=True)
    return ranked[: max(0, int(top))]


def pick_growers(
    tables: List[dict],
    *,
    window_days: int = 7,
    top: int = TABLES_GROWERS_N,
) -> List[dict]:
    key = f"delta_mb_{int(window_days)}d"
    growers = [
        t for t in tables
        if t.get(key) is not None and _num(t.get(key)) > 0
    ]
    growers.sort(key=lambda r: _num(r.get(key)), reverse=True)
    return growers[: max(0, int(top))]


def build_tables_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Compose UI-ready payload from provider raw snapshot."""
    current = list(raw.get("tables") or [])
    history_by_window: Dict[int, Dict[Tuple[str, str, str], dict]] = {}
    hist_raw = raw.get("history_by_window") or {}
    for days in TABLES_DELTA_WINDOWS_DAYS:
        rows = hist_raw.get(str(days)) or hist_raw.get(days) or []
        history_by_window[int(days)] = {_key(r): r for r in rows}

    with_deltas = attach_deltas(current, history_by_window)
    databases = rollup_databases(with_deltas)
    top_tables = pick_top_tables(with_deltas)
    growers = pick_growers(with_deltas, window_days=7)
    if not growers:
        growers = pick_growers(with_deltas, window_days=1)

    return {
        "source": raw.get("source") or "live",
        "history_available": bool(raw.get("history_available")),
        "latest_capture_date": raw.get("latest_capture_date"),
        "databases": databases,
        "top_tables": top_tables,
        "growers": growers,
        "table_count": len(with_deltas),
        "errors": raw.get("errors") or {},
        "permissions_hint": raw.get("permissions_hint"),
        "note": raw.get("note"),
    }
