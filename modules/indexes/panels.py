"""Index Intelligence — Figma-matched panel renderers.

Overview · Triage sub-bar/rail/detail · Table Explorer list — all pure
render functions (no SQL, no Dash callbacks). `layout.py` wires these into
the shell; `callbacks.py` re-renders them from `store-indexes-overview` /
`store-indexes-table-cache`.
"""
from __future__ import annotations

from datetime import datetime

from dash import html

from core.formatters import fmt_compact, fmt_int, fmt_size_mb
from modules.indexes.triage import (
    filter_triage_findings,
    per_database_summary,
    recoverable_mb,
    triage_filter_counts,
)

_SEVERITY_LABEL = {"critical": "CRITICAL", "warning": "WARNING", "watch": "WATCH"}

_CARD_ICON = {
    "unused": "⛔",
    "write_heavy": "✍",
    "heap": "▦",
    "missing": "＋",
}

_TONE_ICON = {"critical": "●", "warning": "▲", "watch": "◆"}

_EXPLORER_ROW_CAP = 500
_PER_DB_CAP = 8


def _fmt_size(mb) -> str:
    """Thin wrapper kept for call-site compatibility with the old `_fmt_size` helper."""
    return fmt_size_mb(mb)


def _sev(value: str | None) -> str:
    s = (value or "watch").lower().strip()
    return s if s in _SEVERITY_LABEL else "watch"


def _sev_badge(sev: str, *, prefix: str = "") -> html.Span:
    label = f"{prefix}{_SEVERITY_LABEL.get(sev, sev.upper())}"
    return html.Span(label, className=f"idx-badge is-{sev}")


def _short_time(value) -> str | None:
    """Best-effort HH:MM from an ISO-ish timestamp; None if unparseable."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%H:%M")
    except ValueError:
        pass
    for sep in ("T", " "):
        if sep in text:
            _, _, tail = text.partition(sep)
            if len(tail) >= 5 and tail[2] == ":":
                return tail[:5]
    return None


def triage_badge_children(count: int):
    """Tab label children for the Triage main tab — badge only when count > 0."""
    if count:
        return ["Triage", html.Span(str(count), className="indexes-ii-badge")]
    return "Triage"


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


def render_overview_idle() -> html.Div:
    return html.Div(
        className="idx-idle",
        children=[
            html.Div(
                className="idx-idle-card",
                children=[
                    html.H3("No scan yet", className="idx-idle-title"),
                    html.P(
                        "Click Refresh to scan accessible databases for unused, write-heavy, "
                        "heap, and missing-index findings.",
                        className="idx-idle-text",
                    ),
                    html.Button(
                        "Go to Triage →",
                        id="btn-indexes-goto-triage",
                        className="idx-cta-btn",
                        n_clicks=0,
                        type="button",
                        disabled=True,
                        style={"marginTop": "12px"},
                    ),
                ],
            ),
        ],
    )


def render_overview(payload: dict | None):
    if not payload:
        return render_overview_idle()

    totals = payload.get("totals") or {}
    findings = payload.get("findings") or []
    counts = triage_filter_counts(findings)

    indexes = int(totals.get("indexes") or 0)
    need_review = int(totals.get("need_review") or 0)
    ok_count = max(0, indexes - need_review)

    if indexes <= 0:
        health_score = 100 if need_review == 0 else 50
    else:
        ratio = min(1.0, need_review / max(indexes, 1))
        health_score = int(round(100 * (1.0 - ratio * 0.85)))
    ring_pct = f"{health_score}%"
    is_healthy = need_review == 0
    status_label = "Healthy" if is_healthy else "Needs attention"
    status_tone = "is-healthy" if is_healthy else "is-attention"

    health_card = html.Div(
        className="idx-health-card",
        children=[
            html.Div(
                className="indexes-health-ring",
                style={"--idx-ring-pct": ring_pct},
                children=[
                    html.Div(
                        className="indexes-health-ring-inner",
                        children=[
                            html.Div(str(health_score), className="indexes-health-ring-score"),
                            html.Div("/ 100", className="idx-health-ring-max"),
                        ],
                    )
                ],
            ),
            html.Div(status_label, className=f"idx-health-status {status_tone}"),
            html.Div(
                f"{fmt_int(ok_count)}/{fmt_int(indexes)} indexes OK",
                className="idx-health-sub",
                dir="ltr",
            ),
        ],
    )

    unused_mb = recoverable_mb([f for f in findings if f.get("category") == "unused"])

    def metric_card(label: str, value, sub: str, *, tone: str = ""):
        return html.Div(
            className=f"idx-metric-card {tone}".strip(),
            children=[
                html.Div(fmt_int(value), className="idx-metric-value"),
                html.Div(label, className="idx-metric-label"),
                html.Div(sub, className="idx-metric-sub"),
            ],
        )

    metrics_grid = html.Div(
        className="idx-metrics-grid",
        children=[
            metric_card(
                "Unused Indexes",
                totals.get("unused") or 0,
                f"{fmt_size_mb(unused_mb)} recoverable" if unused_mb else "No reclaimable space found",
                tone="is-warn" if (totals.get("unused") or 0) else "",
            ),
            metric_card(
                "Write-Heavy",
                totals.get("write_heavy") or 0,
                "High write amplification",
                tone="is-warn" if (totals.get("write_heavy") or 0) else "",
            ),
            metric_card(
                "Heap Tables",
                totals.get("heaps") or 0,
                "No clustered index",
                tone="is-warn" if (totals.get("heaps") or 0) else "",
            ),
            metric_card(
                "Missing Index Hints",
                totals.get("missing_suggestions") or 0,
                "From optimizer DMV",
            ),
        ],
    )

    top_row = html.Div(className="idx-ov-row idx-ov-row-top", children=[health_card, metrics_grid])

    total_issues = max(1, counts.get("critical", 0) + counts.get("warning", 0) + counts.get("watch", 0))

    def issue_row(key: str, label: str):
        n = counts.get(key, 0)
        pct = max(4.0, min(100.0, (n / total_issues) * 100.0)) if n else 0.0
        return html.Div(
            className="idx-issue-row",
            children=[
                html.Span(label, className=f"idx-issue-label is-{key}"),
                html.Div(
                    className="idx-issue-bar",
                    children=html.Div(className=f"idx-issue-fill is-{key}", style={"width": f"{pct:.0f}%"}),
                ),
                html.Span(fmt_int(n), className="idx-issue-count"),
            ],
        )

    issues_card = html.Div(
        className="idx-panel-card",
        children=[
            html.Div("Issue Breakdown", className="idx-panel-title"),
            issue_row("critical", "Critical"),
            issue_row("warning", "Warning"),
            issue_row("watch", "Watch"),
        ],
    )

    db_rows = per_database_summary(findings)
    db_items = []
    for row in db_rows[:_PER_DB_CAP]:
        badges = []
        if row.get("critical"):
            badges.append(html.Span(f"{fmt_int(row['critical'])} critical", className="idx-db-badge is-critical"))
        if row.get("warning"):
            badges.append(html.Span(f"{fmt_int(row['warning'])} warn", className="idx-db-badge is-warning"))
        if not badges and row.get("watch"):
            badges.append(html.Span(f"{fmt_int(row['watch'])} watch", className="idx-db-badge is-watch"))
        db_items.append(
            html.Div(
                className="idx-db-row",
                children=[
                    html.Span(row.get("database_name") or "—", className="idx-db-name", dir="ltr"),
                    html.Div(
                        badges or [html.Span("OK", className="idx-db-badge is-ok")],
                        className="idx-db-badges",
                    ),
                ],
            )
        )
    if len(db_rows) > _PER_DB_CAP:
        db_items.append(
            html.Div(f"+{fmt_int(len(db_rows) - _PER_DB_CAP)} more", className="idx-db-more")
        )

    dbs_card = html.Div(
        className="idx-panel-card",
        children=[
            html.Div("Per Database", className="idx-panel-title"),
            html.Div(
                db_items or [html.Div("No databases scanned yet.", className="idx-empty-hint")],
                className="idx-db-list",
            ),
        ],
    )

    mid_row = html.Div(className="idx-ov-row idx-ov-row-mid", children=[issues_card, dbs_card])

    critical_n = counts.get("critical", 0)
    goto_triage_btn = html.Button(
        "Go to Triage →",
        id="btn-indexes-goto-triage",
        className="idx-cta-btn",
        n_clicks=0,
        type="button",
    )
    if critical_n:
        cta = html.Div(
            className="idx-cta-banner is-critical",
            children=[
                html.Div(
                    className="idx-cta-text-block",
                    children=[
                        html.Div(
                            f"{fmt_int(critical_n)} critical issue{'s' if critical_n != 1 else ''} "
                            "require immediate attention",
                            className="idx-cta-title",
                        ),
                        html.P(
                            "These indexes are actively hurting write performance or wasting "
                            "storage — review them before your next maintenance window.",
                            className="idx-cta-sub",
                        ),
                    ],
                ),
                goto_triage_btn,
            ],
        )
    else:
        cta = html.Div(
            className="idx-cta-banner is-ok",
            children=[
                html.Div(
                    className="idx-cta-text-block",
                    children=[
                        html.Div("No critical issues right now", className="idx-cta-title"),
                        html.P(
                            "Nice work — keep an eye on Warning / Watch findings in Triage.",
                            className="idx-cta-sub",
                        ),
                    ],
                ),
                goto_triage_btn,
            ],
        )

    return html.Div(className="idx-overview-inner", children=[top_row, mid_row, cta])


# ---------------------------------------------------------------------------
# Triage — sub-bar / rail / detail
# ---------------------------------------------------------------------------


def render_triage_subbar(payload: dict | None, filter_key: str = "all"):
    findings = (payload or {}).get("findings") or []
    counts = triage_filter_counts(findings)
    active = (filter_key or "all").lower()
    mb = recoverable_mb(filter_triage_findings(findings, active))

    def pill(key: str, label: str):
        cls = f"idx-triage-pill is-{key}"
        if active == key:
            cls += " active"
        return html.Button(
            [
                html.Span(className=f"idx-dot is-{key}"),
                html.Span(label),
                html.Span(fmt_int(counts.get(key) or 0), className="idx-triage-pill-count"),
            ],
            id={"type": "indexes-triage-pill", "key": key},
            className=cls,
            n_clicks=0,
            type="button",
        )

    pills = html.Div(
        className="idx-triage-pills",
        children=[pill("critical", "Critical"), pill("warning", "Warning"), pill("watch", "Watch")],
    )
    center = html.Div(
        f"{fmt_size_mb(mb)} recoverable" if mb else "No reclaimable space in this filter",
        className="idx-triage-center",
        dir="ltr",
    )
    clear_btn = html.Button(
        "Clear filter ×",
        id="btn-indexes-clear-filter",
        className=f"idx-clear-btn{'' if active in _SEVERITY_LABEL else ' hidden'}",
        n_clicks=0,
        type="button",
    )
    return [pills, center, clear_btn]


def render_triage_rail(
    payload: dict | None,
    filter_key: str = "all",
    selected_id: str | None = None,
):
    if payload is None:
        return html.Div(
            className="idx-rail-empty",
            children=[
                html.Div("No findings loaded yet", className="idx-rail-empty-title"),
                html.Div("Open Overview or click Refresh to scan the catalog / DMVs."),
            ],
        )

    findings = filter_triage_findings(payload.get("findings"), filter_key)
    header = html.Div(
        f"{fmt_int(len(findings))} FINDINGS · RANKED BY IMPACT",
        className="idx-rail-header",
        dir="ltr",
    )
    if not findings:
        return html.Div(
            [
                header,
                html.Div(
                    className="idx-rail-empty",
                    children=[
                        html.Div("No findings in this filter"),
                        html.Div("Try clearing the filter, or refresh the catalog.", className="idx-rail-empty-sub"),
                    ],
                ),
            ]
        )

    cards = []
    for i, f in enumerate(findings):
        sev = _sev(f.get("severity"))
        fid = f.get("id") or str(i)
        score = float(f.get("impact_score") or 0)
        icon = _CARD_ICON.get(f.get("category") or "", "•")
        subtitle = f.get("display_title") or f.get("index_name") or f.get("title") or ""
        selected = " is-selected" if fid == selected_id else ""
        cards.append(
            html.Button(
                [
                    html.Div(
                        className="idx-fc-top",
                        children=[
                            html.Span(f.get("database_name") or "", className="idx-fc-db", dir="ltr"),
                            _sev_badge(sev),
                        ],
                    ),
                    html.Div(f.get("object_path") or "", className="idx-fc-path", dir="ltr"),
                    html.Div(
                        [html.Span(icon, className="idx-fc-icon"), html.Span(subtitle, dir="ltr")],
                        className="idx-fc-subtitle",
                    ),
                    html.Div(
                        className="idx-fc-impact",
                        children=[
                            html.Span(fmt_int(round(score)), className="idx-fc-impact-num"),
                            html.Div(
                                className="idx-fc-impact-bar",
                                children=html.Div(
                                    className=f"idx-fc-impact-fill is-{sev}",
                                    style={"width": f"{max(4.0, min(100.0, score)):.0f}%"},
                                ),
                            ),
                        ],
                    ),
                ],
                id={"type": "indexes-finding-card", "index": i},
                className=f"idx-finding-card is-{sev}{selected}",
                n_clicks=0,
                type="button",
            )
        )
    return html.Div([header, html.Div(cards, className="idx-finding-list")])


def render_triage_detail(finding: dict | None):
    if not finding:
        return html.Div(
            className="idx-detail-empty",
            children=[
                html.Div("Select a finding", className="idx-detail-empty-title"),
                html.Div("Pick an item from the left rail to see why it matters and copy review-only T-SQL."),
            ],
        )

    sev = _sev(finding.get("severity"))
    metrics = finding.get("metrics") or {}
    score = round(float(finding.get("impact_score") or 0))
    title = finding.get("display_title") or finding.get("index_name") or finding.get("title") or "Finding"
    path = f"{finding.get('database_name') or ''} · {finding.get('object_path') or ''}"
    action_label = finding.get("action_label")

    header = html.Div(
        className=f"idx-detail-header is-{sev}",
        children=[
            html.Div(
                className="idx-detail-header-top",
                children=[_sev_badge(sev, prefix="")],
            ),
            html.Span(f"Impact: {score}/100", className="idx-detail-impact"),
            html.Div(path, className="idx-detail-path", dir="ltr"),
            html.H2(title, className="idx-detail-title", dir="ltr"),
            html.Div(action_label, className="idx-detail-action") if action_label else html.Div(),
        ],
    )

    reads = metrics.get("reads")
    writes = metrics.get("writes")
    wr_label = metrics.get("write_read_ratio_label")
    size_mb = metrics.get("size_mb")

    writes_hot = False
    if writes:
        try:
            writes_hot = sev == "critical" or (
                reads not in (None, 0) and float(writes) >= float(reads) * 2
            )
        except (TypeError, ValueError):
            writes_hot = sev == "critical"

    def metric_box(label: str, value: str, *, hot: bool = False):
        return html.Div(
            className=f"idx-detail-metric{' is-hot' if hot else ''}",
            children=[
                html.Div(label, className="idx-detail-metric-label"),
                html.Div(value, className="idx-detail-metric-value", dir="ltr"),
            ],
        )

    metric_cards = [
        metric_box("READS", fmt_compact(reads) if reads is not None else "—"),
        metric_box("WRITES", fmt_compact(writes) if writes is not None else "—", hot=writes_hot),
        metric_box("W/R RATIO", wr_label or "—"),
        metric_box("SIZE", fmt_size_mb(size_mb)),
    ]

    bullets = []
    for b in finding.get("why_bullets") or []:
        tone = (b.get("tone") or "watch").lower()
        bullets.append(
            html.Li(
                [
                    html.Span(_TONE_ICON.get(tone, "•"), className=f"idx-why-ico is-{tone}"),
                    html.Span(b.get("text") or ""),
                ],
                className="idx-why-item",
            )
        )
    why_block = html.Div(
        className="idx-detail-section",
        children=[
            html.Div("WHY THIS IS A PROBLEM", className="idx-detail-section-title"),
            html.Ul(bullets, className="idx-why-list")
            if bullets
            else html.P(finding.get("why") or "—", className="idx-empty-hint"),
        ],
    )

    scripts = []
    for j, s in enumerate(finding.get("scripts") or []):
        scripts.append(
            html.Div(
                className="idx-sql-block",
                children=[
                    html.Pre(
                        s.get("tsql") or "",
                        id={"type": "indexes-copy-payload", "index": 9000, "script": j},
                        className="indexes-copy-payload",
                    ),
                    html.Button(
                        s.get("label") or "Copy",
                        id={"type": "indexes-copy-btn", "index": 9000, "script": j},
                        className="idx-copy-btn",
                        n_clicks=0,
                        type="button",
                    ),
                ],
            )
        )
    sql_block = html.Div(
        className="idx-detail-section",
        children=[
            html.Div("SUGGESTED SQL", className="idx-detail-section-title"),
            html.Div(scripts)
            if scripts
            else html.P(
                "No suggested script for this finding — investigate in Table Explorer.",
                className="idx-empty-hint",
            ),
        ],
    )

    return html.Div(
        className="idx-detail-inner",
        children=[
            header,
            html.Div(metric_cards, className="idx-detail-metrics"),
            why_block,
            sql_block,
        ],
    )


# ---------------------------------------------------------------------------
# Catalog status chip (compact — header)
# ---------------------------------------------------------------------------


def render_catalog_status(status: dict | None):
    if not status or not status.get("available"):
        return html.Span(
            [html.Span(className="idx-dot is-muted"), html.Span("No catalog", className="idx-catalog-text")],
            className="idx-catalog-chip is-muted",
        )

    last = status.get("last_refresh") or {}
    finished = last.get("finished_at") or last.get("started_at")
    st = (last.get("status") or "").lower()
    when = _short_time(finished)

    if st == "error":
        return html.Span(
            [
                html.Span(className="idx-dot is-critical"),
                html.Span("Catalog · failed", className="idx-catalog-text"),
            ],
            className="idx-catalog-chip is-error",
            title=str(last.get("error") or ""),
        )
    if st == "running":
        return html.Span(
            [
                html.Span(className="idx-dot is-warning"),
                html.Span("Catalog · refreshing…", className="idx-catalog-text"),
            ],
            className="idx-catalog-chip is-warn",
        )
    if not status.get("ready"):
        return html.Span(
            [html.Span(className="idx-dot is-muted"), html.Span("No catalog", className="idx-catalog-text")],
            className="idx-catalog-chip is-muted",
        )

    label = f"Catalog · {when}" if when else "Catalog · ready"
    return html.Span(
        [html.Span(className="idx-dot is-ok"), html.Span(label, className="idx-catalog-text", dir="ltr")],
        className="idx-catalog-chip is-ok",
    )


# ---------------------------------------------------------------------------
# Table Explorer — full list view
# ---------------------------------------------------------------------------


def _explorer_status_tone(t: dict) -> str:
    """Row status dot: critical (heap / 0 indexes), warning (large), else muted ok."""
    if t.get("is_heap"):
        return "critical"
    try:
        if t.get("index_count") is not None and int(t.get("index_count")) == 0:
            return "critical"
    except (TypeError, ValueError):
        pass
    try:
        if t.get("size_mb") is not None and float(t.get("size_mb")) >= 1024:
            return "warning"
    except (TypeError, ValueError):
        pass
    return "ok"


def render_explorer_table_list(
    cache: dict | None,
    selected: dict | None,
    query: str = "",
    *,
    sort_key: str = "table",
):
    if not cache:
        return html.Div(
            className="idx-ex-empty",
            children="Choose a database (or All) to load tables from the catalog.",
        )

    cache_db = cache.get("database") or ""
    tables = list(cache.get("tables") or [])
    q = (query or "").strip().lower()
    if q:
        tables = [
            t
            for t in tables
            if q in str(t.get("full_name") or "").lower()
            or q in str(t.get("table_name") or "").lower()
            or q in str(t.get("database_name") or cache_db or "").lower()
        ]
    if not tables:
        return html.Div(className="idx-ex-empty", children="No tables match this filter.")

    def sort_val(t: dict):
        if sort_key == "schema":
            return str(t.get("schema_name") or "").lower()
        if sort_key == "rows":
            try:
                return -float(t.get("row_count") or 0)
            except (TypeError, ValueError):
                return 0
        if sort_key == "heap":
            return 0 if t.get("is_heap") else 1
        return str(t.get("table_name") or "").lower()

    visible = sorted(tables, key=sort_val)[:_EXPLORER_ROW_CAP]
    sel_schema = (selected or {}).get("schema")
    sel_table = (selected or {}).get("table")
    sel_db = (selected or {}).get("database")
    cache_time = _short_time(cache.get("refreshed_at") or cache.get("cached_at"))

    # Keep the selected table visible even when search was cleared / outside row cap
    if selected and sel_table:
        def _is_sel(t: dict) -> bool:
            return (
                (t.get("schema_name") or "dbo") == (sel_schema or "dbo")
                and (t.get("table_name") or "") == sel_table
                and (
                    not sel_db
                    or (t.get("database_name") or cache_db) == sel_db
                )
            )

        if not any(_is_sel(t) for t in visible):
            pinned = next((t for t in (cache.get("tables") or []) if _is_sel(t)), None)
            if pinned is None:
                pinned = {
                    "database_name": sel_db or cache_db,
                    "schema_name": sel_schema or "dbo",
                    "table_name": sel_table,
                    "full_name": f"{sel_schema or 'dbo'}.{sel_table}",
                }
            visible = [pinned] + visible[: max(0, _EXPLORER_ROW_CAP - 1)]

    head = html.Div(
        className="idx-ex-row idx-ex-row-head",
        children=[
            html.Span("", className="idx-ex-col idx-ex-status"),
            html.Span("DATABASE", className="idx-ex-col idx-ex-db"),
            html.Span("SCHEMA.TABLE", className="idx-ex-col idx-ex-table"),
            html.Span("TYPE", className="idx-ex-col idx-ex-type"),
            html.Span("ROWS", className="idx-ex-col idx-ex-num"),
            html.Span("SIZE", className="idx-ex-col idx-ex-num"),
            html.Span("INDEXES", className="idx-ex-col idx-ex-num"),
            html.Span("CACHED", className="idx-ex-col idx-ex-cached"),
        ],
    )

    rows = [head]
    for i, t in enumerate(visible):
        schema = t.get("schema_name") or "dbo"
        table = t.get("table_name") or ""
        db_name = t.get("database_name") or cache_db or "—"
        is_heap = bool(t.get("is_heap"))
        size_mb = t.get("size_mb")
        idx_count = t.get("index_count")
        try:
            size_hot = size_mb is not None and float(size_mb) >= 1024
        except (TypeError, ValueError):
            size_hot = False
        try:
            idx_zero = idx_count is not None and int(idx_count) == 0
        except (TypeError, ValueError):
            idx_zero = False
        tone = _explorer_status_tone(t)
        is_sel = (
            schema == sel_schema
            and table == sel_table
            and (not sel_db or sel_db == db_name)
        )
        row_cached = _short_time(t.get("refreshed_at") or t.get("cached_at")) or cache_time or "—"
        type_child = (
            html.Span("HEAP", className="idx-type-badge is-heap")
            if is_heap
            else html.Span("CLUSTERED", className="idx-type-badge is-clustered")
        )
        rows.append(
            html.Button(
                [
                    html.Span(
                        html.Span(className=f"idx-ex-dot is-{tone}"),
                        className="idx-ex-col idx-ex-status",
                    ),
                    html.Span(db_name, className="idx-ex-col idx-ex-db", dir="ltr"),
                    html.Span(f"{schema}.{table}", className="idx-ex-col idx-ex-table", dir="ltr"),
                    html.Span(type_child, className="idx-ex-col idx-ex-type"),
                    html.Span(
                        fmt_compact(t.get("row_count")) if t.get("row_count") is not None else "—",
                        className="idx-ex-col idx-ex-num",
                        dir="ltr",
                    ),
                    html.Span(
                        fmt_size_mb(size_mb) if size_mb is not None else "—",
                        className=f"idx-ex-col idx-ex-num{' is-hot' if size_hot else ''}",
                        dir="ltr",
                    ),
                    html.Span(
                        fmt_int(idx_count) if idx_count is not None else "—",
                        className=f"idx-ex-col idx-ex-num{' is-zero' if idx_zero else ''}",
                        dir="ltr",
                    ),
                    html.Span(row_cached, className="idx-ex-col idx-ex-cached", dir="ltr"),
                ],
                id={"type": "indexes-table-row", "index": i},
                className=f"indexes-ex-row{' is-selected' if is_sel else ''}",
                n_clicks=0,
                type="button",
            )
        )

    return html.Div(rows, className="idx-ex-list", **{"data-visible-count": str(len(visible))})
