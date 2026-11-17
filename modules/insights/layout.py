"""Today's Insights — glance first, details on demand."""
from __future__ import annotations

import json
import re

from dash import dcc, html

from core.formatters import fmt_duration_hms, fmt_int
from core.i18n import DEFAULT_LOCALE, normalize_locale, t
from core.insight.rules import blocking_action_fa, blocking_cause_fa, blocking_glance_fa


def _fmt_ts(v) -> str:
    if v is None:
        return "—"
    try:
        return v.strftime("%H:%M:%S")
    except Exception:
        s = str(v)
        if "T" in s:
            return s.split("T")[-1][:8]
        return s[11:19] if len(s) >= 19 else s[:19]


def _parse_evidence(raw) -> dict | None:
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return None


def _clean_detail(text: str) -> str:
    if not text:
        return ""
    if "[snapshot]" in text:
        text = text.split("[snapshot]", 1)[0]
    text = re.sub(r"\n•[^\n]*", "", text)
    return text.strip()


def build_insights_layout(locale: str = DEFAULT_LOCALE):
    loc = normalize_locale(locale)
    return html.Div(
        className="insights-shell",
        children=[
            html.Div(className="activity-toolbar insights-toolbar", children=[
                html.Div(className="activity-tabs", children=[
                    html.Span(t("module.insights.title", loc), className="insights-title"),
                    html.Span(
                        t("module.insights.subtitle", loc),
                        className="insights-sub",
                    ),
                ]),
                html.Div(className="activity-controls", children=[
                    html.Button(
                        [html.Span("↻", className="ctrl-ico"), html.Span(t("header.refresh", loc), className="ctrl-txt")],
                        id="btn-insights-refresh",
                        className="activity-ctrl-btn is-refresh",
                        n_clicks=0,
                        title="تازه‌سازی Insights",
                    ),
                ]),
            ]),
            html.Div(id="insights-health-strip", className="health-strip"),
            html.Div(id="insights-meta", className="activity-meta"),
            html.Div(
                id="insights-loading",
                className="activity-loading hidden",
                children=[
                    html.Div(className="activity-loading-card", children=[
                        html.Div(className="activity-loading-spinner"),
                        html.Div(t("insights.loading", loc), className="activity-loading-text"),
                    ]),
                ],
            ),
            html.Div(id="insights-body", className="insights-body"),
            dcc.Store(id="store-insights", data=None),
            dcc.Interval(id="interval-insights", interval=30_000, n_intervals=0),
        ],
    )


def render_insights_health(rows: list, locale: str = DEFAULT_LOCALE) -> list:
    loc = normalize_locale(locale)
    crit = sum(1 for r in rows if (r.get("severity") or "").lower() == "critical")
    warn = sum(1 for r in rows if (r.get("severity") or "").lower() == "warning")
    info = sum(1 for r in rows if (r.get("severity") or "").lower() == "info")
    cards = [
        (t("insights.kpi.critical", loc), crit, "tone-crit" if crit else "tone-ok"),
        (t("insights.kpi.warning", loc), warn, "tone-hot" if warn else "tone-ok"),
        (t("insights.kpi.info", loc), info, "tone-ok"),
        (t("insights.kpi.total", loc), len(rows), "tone-ok"),
    ]
    return [
        html.Div(className=f"health-card {tone}", children=[
            html.Div(label, className="health-card-label"),
            html.Div(fmt_int(val), className="health-card-value num-ltr"),
        ])
        for label, val, tone in cards
    ]


def _sql_box(label: str, sql: str | None, empty_hint: str) -> html.Div:
    text = (sql or "").strip()
    if not text:
        return html.Div(className="insight-sql-box", children=[
            html.Div(label, className="insight-sql-lbl"),
            html.Pre(empty_hint, className="insight-blk-sql is-empty"),
        ])
    from modules.activity.layout import _sql_highlight_nodes, extract_sql_target
    target = extract_sql_target(text)
    return html.Div(className="insight-sql-box", children=[
        html.Div(label, className="insight-sql-lbl"),
        (
            html.Div(
                f"{target.get('verb')} · {target.get('table')}",
                className="insight-sql-table num-ltr",
            )
            if target and target.get("table") else None
        ),
        html.Pre(
            _sql_highlight_nodes(text, emphasize_table=(target or {}).get("table")),
            className="insight-blk-sql has-tokens",
        ),
    ])


def _render_blocking_edge_compact(r: dict) -> html.Div:
    """One blocking edge inside Details — still scannable, SQL nested deeper."""
    blocker = r.get("blocker_session_id")
    blocked = r.get("blocked_session_id")
    wait_ms = int(r.get("wait_ms") or 0)
    is_head = int(r.get("is_head_blocker") or 0) == 1
    chain = (r.get("chain_display") or f"{blocker} → {blocked}").strip()
    cause = (r.get("cause_fa") or "").strip() or blocking_cause_fa(r)
    action = (r.get("action_fa") or "").strip() or blocking_action_fa(r)

    return html.Div(className="insight-blk", children=[
        html.Div(className="insight-blk-top", children=[
            html.Span(chain, className="insight-blk-chain"),
            html.Span(
                f"{fmt_duration_hms(wait_ms)} wait",
                className="insight-blk-wait num-ltr",
            ),
            html.Span("Head blocker", className="insight-blk-head") if is_head else None,
        ]),
        html.Div(cause, className="insight-cause"),
        html.Div(className="insight-blk-action-line", children=[
            html.Span("اقدام", className="insight-glance-lbl"),
            html.Span(action),
        ]),
        html.Div(className="insight-blk-meta", children=[
            html.Span(r.get("wait_type") or "—", className="tag"),
            html.Span(r.get("database_name") or "—", className="tag"),
            html.Span(r.get("blocker_command") or "—", className="tag"),
        ]),
        html.Details(className="insight-sql-details", children=[
            html.Summary("کوئری Blocker / Blocked"),
            html.Div(className="insight-blk-sides", children=[
                html.Div(className="insight-blk-side", children=[
                    html.Div(f"Blocker {blocker}", className="insight-blk-lbl"),
                    html.Div(
                        f"{r.get('blocker_login') or '—'} · {r.get('blocker_host') or '—'}",
                        className="insight-blk-sub",
                    ),
                    _sql_box(
                        "کوئری Blocker",
                        r.get("blocker_sql"),
                        "متن در دسترس نبود (Sleeping / open tran).",
                    ),
                ]),
                html.Div(className="insight-blk-side", children=[
                    html.Div(f"Blocked {blocked}", className="insight-blk-lbl"),
                    html.Div(
                        f"{r.get('blocked_login') or '—'} · {r.get('blocked_host') or '—'}",
                        className="insight-blk-sub",
                    ),
                    _sql_box(
                        "کوئری Blocked",
                        r.get("blocked_sql"),
                        "متن در دسترس نبود.",
                    ),
                ]),
            ]),
        ]),
    ])


def _render_blocking_evidence(evidence: dict | None, rule_id: str) -> html.Div | None:
    if rule_id != "blocking_active":
        return None

    if not evidence or not (evidence.get("rows") or []):
        return html.Div(className="insight-evidence insight-evidence-empty", children=[
            html.P(
                "هنوز snapshot با کوئری ذخیره نشده. با Blocking بعدی اینجا پر می‌شود.",
                className="insight-evidence-note",
            ),
        ])

    captured = evidence.get("captured_at") or "—"
    blocks = [_render_blocking_edge_compact(r) for r in (evidence.get("rows") or [])]

    return html.Div(className="insight-evidence", children=[
        html.Div(className="insight-evidence-head", children=[
            html.Span("زنجیره‌های Blocking", className="insight-evidence-title"),
            html.Span(f"captured {captured}", className="insight-evidence-when"),
        ]),
        html.P(
            "این snapshot لحظهٔ ثبت است — Live ممکن است الان خالی باشد.",
            className="insight-evidence-note",
        ),
        html.Div(className="insight-blk-list", children=blocks),
    ])


def _job_glance(detail: str, title: str) -> tuple[str, str]:
    problem = (detail or title or "خطای جاب Agent").strip()
    action = "در Agent Jobs لاگ step را ببین؛ علت را رفع و جاب را دوباره اجرا کن."
    return problem, action


def render_insights_list(rows: list, locale: str = DEFAULT_LOCALE):
    loc = normalize_locale(locale)
    if not rows:
        return html.Div(className="state-box state-empty", children=[
            html.Div("✓", className="state-icon"),
            html.H3(t("insights.empty.title", loc)),
            html.P(
                "وقتی blocking یا job failure در Metric Store ثبت شود، اینجا ظاهر می‌شود.",
            ),
        ])

    items = []
    for r in rows:
        sev = (r.get("severity") or "info").lower()
        iid = r.get("insight_id")
        rule_id = r.get("rule_id") or ""
        link = r.get("link_target") or ""
        evidence = _parse_evidence(r.get("evidence_json"))
        detail = _clean_detail(r.get("detail") or "")
        title = r.get("title") or "—"

        if rule_id == "blocking_active":
            ev_rows = (evidence or {}).get("rows") or []
            problem, action = blocking_glance_fa(ev_rows, detail)
            link_btn = html.Button(
                "Live Blocking",
                id={"type": "insight-goto", "target": "activity-blocking", "id": iid},
                className="insight-link-btn is-secondary",
                n_clicks=0,
                title="ممکن است دیگر در Live دیده نشود",
            )
            evidence_block = _render_blocking_evidence(evidence, rule_id)
        elif rule_id == "job_failed_today" or link == "jobs":
            problem, action = _job_glance(detail, title)
            link_btn = html.Button(
                "Agent Jobs",
                id={"type": "insight-goto", "target": "jobs", "id": iid},
                className="insight-link-btn",
                n_clicks=0,
            )
            evidence_block = html.Div(detail, className="insight-detail") if detail else None
        else:
            problem = detail or title
            action = "جزئیات را باز کن و منبع مربوطه را بررسی کن."
            link_btn = None
            evidence_block = html.Div(detail, className="insight-detail") if detail else None

        details_children = []
        if detail and rule_id == "blocking_active":
            details_children.append(html.Div(detail, className="insight-detail is-muted"))
        if evidence_block is not None:
            details_children.append(evidence_block)

        items.append(html.Div(className=f"insight-card sev-{sev}", children=[
            html.Div(className="insight-card-top", children=[
                html.Span(sev.upper(), className=f"insight-sev {sev}"),
                html.Span(
                    f"{_fmt_ts(r.get('first_seen_at'))} → {_fmt_ts(r.get('last_seen_at'))}",
                    className="insight-when",
                ),
                html.Span(f"×{r.get('occurrence_count') or 1}", className="insight-count"),
            ]),
            html.Div(title, className="insight-title"),
            html.Div(className="insight-glance", children=[
                html.Div(className="insight-glance-row is-problem", children=[
                    html.Span(t("insights.glance.problem", loc), className="insight-glance-lbl"),
                    html.Span(problem, className="insight-glance-text"),
                ]),
                html.Div(className="insight-glance-row is-action", children=[
                    html.Span(t("insights.glance.action", loc), className="insight-glance-lbl"),
                    html.Span(action, className="insight-glance-text"),
                ]),
            ]),
            html.Details(className="insight-details", open=False, children=[
                html.Summary(t("insights.details", loc)),
                html.Div(className="insight-details-body", children=details_children),
            ]) if details_children else None,
            html.Div(className="insight-actions", children=[
                c for c in [
                    link_btn,
                    html.Button(
                        t("insights.dismiss", loc),
                        id={"type": "insight-dismiss", "id": iid},
                        className="insight-dismiss-btn",
                        n_clicks=0,
                        title="Feedback برای تنظیم آستانه",
                    ),
                ] if c is not None
            ]),
        ]))
    return html.Div(className="insights-list", children=items)
