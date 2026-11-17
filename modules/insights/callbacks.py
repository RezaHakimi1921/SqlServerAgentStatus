"""Today's Insights callbacks."""
from __future__ import annotations

from datetime import datetime

from dash import ALL, Input, Output, State, ctx, html, no_update

from core.insight.events import fetch_todays_insights, set_insight_feedback
from core.insight.rules import enrich_insight_rows, evaluate_rules
from core.logging_setup import get_logger
from modules.insights.layout import render_insights_health, render_insights_list

log = get_logger("sqlmonitor.insights.ui")


def _rows_for_ui():
    rows = fetch_todays_insights(include_dismissed=False)
    return enrich_insight_rows(rows)


def _serialize_insight_rows(rows: list) -> list:
    payload = []
    for r in rows:
        item = dict(r)
        for k in ("created_at", "first_seen_at", "last_seen_at"):
            v = item.get(k)
            if hasattr(v, "isoformat"):
                item[k] = v.isoformat(sep=" ", timespec="seconds")
        ej = item.get("evidence_json")
        if ej is not None and not isinstance(ej, str):
            item["evidence_json"] = str(ej)
        payload.append(item)
    return payload


def register_insights_callbacks(app):
    # Immediate overlay on enter / manual refresh (not on silent 30s poll)
    app.clientside_callback(
        """
        function(n_refresh, module) {
            const ctx = dash_clientside.callback_context;
            if (!ctx || !ctx.triggered || !ctx.triggered.length) {
                return window.dash_clientside.no_update;
            }
            if (module !== 'insights') {
                return window.dash_clientside.no_update;
            }
            const id = (ctx.triggered[0].prop_id || '').split('.')[0];
            if (id === 'interval-insights') {
                return window.dash_clientside.no_update;
            }
            return 'activity-loading';
        }
        """,
        Output("insights-loading", "className", allow_duplicate=True),
        Input("btn-insights-refresh", "n_clicks"),
        Input("store-module", "data"),
        prevent_initial_call=True,
    )

    # interval-insights.disabled is owned by app.disable_intervals (module + pause).

    @app.callback(
        Output("store-insights", "data"),
        Output("insights-health-strip", "children"),
        Output("insights-body", "children"),
        Output("insights-meta", "children"),
        Output("insights-loading", "className"),
        Input("btn-insights-refresh", "n_clicks"),
        Input("interval-insights", "n_intervals"),
        Input("store-module", "data"),
        State("store-paused", "data"),
        State("store-locale", "data"),
        prevent_initial_call=False,
    )
    def load_insights(_refresh, _n, module, paused, locale):
        if module != "insights":
            return no_update, no_update, no_update, no_update, "activity-loading hidden"

        triggered = ctx.triggered_id
        if triggered == "interval-insights" and paused:
            return no_update, no_update, no_update, no_update, no_update

        try:
            # Rule evaluation is scheduler's job. Manual Refresh re-evaluates once.
            # Interval / first paint only read Metric Store (architect: avoid duplicate DMV load).
            if triggered == "btn-insights-refresh":
                evaluate_rules()
            rows = _rows_for_ui()
        except Exception as ex:
            log.exception("load insights failed")
            err_body = html.Div(className="state-box state-error", children=[
                html.Div("!", className="state-icon"),
                html.H3("Could not load insights"),
                html.P(str(ex)),
            ])
            return (
                None,
                render_insights_health([], locale),
                err_body,
                f"Error · {datetime.now().strftime('%H:%M:%S')}",
                "activity-loading hidden",
            )

        payload = _serialize_insight_rows(rows)
        ts = datetime.now().strftime("%H:%M:%S")
        meta = f"Today's Insights  ·  {len(rows)} item(s)  ·  refreshed {ts}"
        loading_cls = (
            no_update if triggered == "interval-insights" else "activity-loading hidden"
        )
        return (
            payload,
            render_insights_health(rows, locale),
            render_insights_list(rows, locale),
            meta,
            loading_cls,
        )

    @app.callback(
        Output("store-insights", "data", allow_duplicate=True),
        Output("insights-body", "children", allow_duplicate=True),
        Output("insights-health-strip", "children", allow_duplicate=True),
        Input({"type": "insight-dismiss", "id": ALL}, "n_clicks"),
        State("store-locale", "data"),
        prevent_initial_call=True,
    )
    def dismiss_insight(clicks, locale):
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or not any(clicks or []):
            return no_update, no_update, no_update
        iid = triggered.get("id")
        try:
            set_insight_feedback(int(iid), 0)
            rows = _rows_for_ui()
        except Exception:
            log.exception("dismiss insight failed")
            return no_update, no_update, no_update
        return (
            _serialize_insight_rows(rows),
            render_insights_list(rows, locale),
            render_insights_health(rows, locale),
        )

    @app.callback(
        Output("store-module", "data", allow_duplicate=True),
        Output("store-activity-tab", "data", allow_duplicate=True),
        Input({"type": "insight-goto", "target": ALL, "id": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def insight_goto(clicks):
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or not any(clicks or []):
            return no_update, no_update
        target = triggered.get("target")
        if target == "activity-blocking":
            return "activity", "blocking"
        if target == "jobs":
            return "jobs", no_update
        return no_update, no_update
