"""Activity callbacks — register from app.py."""
from __future__ import annotations

from datetime import datetime

from dash import ALL, Input, Output, State, ctx, html, no_update

from modules.activity.layout import (
    _append_pulse_sample,
    _interval_chips,
    render_blocking_table,
    render_health_strip,
    render_running_table,
    render_session_lookup,
)
from modules.activity.service import (
    fetch_blocking,
    fetch_running_now,
    fetch_server_resource_pulse,
    fetch_session_by_id,
)


def _loading_shell():
    return html.Div(className="activity-loading-inline", children=[
        html.Div(className="activity-loading-spinner"),
        html.Div("Loading…", className="activity-loading-text"),
    ])


def _clock_label(ts) -> str:
    """Short clock so each auto-refresh is obvious (HH:MM:SS)."""
    if isinstance(ts, datetime):
        return ts.strftime("%H:%M:%S")
    raw = (str(ts) if ts not in (None, "") else "").strip()
    if "T" in raw:
        # 2026-08-01T15:34:35+03:30 → 15:34:35
        try:
            return raw.split("T", 1)[1][:8]
        except Exception:
            pass
    if len(raw) >= 8 and raw[2] == ":" and raw[5] == ":":
        return raw[:8]
    return datetime.now().strftime("%H:%M:%S")


def _activity_meta(tab: str, ts, rows) -> html.Div:
    clock = _clock_label(ts)
    return html.Div(className="activity-meta", children=[
        html.Span(f"Tab: {tab}", className="activity-meta-part"),
        html.Span("·", className="activity-meta-sep"),
        html.Span("Updated", className="activity-meta-lbl"),
        html.Span(clock, className="activity-meta-clock"),
        html.Span("·", className="activity-meta-sep"),
        html.Span(f"rows: {rows}", className="activity-meta-part num-ltr"),
    ])


def register_activity_callbacks(app):
    # Overlay ONLY for explicit user fetch — never on tab/module/WS.
    # Tab switch already sets loading serverside; listening to store-activity-tab here
    # races AFTER load_activity and can leave the spinner stuck forever.
    app.clientside_callback(
        """
        function(n_refresh, n_lookup, n_submit) {
            const ctx = dash_clientside.callback_context;
            if (!ctx || !ctx.triggered || !ctx.triggered.length) {
                return window.dash_clientside.no_update;
            }
            const id = (ctx.triggered[0].prop_id || '').split('.')[0];
            if (id === 'btn-activity-refresh' || id === 'btn-session-lookup'
                || id === 'input-session-id') {
                return 'activity-loading';
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("activity-loading", "className", allow_duplicate=True),
        Input("btn-activity-refresh", "n_clicks"),
        Input("btn-session-lookup", "n_clicks"),
        Input("input-session-id", "n_submit"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("store-activity-tab", "data"),
        Output("activity-tab-running", "className"),
        Output("activity-tab-blocking", "className"),
        Output("activity-tab-lookup", "className"),
        Output("session-lookup-bar", "style"),
        Output("activity-loading", "className", allow_duplicate=True),
        Input("activity-tab-running", "n_clicks"),
        Input("activity-tab-blocking", "n_clicks"),
        Input("activity-tab-lookup", "n_clicks"),
        State("store-activity-tab", "data"),
        prevent_initial_call=True,
    )
    def switch_activity_tab(n_run, n_block, n_lookup, current):
        triggered = ctx.triggered_id
        tab = current or "running"
        if triggered == "activity-tab-blocking":
            tab = "blocking"
        elif triggered == "activity-tab-running":
            tab = "running"
        elif triggered == "activity-tab-lookup":
            tab = "lookup"
        run_cls = "activity-tab active" if tab == "running" else "activity-tab"
        blk_cls = "activity-tab active" if tab == "blocking" else "activity-tab"
        look_cls = "activity-tab active" if tab == "lookup" else "activity-tab"
        bar_style = {"display": "flex"} if tab == "lookup" else {"display": "none"}
        return tab, run_cls, blk_cls, look_cls, bar_style, "activity-loading"

    @app.callback(
        Output("store-activity-tab", "data", allow_duplicate=True),
        Output("input-session-id", "value"),
        Output("activity-tab-running", "className", allow_duplicate=True),
        Output("activity-tab-blocking", "className", allow_duplicate=True),
        Output("activity-tab-lookup", "className", allow_duplicate=True),
        Output("session-lookup-bar", "style", allow_duplicate=True),
        Output("activity-loading", "className", allow_duplicate=True),
        Input({"type": "blk-lookup-spid", "sid": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_lookup_from_blocking_spid(clicks):
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or triggered.get("type") != "blk-lookup-spid":
            return (no_update,) * 7
        if not any(clicks or []):
            return (no_update,) * 7
        sid = str(triggered.get("sid") or "").strip()
        if not sid:
            return (no_update,) * 7
        return (
            "lookup",
            sid,
            "activity-tab",
            "activity-tab",
            "activity-tab active",
            {"display": "flex"},
            "activity-loading",
        )

    @app.callback(
        Output("store-activity-running", "data"),
        Output("store-activity-blocking", "data"),
        Output("store-activity-lookup", "data"),
        Output("store-lookup-pulse-series", "data"),
        Output("activity-health-strip", "children"),
        Output("activity-body", "children"),
        Output("activity-last-refresh", "children"),
        Output("btn-activity-refresh", "className"),
        Output("activity-loading", "className"),
        Input("btn-activity-refresh", "n_clicks"),
        Input("interval-activity", "n_intervals"),
        Input("store-module", "data"),
        Input("store-activity-tab", "data"),
        Input("btn-session-lookup", "n_clicks"),
        Input("input-session-id", "n_submit"),
        Input("store-ws-activity-tick", "data"),
        State("store-paused", "data"),
        State("input-session-id", "value"),
        State("store-activity-lookup", "data"),
        State("store-lookup-pulse-series", "data"),
        prevent_initial_call=False,
    )
    def load_activity(
        n_refresh, n_int, module, tab, n_lookup, n_submit, ws_tick, paused, session_id, prev_lookup, pulse_series,
    ):
        if module != "activity":
            return (no_update,) * 9

        triggered = ctx.triggered_id
        if triggered in ("interval-activity", "store-ws-activity-tick") and paused:
            return (no_update,) * 9

        tab = tab or "running"
        store_run = store_blk = store_look = no_update
        store_pulse = no_update

        if tab == "lookup":
            sid_raw = "" if session_id in (None, "") else str(session_id).strip()
            # store-activity-tab: Blocking SPID → Lookup sets sid + tab together
            should_fetch = triggered in (
                "btn-session-lookup",
                "btn-activity-refresh",
                "input-session-id",
                "interval-activity",
                "store-ws-activity-tick",
                "store-activity-tab",
            ) and sid_raw
            if should_fetch:
                result = fetch_session_by_id(sid_raw)
                store_look = result
            elif triggered == "store-activity-tab" and not prev_lookup:
                result = None
            else:
                result = prev_lookup

            # Charts only while a SessionId is actively looked up
            series = []
            if sid_raw and result and result.get("status") == "ok" and (result.get("rows") or []):
                try:
                    pulse = fetch_server_resource_pulse()
                except Exception:
                    pulse = {"status": "error", "summary": {}}
                series = _append_pulse_sample(
                    pulse_series, pulse, session_row=result["rows"][0],
                )
                store_pulse = series
            elif not sid_raw:
                store_pulse = []

            body = render_session_lookup(result, pulse_series=series)
            summary = (result or {}).get("summary") or {}
            severity = (result or {}).get("severity") or "healthy"
            strip = render_health_strip(summary, severity, tab="lookup")
            ts = (result or {}).get("timestamp") or datetime.now().isoformat(timespec="seconds")
            rows = (result or {}).get("meta", {}).get("row_count", 0) if result else 0
            meta = _activity_meta("lookup", ts, rows)
        elif tab == "blocking":
            # WS + interval both refresh blocking
            result = fetch_blocking()
            body = render_blocking_table(result)
            store_blk = result
            strip = render_health_strip(
                result.get("summary") or {},
                result.get("severity") or "healthy",
                tab=tab,
            )
            ts = result.get("timestamp") or datetime.now().isoformat(timespec="seconds")
            meta = _activity_meta(
                tab,
                ts,
                (result.get("meta") or {}).get("row_count", 0),
            )
        else:
            result = fetch_running_now()
            body = render_running_table(result)
            store_run = result
            strip = render_health_strip(
                result.get("summary") or {},
                result.get("severity") or "healthy",
                tab=tab,
            )
            ts = result.get("timestamp") or datetime.now().isoformat(timespec="seconds")
            meta = _activity_meta(
                tab,
                ts,
                (result.get("meta") or {}).get("row_count", 0),
            )

        refresh_cls = (
            "activity-ctrl-btn is-refresh is-active"
            if triggered in ("btn-activity-refresh", "btn-session-lookup", "input-session-id")
            else "activity-ctrl-btn is-refresh"
        )
        # Always clear overlay when data is painted — WS/interval used to return
        # no_update and could leave a spinner stuck after a tab/lookup race.
        loading_cls = "activity-loading hidden"
        return (
            store_run, store_blk, store_look, store_pulse,
            strip, body, meta, refresh_cls, loading_cls,
        )

    @app.callback(
        Output("activity-refresh-interval", "data"),
        Output("activity-interval-chips", "children"),
        Input({"type": "activity-interval-chip", "value": ALL}, "n_clicks"),
        State("activity-refresh-interval", "data"),
        prevent_initial_call=True,
    )
    def pick_interval(clicks, current):
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            return no_update, no_update
        value = str(triggered.get("value", current or "10"))
        if value == "5":
            value = "10"
        return value, _interval_chips(value)

    @app.callback(
        Output("interval-activity", "interval"),
        Output("interval-activity", "disabled"),
        Input("activity-refresh-interval", "data"),
        Input("store-paused", "data"),
        Input("store-module", "data"),
        Input("store-activity-tab", "data"),
        prevent_initial_call=False,
    )
    def tune_activity_interval(value, paused, module, tab):
        """Honor selected interval exactly (min 10s; 5s removed). WS still ticks live."""
        try:
            sec = int(value or "10")
        except (TypeError, ValueError):
            sec = 10
        if sec == 5:
            sec = 10
        if module != "activity" or paused or sec <= 0:
            return 3600 * 1000, True
        return sec * 1000, False

    @app.callback(
        Output("activity-sql-modal", "className"),
        Output("activity-sql-modal-title", "children"),
        Output("activity-sql-modal-body", "children"),
        Output("store-activity-sql-copy-text", "data"),
        Output("btn-activity-sql-copy", "className"),
        Output("sql-copy-toast", "children"),
        Input({"type": "activity-sql-open", "kind": ALL, "sid": ALL, "i": ALL}, "n_clicks"),
        Input("btn-activity-sql-close", "n_clicks"),
        State({"type": "activity-sql-payload", "kind": ALL, "sid": ALL, "i": ALL}, "children"),
        State({"type": "activity-sql-payload", "kind": ALL, "sid": ALL, "i": ALL}, "id"),
        prevent_initial_call=True,
    )
    def toggle_sql_modal(open_clicks, close_n, payloads, payload_ids):
        import json
        from dash import html as _html

        triggered = ctx.triggered_id
        if triggered == "btn-activity-sql-close":
            return (
                "modal-overlay hidden", no_update, no_update, "",
                "btn-ghost sql-copy-btn", "",
            )
        if not isinstance(triggered, dict) or triggered.get("type") != "activity-sql-open":
            return (no_update,) * 6
        if not any(open_clicks or []):
            return (no_update,) * 6
        sid = str(triggered.get("sid"))
        kind = triggered.get("kind")
        idx = triggered.get("i")
        raw = ""
        for pid, text in zip(payload_ids or [], payloads or []):
            if (
                isinstance(pid, dict)
                and str(pid.get("sid")) == sid
                and pid.get("kind") == kind
                and pid.get("i") == idx
            ):
                raw = text or ""
                break

        statement = ""
        batch = ""
        copy_text = ""
        progress = {}
        pct = None
        cmd = None
        sess_status = None
        has_active = True
        data = {}
        if isinstance(raw, str) and raw.strip().startswith("{"):
            try:
                data = json.loads(raw)
                statement = (data.get("statement") or "").strip()
                batch = (data.get("batch") or "").strip()
                copy_text = (data.get("copy") or statement or batch).strip()
                progress = data.get("progress") or {}
                pct = data.get("percent_complete")
                cmd = data.get("command")
                sess_status = data.get("status")
                has_active = bool(data.get("has_active_request", True))
            except Exception:
                data = {}
                batch = raw.strip()
                copy_text = batch
        else:
            batch = (raw or "").strip() if isinstance(raw, str) else ""
            copy_text = batch

        if kind == "stmt":
            from modules.activity.layout import (
                _highlight_batch_nodes,
                _render_row_metric_boxes,
                _command_action_tag,
                _sql_statement_panel,
                extract_dml_target,
                extract_index_op,
                render_index_op_panel,
                render_request_ended_note,
            )

            title = f"Statement now — Session {sid}"
            src_sql = statement or batch
            index_op = extract_index_op(src_sql)
            target = extract_dml_target(src_sql)
            # For statement panel emphasize: index table wins over DML target
            panel_target = None
            if index_op and index_op.get("table"):
                panel_target = {
                    "verb": index_op.get("action_label") or "INDEX",
                    "table": index_op["table"],
                    "table_short": index_op.get("table_short") or index_op["table"].split(".")[-1],
                }
            elif target:
                panel_target = target
            tag = _command_action_tag(cmd, src_sql, is_head=False)
            metrics = _render_row_metric_boxes(
                progress,
                percent_complete=pct,
                status=sess_status,
                has_active_request=has_active,
            )
            # Target / index summary box in metric strip
            target_box = None
            if index_op and index_op.get("table"):
                target_box = _html.Div(
                    className="progress-stat is-hero is-target is-index",
                    title=index_op.get("index_name") or index_op["table"],
                    children=[
                        _html.Span("Index op", className="progress-stat-lbl"),
                        _html.Span(
                            index_op.get("action_label") or "INDEX",
                            className="target-table-verb",
                        ),
                        _html.Span(
                            index_op.get("index_name") or index_op.get("table_short") or "—",
                            className="progress-stat-val num-ltr target-table-val",
                        ),
                        _html.Span(
                            index_op["table"],
                            className="target-table-full num-ltr",
                        ),
                    ],
                )
            elif target and target.get("table"):
                short = target.get("table_short") or target["table"].split(".")[-1]
                target_box = _html.Div(
                    className="progress-stat is-hero is-target",
                    title=target["table"],
                    children=[
                        _html.Span("Target table", className="progress-stat-lbl"),
                        _html.Span(
                            target.get("verb") or "DML",
                            className="target-table-verb",
                        ),
                        _html.Span(short, className="progress-stat-val num-ltr target-table-val"),
                        _html.Span(
                            target["table"],
                            className="target-table-full num-ltr",
                        ),
                    ],
                )
            if target_box is not None:
                if metrics is not None:
                    metrics = _html.Div(
                        className="progress-stats is-hero-strip",
                        children=[target_box, *(metrics.children or [])],
                    )
                else:
                    metrics = _html.Div(
                        className="progress-stats is-hero-strip",
                        children=[target_box],
                    )

            sql_object = (data.get("sql_object") or "").strip() if isinstance(data, dict) else ""
            finished = (
                not has_active
                and (str(sess_status or "").strip().lower() in ("sleeping", "dormant", ""))
            )
            ended_row = None
            if finished:
                end_ts = (data.get("last_request_end_time") or "") if isinstance(data, dict) else ""
                open_tran = int((data.get("open_tran_count") or 0) if isinstance(data, dict) else 0)
                ended_row = render_request_ended_note(end_ts=end_ts, open_tran=open_tran)

            batch_label = "Full batch / SP text (active part highlighted)"
            if sql_object:
                batch_label = f"Full batch / SP — {sql_object}"

            index_panel = render_index_op_panel(index_op)

            body = _html.Div(className="sql-modal-rich", children=[
                ended_row,
                _html.Div(className="sql-modal-action-row", children=[
                    _html.Span("Action", className="sql-modal-section-title"),
                    tag,
                ]),
                index_panel,
                metrics,
                _html.Div("Current statement", className="sql-modal-section-title"),
                _sql_statement_panel(statement, target=panel_target),
                _html.Div(batch_label, className="sql-modal-section-title"),
                _html.Div(className="sql-batch-panel", children=[
                    _highlight_batch_nodes(batch, statement),
                ]),
            ])
            copy_text = batch or statement or "(no statement)"
        else:
            title = f"SQL — Session {sid}"
            body = _html.Pre(copy_text or "(no SQL text)", className="sql-modal-pre")
            copy_text = copy_text or "(no SQL text)"

        return (
            "modal-overlay",
            title,
            body,
            copy_text,
            "btn-ghost sql-copy-btn",
            "",
        )
