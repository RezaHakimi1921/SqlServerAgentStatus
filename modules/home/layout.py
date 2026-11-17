"""Home / overview — Figma Make fidelity (greeting, freshness, KPIs, jobs preview, lower grid)."""
from __future__ import annotations

from dash import html

from core.i18n import DEFAULT_LOCALE, module_subtitle, module_title, t
from core.registry import list_modules
from modules.shell.rail import ICON_BY_MODULE, icon


def _tile(module: str, slot: str, **kwargs):
    """Unique Dash id: pattern callbacks require distinct dicts per component."""
    return {"type": "home-tile", "module": module, "slot": slot}


def _stat_card(
    *,
    slot: str,
    tone: str,
    ico: str,
    trend: str,
    trend_cls: str,
    value: str,
    label: str,
    sub: str,
    spark,
) -> html.Button:
    return html.Button(
        type="button",
        className=f"stat-card {tone}",
        id=_tile("jobs", slot),
        n_clicks=0,
        children=[
            html.Div(
                className="stat-top",
                children=[
                    html.Span(icon(ico), className="stat-icon"),
                    html.Span(trend, className=("trend " + trend_cls).strip()),
                ],
            ),
            html.Strong(value),
            html.Span(label),
            html.Small(sub),
            spark,
        ],
    )


def build_home_layout(locale: str = DEFAULT_LOCALE):
    fa = locale == "fa"
    chev = "chevrons-left" if fa else "chevrons-right"

    # Extra product modules not in Figma primary nav — keep discoverable under overview.
    extra_ids = ("activity", "tables", "indexes", "docs", "disk", "waits")
    by_id = {m["id"]: m for m in list_modules()}
    extra_tiles = []
    for mid in extra_ids:
        m = by_id.get(mid)
        if not m:
            continue
        soon = m.get("status") == "soon"
        extra_tiles.append(
            html.Button(
                className="home-tile" + (" soon" if soon else " ready"),
                id=_tile(mid, f"extra-{mid}"),
                n_clicks=0,
                disabled=soon,
                children=[
                    html.Div(icon(ICON_BY_MODULE.get(mid, "home")), className="home-tile-icon"),
                    html.Div(module_title(mid, locale), className="home-tile-title"),
                    html.Div(module_subtitle(mid, locale), className="home-tile-sub"),
                    html.Div(
                        t("home.soon", locale) if soon else t("home.open", locale),
                        className="home-tile-cta",
                    ),
                ],
            )
        )

    spark_bars = html.Div(
        className="spark bars",
        children=[html.I(style={"height": f"{h}px"}) for h in (5, 8, 6, 12, 9, 15, 13, 18, 14, 20, 17, 22)],
    )
    spark_line = html.Div(className="spark line home-spark-placeholder")
    incident_mini = html.Div(
        className="incident-mini",
        children=[html.Span(), html.Span(), html.Span(), html.I(), html.I()],
    )

    stats = html.Section(
        className="stats-grid",
        children=[
            _stat_card(
                slot="stat-running",
                tone="running",
                ico="jobs",
                trend=t("home.stat.running_trend", locale),
                trend_cls="up",
                value="—",
                label=t("home.stat.running", locale),
                sub=t("home.stat.running_sub", locale),
                spark=spark_bars,
            ),
            _stat_card(
                slot="stat-success",
                tone="success",
                ico="home",
                trend=t("home.stat.success_trend", locale),
                trend_cls="",
                value="—",
                label=t("home.stat.success", locale),
                sub=t("home.stat.success_sub", locale),
                spark=spark_line,
            ),
            _stat_card(
                slot="stat-attention",
                tone="failed",
                ico="insights",
                trend=t("home.stat.attention_trend", locale),
                trend_cls="down",
                value="—",
                label=t("home.stat.attention", locale),
                sub=t("home.stat.attention_sub", locale),
                spark=incident_mini,
            ),
            _stat_card(
                slot="stat-duration",
                tone="duration",
                ico="waits",
                trend=t("home.stat.duration_trend", locale),
                trend_cls="",
                value="—",
                label=t("home.stat.duration", locale),
                sub=t("home.stat.duration_sub", locale),
                spark=spark_line,
            ),
        ],
    )

    incidents = [
        ("Sync_CRM_Customers", t("home.incident.1.msg", locale), t("home.incident.1.sev", locale), t("home.incident.1.age", locale), "critical"),
        ("Calculate_Daily_KPIs", t("home.incident.2.msg", locale), t("home.incident.2.sev", locale), t("home.incident.2.age", locale), "warning"),
        ("SQL-PROD-02", t("home.incident.3.msg", locale), t("home.incident.3.sev", locale), t("home.incident.3.age", locale), "info"),
    ]
    servers = [
        ("SQL-PROD-01", "Production", t("home.health.ok", locale), "12ms", "online", 48),
        ("SQL-PROD-02", "Production", t("home.health.slow", locale), "120ms", "slow", 76),
        ("SQL-REPORT-01", "Reporting", t("home.health.ok", locale), "18ms", "online", 61),
    ]

    return html.Div(
        id="home-shell-root",
        className="home-shell content",
        children=[
            html.Div(
                className="page-heading",
                children=[
                    html.Div(
                        children=[
                            html.Div(className="eyebrow", children=t("home.eyebrow", locale)),
                            html.H1(t("home.hero_title", locale)),
                            html.P(t("home.hero_sub", locale)),
                        ]
                    ),
                    html.Div(
                        className="heading-actions",
                        children=[
                            html.Button(
                                type="button",
                                className="button secondary",
                                id=_tile("jobs", "heading-jobs"),
                                n_clicks=0,
                                children=[icon("jobs"), t("home.cta.jobs", locale)],
                            ),
                            html.Button(
                                type="button",
                                className="button primary",
                                id=_tile("settings", "heading-settings"),
                                n_clicks=0,
                                children=[icon("settings"), t("home.cta.connections", locale)],
                            ),
                        ],
                    ),
                ],
            ),
            html.Section(
                className="freshness-banner",
                children=[
                    html.Div(className="freshness-icon", children=[icon("activity")]),
                    html.Div(
                        children=[
                            html.B(t("home.freshness_ok", locale)),
                            html.Span(t("home.freshness_sub", locale)),
                        ]
                    ),
                    html.Button(
                        type="button",
                        id=_tile("settings", "freshness-cta"),
                        n_clicks=0,
                        children=[t("home.freshness_cta", locale), icon(chev)],
                    ),
                ],
            ),
            stats,
            html.Section(
                className="workspace-card",
                children=[
                    html.Div(
                        className="section-head",
                        children=[
                            html.Div(
                                children=[
                                    html.H2(t("jobs.workspace_title", locale)),
                                    html.P(t("jobs.workspace_sub", locale)),
                                ]
                            ),
                            html.Div(
                                className="view-tabs",
                                children=[
                                    html.Button(
                                        type="button",
                                        className="active",
                                        id=_tile("jobs", "ws-tab-list"),
                                        n_clicks=0,
                                        children=[icon("jobs"), " ", t("jobs.tab.list", locale)],
                                    ),
                                    html.Button(
                                        type="button",
                                        id=_tile("jobs", "ws-tab-gantt"),
                                        n_clicks=0,
                                        children=[icon("activity"), " ", t("jobs.tab.gantt", locale)],
                                    ),
                                ],
                            ),
                        ],
                    ),
                    html.Div(
                        className="home-jobs-preview",
                        children=[
                            html.Div(
                                className="empty-state",
                                children=[
                                    icon("jobs"),
                                    html.B(t("home.jobs_preview_title", locale)),
                                    html.Span(t("home.jobs_preview_sub", locale)),
                                    html.Button(
                                        type="button",
                                        className="button primary",
                                        id=_tile("jobs", "preview-open"),
                                        n_clicks=0,
                                        children=t("home.cta.open_jobs", locale),
                                    ),
                                ],
                            )
                        ],
                    ),
                ],
            ),
            html.Div(
                className="lower-grid",
                children=[
                    html.Section(
                        className="workspace-card incidents-card",
                        children=[
                            html.Div(
                                className="section-head",
                                children=[
                                    html.Div(
                                        children=[
                                            html.H2(t("home.incidents_title", locale)),
                                            html.P(t("home.incidents_sub", locale)),
                                        ]
                                    ),
                                    html.Button(
                                        type="button",
                                        className="text-button",
                                        id=_tile("insights", "incidents-all"),
                                        n_clicks=0,
                                        children=[t("home.view_all", locale), icon(chev)],
                                    ),
                                ],
                            ),
                            *[
                                html.Button(
                                    type="button",
                                    className="incident-row",
                                    id=_tile("insights", f"incident-{i}"),
                                    n_clicks=0,
                                    children=[
                                        html.Span(className=f"incident-icon {sev}", children=[icon("insights")]),
                                        html.Div(children=[html.B(title), html.Span(msg)]),
                                        html.Div(
                                            className="incident-meta",
                                            children=[html.Em(sev_label, className=sev), html.Small(age)],
                                        ),
                                        icon(chev),
                                    ],
                                )
                                for i, (title, msg, sev_label, age, sev) in enumerate(incidents)
                            ],
                        ],
                    ),
                    html.Section(
                        className="workspace-card servers-card",
                        children=[
                            html.Div(
                                className="section-head",
                                children=[
                                    html.Div(
                                        children=[
                                            html.H2(t("home.servers_title", locale)),
                                            html.P(t("home.servers_sub", locale)),
                                        ]
                                    ),
                                    html.Button(
                                        type="button",
                                        className="text-button",
                                        id=_tile("settings", "servers-details"),
                                        n_clicks=0,
                                        children=[t("home.details", locale), icon(chev)],
                                    ),
                                ],
                            ),
                            *[
                                html.Div(
                                    className="server-row",
                                    children=[
                                        html.Span(className=f"server-icon {tone}", children=[icon("disk")]),
                                        html.Div(children=[html.B(name), html.Small(role)]),
                                        html.Div(
                                            className="server-load",
                                            children=[
                                                html.Span([t("home.agent_load", locale), " ", html.B(f"{load}%")]),
                                                html.I(children=html.Em(style={"width": f"{load}%"})),
                                            ],
                                        ),
                                        html.Span(
                                            className=f"health-badge {tone}",
                                            children=[html.I(), f"{status} · {latency}"],
                                        ),
                                    ],
                                )
                                for name, role, status, latency, tone, load in servers
                            ],
                        ],
                    ),
                ],
            ),
            html.Div(
                className="home-extra",
                children=[
                    html.Div(
                        className="sidebar-section-label home-extra-label",
                        children=t("home.extra_modules", locale),
                    ),
                    html.Div(className="home-grid", children=extra_tiles),
                ],
            )
            if extra_tiles
            else None,
        ],
    )
