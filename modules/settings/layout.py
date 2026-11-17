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
    """Dash html.Select does not support `value` in callback State — use Dropdown."""
    str_val = str(value) if value is not None else ""
    return dcc.Dropdown(
        id=select_id,
        className=className,
        options=[{"label": o["label"], "value": str(o["value"])} for o in options],
        value=str_val or None,
        clearable=False,
        searchable=False,
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


def build_settings_layout(locale: str = "en"):
    from core.i18n import normalize_locale, t

    locale = normalize_locale(locale)
    cfg = load_config()
    configured = is_configured()
    current_loc = normalize_locale(cfg.get("locale") or locale)
    return html.Div(
        className="settings-page",
        children=[
            html.Div(className="settings-page-hero", children=[
                html.H2(t("settings.title", locale)),
                html.P(t("settings.subtitle", locale)),
            ]),
            html.Div(className="settings-page-card", children=[
                html.Div(className="settings-layout", children=[
                    html.Div(className="settings-nav", role="tablist", children=[
                        html.Button(
                            t("settings.nav.connection", locale),
                            id="settings-nav-connection",
                            className="settings-nav-btn is-active",
                            n_clicks=0,
                            type="button",
                        ),
                        html.Button(
                            t("settings.nav.language", locale),
                            id="settings-nav-language",
                            className="settings-nav-btn",
                            n_clicks=0,
                            type="button",
                        ),
                        html.Button(
                            t("settings.nav.metrics", locale),
                            id="settings-nav-metrics",
                            className="settings-nav-btn",
                            n_clicks=0,
                            type="button",
                        ),
                        html.Button(
                            t("settings.nav.refresh", locale),
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
                                html.H3(t("settings.conn.title", locale), className="settings-section-title"),
                                html.P(
                                    t("settings.conn.hint", locale),
                                    className="settings-hint",
                                ),
                                html.Div(className="form-group", children=[
                                    html.Label(t("settings.conn.server", locale)),
                                    dcc.Input(
                                        id="setup-server", className="form-input", type="text",
                                        placeholder="192.168.1.10 یا SERVER\\INSTANCE",
                                        value=cfg["server"],
                                    ),
                                ]),
                                html.Div(className="form-group", children=[
                                    html.Label(t("settings.conn.database", locale)),
                                    dcc.Input(
                                        id="setup-database", className="form-input", type="text",
                                        placeholder="msdb", value=cfg["database"],
                                    ),
                                ]),
                                html.Div(className="form-group", children=[
                                    html.Label(t("settings.conn.user", locale)),
                                    dcc.Input(
                                        id="setup-user", className="form-input", type="text",
                                        placeholder="sql_login", value=cfg["user"],
                                    ),
                                ]),
                                html.Div(className="form-group", children=[
                                    html.Label(t("settings.conn.password", locale)),
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
                                    html.Label(t("settings.conn.driver", locale)),
                                    _native_select(
                                        "setup-driver",
                                        list_sql_driver_options(),
                                        cfg["driver"] or "17",
                                    ),
                                ]),
                                html.Div(className="permissions-box", children=[
                                    html.H3(t("settings.conn.perms", locale)),
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
                                        t("settings.conn.btn_test", locale), id="btn-test-connection",
                                        className="btn-primary", n_clicks=0,
                                    ),
                                    html.Button(
                                        t("settings.conn.btn_save", locale), id="btn-save-connection",
                                        className="btn-success", n_clicks=0,
                                    ),
                                ]),
                            ],
                        ),
                        html.Div(
                            id="settings-panel-language",
                            className="settings-panel hidden",
                            children=[
                                html.H3(t("settings.lang.title", locale), className="settings-section-title"),
                                html.P(t("settings.lang.help", locale), className="settings-hint"),
                                html.Div(className="lang-choice-row", children=[
                                    html.Button(
                                        t("settings.lang.en", locale),
                                        id={"type": "locale-chip", "value": "en"},
                                        n_clicks=0,
                                        type="button",
                                        className=(
                                            "activity-chip lang-chip"
                                            + (" active" if current_loc == "en" else "")
                                        ),
                                    ),
                                    html.Button(
                                        t("settings.lang.fa", locale),
                                        id={"type": "locale-chip", "value": "fa"},
                                        n_clicks=0,
                                        type="button",
                                        className=(
                                            "activity-chip lang-chip"
                                            + (" active" if current_loc == "fa" else "")
                                        ),
                                    ),
                                ]),
                                html.Div(id="locale-message", className="setup-message"),
                            ],
                        ),
                        html.Div(
                            id="settings-panel-metrics",
                            className="settings-panel hidden",
                            children=[
                                html.H3(t("settings.metrics.title", locale), className="settings-section-title"),
                                html.P(
                                    t("settings.metrics.hint", locale),
                                    className="settings-hint",
                                ),
                                html.Div(id="settings-metric-schedule", className="metric-schedule-editor"),
                                html.Div(id="metric-schedule-msg", className="setup-message"),
                                html.Div(className="settings-panel-actions", children=[
                                    html.Button(
                                        t("settings.metrics.btn_reset", locale),
                                        id="btn-reset-metric-schedule",
                                        className="btn-ghost",
                                        n_clicks=0,
                                    ),
                                    html.Button(
                                        t("settings.metrics.btn_save", locale),
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
                                html.H3(t("settings.refresh.title", locale), className="settings-section-title"),
                                html.P(
                                    t("settings.refresh.hint", locale),
                                    className="settings-hint",
                                ),
                                html.Div(className="form-group", children=[
                                    html.Label(t("settings.refresh.title", locale)),
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
                                        t("settings.refresh.btn_save", locale), id="btn-save-refresh",
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
