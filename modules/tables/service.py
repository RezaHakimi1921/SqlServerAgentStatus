"""Tables & Growth — pure composition (no Dash, no SQL)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Sequence, Tuple

from modules.tables.constants import (
    TABLES_DELTA_HOT_MULT,
    TABLES_DELTA_MEAN_FLOOR_MB,
    TABLES_DELTA_MEAN_FLOOR_ROWS,
    TABLES_DELTA_WARM_MULT,
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


def as_bit(v: Any) -> bool:
    """Normalize SQL BIT / pyodbc bytes / 0|1 into a real bool."""
    if v is None or v is False:
        return False
    if v is True:
        return True
    if isinstance(v, (bytes, bytearray, memoryview)):
        b = bytes(v)
        return len(b) > 0 and b[0] != 0
    if isinstance(v, (int, float)):
        return int(v) != 0
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y")
    return bool(v)


def _as_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None
    return None


def pick_prior_capture_date(
    latest: Any,
    capture_dates: Sequence[Any],
    window_days: int,
) -> date | None:
    """Pick baseline capture for an N-day window.

    Prefer the newest date on or before (latest − N days). If history is shorter
    than N days, fall back to the **oldest** date strictly before latest so
    7d/30d use the full available span (not the same 1-day prior as 1d).
    """
    latest_d = _as_date(latest)
    if latest_d is None:
        return None
    dates = sorted({d for d in (_as_date(x) for x in capture_dates) if d is not None})
    if not dates:
        return None
    target = latest_d - timedelta(days=int(window_days))
    on_or_before_target = [d for d in dates if d <= target]
    if on_or_before_target:
        return on_or_before_target[-1]
    older = [d for d in dates if d < latest_d]
    return older[0] if older else None


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
                "delta_mb_1d": 0.0,
                "delta_mb_7d": 0.0,
                "delta_mb_30d": 0.0,
                "has_delta_1d": False,
                "has_delta_7d": False,
                "has_delta_30d": False,
            },
        )
        bucket["table_count"] += 1
        bucket["total_size_mb"] += _num(t.get("size_mb"))
        bucket["total_rows"] += _int(t.get("row_count"))
        if as_bit(t.get("is_heap")):
            bucket["heap_count"] += 1
        for days in (1, 7, 30):
            dkey = f"delta_mb_{days}d"
            val = t.get(dkey)
            if val is not None:
                bucket[dkey] += _num(val)
                bucket[f"has_delta_{days}d"] = True
    out = list(by_db.values())
    out.sort(key=lambda r: r["total_size_mb"], reverse=True)
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
        if not t.get("is_deleted")
        and t.get(key) is not None
        and _num(t.get(key)) > 0
    ]
    growers.sort(key=lambda r: _num(r.get(key)), reverse=True)
    return growers[: max(0, int(top))]


def positive_delta_mean(tables: List[dict], key: str) -> float | None:
    """Mean of positive deltas across all live tables (all databases)."""
    vals = [
        _num(t.get(key))
        for t in tables
        if not t.get("is_deleted")
        and t.get(key) is not None
        and _num(t.get(key)) > 0
    ]
    if not vals:
        return None
    return sum(vals) / len(vals)


def delta_tone(
    value: Any,
    mean: float | None,
    *,
    floor: float,
    hot_mult: float = TABLES_DELTA_HOT_MULT,
    warm_mult: float = TABLES_DELTA_WARM_MULT,
) -> str:
    """Relative tone vs server-wide positive mean for the window.

    hot ≥ 2× mean · warm ≥ 1.25× mean · ok = below that ·
    drop = negative (shrink) · muted = zero / missing
    """
    if value is None:
        return "muted"
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "muted"
    if n < 0:
        return "drop"
    if n == 0:
        return "muted"
    baseline = max(float(mean) if mean is not None and mean > 0 else 0.0, float(floor))
    if baseline <= 0:
        return "ok"
    if n >= baseline * float(hot_mult):
        return "hot"
    if n >= baseline * float(warm_mult):
        return "warm"
    return "ok"


def build_delta_baselines(
    tables: List[dict],
    databases: List[dict] | None = None,
) -> Dict[str, Dict[str, float | None]]:
    """Per-window mean positive Δ across all databases (tables + DB rollups)."""
    out: Dict[str, Dict[str, float | None]] = {}
    for days in TABLES_DELTA_WINDOWS_DAYS:
        mb_key = f"delta_mb_{days}d"
        rows_key = f"delta_rows_{days}d"
        mb_mean = positive_delta_mean(tables, mb_key)
        rows_mean = positive_delta_mean(tables, rows_key)
        db_vals = [
            _num(d.get(mb_key))
            for d in (databases or [])
            if d.get(f"has_delta_{days}d")
            and d.get(mb_key) is not None
            and _num(d.get(mb_key)) > 0
        ]
        db_mean = (sum(db_vals) / len(db_vals)) if db_vals else None
        out[str(days)] = {
            "mb": None if mb_mean is None else round(mb_mean, 3),
            "rows": None if rows_mean is None else round(rows_mean, 3),
            "db_mb": None if db_mean is None else round(db_mean, 3),
        }
    return out


def window_delta_total(tables: List[dict], *, window_days: int) -> float | None:
    key = f"delta_mb_{int(window_days)}d"
    vals = [t.get(key) for t in tables if t.get(key) is not None]
    if not vals:
        return None
    return sum(_num(v) for v in vals)


def compose_deleted_tables(
    history_rows: List[dict],
    current_keys: set[Tuple[str, str, str]],
) -> List[dict]:
    """Build DELETED rows: last known size/rows + growth vs older history captures."""
    from collections import defaultdict

    by_key: Dict[Tuple[str, str, str], List[dict]] = defaultdict(list)
    for r in history_rows or []:
        by_key[_key(r)].append(r)

    out: List[dict] = []
    for key, series in by_key.items():
        if key in current_keys:
            continue
        dated: list[tuple[date, dict]] = []
        for r in series:
            d = _as_date(r.get("captured_date"))
            if d is None:
                continue
            dated.append((d, r))
        if not dated:
            continue
        dated.sort(key=lambda x: x[0])
        last_d, last = dated[-1]
        dates = [d for d, _ in dated]
        by_date = {d: r for d, r in dated}
        last_mb = _num(last.get("size_mb"))
        last_rows = _int(last.get("row_count"))
        item: Dict[str, Any] = {
            "database_name": key[0],
            "schema_name": key[1] or "dbo",
            "table_name": key[2],
            "row_count": last_rows,
            "size_mb": round(last_mb, 3),
            "is_heap": as_bit(last.get("is_heap")),
            "source": "history",
            "is_deleted": True,
            "last_seen": last_d.isoformat(),
        }
        for days in TABLES_DELTA_WINDOWS_DAYS:
            prior_d = pick_prior_capture_date(last_d, dates, int(days))
            if prior_d is None or prior_d == last_d:
                item[f"delta_mb_{days}d"] = None
                item[f"delta_rows_{days}d"] = None
                continue
            prior = by_date.get(prior_d)
            if prior is None:
                item[f"delta_mb_{days}d"] = None
                item[f"delta_rows_{days}d"] = None
                continue
            item[f"delta_mb_{days}d"] = round(last_mb - _num(prior.get("size_mb")), 3)
            item[f"delta_rows_{days}d"] = last_rows - _int(prior.get("row_count"))
        out.append(item)
    out.sort(key=lambda r: _num(r.get("size_mb")), reverse=True)
    return out


def filter_sort_tables(
    tables: List[dict],
    *,
    database: str | None = None,
    search: str = "",
    sort: str = "size_mb",
    window_days: int = 7,
    type_status: str | None = "all",
) -> List[dict]:
    q = (search or "").strip().lower()
    db = (database or "").strip()
    if db in ("", "All", "__all__"):
        db = ""
    status = (type_status or "all").strip().lower()
    if status in ("", "all", "all types"):
        status = "all"
    delta_key = f"delta_mb_{int(window_days)}d"
    rows_key = f"delta_rows_{int(window_days)}d"

    filtered: List[dict] = []
    for t in tables:
        if db and str(t.get("database_name") or "") != db:
            continue
        is_deleted = bool(t.get("is_deleted"))
        is_heap = as_bit(t.get("is_heap"))
        if status == "deleted":
            if not is_deleted:
                continue
        elif status == "heap":
            if is_deleted or not is_heap:
                continue
        elif status == "clustered":
            if is_deleted or is_heap:
                continue
        if q:
            # Type keywords still work in search; prefer Type picker for status.
            if q == "deleted":
                if not is_deleted:
                    continue
            elif q in ("heap", "heaps"):
                if is_deleted or not is_heap:
                    continue
            elif q in ("clustered", "cluster", "ci"):
                if is_deleted or is_heap:
                    continue
            else:
                blob = t.get("_q")
                if not blob:
                    type_label = (
                        "deleted" if is_deleted else ("heap" if is_heap else "clustered")
                    )
                    blob = (
                        f"{t.get('schema_name')}.{t.get('table_name')} "
                        f"{t.get('database_name')} {type_label} "
                        f"{t.get('last_seen') or ''}"
                    ).lower()
                if q not in blob:
                    continue
        filtered.append(t)

    def sort_key(t: dict):
        if sort == "delta_mb":
            v = t.get(delta_key)
            return _num(v) if v is not None else -1e18
        if sort == "delta_pct":
            size = _num(t.get("size_mb"))
            d = t.get(delta_key)
            if d is None or size <= 0:
                return -1e18
            return _num(d) / size
        if sort == "row_count":
            return _num(t.get("row_count"))
        if sort == "delta_rows":
            v = t.get(rows_key)
            return _num(v) if v is not None else -1e18
        return _num(t.get("size_mb"))

    filtered.sort(key=sort_key, reverse=True)
    return filtered


def build_tables_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Compose UI-ready payload from provider raw snapshot."""
    current = list(raw.get("tables") or [])
    history_by_window: Dict[int, Dict[Tuple[str, str, str], dict]] = {}
    hist_raw = raw.get("history_by_window") or {}
    for days in TABLES_DELTA_WINDOWS_DAYS:
        rows = hist_raw.get(str(days)) or hist_raw.get(days) or []
        history_by_window[int(days)] = {_key(r): r for r in rows}

    with_deltas = attach_deltas(current, history_by_window)
    current_keys = {_key(t) for t in with_deltas}
    deleted_raw = list(raw.get("deleted_history_rows") or [])
    if deleted_raw:
        # Provider already scoped these rows to missing keys; empty current_keys
        # intersection still required so compose keeps last-seen + deltas.
        deleted_tables = compose_deleted_tables(deleted_raw, current_keys)
    else:
        deleted_tables = [
            t for t in (raw.get("deleted_tables") or []) if _key(t) not in current_keys
        ]

    databases = rollup_databases(with_deltas)
    total_size = sum(_num(t.get("size_mb")) for t in with_deltas)
    total_rows = sum(_int(t.get("row_count")) for t in with_deltas)
    heap_tables = sum(1 for t in with_deltas if as_bit(t.get("is_heap")))
    heap_dbs = sum(1 for d in databases if (d.get("heap_count") or 0) > 0)

    def _slim(t: dict, *, deleted: bool = False) -> dict:
        item = {
            "database_name": t.get("database_name"),
            "schema_name": t.get("schema_name"),
            "table_name": t.get("table_name"),
            "row_count": _int(t.get("row_count")),
            "size_mb": round(_num(t.get("size_mb")), 3),
            "is_heap": as_bit(t.get("is_heap")),
            "source": t.get("source") or ("history" if deleted else "live"),
            "is_deleted": bool(deleted or t.get("is_deleted")),
        }
        if item["is_deleted"]:
            item["last_seen"] = t.get("last_seen")
        for days in TABLES_DELTA_WINDOWS_DAYS:
            dmb = t.get(f"delta_mb_{days}d")
            dr = t.get(f"delta_rows_{days}d")
            item[f"delta_mb_{days}d"] = None if dmb is None else round(_num(dmb), 3)
            item[f"delta_rows_{days}d"] = None if dr is None else _int(dr)
        type_label = (
            "deleted" if item["is_deleted"]
            else ("heap" if item["is_heap"] else "clustered")
        )
        # Precomputed lowercase blob — All Tables live search stays O(n) but cheap.
        item["_q"] = (
            f"{item.get('schema_name')}.{item.get('table_name')} "
            f"{item.get('database_name')} {type_label} "
            f"{item.get('last_seen') or ''}"
        ).lower()
        return item

    # Live/catalog first; DELETED appended (search `deleted` filters to these).
    slim_tables: List[dict] = [_slim(t) for t in with_deltas]
    slim_deleted = [_slim(t, deleted=True) for t in deleted_tables]
    slim_tables.extend(slim_deleted)

    live_only = [t for t in slim_tables if not t.get("is_deleted")]
    growers_by_window = {
        str(days): pick_growers(live_only, window_days=days, top=TABLES_GROWERS_N)
        for days in (1, 7, 30)
    }
    growth_totals = {
        str(days): window_delta_total(live_only, window_days=days)
        for days in (1, 7, 30)
    }
    delta_baselines = build_delta_baselines(live_only, databases)
    db_names = sorted(
        {str(t.get("database_name") or "") for t in slim_tables if t.get("database_name")}
    )

    return {
        "source": raw.get("source") or "live",
        "history_available": bool(raw.get("history_available")),
        "latest_capture_date": raw.get("latest_capture_date"),
        "databases": databases,
        "db_names": db_names,
        "tables": slim_tables,
        "top_tables": pick_top_tables(live_only),
        "growers": growers_by_window.get("7") or growers_by_window.get("1") or [],
        "growers_by_window": growers_by_window,
        "growth_totals": growth_totals,
        "delta_baselines": delta_baselines,
        "total_size_mb": round(total_size, 3),
        "total_rows": total_rows,
        "heap_table_count": heap_tables,
        "heap_db_count": heap_dbs,
        "table_count": len(live_only),
        "deleted_table_count": len(slim_deleted),
        "errors": raw.get("errors") or {},
        "permissions_hint": raw.get("permissions_hint"),
        "note": raw.get("note"),
    }
