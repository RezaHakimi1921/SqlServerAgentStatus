"""Settings as a full app module (not a modal)."""
from __future__ import annotations

from dash import dcc, html

from config import is_configured, list_sql_driver_options, load_config
from core.insight.registry import DEFAULT_METRICS
from core.insight.schedule import load_schedule, table_exists

REFRESH_OPTIONS = [
    {"label": "1 min", "value": "1"},
    {"label": "5 min", "value": "5"},
    {"label": "10 min", "value": "10"},
    {"label": "30 min", "value": "30"},
    {"label": "60 min", "value": "60"},
]


def _native_select(select_id, options, value, className="form-input native-select"):
    str_val = str(value) if value is not None else ""
    return html.Select(
        id=select_id,
        className=className,
        children=[
            html.Option(
                opt["label"],
                value=str(opt["value"]),
                selected=(str(opt["value"]) == str_val),
            )
            for opt in options
        ],
    )


def render_metric_schedule_editor():
    """Settings UI rows for per-metric capture intervals."""
    try:
        sched = load_schedule(use_cache=False)
    except Exception:
        sched = {}

    parts = []
    if not table_exists():
        parts.append(html.Div(
            className="metric-schedule-warn",
            children=[
                html.Strong("جدول insight.metric_schedule هنوز ساخته نشده."),
                html.P(
                    "با کاربر dbo روی SmartMonitorDB این اسکریپت را اجرا کنید، "
                    "سپس به لاگین برنامه GRANT بدهید:",
                    className="metric-schedule-warn-text",
                ),
                html.Code(
                    "phase2/queries/insight-metric-schedule.sql",
                    className="metric-schedule-code",
                ),
            ],
        ))

    for m in DEFAULT_METRICS:
        row = sched.get(m.name) or {}
        interval = int(row.get("interval_sec") or m.interval_sec)
        enabled = bool(row.get("enabled", True))
        parts.append(html.Div(className="metric-schedule-row", children=[
            html.Div(className="metric-schedule-info", children=[
                html.Code(m.name, className="metric-schedule-name"),
                html.Span(m.description, className="metric-schedule-desc"),
                html.Span(f"scope: {m.scope}", className="metric-schedule-scope"),
            ]),
            dcc.Input(
                id={"type": "metric-interval", "name": m.name},
                type="number",
                min=10,
                step=5,
                value=interval,
                className="form-input metric-interval-input",
            ),
            html.Span("sec", className="metric-schedule-unit"),
            dcc.Checklist(
                id={"type": "metric-enabled", "name": m.name},
                options=[{"label": "On", "value": "1"}],
                value=["1"] if enabled else [],
                className="metric-enabled-check",
            ),
        ]))
    return parts


def build_settings_layout():
    cfg = load_config()
    configured = is_configured()
    return html.Div(
        className="settings-page",
        children=[
            html.Div(className="settings-page-hero", children=[
                html.H2("Settings"),
                html.P("Connection, Insight metric intervals, and Jobs auto-refresh — each in its own section."),
            ]),
            html.Div(className="settings-page-card", children=[
                html.Div(className="settings-layout", children=[
                    html.Div(className="settings-nav", role="tablist", children=[
                        html.Button(
                            "Connection",
                            id="settings-nav-connection",
                            className="settings-nav-btn is-active",
                            n_clicks=0,
                            type="button",
                        ),
                        html.Button(
                            "Insight metrics",
                            id="settings-nav-metrics",
                            className="settings-nav-btn",
                            n_clicks=0,
                            type="button",
                        ),
                        html.Button(
                            "Auto refresh",
                            id="settings-nav-refresh",
                            className="settings-nav-btn",
                            n_clicks=0,
                            type="button",
                        ),
                    ]),
                    html.Div(className="settings-panels", children=[
                        html.Div(
                            id="settings-panel-connection",
                            className="settings-panel",
                            children=[
                                html.H3("SQL Server connection", className="settings-section-title"),
                                html.P(
                                    "Password is stored in Windows Credential Manager.",
                                    className="settings-hint",
                                ),
                                html.Div(className="form-group", children=[
                                    html.Label("Server / IP"),
                                    dcc.Input(
                                        id="setup-server", className="form-input", type="text",
                                        placeholder="192.168.1.10 یا SERVER\\INSTANCE",
                                        value=cfg["server"],
                                    ),
                                ]),
                                html.Div(className="form-group", children=[
                                    html.Label("Database"),
                                    dcc.Input(
                                        id="setup-database", className="form-input", type="text",
                                        placeholder="msdb", value=cfg["database"],
                                    ),
                                ]),
                                html.Div(className="form-group", children=[
                                    html.Label("Username"),
                                    dcc.Input(
                                        id="setup-user", className="form-input", type="text",
                                        placeholder="sql_login", value=cfg["user"],
                                    ),
                                ]),
                                html.Div(className="form-group", children=[
                                    html.Label("Password"),
                                    dcc.Input(
                                        id="setup-password", className="form-input", type="password",
                                        placeholder=(
                                            "New password (only to change)"
                                            if configured else "SQL Server password"
                                        ),
                                        value="",
                                        autoComplete="new-password",
                                    ),
                                    html.P(
                                        (
                                            "Password is stored in Credential Manager — leave blank to keep the current password."
                                            if configured else
                                            "On first save, enter the password here to store it in Credential Manager."
                                        ),
                                        className="settings-hint",
                                    ),
                                ]),
                                html.Div(className="form-group", children=[
                                    html.Label("ODBC Driver"),
                                    _native_select(
                                        "setup-driver",
                                        list_sql_driver_options(),
                                        cfg["driver"] or "17",
                                    ),
                                ]),
                                html.Div(className="permissions-box", children=[
                                    html.H3("Required permissions"),
                                    html.Ul([
                                        html.Li("SELECT on msdb.dbo.sysjobs"),
                                        html.Li("SELECT on msdb.dbo.sysjobsteps"),
                                        html.Li("SELECT on msdb.dbo.sysjobhistory"),
                                        html.Li("SELECT on msdb.dbo.sysjobactivity"),
                                        html.Li("VIEW SERVER STATE (for Activity Monitor)"),
                                    ]),
                                ]),
                                html.Div(id="setup-message", className="setup-message"),
                                html.Div(className="settings-panel-actions", children=[
                                    html.Button(
                                        "Test connection", id="btn-test-connection",
                                        className="btn-primary", n_clicks=0,
                                    ),
                                    html.Button(
                                        "Save connection", id="btn-save-connection",
                                        className="btn-success", n_clicks=0,
                                    ),
                                ]),
                            ],
                        ),
                        html.Div(
                            id="settings-panel-metrics",
                            className="settings-panel hidden",
                            children=[
                                html.H3("Insight metric intervals", className="settings-section-title"),
                                html.P(
                                    "How often each metric is written to SmartMonitorDB. "
                                    "Minimum 10 seconds. Saved in insight.metric_schedule.",
                                    className="settings-hint",
                                ),
                                html.Div(id="settings-metric-schedule", className="metric-schedule-editor"),
                                html.Div(id="metric-schedule-msg", className="setup-message"),
                                html.Div(className="settings-panel-actions", children=[
                                    html.Button(
                                        "Reset to defaults",
                                        id="btn-reset-metric-schedule",
                                        className="btn-ghost",
                                        n_clicks=0,
                                    ),
                                    html.Button(
                                        "Save metric intervals",
                                        id="btn-save-metric-schedule",
                                        className="btn-primary",
                                        n_clicks=0,
                                    ),
                                ]),
                            ],
                        ),
                        html.Div(
                            id="settings-panel-refresh",
                            className="settings-panel hidden",
                            children=[
                                html.H3("Auto refresh", className="settings-section-title"),
                                html.P(
                                    "How often Jobs reloads data from SQL Server.",
                                    className="settings-hint",
                                ),
                                html.Div(className="form-group", children=[
                                    html.Label("Jobs refresh interval"),
                                    html.Div(
                                        id="settings-refresh-chips",
                                        className="activity-chip-row settings-refresh-chips",
                                        children=[
                                            html.Button(
                                                opt["label"],
                                                id={"type": "settings-refresh-chip", "value": opt["value"]},
                                                className=(
                                                    "activity-chip active"
                                                    if str(opt["value"]) == str(cfg.get("refresh_minutes", 5))
                                                    else "activity-chip"
                                                ),
                                                n_clicks=0,
                                                type="button",
                                            )
                                            for opt in REFRESH_OPTIONS
                                        ],
                                    ),
                                    dcc.Store(
                                        id="setup-refresh-interval",
                                        data=str(cfg.get("refresh_minutes", 5)),
                                    ),
                                ]),
                                html.Div(id="setup-refresh-message", className="setup-message"),
                                html.Div(className="settings-panel-actions", children=[
                                    html.Button(
                                        "Save refresh", id="btn-save-refresh",
                                        className="btn-primary", n_clicks=0,
                                    ),
                                ]),
                            ],
                        ),
                    ]),
                ]),
                dcc.Store(id="store-settings-tab", data="connection"),
            ]),
        ],
    )
