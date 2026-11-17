"""Table Explorer — mockup-aligned detail panels (missing index + audit table)."""
from __future__ import annotations

from dash import html

from core.formatters import fmt_compact, fmt_int, fmt_size_mb
from core.i18n import DEFAULT_LOCALE, normalize_locale, t
from modules.indexes.constants import INDEX_HIGH_FRAG_PCT

INDEX_TYPE_CSS = {
    "HEAP": "is-heap",
    "CLUSTERED": "is-clustered",
    "NONCLUSTERED": "is-nonclustered",
    "CLUSTERED COLUMNSTORE": "is-columnstore",
    "NONCLUSTERED COLUMNSTORE": "is-columnstore",
}


def index_type_css(type_desc: str | None) -> str:
    key = str(type_desc or "").strip().upper()
    mod = INDEX_TYPE_CSS.get(key, "is-other")
    return f"idx-type-badge {mod}"


def _split_cols(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    return [c.strip().strip("[]") for c in str(raw).split(",") if c.strip()]


def _pct_bar(pct: float | None, *, pages: int = 0) -> html.Div:
    if pct is None:
        return html.Span("—", className="idx-ex-frag-none", dir="ltr")
    try:
        v = float(pct)
    except (TypeError, ValueError):
        return html.Span("—", className="idx-ex-frag-none", dir="ltr")
    tone = "is-ok"
    if v >= INDEX_HIGH_FRAG_PCT:
        tone = "is-critical"
    elif v >= 10.0:
        tone = "is-warn"
    width = max(4, min(100, int(round(v))))
    return html.Div(
        className="idx-ex-frag-cell",
        children=[
            html.Div(
                className=f"idx-ex-frag-bar {tone}",
                children=[html.Span(style={"width": f"{width}%"}, className="idx-ex-frag-fill")],
            ),
            html.Span(f"{v:.1f}%", className=f"idx-ex-frag-pct {tone}", dir="ltr"),
        ],
    )


def _action_badge(row: dict):
    tags = row.get("tags") or []
    metrics = row.get("metrics") or {}
    usage = metrics.get("usage") or {}
    reads = int(usage.get("reads") or 0)
    writes = int(usage.get("writes") or 0)
    frag = metrics.get("frag_pct")
    name = row.get("index_name") or "idx"
    try:
        frag_f = float(frag) if frag is not None else None
    except (TypeError, ValueError):
        frag_f = None

    label = "HEALTHY"
    css = "idx-ex-action is-ok"
    clickable = False
    if "Disabled" in tags:
        label, css = "DISABLED", "idx-ex-action is-muted"
    elif "Unused" in tags and reads == 0 and writes > 0:
        label, css, clickable = "DROP_UNUSED", "idx-ex-action is-drop", True
    elif frag_f is not None and frag_f >= INDEX_HIGH_FRAG_PCT:
        label, css, clickable = "REBUILD", "idx-ex-action is-rebuild", True
    elif frag_f is not None and frag_f >= 10.0:
        label, css, clickable = "REORGANIZE", "idx-ex-action is-reorg", True
    elif "Write-heavy" in tags or "Duplicate" in tags:
        label, css, clickable = "REVIEW", "idx-ex-action is-review", True

    if clickable:
        return html.Button(
            label,
            id={"type": "indexes-ex-review", "name": name},
            className=css,
            n_clicks=0,
            type="button",
            title="Open Recommendations for this index",
        )
    return html.Span(label, className=css)


def _col_pills(cols: list[str], tone: str) -> list:
    return [
        html.Span(f"[{c}]", className=f"idx-ex-col-pill is-{tone}", dir="ltr")
        for c in cols
        if c
    ]


def render_explore_header(payload: dict, locale: str = DEFAULT_LOCALE) -> html.Div:
    loc = normalize_locale(locale)
    meta = payload.get("table_meta") or {}
    health = payload.get("health") or {}
    schema = payload.get("schema_name") or ""
    table = payload.get("table_name") or ""
    db = payload.get("database_name") or ""
    inv_n = len(payload.get("inventory") or [])
    badges = []
    for tag in ("High frag", "Unused", "Write-heavy", "Duplicate", "Missing"):
        if health.get("health") == "needs_optimization" and tag == "High frag":
            badges.append(html.Span(tag, className="idx-ex-head-badge is-warn"))
        elif tag == "Missing" and (payload.get("missing_intelligence") or payload.get("missing")):
            badges.append(html.Span(tag, className="idx-ex-head-badge is-missing"))
    if payload.get("is_heap"):
        badges.append(html.Span("Heap", className="idx-ex-head-badge is-heap"))

    return html.Div(
        className="idx-ex-header",
        children=[
            html.Div(
                className="idx-ex-header-top",
                children=[
                    html.Div(
                        className="idx-ex-header-id",
                        children=[
                            html.Span(db, className="idx-ex-db-pill", dir="ltr"),
                            html.Span(f"[{table}].[{schema}]", className="idx-ex-table-title", dir="ltr"),
                        ],
                    ),
                    html.Div(badges, className="idx-ex-head-badges") if badges else None,
                ],
            ),
            html.Div(
                className="idx-ex-header-stats",
                children=[
                    html.Span(
                        t("indexes.explore.rows", loc, n=fmt_int(meta.get("row_count") or 0)),
                        dir="ltr",
                    ),
                    html.Span("·"),
                    html.Span(
                        t("indexes.explore.data_gb", loc, gb=fmt_size_mb(meta.get("size_mb"))),
                        dir="ltr",
                    ),
                    html.Span("·"),
                    html.Span(
                        t("indexes.explore.index_count", loc, n=inv_n or health.get("indexes") or 0),
                        dir="ltr",
                    ),
                ],
            ),
        ],
    )


def _render_missing_section(payload: dict, locale: str) -> html.Div:
    loc = normalize_locale(locale)
    analyzed = list(payload.get("missing_intelligence") or [])
    create_rows = [m for m in analyzed if m.get("action") == "create_new"]
    primary = create_rows[0] if create_rows else (analyzed[0] if analyzed else None)

    if not primary:
        return html.Div(
            className="idx-ex-panel idx-ex-missing is-empty",
            children=[
                html.Div(className="idx-ex-panel-title", children=t("indexes.explore.missing_title", loc)),
                html.Div(
                    className="idx-ex-missing-ok",
                    children=[
                        html.Span(className="idx-ex-ok-icon", **{"aria-hidden": "true"}),
                        html.P(t("indexes.explore.missing_none", loc), className="idx-ex-missing-ok-text"),
                    ],
                ),
            ],
        )

    eq = _split_cols(primary.get("equality_columns"))
    ineq = _split_cols(primary.get("inequality_columns"))
    inc = _split_cols(primary.get("included_columns"))
    impact = primary.get("impact_score")
    try:
        impact_pct = float(primary.get("avg_user_impact") or 0)
    except (TypeError, ValueError):
        impact_pct = 0.0
    seeks = int(primary.get("user_seeks") or 0)

    scripts = primary.get("scripts") or []
    script_text = (scripts[0].get("tsql") or "") if scripts else ""

    kpis = html.Div(
        className="idx-ex-missing-kpis",
        children=[
            html.Div(
                className="idx-ex-mini-kpi",
                children=[
                    html.Span(t("indexes.explore.kpi_impact", loc), className="idx-ex-mini-label"),
                    html.Span(
                        f"{impact_pct:.1f}%" if impact_pct else fmt_compact(impact or 0),
                        className="idx-ex-mini-value is-green",
                        dir="ltr",
                    ),
                ],
            ),
            html.Div(
                className="idx-ex-mini-kpi",
                children=[
                    html.Span(t("indexes.explore.kpi_seeks", loc), className="idx-ex-mini-label"),
                    html.Span(fmt_int(seeks), className="idx-ex-mini-value", dir="ltr"),
                ],
            ),
            html.Div(
                className="idx-ex-mini-kpi",
                children=[
                    html.Span(t("indexes.explore.kpi_scans", loc), className="idx-ex-mini-label"),
                    html.Span("—", className="idx-ex-mini-value is-muted", dir="ltr"),
                ],
            ),
            html.Div(
                className="idx-ex-mini-kpi",
                children=[
                    html.Span(t("indexes.explore.kpi_action", loc), className="idx-ex-mini-label"),
                    html.Span(
                        (primary.get("action") or "create_new").replace("_", " ").upper(),
                        className="idx-ex-mini-value is-cyan",
                    ),
                ],
            ),
        ],
    )

    cols_block = html.Div(
        className="idx-ex-cols-grid",
        children=[
            html.Div(
                className="idx-ex-cols-group",
                children=[
                    html.Div(t("indexes.explore.cols_eq", loc), className="idx-ex-cols-title is-eq"),
                    html.Div(_col_pills(eq, "eq") or [html.Span("—", className="idx-ex-col-empty")]),
                ],
            ),
            html.Div(
                className="idx-ex-cols-group",
                children=[
                    html.Div(t("indexes.explore.cols_ineq", loc), className="idx-ex-cols-title is-ineq"),
                    html.Div(_col_pills(ineq, "ineq") or [html.Span("—", className="idx-ex-col-empty")]),
                ],
            ),
            html.Div(
                className="idx-ex-cols-group",
                children=[
                    html.Div(t("indexes.explore.cols_inc", loc), className="idx-ex-cols-title is-inc"),
                    html.Div(_col_pills(inc, "inc") or [html.Span("—", className="idx-ex-col-empty")]),
                ],
            ),
        ],
    )

    sql_block = None
    if script_text.strip():
        sql_block = html.Div(
            className="idx-ex-sql-block",
            children=[
                html.Pre(script_text, className="idx-ex-sql-pre", dir="ltr"),
                html.Button(
                    t("indexes.script.copy", loc),
                    id={"type": "indexes-copy-btn", "index": 8000, "script": 0},
                    className="idx-ex-copy-btn",
                    n_clicks=0,
                    type="button",
                ),
                html.Pre(
                    script_text,
                    id={"type": "indexes-copy-payload", "index": 8000, "script": 0},
                    className="indexes-copy-payload hidden",
                ),
            ],
        )

    return html.Div(
        className="idx-ex-panel idx-ex-missing",
        children=[
            html.Div(
                className="idx-ex-panel-head",
                children=[
                    html.Div(t("indexes.explore.missing_title", loc), className="idx-ex-panel-title"),
                    html.Span(
                        t("indexes.explore.impact_badge", loc, pct=f"{impact_pct:.1f}" if impact_pct else "—"),
                        className="idx-ex-impact-badge",
                        dir="ltr",
                    )
                    if impact_pct
                    else None,
                ],
            ),
            html.P(primary.get("analysis") or primary.get("recommendation") or "", className="idx-ex-panel-lead"),
            kpis,
            cols_block,
            sql_block,
        ],
    )


def _render_audit_table(payload: dict, locale: str) -> html.Div:
    loc = normalize_locale(locale)
    inv = list(payload.get("inventory") or [])
    total_mb = sum(
        float((r.get("metrics") or {}).get("storage", {}).get("size_mb") or 0) for r in inv
    )

    if not inv:
        return html.Div(
            className="idx-ex-panel idx-ex-audit",
            children=[
                html.Div(t("indexes.explore.audit_title", loc), className="idx-ex-panel-title"),
                html.P(t("indexes.explore.audit_empty", loc), className="idx-empty-hint"),
            ],
        )

    rows = []
    for row in inv:
        name = row.get("index_name") or "—"
        usage = (row.get("metrics") or {}).get("usage") or {}
        storage = (row.get("metrics") or {}).get("storage") or {}
        reads = int(usage.get("reads") or 0)
        writes = int(usage.get("writes") or 0)
        pages = int(storage.get("page_count") or 0)
        size_mb = storage.get("size_mb")
        key = row.get("key_cols") or ""
        inc = row.get("include_cols") or ""
        cols_hint = f"({key}{', ' + inc if inc else ''})".strip()

        rows.append(
            html.Tr(
                className="idx-ex-audit-row",
                children=[
                    html.Td(
                        [
                            html.Div(name, className="idx-ex-idx-name", dir="ltr"),
                            html.Div(cols_hint[:80], className="idx-ex-idx-cols", dir="ltr"),
                        ],
                        className="idx-ex-td-name",
                    ),
                    html.Td(
                        html.Span(row.get("type_desc") or "—", className=index_type_css(row.get("type_desc"))),
                        className="idx-ex-td-type",
                    ),
                    html.Td(
                        _pct_bar((row.get("metrics") or {}).get("frag_pct"), pages=pages),
                        className="idx-ex-td-frag",
                    ),
                    html.Td(
                        [
                            html.Div(fmt_size_mb(size_mb) if size_mb else "—", dir="ltr"),
                            html.Div(
                                t("indexes.explore.pages", loc, n=fmt_int(pages)) if pages else "",
                                className="idx-ex-pages",
                                dir="ltr",
                            ),
                        ],
                        className="idx-ex-td-size",
                    ),
                    html.Td(
                        html.Span(
                            t(
                                "indexes.explore.rw_ratio",
                                loc,
                                writes=fmt_int(writes),
                                reads=fmt_int(reads),
                            ),
                            className="idx-ex-rw",
                            dir="ltr",
                        ),
                        className="idx-ex-td-rw",
                    ),
                    html.Td(_action_badge(row), className="idx-ex-td-action"),
                ],
            )
        )

    return html.Div(
        className="idx-ex-panel idx-ex-audit",
        children=[
            html.Div(
                className="idx-ex-panel-head",
                children=[
                    html.Div(t("indexes.explore.audit_title", loc), className="idx-ex-panel-title"),
                    html.Span(
                        t("indexes.explore.audit_summary", loc, n=len(inv), mb=fmt_size_mb(total_mb)),
                        className="idx-ex-audit-summary",
                        dir="ltr",
                    ),
                ],
            ),
            html.Div(
                className="idx-ex-audit-wrap",
                children=[
                    html.Table(
                        className="idx-ex-audit-table",
                        children=[
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th(t("indexes.explore.th_name", loc)),
                                        html.Th(t("indexes.explore.th_type", loc)),
                                        html.Th(t("indexes.explore.th_frag", loc)),
                                        html.Th(t("indexes.explore.th_size", loc)),
                                        html.Th(t("indexes.explore.th_rw", loc)),
                                        html.Th(t("indexes.explore.th_action", loc)),
                                    ]
                                )
                            ),
                            html.Tbody(rows),
                        ],
                    )
                ],
            ),
        ],
    )


def render_explore_body(payload: dict, locale: str = DEFAULT_LOCALE) -> html.Div:
    """Unified Explore detail — missing recommendation + existing index audit."""
    loc = normalize_locale(locale)
    return html.Div(
        className="idx-ex-body",
        children=[
            render_explore_header(payload, locale=loc),
            _render_missing_section(payload, loc),
            _render_audit_table(payload, loc),
        ],
    )
