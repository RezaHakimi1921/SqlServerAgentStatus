"""Tables & Growth callbacks."""
from __future__ import annotations

from dash import Input, Output, State, ctx, no_update

from core.logging_setup import get_logger
from core.providers.sqlserver_provider import get_provider
from modules.tables.layout import render_tables_body, render_tables_meta
from modules.tables.service import build_tables_payload

log = get_logger("sqlmonitor.tables.ui")


def _load_payload() -> dict:
    raw = get_provider().get_table_growth_snapshot()
    return build_tables_payload(raw)


def register_tables_callbacks(app):
    app.clientside_callback(
        """
        function(n_refresh, n_capture, module) {
            const ctx = dash_clientside.callback_context;
            if (!ctx || !ctx.triggered || !ctx.triggered.length) {
                return window.dash_clientside.no_update;
            }
            if (module !== 'tables') {
                return window.dash_clientside.no_update;
            }
            const id = (ctx.triggered[0].prop_id || '').split('.')[0];
            if (id === 'btn-tables-refresh' || id === 'btn-tables-capture' || id === 'store-module') {
                return 'activity-loading';
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("tables-loading", "className", allow_duplicate=True),
        Input("btn-tables-refresh", "n_clicks"),
        Input("btn-tables-capture", "n_clicks"),
        Input("store-module", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("store-tables", "data"),
        Output("tables-body", "children"),
        Output("tables-meta", "children"),
        Output("tables-loading", "className"),
        Input("btn-tables-refresh", "n_clicks"),
        Input("btn-tables-capture", "n_clicks"),
        Input("store-module", "data"),
        State("store-paused", "data"),
        prevent_initial_call=False,
    )
    def load_tables(_refresh, _capture, module, _paused):
        if module != "tables":
            return no_update, no_update, no_update, "activity-loading hidden"

        capture_msg = None
        triggered = ctx.triggered_id
        try:
            if triggered == "btn-tables-capture":
                result = get_provider().capture_objsize_history()
                if result.get("ok"):
                    capture_msg = (
                        f"Captured {result.get('rows_captured') or 0} rows "
                        f"({result.get('source') or '?'})"
                    )
                else:
                    capture_msg = f"Capture failed: {result.get('error') or 'unknown'}"
            payload = _load_payload()
        except Exception as ex:
            log.exception("load tables failed")
            from dash import html

            err = html.Div(className="state-box state-error", children=[
                html.H3("Could not load Tables & Growth"),
                html.P(str(ex)),
            ])
            return None, err, str(ex), "activity-loading hidden"

        return (
            payload,
            render_tables_body(payload),
            render_tables_meta(payload, capture_msg),
            "activity-loading hidden",
        )
