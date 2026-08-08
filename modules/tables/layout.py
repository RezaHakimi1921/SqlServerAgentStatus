"""Tables & Growth UI — DB rollups, largest tables, growers."""
from __future__ import annotations

from dash import dcc, html

from core.formatters import fmt_int


def _fmt_mb(v) -> str:
    if v is None:
        return "—"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    if abs(n) >= 1024:
        return f"{n / 1024:,.2f} GB"
    return f"{n:,.1f} MB"


def _fmt_delta(v) -> str:
    if v is None:
        return "—"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    sign = "+" if n > 0 else ""
    return f"{sign}{_fmt_mb(n)}"


def build_tables_layout() -> html.Div:
    return html.Div(
        className="tables-shell insights-shell",
        children=[
            html.Div(className="activity-toolbar insights-toolbar", children=[
                html.Div(className="activity-tabs", children=[
                    html.Span("Tables & Growth", className="insights-title"),
                    html.Span(
                        "Space by database · largest tables · recent growth",
                        className="insights-sub",
                    ),
                ]),
                html.Div(className="activity-controls", children=[
                    html.Button(
                        [html.Span("↻", className="ctrl-ico"), html.Span("Refresh", className="ctrl-txt")],
                        id="btn-tables-refresh",
                        className="activity-ctrl-btn is-refresh",
                        n_clicks=0,
                        title="Refresh table sizes",
                    ),
                    html.Button(
                        [html.Span("⇪", className="ctrl-ico"), html.Span("Capture today", className="ctrl-txt")],
                        id="btn-tables-capture",
                        className="activity-ctrl-btn",
                        n_clicks=0,
                        title="Run ObjSize history capture for today",
                    ),
                ]),
            ]),
            html.Div(id="tables-meta", className="activity-meta"),
            html.Div(
                id="tables-loading",
                className="activity-loading",
                children=[
                    html.Div(className="activity-loading-card", children=[
                        html.Div(className="activity-loading-spinner"),
                        html.Div("Loading table sizes…", className="activity-loading-text"),
                    ]),
                ],
            ),
            html.Div(id="tables-body", className="insights-body tables-body"),
            dcc.Store(id="store-tables", data=None),
        ],
    )


def render_tables_body(payload: dict | None) -> list:
    if not payload:
        return [
            html.Div(className="state-box", children=[
                html.H3("No table data"),
                html.P("Connect to SQL Server and refresh."),
            ])
        ]

    errors = payload.get("errors") or {}
    hint = payload.get("permissions_hint")
    children: list = []

    if errors and not (payload.get("top_tables") or payload.get("databases")):
        children.append(html.Div(className="state-box state-error", children=[
            html.H3("Could not load table sizes"),
            html.P("; ".join(f"{k}: {v}" for k, v in list(errors.items())[:3])),
            html.P(hint) if hint else None,
        ]))
        return children

    dbs = payload.get("databases") or []
    if dbs:
        cards = []
        for d in dbs[:12]:
            cards.append(html.Div(className="tables-db-card", children=[
                html.Div(d.get("database_name") or "?", className="tables-db-name"),
                html.Div(_fmt_mb(d.get("total_size_mb")), className="tables-db-size"),
                html.Div(
                    f"{fmt_int(d.get('table_count') or 0)} tables · "
                    f"{fmt_int(d.get('total_rows') or 0)} rows · "
                    f"{fmt_int(d.get('heap_count') or 0)} heaps",
                    className="tables-db-meta",
                ),
            ]))
        children.append(html.Div(className="tables-section", children=[
            html.H3("Databases by size", className="tables-section-title"),
            html.Div(className="tables-db-grid", children=cards),
        ]))

    growers = payload.get("growers") or []
    if growers:
        children.append(html.Div(className="tables-section", children=[
            html.H3("Fast growers", className="tables-section-title"),
            html.P(
                "Largest positive size change vs prior history (7d, else 1d).",
                className="tables-section-sub",
            ),
            _tables_grid(
                growers,
                delta_key="delta_mb_7d" if growers[0].get("delta_mb_7d") is not None else "delta_mb_1d",
            ),
        ]))
    elif not payload.get("history_available"):
        children.append(html.Div(className="tables-section tables-hint", children=[
            html.H3("Growth history", className="tables-section-title"),
            html.P(
                "History not installed or empty yet. Current sizes still work. "
                "Install scripts/sql/SqlMonitor_ObjSizeHistory.sql and run Capture today "
                "(or the daily Agent job) to unlock 1d / 7d / 30d deltas."
            ),
        ]))

    top = payload.get("top_tables") or []
    children.append(html.Div(className="tables-section", children=[
        html.H3("Largest tables", className="tables-section-title"),
        _tables_grid(top, delta_key="delta_mb_7d") if top else html.P("No tables found."),
    ]))

    return children


def _tables_grid(rows: list, *, delta_key: str) -> html.Div:
    header = html.Div(className="tables-grid-header", children=[
        html.Div("Table"),
        html.Div("DB"),
        html.Div("Rows"),
        html.Div("Size"),
        html.Div("Δ size"),
        html.Div("Type"),
    ])
    body = []
    for r in rows:
        name = f"{r.get('schema_name') or 'dbo'}.{r.get('table_name') or '?'}"
        delta = r.get(delta_key)
        if delta is None and delta_key != "delta_mb_1d":
            delta = r.get("delta_mb_1d")
        body.append(html.Div(className="tables-grid-row", children=[
            html.Div(name, className="tables-col-table", title=name),
            html.Div(r.get("database_name") or "—", className="tables-col-db"),
            html.Div(fmt_int(r.get("row_count") or 0), className="tables-col-num"),
            html.Div(_fmt_mb(r.get("size_mb")), className="tables-col-num"),
            html.Div(_fmt_delta(delta), className="tables-col-num"),
            html.Div("HEAP" if r.get("is_heap") else "CLUSTERED", className="tables-col-type"),
        ]))
    return html.Div(className="tables-grid", children=[header, *body])


def render_tables_meta(payload: dict | None, capture_msg: str | None = None) -> str:
    if not payload:
        return capture_msg or ""
    parts = [
        f"Source: {payload.get('source') or '—'}",
        f"Tables: {fmt_int(payload.get('table_count') or 0)}",
    ]
    if payload.get("history_available"):
        parts.append(f"History: yes · last {payload.get('latest_capture_date') or '—'}")
    else:
        parts.append("History: none")
    if payload.get("note"):
        parts.append(str(payload["note"]))
    if capture_msg:
        parts.append(capture_msg)
    return " · ".join(parts)
