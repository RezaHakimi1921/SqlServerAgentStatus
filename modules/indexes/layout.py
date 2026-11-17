"""Index Intelligence UI — Overview · Triage · Table Explorer."""
from __future__ import annotations

from collections import defaultdict

from dash import dcc, html

from core.formatters import fmt_int
from core.i18n import DEFAULT_LOCALE, normalize_locale, t
from modules.indexes.constants import INDEX_CONFIDENCE_SCRIPT_MIN, INDEX_TABLE_SEARCH_MIN_CHARS
from modules.indexes.explore_panels import (
    _render_audit_table,
    _render_missing_section,
    render_explore_header,
)
from modules.indexes.panels import (
    render_catalog_status,
    render_explorer_table_list,
    render_overview,
    render_overview_idle,
    render_triage_detail,
    render_triage_rail,
    render_triage_subbar,
    triage_badge_children,
)

TAG_CSS = {
    "Unused": "idx-tag is-unused",
    "Write-heavy": "idx-tag is-write-heavy",
    "High frag": "idx-tag is-high-frag",
    "Duplicate": "idx-tag is-duplicate",
    "OK": "idx-tag is-ok",
    "Filtered": "idx-tag is-struct",
    "Unique": "idx-tag is-struct",
    "Disabled": "idx-tag is-disabled",
    "Heap": "idx-tag is-heap",
    "Missing": "idx-tag is-missing",
}

# Index type_desc → CSS modifier (HEAP / CLUSTERED / NONCLUSTERED / …)
INDEX_TYPE_CSS = {
    "HEAP": "is-heap",
    "CLUSTERED": "is-clustered",
    "NONCLUSTERED": "is-nonclustered",
    "CLUSTERED COLUMNSTORE": "is-columnstore",
    "NONCLUSTERED COLUMNSTORE": "is-columnstore",
    "XML": "is-xml",
    "SPATIAL": "is-spatial",
}


def index_type_css(type_desc: str | None) -> str:
    key = str(type_desc or "").strip().upper()
    mod = INDEX_TYPE_CSS.get(key, "is-other")
    return f"idx-type-badge {mod}"


REC_CAT_CSS = {
    "REMOVE_CANDIDATE": "idx-rec is-remove",
    "CONSOLIDATE": "idx-rec is-consolidate",
    "IMPROVE_EXISTING": "idx-rec is-improve",
    "INVESTIGATE": "idx-rec is-investigate",
}

REC_CAT_LABEL = {
    "REMOVE_CANDIDATE": "Remove candidates",
    "CONSOLIDATE": "Overlap signal",
    "IMPROVE_EXISTING": "Extend existing index",
    "INVESTIGATE": "Investigate",
}

REC_CAT_ORDER = ("REMOVE_CANDIDATE", "CONSOLIDATE", "IMPROVE_EXISTING", "INVESTIGATE")


def _ltr(text: str) -> html.Span:
    """Keep English UI strings LTR even when the shell is RTL."""
    return html.Span(text, dir="ltr", className="indexes-ltr")


def _tab_cls(active: bool) -> str:
    return "indexes-ii-tab active" if active else "indexes-ii-tab"


def build_indexes_layout(locale: str = DEFAULT_LOCALE) -> html.Div:
    loc = normalize_locale(locale)
    return html.Div(
        className="indexes-shell",
        dir="ltr",
        children=[
            html.Div(
                className="indexes-ii-header",
                children=[
                    html.Div(className="indexes-ii-brand", children=[
                        html.Span("SM", className="indexes-ii-logo"),
                        html.Div(className="indexes-ii-brand-text", children=[
                            html.Span([
                                html.Span("SmartMonitor", className="indexes-ii-brand-muted"),
                                html.Span(" / ", className="indexes-ii-brand-muted"),
                                html.Span("Object Intelligence", className="indexes-ii-brand-name"),
                            ]),
                            html.Span("UI v2", className="indexes-ui-build", title="Explore + Overview redesign"),
                        ]),
                    ]),
                    html.Div(
                        className="indexes-main-tabs",
                        children=[
                            html.Button(
                                t("indexes.tab.overview", loc),
                                id="indexes-tab-overview",
                                className=_tab_cls(True),
                                n_clicks=0,
                                type="button",
                                title="Environment health summary",
                            ),
                            html.Button(
                                triage_badge_children(0, loc),
                                id="indexes-tab-triage",
                                className=_tab_cls(False),
                                n_clicks=0,
                                type="button",
                                title="Ranked findings to review",
                            ),
                            html.Button(
                                t("indexes.tab.explorer", loc),
                                id="indexes-tab-explorer",
                                className=_tab_cls(False),
                                n_clicks=0,
                                type="button",
                                title="Browse tables and investigate",
                            ),
                        ],
                    ),
                    html.Div(
                        className="indexes-ii-actions",
                        children=[
                            html.Div(
                                id="indexes-catalog-status",
                                className="indexes-ii-status-chip",
                                children=render_catalog_status(None),
                            ),
                            html.Button(
                                t("header.refresh", loc),
                                id="btn-indexes-refresh",
                                className="indexes-ii-ghost-btn",
                                n_clicks=0,
                                type="button",
                                title="Refresh current view",
                            ),
                            html.Button(
                                t("indexes.btn.update_catalog", loc),
                                id="btn-indexes-catalog-refresh",
                                className="indexes-ii-outline-btn",
                                n_clicks=0,
                                type="button",
                                title="Rebuild insight index catalog tables",
                            ),
                        ],
                    ),
                ],
            ),
            html.Div(
                id="indexes-loading",
                className="activity-loading hidden",
                children=[
                    html.Div(className="activity-loading-card", children=[
                        html.Div(className="activity-loading-spinner"),
                        html.Div(
                            id="indexes-loading-text",
                            children=t("indexes.loading", loc),
                            className="activity-loading-text",
                        ),
                    ]),
                ],
            ),
            # Overview panel
            html.Div(
                id="indexes-panel-overview",
                className="indexes-panel",
                children=[
                    html.Div(className="indexes-ii-subbar idx-ov-subbar", children=[
                        html.Button(
                            "Scan more databases",
                            id="btn-indexes-deep-scan",
                            className="indexes-ii-ghost-btn",
                            n_clicks=0,
                            type="button",
                            title="Scan more accessible databases (slower than Quick scan)",
                        ),
                    ]),
                    html.Div(
                        id="indexes-overview-body",
                        className="idx-overview-body",
                        children=[
                            # Must exist in initial layout for switch_tab Input
                            html.Button(
                                "Go to Triage →",
                                id="btn-indexes-goto-triage",
                                className="idx-cta-btn",
                                n_clicks=0,
                                type="button",
                                style={"display": "none"},
                            ),
                        ],
                    ),
                    html.Div(
                        id="indexes-overview-loading",
                        className="",  # visible until first overview payload
                        children=[
                            html.Div(className="activity-loading-card", children=[
                                html.Div(className="activity-loading-spinner"),
                                html.Div(
                                    id="indexes-overview-loading-text",
                                    children=t("indexes.loading", loc),
                                    className="activity-loading-text",
                                ),
                            ]),
                        ],
                    ),
                ],
            ),
            # Triage panel
            html.Div(
                id="indexes-panel-triage",
                className="indexes-panel hidden",
                children=[
                    html.Div(
                        id="indexes-triage-subbar",
                        className="indexes-ii-subbar",
                        children=render_triage_subbar(None, "all"),
                    ),
                    html.Div(
                        className="indexes-triage-layout",
                        children=[
                            html.Div(
                                id="indexes-triage-rail",
                                className="indexes-triage-rail",
                                children=render_triage_rail(None, "all", None),
                            ),
                            html.Div(
                                className="indexes-triage-main",
                                children=[
                                    html.Div(
                                        id="indexes-triage-detail",
                                        children=render_triage_detail(None),
                                    ),
                                    html.Div(
                                        className="indexes-detail-actions",
                                        style={"padding": "0 20px 16px"},
                                        children=[
                                            html.Button(
                                                "Open in Table Explorer",
                                                id="btn-indexes-open-table",
                                                className="indexes-cta-btn",
                                                n_clicks=0,
                                                type="button",
                                                disabled=True,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
            # Explorer panel — mockup: slim toolbar + full-width status table + detail below
            html.Div(
                id="indexes-panel-explorer",
                className="indexes-panel hidden",
                children=[
                    html.Div(
                        className="idx-ex-toolbar",
                        children=[
                            html.Div(className="idx-ex-db-wrap indexes-cmd-db", children=[
                                html.Div(className="indexes-db-picker", children=[
                                    html.Button(
                                        [
                                            html.Span(
                                                id="indexes-db-label",
                                                children="All",
                                                className="indexes-db-label",
                                            ),
                                            html.Span(className="indexes-db-chevron", children="▾"),
                                        ],
                                        id="indexes-db-toggle",
                                        className="indexes-db-toggle idx-ex-db-toggle",
                                        n_clicks=0,
                                        type="button",
                                        title="Choose database",
                                    ),
                                    html.Div(
                                        id="indexes-db-panel",
                                        className="indexes-db-panel hidden",
                                        children=[
                                            dcc.Input(
                                                id="indexes-db-filter",
                                                type="text",
                                                placeholder="Filter databases…",
                                                debounce=False,
                                                className="indexes-db-filter",
                                                autoComplete="off",
                                            ),
                                            html.Div(
                                                id="indexes-db-options",
                                                className="indexes-db-options",
                                            ),
                                        ],
                                    ),
                                ]),
                                dcc.Store(id="indexes-db-dropdown", data=None),
                            ]),
                            html.Div(className="idx-ex-search", children=[
                                html.Span(className="indexes-search-ico", children=[
                                    html.Span(className="indexes-search-ico-glyph"),
                                ]),
                                dcc.Input(
                                    id="indexes-table-search",
                                    type="text",
                                    placeholder=t("indexes.placeholder.search", loc),
                                    debounce=False,
                                    className="indexes-search-input idx-ex-search-input",
                                    autoComplete="off",
                                    n_submit=0,
                                    spellCheck=False,
                                ),
                                html.Span(
                                    id="indexes-search-spinner",
                                    className="indexes-search-spinner hidden",
                                ),
                            ]),
                            html.Div(
                                id="indexes-search-results",
                                className="indexes-search-results idx-ex-search-results",
                            ),
                            html.Div(
                                className="indexes-ii-pills idx-ex-sort-pills",
                                children=[
                                    html.Button(t("indexes.sort.schema", loc), id="indexes-sort-schema", n_clicks=0, type="button", className="indexes-ii-pill"),
                                    html.Button(t("indexes.sort.table", loc), id="indexes-sort-table", n_clicks=0, type="button", className="indexes-ii-pill active"),
                                    html.Button(t("indexes.sort.heap", loc), id="indexes-sort-heap", n_clicks=0, type="button", className="indexes-ii-pill"),
                                    html.Button(t("indexes.sort.rows", loc), id="indexes-sort-rows", n_clicks=0, type="button", className="indexes-ii-pill"),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        id="indexes-table-cache-hint",
                        className="idx-ex-hint",
                        children="",
                    ),
                    # Kept for callbacks / drill-down; visually secondary
                    html.Div(
                        className="idx-ex-aux",
                        children=[
                            html.Div(
                                id="indexes-selected-table",
                                className="idx-ex-selected",
                                children=render_selected_table(None),
                            ),
                            html.Button(
                                t("indexes.btn.load_frag", loc),
                                id="btn-indexes-load-frag",
                                className="activity-ctrl-btn indexes-frag-btn",
                                n_clicks=0,
                                type="button",
                                title=t("indexes.btn.load_frag", loc),
                                disabled=True,
                            ),
                            html.Div(id="indexes-frag-status", className="indexes-frag-status"),
                        ],
                    ),
                    html.Div(
                        id="indexes-explorer-table-list",
                        className="idx-ex-table-wrap indexes-explorer-list",
                        children=render_explorer_table_list(None, None, "", locale=loc),
                    ),
                    html.Div(
                        id="indexes-ex-pagination",
                        className="tables-pagination idx-ex-pagination",
                        children=[
                            html.Div(
                                id="indexes-ex-pagination-info",
                                className="tables-pagination-info",
                                children="—",
                            ),
                            html.Div(
                                className="tables-pagination-controls",
                                children=[
                                    html.Button(
                                        "‹ Prev",
                                        id="btn-indexes-ex-page-prev",
                                        n_clicks=0,
                                        type="button",
                                        className="tables-page-btn",
                                        disabled=True,
                                    ),
                                    html.Span(
                                        id="indexes-ex-page-pos",
                                        className="tables-page-pos",
                                        children="—",
                                    ),
                                    html.Button(
                                        "Next ›",
                                        id="btn-indexes-ex-page-next",
                                        n_clicks=0,
                                        type="button",
                                        className="tables-page-btn",
                                        disabled=True,
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        id="indexes-explorer-subtabs-bar",
                        className="indexes-explorer-subtabs-bar is-disabled",
                        children=[
                            html.Button(
                                [
                                    html.Span(
                                        t("indexes.view.recommendations", loc),
                                        id="indexes-rec-label",
                                    ),
                                    html.Span("0", id="indexes-rec-count", className="indexes-subtab-count"),
                                ],
                                id="indexes-view-recommendations",
                                className="indexes-subtab active",
                                n_clicks=0,
                                type="button",
                                disabled=True,
                            ),
                            html.Button(
                                t("indexes.view.status", loc),
                                id="indexes-view-status",
                                className="indexes-subtab",
                                n_clicks=0,
                                type="button",
                                disabled=True,
                                title=t("indexes.view.status", loc),
                            ),
                        ],
                    ),
                    html.Div(
                        id="indexes-explorer-body",
                        className="idx-ex-detail indexes-explorer-detail",
                        children=render_explorer_idle(),
                    ),
                    html.Div(
                        id="indexes-explorer-loading",
                        className="idx-ex-loading hidden",
                        children=[
                            html.Div(className="activity-loading-card", children=[
                                html.Div(className="activity-loading-spinner"),
                                html.Div(
                                    id="indexes-explorer-loading-text",
                                    children="Loading table intelligence…",
                                    className="activity-loading-text",
                                ),
                            ]),
                        ],
                    ),
                ],
            ),
            dcc.Store(id="store-indexes-tab", data="overview"),
            dcc.Store(id="store-indexes-overview", data=None),
            dcc.Store(id="store-indexes", data=None),
            dcc.Store(id="store-indexes-db-list", data=None),
            dcc.Store(id="store-indexes-db-filtered", data=None),
            dcc.Store(id="store-indexes-selected-table", data=None),
            dcc.Store(id="store-indexes-search-results", data=None),
            dcc.Store(id="store-indexes-table-cache", data=None),
            dcc.Store(id="store-indexes-explorer-view", data="recommendations"),
            dcc.Store(id="store-indexes-db-open", data=False),
            dcc.Store(id="store-indexes-catalog-version", data=0),
            dcc.Store(id="store-indexes-catalog-job", data=None),
            dcc.Store(id="store-indexes-table-job", data=None),
            dcc.Store(id="store-indexes-triage-filter", data="all"),
            dcc.Store(id="store-indexes-selected-finding", data=None),
            dcc.Store(id="store-indexes-triage-visible", data=None),
            dcc.Store(id="store-indexes-table-visible", data=None),
            dcc.Store(id="store-indexes-table-sort", data="table"),
            dcc.Store(id="store-indexes-table-page", data=1),
            dcc.Interval(
                id="indexes-catalog-poll",
                interval=1000,
                n_intervals=0,
                disabled=True,
            ),
            dcc.Interval(
                id="indexes-table-poll",
                interval=400,
                n_intervals=0,
                disabled=True,
            ),
            dcc.Interval(
                id="indexes-search-debounce",
                interval=350,
                n_intervals=0,
                disabled=True,
                max_intervals=-1,
            ),
        ],
    )


















def render_explorer_idle() -> html.Div:
    return html.Div(
        className="indexes-idle idx-idle",
        children=[
            html.Div(className="indexes-idle-card", children=[
                html.H3("Table Explorer", className="indexes-idle-title"),
                html.Ol(className="indexes-idle-steps", children=[
                    html.Li("Filter by database (or All) and search"),
                    html.Li("Select a table from the list"),
                    html.Li("Review Recommendations / Index status below"),
                ]),
            ]),
        ],
    )


def render_explorer_loading(table_label: str = "") -> html.Div:
    label = f" for {table_label}" if table_label else ""
    return html.Div(
        className="indexes-inline-loading",
        children=[
            html.Div(className="activity-loading-spinner"),
            html.Div(f"Loading table intelligence{label}…", className="activity-loading-text"),
        ],
    )


def _fmt_size(mb) -> str:
    if mb is None:
        return "—"
    try:
        v = float(mb)
    except (TypeError, ValueError):
        return "—"
    if v >= 1024:
        return f"{v / 1024:.2f} GB"
    return f"{v:.1f} MB"


def _chip(label: str, value, *, tone: str = "", max_chars: int | None = None):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        display = fmt_int(value)
        title = display
    else:
        title = str(value if value is not None else "—")
        display = title
        if max_chars and len(display) > max_chars:
            display = display[: max_chars - 1] + "…"
    return html.Div(
        className=f"indexes-stat-card {tone}".strip(),
        title=title if title != display else None,
        children=[
            html.Div(label, className="indexes-stat-label"),
            html.Div(display, className="indexes-stat-value", dir="ltr", title=title),
        ],
    )


def _truncate(text: str | None, limit: int = 72) -> str:
    s = str(text or "").strip()
    if len(s) <= limit:
        return s or "—"
    return s[: limit - 1] + "…"






def render_db_options(names: list[str] | None, selected: str | None = None, filter_text: str = ""):
    from modules.indexes.constants import INDEX_DB_ALL

    names = names or []
    q = (filter_text or "").strip().lower()
    options: list[tuple[str, str]] = []
    if not q or "all" in q:
        options.append((INDEX_DB_ALL, "All"))
    for n in names:
        if not q or q in n.lower():
            options.append((n, n))
    if not options:
        return html.Div("No databases match.", className="indexes-db-empty")
    items = []
    for i, (value, label) in enumerate(options):
        active = " is-active" if value == selected else ""
        items.append(
            html.Button(
                label,
                id={"type": "indexes-db-hit", "index": i},
                className=f"indexes-db-hit{active}",
                n_clicks=0,
                type="button",
                title=label,
            )
        )
    return html.Div(items, className="indexes-db-hit-list")


def db_option_values(names: list[str] | None, filter_text: str = "") -> list[str]:
    """Same order as render_db_options — used for click index → value mapping."""
    from modules.indexes.constants import INDEX_DB_ALL

    names = names or []
    q = (filter_text or "").strip().lower()
    values: list[str] = []
    if not q or "all" in q:
        values.append(INDEX_DB_ALL)
    for n in names:
        if not q or q in n.lower():
            values.append(n)
    return values


def db_label(value: str | None) -> str:
    from modules.indexes.constants import INDEX_DB_ALL

    if not value:
        return "All"
    if value == INDEX_DB_ALL:
        return "All"
    return value


def render_frag_status(errors: dict | None = None, *, ok: bool = False):
    if ok:
        return html.Div(
            className="indexes-soft-fail is-ok",
            role="status",
            children=[
                html.Div("Fragmentation loaded", className="indexes-soft-fail-title"),
                html.P("Frag % is now available on Index status cards.", className="indexes-soft-fail-text"),
            ],
        )
    if not errors:
        return html.Div()
    code = errors.get("frag") or "failed"
    title = "Fragmentation skipped" if code == "timeout" else "Fragmentation unavailable"
    detail = (
        "This table is too large for a quick LIMITED scan (query timed out). "
        "Recommendations and Index status still work without fragmentation %."
        if code == "timeout"
        else "Could not read physical stats for this table right now."
    )
    return html.Div(
        className="indexes-soft-fail",
        role="alert",
        children=[
            html.Div(title, className="indexes-soft-fail-title"),
            html.P(detail, className="indexes-soft-fail-text"),
            html.P(
                "Tip: check frag in SSMS off-hours for huge tables.",
                className="indexes-soft-fail-hint",
            ),
        ],
    )




def render_search_loading(query: str = "") -> html.Div:
    q = (query or "").strip()
    label = f'Searching tables for "{q}"…' if q else "Searching tables…"
    return html.Div(
        className="indexes-search-list is-loading",
        children=[
            html.Div(className="indexes-search-loading-row", children=[
                html.Span(className="indexes-search-spinner is-inline"),
                html.Span(label, className="indexes-search-hint"),
            ]),
        ],
    )


def render_search_results(results: list | None, query: str):
    q = (query or "").strip()
    if len(q) < INDEX_TABLE_SEARCH_MIN_CHARS:
        return html.Div(className="indexes-search-results-empty")
    if not results:
        return html.Div(
            className="indexes-search-list",
            children=[
                html.Div(
                    className="indexes-search-hint",
                    children=_ltr(f'No tables matching "{q}".'),
                )
            ],
        )
    items = []
    for i, t in enumerate(results):
        full = t.get("full_name") or f"{t.get('schema_name')}.{t.get('table_name')}"
        items.append(
            html.Button(
                full,
                id={"type": "indexes-search-hit", "index": i},
                className="indexes-search-hit",
                n_clicks=0,
                type="button",
                title=full,
            )
        )
    return html.Div(items, className="indexes-search-list")


def render_selected_table(sel: dict | None):
    if not sel:
        return html.Div(
            className="indexes-selected-empty-card",
            children=[
                html.Span("Selected table", className="indexes-selected-label"),
                html.Span("None yet — search above", className="indexes-selected-value is-muted"),
            ],
        )
    full = f"{sel.get('schema')}.{sel.get('table')}"
    return html.Div(
        className="indexes-selected-chip",
        children=[
            html.Span("Selected table", className="indexes-selected-label"),
            html.Span(f"{sel.get('database')}", className="indexes-selected-db", dir="ltr"),
            html.Span(full, className="indexes-selected-value", dir="ltr"),
        ],
    )


def _render_table_header(payload: dict, *, view: str, locale: str = DEFAULT_LOCALE):
    loc = normalize_locale(locale)
    meta = payload.get("table_meta") or {}
    health = payload.get("health") or {}
    schema = payload.get("schema_name")
    table = payload.get("table_name")
    db = payload.get("database_name")
    needs = health.get("health") == "needs_optimization"
    rec_n = len(payload.get("recommendations") or [])

    return html.Div(
        className="indexes-table-overview",
        children=[
            html.Div(className="indexes-table-head", children=[
                html.Div([
                    html.H2(f"{schema}.{table}", className="indexes-table-name", dir="ltr"),
                    html.Span(db or "", className="indexes-table-db", dir="ltr"),
                ]),
                html.Span(
                    t("indexes.health.needs", loc) if needs else t("indexes.health.ok", loc),
                    className=f"indexes-health-pill {'is-warn' if needs else 'is-ok'}",
                ),
            ]),
            html.Div(
                className="indexes-stat-row compact meta-only",
                children=[
                    _chip(t("indexes.meta.rows", loc), meta.get("row_count") or 0),
                    _chip(t("indexes.meta.size", loc), _fmt_size(meta.get("size_mb"))),
                    _chip(t("indexes.meta.indexes", loc), health.get("indexes") or meta.get("index_count") or 0),
                    _chip(
                        t("indexes.meta.clustered", loc),
                        meta.get("clustered_index_name")
                        or ("Heap" if payload.get("is_heap") else "—"),
                        max_chars=22,
                    ),
                    _chip(
                        t("indexes.meta.pk", loc),
                        meta.get("primary_key_name") or "—",
                        max_chars=22,
                    ),
                    _chip(t("indexes.meta.advice", loc), rec_n, tone="is-warn" if rec_n else ""),
                ],
            ),
        ],
    )


def _render_status_view(payload: dict, locale: str = DEFAULT_LOCALE) -> html.Div:
    loc = normalize_locale(locale)
    inv = payload.get("inventory") or []
    rels = payload.get("relationships") or []
    health = payload.get("health") or {}

    problem_rows = []
    ok_rows = []
    for row in inv:
        tags = row.get("tags") or []
        if any(t in ("Unused", "Write-heavy", "Duplicate", "High frag", "Disabled") for t in tags):
            problem_rows.append(row)
        else:
            ok_rows.append(row)

    signal = html.Div(
        className="indexes-signal-row",
        children=[
            _chip("Needs attention", len(problem_rows), tone="is-warn" if problem_rows else ""),
            _chip("Looking fine", len(ok_rows)),
            _chip("Unused", health.get("unused") or 0, tone="is-warn" if health.get("unused") else ""),
            _chip("Write-heavy", health.get("write_heavy") or 0, tone="is-warn" if health.get("write_heavy") else ""),
        ],
    )

    def _arch_card(row: dict, *, open_card: bool = False) -> html.Details:
        tags = [html.Span(t, className=TAG_CSS.get(t, "idx-tag")) for t in (row.get("tags") or [])]
        usage = (row.get("metrics") or {}).get("usage") or {}
        storage = (row.get("metrics") or {}).get("storage") or {}
        problem = any(
            t in ("Unused", "Write-heavy", "Duplicate", "High frag", "Disabled")
            for t in (row.get("tags") or [])
        )
        summary = html.Summary(
            className="indexes-arch-summary",
            children=[
                html.Span(row.get("index_name") or "—", className="indexes-arch-name", dir="ltr"),
                html.Span(
                    row.get("type_desc") or "—",
                    className=f"indexes-arch-type {index_type_css(row.get('type_desc'))}",
                ),
                html.Span(tags, className="idx-col-tags"),
                html.Span(
                    f"R {fmt_int(usage.get('reads') or 0)} · W {fmt_int(usage.get('writes') or 0)} · {_fmt_size(storage.get('size_mb'))}",
                    className="indexes-arch-metrics-inline",
                    dir="ltr",
                ),
            ],
        )
        return html.Details(
            className=f"indexes-arch-card {'is-problem' if problem else ''}",
            open=open_card,
            children=[
                summary,
                html.Div(className="indexes-arch-keys", children=[
                    html.Div([
                        html.Span("KEY", className="indexes-arch-k"),
                        html.Span(row.get("key_cols") or "—", className="indexes-arch-v", dir="ltr"),
                    ]),
                    html.Div([
                        html.Span("INCLUDE", className="indexes-arch-k"),
                        html.Span(row.get("include_cols") or "—", className="indexes-arch-v", dir="ltr"),
                    ]),
                    html.Div([
                        html.Span("FILTER", className="indexes-arch-k"),
                        html.Span(row.get("filter_def") or "—", className="indexes-arch-v", dir="ltr"),
                    ]),
                ]),
            ],
        )

    cards = []
    if not inv:
        cards.append(html.P("No indexes on this table.", className="indexes-empty-hint"))
    else:
        if problem_rows:
            cards.append(html.H4("Needs attention", className="indexes-mini-title"))
            for i, row in enumerate(problem_rows):
                cards.append(_arch_card(row, open_card=(i == 0)))
        if ok_rows:
            cards.append(
                html.Details(
                    className="indexes-ok-fold",
                    open=False,
                    children=[
                        html.Summary(
                            className="indexes-ok-summary",
                            children=f"{fmt_int(len(ok_rows))} index(es) look fine — expand to inspect keys",
                        ),
                        html.Div([_arch_card(r) for r in ok_rows], className="indexes-arch-list"),
                    ],
                )
            )

    rel_block = []
    if rels:
        rel_block.append(
            html.Details(
                className="indexes-rel-fold",
                open=False,
                children=[
                    html.Summary(
                        className="indexes-ok-summary",
                        children=f"{fmt_int(len(rels))} relationship finding(s) — expand for detail",
                    ),
                    html.Div(
                        [
                            html.Div(
                                className="indexes-rel-card",
                                children=[
                                    html.Div(rel.get("title") or rel.get("kind"), className="indexes-rel-title"),
                                    html.P(rel.get("analysis") or "", className="indexes-rel-analysis"),
                                ],
                            )
                            for rel in rels[:12]
                        ],
                        className="indexes-rel-list",
                    ),
                ],
            )
        )

    return html.Div(
        className="indexes-section-block",
        children=[
            html.H3(t("indexes.section.status", loc), className="indexes-section-title"),
            html.P(
                "Glance at indexes that need attention first. Expand a row for KEY / INCLUDE details.",
                className="indexes-section-lead",
            ),
            signal,
            html.Div(cards, className="indexes-arch-list"),
            *rel_block,
        ],
    )


def _render_recommendations_view(payload: dict, locale: str = DEFAULT_LOCALE) -> html.Div:
    loc = normalize_locale(locale)
    recs = payload.get("recommendations") or []

    if not recs:
        return html.Div(
            className="indexes-section-block",
            children=[
                html.H3(t("indexes.section.recommendations", loc), className="indexes-section-title"),
                html.P(
                    "No actionable recommendations for this table right now.",
                    className="indexes-empty-hint",
                ),
            ],
        )

    grouped: dict[str, list] = defaultdict(list)
    for r in recs:
        grouped[r.get("category") or "INVESTIGATE"].append(r)

    # Summary strip — what to do at a glance
    summary_cards = []
    for cat in REC_CAT_ORDER:
        items = grouped.get(cat) or []
        if not items:
            continue
        summary_cards.append(
            html.Div(
                className=f"indexes-advice-pill {REC_CAT_CSS.get(cat, '')}",
                children=[
                    html.Span(fmt_int(len(items)), className="indexes-advice-pill-n"),
                    html.Span(REC_CAT_LABEL.get(cat, cat), className="indexes-advice-pill-l"),
                ],
            )
        )

    sections = [
        html.P(
            "Read the summary, then expand only the items you want to act on. Scripts are copy-only.",
            className="indexes-section-lead",
        ),
        html.Div(summary_cards, className="indexes-advice-pills"),
    ]

    rec_index = 0
    opened_one = False
    for cat in REC_CAT_ORDER:
        items = grouped.get(cat) or []
        if not items:
            continue
        # Cap noisy extend list
        shown = items[:8] if cat == "IMPROVE_EXISTING" else items[:12]
        hidden_n = len(items) - len(shown)
        # Always expand at least one group — heap-only tables land in INVESTIGATE,
        # which used to stay collapsed and looked like "no data".
        prefer_open = cat in ("REMOVE_CANDIDATE", "CONSOLIDATE")
        group_open = prefer_open or not opened_one
        if group_open:
            opened_one = True
        group_children = [
            html.Summary(
                className="indexes-rec-group-summary",
                children=[
                    html.Span(REC_CAT_LABEL.get(cat, cat), className="indexes-section-title"),
                    html.Span(str(len(items)), className="indexes-subtab-count"),
                ],
            ),
            html.Div(
                className="indexes-rec-group-body",
                children=[
                    _rec_card(
                        r,
                        rec_i,
                        open_first=(group_open and i == 0),
                        locale=loc,
                    )
                    for i, (rec_i, r) in enumerate(
                        zip(range(rec_index, rec_index + len(shown)), shown)
                    )
                ]
                + (
                    [
                        html.P(
                            f"+ {fmt_int(hidden_n)} more in this category — prioritize the ones above first.",
                            className="indexes-cat-footer",
                        )
                    ]
                    if hidden_n > 0
                    else []
                ),
            ),
        ]
        sections.append(
            html.Details(
                className="indexes-rec-group",
                open=group_open,
                children=group_children,
            )
        )
        rec_index += len(shown)

    return html.Div(className="indexes-section-block is-advice", children=sections)


def _rec_card(r: dict, i: int, *, open_first: bool = False, locale: str = DEFAULT_LOCALE) -> html.Details:
    loc = normalize_locale(locale)
    try:
        score = int(r.get("confidence_score")) if r.get("confidence_score") is not None else None
    except (TypeError, ValueError):
        score = None
    reasons = r.get("confidence_reasons") or (
        [r.get("confidence_reason")] if r.get("confidence_reason") else []
    )
    reasons = [str(x) for x in reasons if x]
    blocked = r.get("script_blocked_reason")
    allow_copy = bool(
        not blocked and (score is None or score >= INDEX_CONFIDENCE_SCRIPT_MIN)
    )
    # When score is known and below gate, never show copy buttons
    if score is not None and score < INDEX_CONFIDENCE_SCRIPT_MIN:
        allow_copy = False

    scripts = []
    for j, s in enumerate(r.get("scripts") or []):
        if not (s.get("tsql") or "").strip():
            continue
        if not allow_copy:
            continue
        scripts.append(
            html.Div(
                className="indexes-script-row",
                children=[
                    html.Button(
                        t("indexes.script.copy", loc),
                        id={"type": "indexes-copy-btn", "index": i, "script": j},
                        className="indexes-copy-btn",
                        n_clicks=0,
                        type="button",
                    ),
                    html.Pre(
                        s.get("tsql") or "",
                        id={"type": "indexes-copy-payload", "index": i, "script": j},
                        className="indexes-copy-payload hidden",
                    ),
                ],
            )
        )
    ev = r.get("evidence") or {}
    ev_bits = []
    for k, v in ev.items():
        if k in ("reads", "writes") and v is not None:
            ev_bits.append(f"{k}: {fmt_int(v)}")
        elif k == "size_mb" and v is not None:
            ev_bits.append(f"size: {_fmt_size(v)}")
        elif k == "frag_pct" and v is not None:
            ev_bits.append(f"frag: {float(v):.1f}%")
        elif k in ("a", "b", "related_index", "kind") and v:
            ev_bits.append(f"{k}: {v}")
        elif k == "heap" and v:
            ev_bits.append("type: HEAP")

    headline = _truncate(r.get("problem") or r.get("suggested_action") or "Recommendation", 90)
    action_short = _truncate(r.get("suggested_action") or "", 100)

    body_children = [
        html.P(_truncate(r.get("why") or "", 220), className="idx-rec-why"),
        html.Div(", ".join(ev_bits) if ev_bits else "", className="idx-rec-evidence", dir="ltr"),
        html.P(action_short, className="idx-rec-action"),
    ]

    conf_bits = []
    if score is not None:
        conf_bits.append(
            html.Div(
                t("indexes.script.confidence", loc, score=score),
                className="idx-script-confidence",
                dir="ltr",
            )
        )
    if reasons:
        conf_bits.append(
            html.Div(
                t("indexes.script.reasons", loc, reasons="; ".join(reasons[:3])),
                className="idx-script-reasons",
            )
        )
    if conf_bits:
        body_children.append(html.Div(conf_bits, className="idx-script-meta"))

    if blocked or (score is not None and score < INDEX_CONFIDENCE_SCRIPT_MIN):
        body_children.append(
            html.P(
                blocked
                or t(
                    "indexes.script.blocked",
                    loc,
                    score=score if score is not None else 0,
                    min=INDEX_CONFIDENCE_SCRIPT_MIN,
                ),
                className="indexes-script-blocked",
            )
        )
    elif scripts:
        body_children.append(
            html.Div(t("indexes.script.suggested", loc), className="idx-script-title")
        )
        body_children.append(html.Div(scripts))

    return html.Details(
        className=REC_CAT_CSS.get(r.get("category") or "", "idx-rec"),
        open=open_first,
        children=[
            html.Summary(
                className="idx-rec-summary",
                children=[
                    html.Span(
                        REC_CAT_LABEL.get(r.get("category") or "", r.get("category") or ""),
                        className="idx-rec-cat",
                    ),
                    html.Span(headline, className="idx-rec-problem"),
                    html.Span(f"Risk: {_truncate(r.get('risk'), 40)}", className="idx-rec-risk-inline"),
                ],
            ),
            html.Div(className="idx-rec-body", children=body_children),
        ],
    )



def render_explorer(
    payload: dict | None,
    *,
    selected: dict | None = None,
    view: str = "recommendations",
    locale: str = DEFAULT_LOCALE,
):
    loc = normalize_locale(locale)
    if not selected:
        return render_explorer_idle()
    # While a job runs, keep idle here — the fixed overlay shows the only spinner.
    if not payload:
        return render_explorer_idle()

    view = view if view in ("status", "recommendations") else "recommendations"
    if view == "status":
        body = html.Div(
            className="idx-ex-body",
            children=[
                render_explore_header(payload, locale=loc),
                _render_audit_table(payload, loc),
            ],
        )
    else:
        body = html.Div(
            className="idx-ex-body",
            children=[
                render_explore_header(payload, locale=loc),
                _render_missing_section(payload, loc),
                _render_recommendations_view(payload, locale=loc),
            ],
        )
    return html.Div(
        className="indexes-explorer-inner idx-ex-root",
        children=[body],
    )
