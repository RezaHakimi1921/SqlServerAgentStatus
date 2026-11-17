"""Index Intelligence — Figma-matched panel renderers.

Overview · Triage sub-bar/rail/detail · Table Explorer list — all pure
render functions (no SQL, no Dash callbacks). `layout.py` wires these into
the shell; `callbacks.py` re-renders them from `store-indexes-overview` /
`store-indexes-table-cache`.
"""
from __future__ import annotations

from datetime import datetime

from dash import html

import math

from core.formatters import fmt_compact, fmt_int, fmt_size_mb
from core.i18n import DEFAULT_LOCALE, normalize_locale, t
from modules.indexes.constants import INDEX_CONFIDENCE_SCRIPT_MIN, INDEX_EXPLORER_PAGE_SIZE
from modules.indexes.triage import (
    filter_triage_findings,
    per_database_summary,
    recoverable_mb,
    triage_filter_counts,
)

_SEVERITY_LABEL = {"critical": "CRITICAL", "warning": "WARNING", "watch": "WATCH"}

_CARD_ICON = {
    "unused": "unused",
    "write_heavy": "write",
    "heap": "heap",
    "missing": "missing",
}

_TONE_ICON = {"critical": "critical", "warning": "warning", "watch": "watch"}

_PER_DB_CAP = 8


def _as_heap(v) -> bool:
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
        return v.strip().lower() in ("1", "true", "yes", "heap")
    return bool(v)


def filter_explorer_tables(
    cache: dict | None,
    query: str = "",
    *,
    sort_key: str = "table",
) -> list[dict]:
    """Filter/sort explorer rows — search matches schema.table, DB, or type (heap/clustered)."""
    if not cache:
        return []
    cache_db = cache.get("database") or ""
    tables = list(cache.get("tables") or [])
    q = (query or "").strip().lower()
    if q:
        out = []
        for t in tables:
            is_heap = _as_heap(t.get("is_heap"))
            type_label = "heap" if is_heap else "clustered"
            blob = (
                f"{t.get('schema_name')}.{t.get('table_name')} "
                f"{t.get('database_name') or cache_db} {type_label}"
            ).lower()
            if q in ("heap", "heaps"):
                if is_heap:
                    out.append(t)
            elif q in ("clustered", "cluster", "ci"):
                if not is_heap:
                    out.append(t)
            elif (
                q in blob
                or q in str(t.get("full_name") or "").lower()
                or q in str(t.get("table_name") or "").lower()
            ):
                out.append(t)
        tables = out

    def sort_val(t: dict):
        if sort_key == "schema":
            return str(t.get("schema_name") or "").lower()
        if sort_key == "rows":
            try:
                return -float(t.get("row_count") or 0)
            except (TypeError, ValueError):
                return 0
        if sort_key == "heap":
            return 0 if _as_heap(t.get("is_heap")) else 1
        return str(t.get("table_name") or "").lower()

    return sorted(tables, key=sort_val)


def explorer_page_meta(total: int, page: int) -> tuple[int, int, int, int, int]:
    page_size = int(INDEX_EXPLORER_PAGE_SIZE)
    total_pages = max(1, math.ceil(total / page_size)) if total else 1
    page = max(1, min(int(page or 1), total_pages))
    start = (page - 1) * page_size
    start_n = start + 1 if total else 0
    end_n = min(page * page_size, total)
    return page, total_pages, start, start_n, end_n


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


def triage_badge_children(count: int, locale: str = DEFAULT_LOCALE):
    """Tab label children for the Triage main tab — badge only when count > 0."""
    loc = normalize_locale(locale)
    label = t("indexes.tab.triage", loc)
    if count:
        return [label, html.Span(str(count), className="indexes-ii-badge")]
    return label


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


def _render_health_gauge(
    *,
    score: int,
    ok_count: int,
    indexes: int,
    status_label: str,
    tone: str,
) -> html.Div:
    """Circular score gauge — Needs optimization · 9/11 · 85/100."""
    pct = max(0, min(100, int(score)))
    ring_style = {"--idx-gauge-pct": str(pct)}
    return html.Div(
        className=f"idx-health-gauge {tone}",
        dir="ltr",
        children=[
            html.Div(
                className="idx-health-gauge-ring",
                style=ring_style,
                children=[html.Span(str(pct), className="idx-health-gauge-score")],
            ),
            html.Div(
                className="idx-health-gauge-meta",
                children=[
                    html.Span(status_label, className="idx-health-gauge-label"),
                    html.Span(
                        f"{fmt_int(ok_count)}/{fmt_int(indexes)} · {pct}/100",
                        className="idx-health-gauge-sub",
                    ),
                ],
            ),
        ],
    )


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


def render_overview(payload: dict | None, locale: str = DEFAULT_LOCALE):
    if not payload:
        return render_overview_idle()

    from modules.indexes.service import compute_overview_kpis

    loc = normalize_locale(locale)
    totals = payload.get("totals") or {}
    findings = payload.get("findings") or []
    counts = triage_filter_counts(findings)
    kpis = payload.get("kpis") or compute_overview_kpis(payload)
    cat_counts: dict[str, int] = {}
    for f in findings:
        c = f.get("category") or ""
        cat_counts[c] = cat_counts.get(c, 0) + 1
    if kpis.get("missing_impact") is not None:
        kpis["missing_impact"]["badge"] = cat_counts.get("missing") or int(
            totals.get("missing_suggestions") or 0
        )
    if kpis.get("dead_unused_writes") is not None:
        kpis["dead_unused_writes"]["badge"] = cat_counts.get("unused", 0) + cat_counts.get(
            "write_heavy", 0
        )
    if kpis.get("duplicate_debt") is not None:
        kpis["duplicate_debt"]["badge"] = cat_counts.get("duplicate") or int(
            totals.get("duplicates") or 0
        )
    if kpis.get("high_frag") is not None and kpis["high_frag"].get("display") == "int":
        kpis["high_frag"]["badge"] = int(kpis["high_frag"].get("value") or 0)

    indexes = int(totals.get("indexes") or 0)
    need_review = int(totals.get("need_review") or 0)
    ok_count = max(0, indexes - need_review)
    if indexes <= 0:
        health_score = 100 if need_review == 0 else 50
    else:
        ratio = min(1.0, need_review / max(indexes, 1))
        health_score = int(round(100 * (1.0 - ratio * 0.85)))
    is_healthy = need_review == 0
    status_label = t("indexes.health.ok", loc) if is_healthy else t("indexes.health.needs", loc)
    status_tone = "is-healthy" if is_healthy else "is-attention"

    src = (payload.get("source") or "live").lower()
    if src.startswith("advisor"):
        src_label = t("indexes.source.advisor", loc)
    elif src == "catalog":
        src_label = t("indexes.source.catalog", loc)
    else:
        src_label = t("indexes.source.live", loc)
    meta = payload.get("advisor_meta") or {}
    window = meta.get("window_label") or ""

    header_bar = html.Div(
        className="idx-overview-source",
        children=[
            html.Span(src_label, className="idx-overview-source-label"),
            html.Span(window, className="idx-overview-source-window", dir="ltr") if window else None,
            _render_health_gauge(
                score=health_score,
                ok_count=ok_count,
                indexes=indexes,
                status_label=status_label,
                tone=status_tone,
            ),
        ],
    )

    def kpi_card(kpi_id: str, title_key: str, cell: dict):
        cell = cell or {}
        tone = (cell.get("tone") or "").replace("is-", "") or "neutral"
        if cell.get("display") == "dash":
            value_child = t("indexes.kpi.dash", loc)
        elif kpi_id == "missing" and cell.get("display_mode") == "pct":
            value_child = f"{cell.get('peak_impact_pct'):.1f}%"
        elif kpi_id == "missing":
            value_child = fmt_compact(cell.get("value") or 0)
        else:
            value_child = fmt_int(cell.get("value") or 0)
        sub_key = cell.get("sub_key") or "missing_sub"
        if kpi_id == "missing" and (payload.get("kpi_supplement") == "live_dmv_peek"):
            sub_key = "missing_peek_sub"
        sub = t(
            f"indexes.kpi.{sub_key}",
            loc,
            writes=fmt_int(cell.get("writes") or 0),
            unused=fmt_int(cell.get("unused_with_writes") or 0),
            wh=fmt_int(cell.get("write_heavy") or 0),
        )
        return html.Div(
            id=f"indexes-kpi-{kpi_id}",
            className=f"idx-kpi-card is-{kpi_id} tone-{tone}".strip(),
            children=[
                html.Span(
                    t("indexes.kpi.cases", loc, n=fmt_int(cell.get("badge") or 0)),
                    className="idx-kpi-badge",
                    dir="ltr",
                )
                if cell.get("badge")
                else None,
                html.Div(
                    className="idx-kpi-card-head",
                    children=[
                        html.Span(className=f"idx-kpi-icon is-{kpi_id}", **{"aria-hidden": "true"}),
                        html.Div(t(title_key, loc), className="idx-kpi-label"),
                    ],
                ),
                html.Div(value_child, className="idx-kpi-value", dir="ltr"),
                html.Div(sub, className="idx-kpi-sub"),
            ],
        )

    # Design §2: four KPI cards as primary strip (no Consolidation)
    kpi_row = html.Div(
        className="idx-ov-row idx-ov-kpi-row",
        children=[
            kpi_card("missing", "indexes.kpi.missing_impact", kpis.get("missing_impact") or {}),
            kpi_card("frag", "indexes.kpi.high_frag", kpis.get("high_frag") or {}),
            kpi_card(
                "unused-writes",
                "indexes.kpi.dead_unused_writes",
                kpis.get("dead_unused_writes") or {},
            ),
            kpi_card("duplicates", "indexes.kpi.duplicate_debt", kpis.get("duplicate_debt") or {}),
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
        id="indexes-ov-per-db",
        className="idx-panel-card",
        children=[
            html.Div(t("indexes.ov.per_db", loc), className="idx-panel-title"),
            html.Div(
                db_items or [html.Div(t("indexes.ov.no_db", loc), className="idx-empty-hint")],
                className="idx-db-list",
            ),
        ],
    )

    frag_available = bool(payload.get("frag_available") or payload.get("frag_loaded"))
    high_frag_cell = kpis.get("high_frag") or {}
    high_frag_n = int(high_frag_cell.get("value") or 0) if frag_available and high_frag_cell.get("display") == "int" else None
    if frag_available and high_frag_n is not None:
        frag_body = html.Div(
            className="idx-frag-bands",
            children=[
                html.Div(
                    className="idx-frag-band is-ok",
                    children=[
                        html.Span(t("indexes.frag.healthy", loc), className="idx-frag-band-label"),
                        html.Span("< 10%", className="idx-frag-band-range", dir="ltr"),
                    ],
                ),
                html.Div(
                    className="idx-frag-band is-warn",
                    children=[
                        html.Span(t("indexes.frag.moderate", loc), className="idx-frag-band-label"),
                        html.Span("10–30% · REORGANIZE", className="idx-frag-band-range", dir="ltr"),
                    ],
                ),
                html.Div(
                    className="idx-frag-band is-critical",
                    children=[
                        html.Span(t("indexes.frag.critical", loc), className="idx-frag-band-label"),
                        html.Span(
                            f"> 30% · REBUILD · {fmt_int(high_frag_n)}",
                            className="idx-frag-band-range",
                            dir="ltr",
                        ),
                    ],
                ),
            ],
        )
    else:
        frag_body = html.Div(
            className="idx-frag-pending",
            children=[
                html.Span("—", className="idx-frag-pending-dash", dir="ltr"),
                html.Span(t("indexes.frag.pending_short", loc), className="idx-frag-pending-note"),
            ],
        )

    frag_card = html.Div(
        id="indexes-ov-frag",
        className="idx-panel-card",
        children=[
            html.Div(t("indexes.ov.frag_dist", loc), className="idx-panel-title"),
            frag_body,
        ],
    )

    unused_findings = [f for f in findings if f.get("category") == "unused"]
    waste_mb = recoverable_mb(unused_findings)
    waste_gb = (waste_mb / 1024.0) if waste_mb else 0.0
    write_waste = kpis.get("dead_unused_writes") or {}
    waste_card = html.Div(
        id="indexes-ov-waste",
        className="idx-panel-card",
        children=[
            html.Div(t("indexes.ov.waste_gb", loc), className="idx-panel-title"),
            html.Div(
                className="idx-waste-value",
                children=fmt_compact(round(waste_gb, 2)) if waste_gb else "0",
                dir="ltr",
            ),
            html.Div(
                t(
                    "indexes.ov.waste_sub",
                    loc,
                    mb=fmt_size_mb(waste_mb) if waste_mb else "0 MB",
                    writes=fmt_int(write_waste.get("writes") or 0),
                ),
                className="idx-metric-sub",
            ),
        ],
    )

    analytics_row = html.Div(
        className="idx-ov-row idx-ov-analytics-row",
        children=[dbs_card, frag_card, waste_card],
    )

    critical_n = counts.get("critical", 0)
    goto_triage_btn = html.Button(
        t("indexes.cta.triage", loc),
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
                            t("indexes.cta.critical_title", loc, n=fmt_int(critical_n)),
                            className="idx-cta-title",
                        ),
                        html.P(t("indexes.cta.critical_sub", loc), className="idx-cta-sub"),
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
                        html.Div(t("indexes.cta.ok_title", loc), className="idx-cta-title"),
                        html.P(t("indexes.cta.ok_sub", loc), className="idx-cta-sub"),
                    ],
                ),
                goto_triage_btn,
            ],
        )

    return html.Div(
        className="idx-overview-inner",
        children=[header_bar, kpi_row, analytics_row, cta],
    )


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
        icon = _CARD_ICON.get(f.get("category") or "", "dot")
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
                        [
                            html.Span(className=f"idx-fc-icon is-{icon}", **{"aria-hidden": "true"}),
                            html.Span(subtitle, dir="ltr"),
                        ],
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
                    html.Span(className=f"idx-why-ico is-{tone}", **{"aria-hidden": "true"}),
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
    blocked = finding.get("script_blocked_reason")
    try:
        score = int(finding.get("confidence_score")) if finding.get("confidence_score") is not None else None
    except (TypeError, ValueError):
        score = None
    allow_copy = not blocked and (
        score is None or score >= INDEX_CONFIDENCE_SCRIPT_MIN
    )
    if score is not None and score < INDEX_CONFIDENCE_SCRIPT_MIN:
        allow_copy = False
    for j, s in enumerate(finding.get("scripts") or []):
        if not allow_copy:
            break
        if not (s.get("tsql") or "").strip():
            continue
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
                        s.get("label") or t("indexes.script.copy", DEFAULT_LOCALE),
                        id={"type": "indexes-copy-btn", "index": 9000, "script": j},
                        className="idx-copy-btn",
                        n_clicks=0,
                        type="button",
                    ),
                ],
            )
        )
    conf_meta = []
    if score is not None:
        conf_meta.append(
            html.Div(
                t("indexes.script.confidence", DEFAULT_LOCALE, score=score),
                className="idx-script-confidence",
                dir="ltr",
            )
        )
    reasons = finding.get("confidence_reasons") or (
        [finding.get("confidence_reason")] if finding.get("confidence_reason") else []
    )
    reasons = [str(x) for x in reasons if x]
    if reasons:
        conf_meta.append(
            html.Div(
                t("indexes.script.reasons", DEFAULT_LOCALE, reasons="; ".join(reasons[:3])),
                className="idx-script-reasons",
            )
        )
    if blocked or (score is not None and score < INDEX_CONFIDENCE_SCRIPT_MIN):
        sql_inner = html.P(
            blocked
            or t(
                "indexes.script.blocked",
                DEFAULT_LOCALE,
                score=score if score is not None else 0,
                min=INDEX_CONFIDENCE_SCRIPT_MIN,
            ),
            className="indexes-script-blocked",
        )
    elif scripts:
        sql_inner = html.Div(scripts)
    else:
        sql_inner = html.P(
            "No suggested script for this finding — investigate in Table Explorer.",
            className="idx-empty-hint",
        )
    sql_block = html.Div(
        className="idx-detail-section",
        children=[
            html.Div("SUGGESTED SQL", className="idx-detail-section-title"),
            html.Div(conf_meta, className="idx-script-meta") if conf_meta else None,
            sql_inner,
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
    if _as_heap(t.get("is_heap")):
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


def render_explorer_pagination_info(
    total: int, page: int, total_pages: int, start_n: int, end_n: int
):
    return [
        "Showing ",
        html.Strong(fmt_int(start_n)),
        "–",
        html.Strong(fmt_int(end_n)),
        " of ",
        html.Strong(fmt_int(total)),
        " tables",
    ]


def render_explorer_table_list(
    cache: dict | None,
    selected: dict | None,
    query: str = "",
    *,
    sort_key: str = "table",
    page: int = 1,
    locale: str = DEFAULT_LOCALE,
):
    loc = normalize_locale(locale)
    if not cache:
        return html.Div(
            className="idx-ex-empty",
            children=t("indexes.empty.choose_db", loc),
        )

    cache_db = cache.get("database") or ""
    filtered = filter_explorer_tables(cache, query, sort_key=sort_key or "table")
    if not filtered:
        return html.Div(className="idx-ex-empty", children=t("indexes.empty.no_tables", loc))

    page, total_pages, start, _start_n, _end_n = explorer_page_meta(len(filtered), page)
    visible = filtered[start : start + INDEX_EXPLORER_PAGE_SIZE]
    sel_schema = (selected or {}).get("schema")
    sel_table = (selected or {}).get("table")
    sel_db = (selected or {}).get("database")
    cache_time = _short_time(cache.get("refreshed_at") or cache.get("cached_at"))

    head = html.Div(
        className="idx-ex-row idx-ex-row-head",
        children=[
            html.Span("", className="idx-ex-col idx-ex-status"),
            html.Span(t("indexes.col.database", loc), className="idx-ex-col idx-ex-db"),
            html.Span(t("indexes.col.schema_table", loc), className="idx-ex-col idx-ex-table"),
            html.Span(t("indexes.col.type", loc), className="idx-ex-col idx-ex-type"),
            html.Span(t("indexes.col.rows", loc), className="idx-ex-col idx-ex-num"),
            html.Span(t("indexes.col.size", loc), className="idx-ex-col idx-ex-num"),
            html.Span(t("indexes.col.indexes", loc), className="idx-ex-col idx-ex-num"),
            html.Span(t("indexes.col.cached", loc), className="idx-ex-col idx-ex-cached"),
        ],
    )

    rows = [head]
    for i, row in enumerate(visible):
        schema = row.get("schema_name") or "dbo"
        table = row.get("table_name") or ""
        db_name = row.get("database_name") or cache_db or "—"
        is_heap = _as_heap(row.get("is_heap"))
        size_mb = row.get("size_mb")
        idx_count = row.get("index_count")
        try:
            size_hot = size_mb is not None and float(size_mb) >= 1024
        except (TypeError, ValueError):
            size_hot = False
        try:
            idx_zero = idx_count is not None and int(idx_count) == 0
        except (TypeError, ValueError):
            idx_zero = False
        tone = _explorer_status_tone(row)
        is_sel = (
            schema == sel_schema
            and table == sel_table
            and (not sel_db or sel_db == db_name)
        )
        row_cached = _short_time(row.get("refreshed_at") or row.get("cached_at")) or cache_time or "—"
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
                        fmt_compact(row.get("row_count")) if row.get("row_count") is not None else "—",
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

    return html.Div(
        rows,
        className="idx-ex-list",
        **{"data-visible-count": str(len(visible)), "data-total": str(len(filtered)), "data-page": str(page)},
    )
