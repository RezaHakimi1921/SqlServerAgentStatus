"""Tables & Growth UI — Figma TablesGrowth.tsx fidelity."""
from __future__ import annotations

import math
from urllib.parse import quote

from dash import dcc, html

from core.formatters import fmt_int
from core.i18n import DEFAULT_LOCALE, normalize_locale, t
from modules.tables.constants import (
    TABLES_DELTA_MEAN_FLOOR_MB,
    TABLES_DELTA_MEAN_FLOOR_ROWS,
    TABLES_PAGE_SIZE,
    TABLES_TYPE_FILTERS,
)
from modules.tables.service import delta_tone, filter_sort_tables


def _fmt_mb(v) -> str:
    if v is None:
        return "—"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    if abs(n) >= 1024:
        return f"{n / 1024:.2f} GB"
    if abs(n) >= 100:
        return f"{n:.0f} MB"
    return f"{n:.1f} MB"


def _fmt_compact(n) -> str:
    """Compact count for dense table (Figma); full value in title via fmt_int."""
    try:
        v = float(n or 0)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1_000_000_000:
        return f"{sign}{v / 1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"{sign}{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{sign}{v / 1_000:.1f}K"
    return sign + fmt_int(int(v))


def _baseline_for(
    payload: dict | None, window_days: int
) -> tuple[float | None, float | None, float | None]:
    base = ((payload or {}).get("delta_baselines") or {}).get(str(window_days)) or {}
    return base.get("mb"), base.get("rows"), base.get("db_mb")


def _delta_class(mb, *, mean_mb: float | None = None) -> str:
    tone = delta_tone(mb, mean_mb, floor=TABLES_DELTA_MEAN_FLOOR_MB)
    return f"tables-delta is-{tone}"


def _rows_delta_class(rows, *, mean_rows: float | None = None) -> str:
    tone = delta_tone(rows, mean_rows, floor=TABLES_DELTA_MEAN_FLOOR_ROWS)
    return f"tables-delta is-{tone}"


def _fmt_delta(mb) -> str:
    if mb is None:
        return "—"
    try:
        n = float(mb)
    except (TypeError, ValueError):
        return "—"
    if n == 0:
        return "—"
    sign = "+" if n > 0 else ""
    return f"{sign}{_fmt_mb(n)}"


def _fmt_rows_delta(rows) -> str:
    if rows is None:
        return "—"
    try:
        n = float(rows)
    except (TypeError, ValueError):
        return "—"
    if n == 0:
        return "—"
    if n > 0:
        return "+" + _fmt_compact(n)
    return _fmt_compact(n)


def _window_days(window: str | None) -> int:
    w = (window or "7d").strip().lower()
    if w == "1d":
        return 1
    if w == "30d":
        return 30
    return 7


def build_tables_layout(locale: str = "en") -> html.Div:
    locale = normalize_locale(locale)
    return html.Div(
        className="tables-shell",
        # App root is dir=rtl; Tables & Growth must stay LTR like Figma.
        **{"dir": "ltr"},
        children=[
            html.Div(className="tables-mod-header", children=[
                html.Div(className="tables-subtabs", children=[
                    html.Button(
                        t("tables.tab.overview", locale),
                        id="tables-tab-overview",
                        n_clicks=0,
                        type="button",
                        className="tables-subtab is-active",
                    ),
                    html.Button(
                        t("tables.tab.all", locale),
                        id="tables-tab-all",
                        n_clicks=0,
                        type="button",
                        className="tables-subtab",
                    ),
                ]),
                html.Div(className="tables-header-right", children=[
                    html.Span(
                        id="tables-history-pill",
                        className="tables-history-pill is-warn",
                        children=t("tables.badge.no_history", locale),
                    ),
                    html.Span(
                        id="tables-source-badge",
                        className="tables-source-badge",
                        children=t("common.none", locale),
                    ),
                    html.Span(id="tables-captured-date", className="tables-captured-date"),
                    html.Div(className="tables-window-group", children=[
                        html.Button("1d", id="tables-win-1d", n_clicks=0, type="button", className="tables-win-btn"),
                        html.Button("7d", id="tables-win-7d", n_clicks=0, type="button", className="tables-win-btn is-active"),
                        html.Button("30d", id="tables-win-30d", n_clicks=0, type="button", className="tables-win-btn"),
                    ]),
                    html.Button(
                        [html.Span("↻", className="ctrl-ico"), html.Span(t("header.refresh", locale), className="ctrl-txt")],
                        id="btn-tables-refresh",
                        className="activity-ctrl-btn is-refresh",
                        n_clicks=0,
                        title=t("tables.btn.refresh_title", locale),
                    ),
                    html.Button(
                        [html.Span("⇪", className="ctrl-ico"), html.Span(t("tables.btn.capture_today", locale), className="ctrl-txt")],
                        id="btn-tables-capture",
                        className="activity-ctrl-btn",
                        n_clicks=0,
                        title=t("tables.btn.capture_title", locale),
                    ),
                ]),
            ]),
            html.Div(
                id="tables-all-toolbar",
                className="tables-all-controls hidden",
                children=[
                    html.Div(className="tables-db-field", children=[
                        html.Label(t("tables.label.database", locale), className="tables-search-label"),
                        html.Div(className="tables-db-picker", children=[
                            html.Button(
                                [
                                    html.Span(
                                        id="tables-db-label",
                                        children=t("common.all", locale),
                                        className="tables-db-label",
                                    ),
                                    html.Span("▾", className="tables-db-chevron"),
                                ],
                                id="tables-db-toggle",
                                className="tables-db-toggle",
                                n_clicks=0,
                                type="button",
                            ),
                            html.Div(
                                id="tables-db-panel",
                                className="tables-db-panel hidden",
                                children=[
                                    dcc.Input(
                                        id="tables-db-filter-q",
                                        type="search",
                                        value="",
                                        placeholder=t("tables.placeholder.search_db", locale),
                                        className="tables-db-filter-q",
                                        debounce=True,
                                        autoComplete="off",
                                    ),
                                    html.Div(
                                        id="tables-db-options",
                                        className="tables-db-options",
                                        children=render_tables_db_options(["All"], selected="All"),
                                    ),
                                ],
                            ),
                        ]),
                    ]),
                    html.Div(className="tables-db-field tables-type-field", children=[
                        html.Label(t("tables.label.type", locale), className="tables-search-label"),
                        html.Div(className="tables-db-picker", children=[
                            html.Button(
                                [
                                    html.Span(
                                        id="tables-type-label",
                                        children=t("tables.type.all", locale),
                                        className="tables-db-label",
                                    ),
                                    html.Span("▾", className="tables-db-chevron"),
                                ],
                                id="tables-type-toggle",
                                className="tables-db-toggle",
                                n_clicks=0,
                                type="button",
                                title="Filter by Clustered / Heap / Deleted",
                            ),
                            html.Div(
                                id="tables-type-panel",
                                className="tables-db-panel hidden",
                                children=render_tables_type_options(selected="all", locale=locale),
                            ),
                        ]),
                    ]),
                    html.Div(className="tables-search-field", children=[
                        html.Label(
                            t("tables.label.search", locale),
                            htmlFor="tables-search",
                            className="tables-search-label",
                        ),
                        html.Div(className="tables-search-wrap", children=[
                            html.Span(
                                className="tables-search-ico",
                                children=html.Img(
                                    src=(
                                        "data:image/svg+xml,"
                                        "%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' "
                                        "fill='none' stroke='%238b949e' stroke-width='2' "
                                        "stroke-linecap='round' stroke-linejoin='round' viewBox='0 0 24 24'%3E"
                                        "%3Ccircle cx='11' cy='11' r='7'/%3E"
                                        "%3Cpath d='M20 20l-3.5-3.5'/%3E"
                                        "%3C/svg%3E"
                                    ),
                                    alt="",
                                    draggable="false",
                                ),
                            ),
                            dcc.Input(
                                id="tables-search",
                                type="search",
                                value="",
                                placeholder=t("tables.placeholder.search", locale),
                                className="tables-search-input",
                                debounce=False,
                                n_submit=0,
                                autoComplete="off",
                            ),
                        ]),
                    ]),
                    html.Div(className="tables-sort-group", children=[
                        html.Span(t("tables.label.sort", locale), className="tables-sort-label"),
                        html.Button(t("tables.sort.size", locale), id={"type": "tables-sort", "key": "size_mb"}, n_clicks=0, type="button", className="tables-sort-btn is-active"),
                        html.Button(t("tables.sort.rows", locale), id={"type": "tables-sort", "key": "row_count"}, n_clicks=0, type="button", className="tables-sort-btn"),
                        html.Button(t("tables.sort.delta_mb", locale, window="7d"), id={"type": "tables-sort", "key": "delta_mb"}, n_clicks=0, type="button", className="tables-sort-btn"),
                        html.Button(t("tables.sort.delta_pct", locale), id={"type": "tables-sort", "key": "delta_pct"}, n_clicks=0, type="button", className="tables-sort-btn"),
                    ]),
                ],
            ),
            html.Div(id="tables-meta", className="tables-meta activity-meta"),
            html.Div(
                className="tables-content-wrap",
                children=[
                    html.Div(
                        id="tables-loading",
                        className="tables-loading-overlay view-center-loading hidden",
                        children=[
                            html.Div(className="activity-loading-spinner"),
                            html.Div(t("tables.loading", locale), className="view-center-loading-text"),
                            html.Div(
                                t("tables.loading_sub", locale),
                                className="view-center-loading-sub",
                            ),
                        ],
                    ),
                    # Dual panels: toggle visibility clientside (instant tab switch)
                    html.Div(
                        id="tables-panel-overview",
                        className="tables-panel-host",
                        children=html.Div("…", className="tables-empty"),
                    ),
                    html.Div(
                        id="tables-panel-all",
                        className="tables-panel-host hidden",
                        children=html.Div("…", className="tables-empty"),
                    ),
                    # Pagination stays in the shell so button IDs are never destroyed
                    html.Div(
                        id="tables-pagination",
                        className="tables-pagination hidden",
                        children=[
                            html.Div(id="tables-pagination-info", className="tables-pagination-info"),
                            html.Div(className="tables-pagination-controls", children=[
                                html.Button(
                                    t("common.pager.prev", locale),
                                    id="btn-tables-page-prev",
                                    n_clicks=0,
                                    type="button",
                                    className="tables-page-btn",
                                    disabled=True,
                                ),
                                html.Span(id="tables-page-pos", className="tables-page-pos", children="—"),
                                html.Button(
                                    t("common.pager.next", locale),
                                    id="btn-tables-page-next",
                                    n_clicks=0,
                                    type="button",
                                    className="tables-page-btn",
                                    disabled=True,
                                ),
                            ]),
                        ],
                    ),
                ],
            ),
            dcc.Store(id="store-tables", data=None),
            dcc.Store(id="store-tables-section", data="overview"),
            dcc.Store(id="store-tables-window", data="7d"),
            dcc.Store(id="store-tables-sort", data="size_mb"),
            dcc.Store(id="store-tables-db", data="All"),
            dcc.Store(id="store-tables-db-names", data=["All"]),
            dcc.Store(id="store-tables-db-open", data=False),
            dcc.Store(id="store-tables-type", data="all"),
            dcc.Store(id="store-tables-type-open", data=False),
            dcc.Store(id="store-tables-search", data=""),
            dcc.Store(id="store-tables-page", data=1),
            dcc.Interval(
                id="tables-search-debounce",
                interval=120,
                n_intervals=0,
                disabled=True,
                max_intervals=-1,
            ),
        ],
    )


_TABLES_TYPE_I18N_KEY = {
    "all": "tables.type.all",
    "clustered": "tables.type.clustered",
    "heap": "tables.type.heap",
    "deleted": "tables.type.deleted",
}


def tables_type_label(key: str | None, locale: str = DEFAULT_LOCALE) -> str:
    locale = normalize_locale(locale)
    k = (key or "all").strip().lower()
    i18n_key = _TABLES_TYPE_I18N_KEY.get(k)
    if i18n_key:
        return t(i18n_key, locale)
    for value, label in TABLES_TYPE_FILTERS:
        if value == k:
            return label
    return t("tables.type.all", locale)


def render_tables_type_options(*, selected: str = "all", locale: str = DEFAULT_LOCALE) -> html.Div:
    """Type status picker: All / Clustered / Heap / Deleted."""
    locale = normalize_locale(locale)
    selected = (selected or "all").strip().lower()
    if selected not in {k for k, _ in TABLES_TYPE_FILTERS}:
        selected = "all"
    items = []
    for key, _fallback_label in TABLES_TYPE_FILTERS:
        label = tables_type_label(key, locale)
        items.append(html.Button(
            label,
            id={"type": "tables-type-hit", "key": key},
            n_clicks=0,
            type="button",
            className="tables-db-hit" + (" is-active" if key == selected else ""),
            title=label,
        ))
    return html.Div(items, className="tables-db-hit-list")


def render_tables_db_options(
    names: list[str] | None,
    *,
    selected: str = "All",
    query: str = "",
) -> html.Div:
    """Dark custom DB picker options (no white Dash dropdown)."""
    q = (query or "").strip().lower()
    selected = selected or "All"
    opts: list[str] = ["All"]
    for n in names or []:
        n = str(n or "").strip()
        if not n or n == "All" or n in opts:
            continue
        opts.append(n)
    if q:
        opts = [n for n in opts if q in n.lower() or n == "All"]
    if not opts:
        return html.Div("No databases match.", className="tables-db-empty")
    items = []
    for i, name in enumerate(opts):
        items.append(html.Button(
            name,
            id={"type": "tables-db-hit", "index": i},
            n_clicks=0,
            type="button",
            className="tables-db-hit" + (" is-active" if name == selected else ""),
            title=name,
        ))
    return html.Div(items, className="tables-db-hit-list")


def tables_db_option_values(names: list[str] | None, query: str = "") -> list[str]:
    q = (query or "").strip().lower()
    opts: list[str] = ["All"]
    for n in names or []:
        n = str(n or "").strip()
        if not n or n == "All" or n in opts:
            continue
        opts.append(n)
    if q:
        opts = [n for n in opts if q in n.lower() or n == "All"]
    return opts


def render_tables_meta(payload: dict | None, capture_msg: str | None = None) -> str:
    if not payload:
        return capture_msg or ""
    parts = []
    if payload.get("note"):
        parts.append(str(payload["note"]))
    if capture_msg:
        parts.append(capture_msg)
    return " · ".join(parts)


def render_header_status(payload: dict | None, locale: str = DEFAULT_LOCALE) -> tuple:
    locale = normalize_locale(locale)
    if not payload:
        return t("tables.badge.no_data", locale), t("common.none", locale), ""
    hist = (
        t("tables.badge.history_ok", locale)
        if payload.get("history_available")
        else t("tables.badge.no_history", locale)
    )
    src = (payload.get("source") or "live").lower()
    if src == "capture":
        src_label = t("tables.badge.capture", locale)
    elif src == "catalog":
        src_label = t("tables.badge.catalog", locale)
    elif src == "history":
        src_label = t("tables.badge.history", locale)
    else:
        src_label = t("tables.badge.live", locale)
    date_el = payload.get("latest_capture_date") or ""
    return hist, src_label, date_el


def render_tables_loading(label: str | None = None, locale: str = DEFAULT_LOCALE) -> html.Div:
    locale = normalize_locale(locale)
    if label is None:
        label = t("tables.loading", locale)
    return html.Div(
        className="tables-inline-loading",
        children=[
            html.Div(className="activity-loading-spinner"),
            html.Div(label, className="activity-loading-text"),
        ],
    )


def render_overview(payload: dict | None, *, window: str = "7d", locale: str = DEFAULT_LOCALE) -> html.Div:
    locale = normalize_locale(locale)
    if not payload:
        return render_tables_loading(locale=locale)
    errors = payload.get("errors") or {}
    if errors and not (payload.get("tables") or payload.get("databases")):
        hint = payload.get("permissions_hint")
        return html.Div(className="state-box state-error", children=[
            html.H3(t("tables.error.load", locale)),
            html.P("; ".join(f"{k}: {v}" for k, v in list(errors.items())[:3])),
            html.P(hint) if hint else None,
        ])

    days = _window_days(window)
    dkey = f"delta_mb_{days}d"
    total_size = payload.get("total_size_mb") or 0
    total_rows = payload.get("total_rows") or 0
    table_count = payload.get("table_count") or 0
    dbs = payload.get("databases") or []
    growth = (payload.get("growth_totals") or {}).get(str(days))
    heap_dbs = payload.get("heap_db_count") or 0
    history = bool(payload.get("history_available"))
    growers = (payload.get("growers_by_window") or {}).get(str(days)) or []
    mean_mb, _mean_rows, mean_db_mb = _baseline_for(payload, days)
    # KPI is server total growth — alert vs sum of DB means is noisy; use 2× mean DB growth × db count heuristic skip.
    # Keep alert when total growth is hot vs mean DB rollup × number of growing DBs is awkward; use simple: total > 0 and extreme.
    growth_alert = False
    if growth is not None and mean_db_mb is not None and mean_db_mb > 0 and dbs:
        growing = sum(
            1
            for d in dbs
            if d.get(f"has_delta_{days}d") and (d.get(dkey) or 0) and float(d.get(dkey) or 0) > 0
        )
        if growing > 0 and float(growth) >= float(mean_db_mb) * growing * 1.5:
            growth_alert = True

    return html.Div(className="tables-overview tables-body", children=[
        html.Div(className="tables-kpi-row", children=[
            _kpi(
                t("tables.kpi.total_size", locale),
                _fmt_mb(total_size),
                t("tables.kpi.sub_dbs", locale, n=fmt_int(len(dbs))),
            ),
            _kpi(
                t("tables.kpi.total_rows", locale),
                _fmt_compact(total_rows),
                t("tables.kpi.sub_tables", locale, n=fmt_int(table_count)),
            ),
            _kpi(
                t("tables.kpi.growth", locale, window=window),
                _fmt_delta(growth) if growth is not None else "—",
                t("tables.kpi.sub_across", locale) if history else t("tables.hint.capture_for_deltas", locale),
                alert=growth_alert,
            ),
            _kpi(
                t("tables.kpi.heaps", locale),
                fmt_int(payload.get("heap_table_count") or 0),
                t("tables.kpi.sub_dbs", locale, n=fmt_int(heap_dbs)),
                alert=(payload.get("heap_table_count") or 0) > 0,
            ),
        ]),
        html.Div(className="tables-two-col", children=[
            html.Div(className="tables-panel", children=[
                html.Div(
                    f"{t('tables.panel.space_by_db', locale)} — {_fmt_mb(total_size)}",
                    className="tables-panel-title",
                ),
                _db_breakdown(
                    dbs,
                    total_size=total_size,
                    delta_key=dkey,
                    mean_db_mb=mean_db_mb,
                ),
            ]),
            html.Div(className="tables-panel", children=[
                html.Div(className="tables-panel-title-row", children=[
                    html.Div(
                        f"{t('tables.panel.top_growers', locale)} — {window}",
                        className="tables-panel-title",
                    ),
                    None if history else html.Span(
                        t("tables.hint.no_history", locale),
                        className="tables-panel-hint",
                    ),
                ]),
                _top_growers(
                    growers,
                    delta_key=dkey,
                    history=history,
                    window_growth=growth,
                    mean_mb=mean_mb,
                    locale=locale,
                ),
            ]),
        ]),
    ])


def page_slice_meta(
    total: int,
    page: int,
) -> tuple[int, int, int, int, int]:
    """Return page, total_pages, start_idx, start_n, end_n (1-based display)."""
    page_size = int(TABLES_PAGE_SIZE)
    total_pages = max(1, math.ceil(total / page_size)) if total else 1
    page = max(1, min(int(page or 1), total_pages))
    start = (page - 1) * page_size
    start_n = start + 1 if total else 0
    end_n = min(page * page_size, total)
    return page, total_pages, start, start_n, end_n


def render_pagination_info(
    total: int, page: int, total_pages: int, start_n: int, end_n: int, locale: str = DEFAULT_LOCALE
):
    locale = normalize_locale(locale)
    return t(
        "tables.pager.showing",
        locale,
        start=fmt_int(start_n),
        end=fmt_int(end_n),
        total=fmt_int(total),
    )


def render_all_tables(
    payload: dict | None,
    *,
    window: str = "7d",
    search: str = "",
    database: str = "All",
    sort: str = "size_mb",
    page: int = 1,
    type_status: str = "all",
    locale: str = DEFAULT_LOCALE,
) -> html.Div:
    locale = normalize_locale(locale)
    if not payload:
        return html.Div(t("tables.empty.no_data", locale), className="tables-empty")

    days = _window_days(window)
    dkey = f"delta_mb_{days}d"
    rkey = f"delta_rows_{days}d"
    filtered = filter_sort_tables(
        payload.get("tables") or [],
        database=database,
        search=search,
        sort=sort or "size_mb",
        window_days=days,
        type_status=type_status,
    )
    total = len(filtered)
    page, _total_pages, start, _sn, _en = page_slice_meta(total, page)
    page_size = int(TABLES_PAGE_SIZE)
    shown = filtered[start:start + page_size]
    mean_mb, mean_rows, _mean_db = _baseline_for(payload, days)

    header = html.Div(className="tables-grid-header", children=[
        html.Div(t("tables.col.database", locale)),
        html.Div(t("tables.col.schema_table", locale)),
        html.Div(t("tables.col.source", locale)),
        html.Div(t("tables.col.type", locale)),
        html.Div(t("tables.col.rows", locale), className="is-num"),
        html.Div(t("tables.col.size", locale), className="is-num"),
        html.Div(t("tables.col.delta_rows", locale, window=window), className="is-num"),
        html.Div(t("tables.col.delta_mb", locale, window=window), className="is-num"),
    ])

    body_rows = []
    for i, row in enumerate(shown):
        d_mb = row.get(dkey)
        d_rows = row.get(rkey)
        is_deleted = bool(row.get("is_deleted"))
        src = (row.get("source") or payload.get("source") or "live").lower()
        if is_deleted:
            src = "history"
        elif src not in ("catalog", "live", "history", "capture"):
            src = "live"
        size_mb = row.get("size_mb")
        size_cls = "tables-col-num"
        try:
            if float(size_mb or 0) > 2000:
                size_cls += " is-size-warn"
        except (TypeError, ValueError):
            pass
        rows_val = row.get("row_count") or 0
        last_seen = row.get("last_seen") or ""
        table_cell = [
            html.Div(
                f"{row.get('schema_name') or 'dbo'}.{row.get('table_name') or '?'}",
                className="tables-col-table-name",
            )
        ]
        if is_deleted and last_seen:
            table_cell.append(
                html.Div(
                    t("tables.hint.last_seen", locale, date=last_seen),
                    className="tables-col-last-seen",
                )
            )
        if src == "history":
            src_label, src_cls = t("tables.badge.history", locale), "tables-source-badge is-history"
        elif src == "capture":
            src_label, src_cls = t("tables.badge.capture", locale), "tables-source-badge is-live"
        elif src == "catalog":
            src_label, src_cls = t("tables.badge.catalog", locale), "tables-source-badge is-catalog"
        else:
            src_label, src_cls = t("tables.badge.live", locale), "tables-source-badge is-live"
        if is_deleted:
            type_child = html.Span(t("tables.type.deleted_badge", locale), className="tables-deleted-pill")
        elif row.get("is_heap"):
            type_child = html.Span(t("tables.type.heap_badge", locale), className="tables-heap-pill")
        else:
            type_child = html.Span(t("tables.type.clustered_badge", locale), className="tables-type-muted")
        body_rows.append(html.Div(
            className="tables-grid-row"
            + (" is-alt" if i % 2 else "")
            + (" is-deleted" if is_deleted else ""),
            children=[
                html.Div(row.get("database_name") or "—", className="tables-col-db"),
                html.Div(table_cell, className="tables-col-table"),
                html.Div(html.Span(src_label, className=src_cls)),
                html.Div(type_child),
                html.Div(
                    _fmt_compact(rows_val),
                    className="tables-col-num",
                    title=(
                        f"Last known rows {fmt_int(rows_val)}"
                        if is_deleted
                        else fmt_int(rows_val)
                    ),
                ),
                html.Div(
                    _fmt_mb(size_mb),
                    className=size_cls,
                    title="Last known size" if is_deleted else None,
                ),
                html.Div(
                    _fmt_rows_delta(d_rows),
                    className="tables-col-num " + _rows_delta_class(d_rows, mean_rows=mean_rows),
                    title=fmt_int(int(d_rows)) if d_rows is not None else "",
                ),
                html.Div(
                    className="tables-col-growth",
                    children=[
                        _sparkline(
                            float(d_mb or 0),
                            seed=f"{row.get('database_name')}.{row.get('table_name')}",
                            mean_mb=mean_mb,
                        )
                        if d_mb is not None and float(d_mb) > 0
                        else html.Span(
                            "↓" if d_mb is not None and float(d_mb) < 0 else "—",
                            className=(
                                "tables-delta is-drop"
                                if d_mb is not None and float(d_mb) < 0
                                else "tables-delta is-muted"
                            ),
                        ),
                        html.Span(_fmt_delta(d_mb), className=_delta_class(d_mb, mean_mb=mean_mb)),
                    ],
                ),
            ],
        ))

    grid_kids = [header]
    if body_rows:
        grid_kids.extend(body_rows)
    else:
        grid_kids.append(html.Div(
            t("tables.empty.no_match", locale),
            className="tables-empty tables-grid-empty",
        ))
    return html.Div(className="tables-all tables-body", children=[
        html.Div(className="tables-grid-scroll", children=[
            html.Div(className="tables-grid", children=grid_kids),
        ]),
    ])


def _kpi(label: str, value: str, sub: str, *, alert: bool = False) -> html.Div:
    return html.Div(
        className="tables-kpi" + (" is-alert" if alert else ""),
        children=[
            html.Div(label, className="tables-kpi-label"),
            html.Div(value, className="tables-kpi-value"),
            html.Div(sub, className="tables-kpi-sub"),
        ],
    )


def _db_breakdown(
    dbs: list,
    *,
    total_size: float,
    delta_key: str,
    mean_db_mb: float | None = None,
) -> html.Div:
    if not dbs:
        return html.Div("No databases.", className="tables-empty")
    total = float(total_size) or 1.0
    rows = []
    for d in dbs:
        size = float(d.get("total_size_mb") or 0)
        pct = min(100, max(0, round(size / total * 100)))
        days = delta_key.replace("delta_mb_", "").replace("d", "")
        has = d.get(f"has_delta_{days}d")
        delta = d.get(delta_key) if has else None
        # Do NOT badge a whole DB as HEAP just because ≥1 heap table exists.
        rows.append(html.Div(className="tables-db-bar-row", children=[
            html.Div(className="tables-db-bar-top", children=[
                html.Div(className="tables-db-bar-left", children=[
                    html.Span(d.get("database_name") or "?", className="tables-db-bar-name"),
                    html.Span(f"{fmt_int(d.get('table_count') or 0)} tables", className="tables-db-bar-count"),
                ]),
                html.Div(className="tables-db-bar-right", children=[
                    html.Span(
                        _fmt_delta(delta),
                        className=_delta_class(delta, mean_mb=mean_db_mb),
                    ),
                    html.Span(_fmt_mb(size), className="tables-db-bar-size"),
                    html.Span(f"{pct}%", className="tables-db-bar-pct"),
                ]),
            ]),
            html.Div(className="tables-db-bar-track", children=[
                html.Div(className="tables-db-bar-fill", style={"width": f"{pct}%"}),
            ]),
        ]))
    return html.Div(className="tables-db-bars", children=rows)


def _spark_color(delta: float, *, mean_mb: float | None = None) -> str:
    tone = delta_tone(delta, mean_mb, floor=TABLES_DELTA_MEAN_FLOOR_MB)
    return {
        "hot": "#f85149",
        "warm": "#d29922",
        "ok": "#3fb950",
        "drop": "#79c0ff",
        "muted": "#484f58",
    }.get(tone, "#484f58")


def _sparkline(delta_mb: float, *, seed: str, mean_mb: float | None = None) -> html.Img:
    """Deterministic mini growth chart (Figma TablesGrowth sparkline)."""
    color = _spark_color(delta_mb, mean_mb=mean_mb)
    h = abs(hash(seed)) & 0xFFFFFFFF
    pts: list[float] = []
    for i in range(7):
        base = (max(delta_mb, 0.0) / 7.0) * (i + 1)
        jitter = (((h >> (i * 3)) & 15) / 15.0 - 0.4) * max(delta_mb, 1.0) * 0.28
        pts.append(max(0.0, base + jitter))
    mx = max(pts) or 1.0
    w, ht = 56, 24
    coords = " ".join(
        f"{(i / 6) * w:.1f},{ht - (v / mx) * (ht - 2):.1f}" for i, v in enumerate(pts)
    )
    last_y = ht - (pts[-1] / mx) * (ht - 2)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{ht}" '
        f'viewBox="0 0 {w} {ht}">'
        f'<polyline points="{coords}" fill="none" stroke="{color}" '
        f'stroke-width="1.5" stroke-linejoin="round" opacity="0.75"/>'
        f'<circle cx="{w}" cy="{last_y:.1f}" r="2.5" fill="{color}"/>'
        f"</svg>"
    )
    return html.Img(
        src="data:image/svg+xml," + quote(svg),
        className="tables-sparkline",
        alt="",
        draggable="false",
    )


def _top_growers(
    growers: list,
    *,
    delta_key: str,
    history: bool,
    window_growth=None,
    mean_mb: float | None = None,
    locale: str = DEFAULT_LOCALE,
) -> html.Div:
    locale = normalize_locale(locale)
    if not growers:
        if not history:
            msg = t("tables.empty.growers_install", locale)
        elif window_growth is None:
            msg = t("tables.empty.growers_need_two", locale)
        else:
            msg = t("tables.empty.growers_none", locale)
        return html.Div(msg, className="tables-empty")
    max_delta = max(float(g.get(delta_key) or 0) for g in growers) or 1.0
    items = []
    for i, g in enumerate(growers):
        delta = float(g.get(delta_key) or 0)
        bar_w = min(100, max(0, round(delta / max_delta * 100)))
        color_cls = _delta_class(delta, mean_mb=mean_mb)
        fill_mod = (
            "is-hot" if "is-hot" in color_cls
            else "is-warm" if "is-warm" in color_cls
            else "is-ok"
        )
        seed = f"{g.get('database_name')}.{g.get('schema_name')}.{g.get('table_name')}"
        items.append(html.Div(
            className="tables-grower-row" + (" is-last" if i == len(growers) - 1 else ""),
            children=[
                html.Div(className="tables-grower-id", children=[
                    html.Div(className="tables-grower-meta", children=[
                        html.Span(g.get("database_name") or "?", className="tables-grower-db"),
                        html.Span(
                            t("tables.type.heap_badge", locale), className="tables-heap-pill"
                        ) if g.get("is_heap") else None,
                    ]),
                    html.Div(
                        f"{g.get('schema_name') or 'dbo'}.{g.get('table_name') or '?'}",
                        className="tables-grower-name",
                    ),
                    html.Div(className="tables-grower-track", children=[
                        html.Div(
                            className=f"tables-grower-fill {fill_mod}",
                            style={"width": f"{bar_w}%"},
                        ),
                    ]),
                ]),
                _sparkline(delta, seed=seed, mean_mb=mean_mb),
                html.Div(className="tables-grower-nums", children=[
                    html.Div(_fmt_delta(delta), className=color_cls + " tables-grower-delta"),
                    html.Div(f"{_fmt_mb(g.get('size_mb'))} total", className="tables-grower-total"),
                ]),
            ],
        ))
    return html.Div(className="tables-growers", children=items)
