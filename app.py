import statistics
import json
from datetime import datetime

import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objects as go

import db
import calculations

app = dash.Dash(__name__, title="SQL Agent Monitor", suppress_callback_exceptions=True)

app.layout = html.Div([
    dcc.Store(id="selected-job-store"),
    dcc.Interval(id="interval", interval=5000, n_intervals=0),

    # Header
    html.Div([
        html.H2("🖥 SQL Server Agent Monitor", style={"margin": 0, "color": "#e2e8f0"}),
        html.Span(id="last-update", style={"color": "#4a5568", "fontSize": "0.85rem"}),
    ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center",
              "padding": "16px 24px", "borderBottom": "1px solid #2d3250", "backgroundColor": "#161929"}),

    # Body
    html.Div([
        html.Div(id="kpi-section", style={"marginBottom": "24px"}),

        html.Div([
            html.Div("⚡ در حال اجرا", className="section-title"),
            html.Div(id="running-section"),
        ], style={"marginBottom": "24px"}),

        html.Div([
            html.Div("📅 Timeline اجراها", className="section-title"),
            dcc.Graph(id="gantt-chart", config={"displayModeBar": False}),
        ], style={"marginBottom": "24px"}),

        html.Div([
            html.Div("📋 همه جاب‌ها", className="section-title"),
            html.Div(id="jobs-table"),
        ], style={"marginBottom": "24px"}),

        html.Div(id="drilldown-section"),
    ], style={"padding": "24px", "maxWidth": "1400px", "margin": "0 auto"}),
])


# ── KPI Cards ─────────────────────────────────────────────────────────────────
@app.callback(
    Output("kpi-section", "children"),
    Output("last-update", "children"),
    Input("interval", "n_intervals"),
)
def update_kpi(n):
    try:
        history = db.get_job_history()
        running = db.get_running_jobs()
        jobs = db.get_all_jobs()
        stats = calculations.calc_job_stats(history)
        latest = {}
        for h in sorted(history, key=lambda x: (x["run_date"], x["run_time"])):
            latest[h["job_id"]] = h
        n_failed = sum(1 for h in latest.values() if h["run_status"] == 0)
        n_success = sum(1 for h in latest.values() if h["run_status"] == 1)
        n_slow = sum(
            1 for r in running
            if calculations.calc_progress(r["job_id"], r["start_execution_date"], stats)["is_slow"]
        )
        items = [
            ("کل جاب‌ها", len(jobs), "kpi-total"),
            ("در حال اجرا", len(running), "kpi-running"),
            ("موفق (آخرین)", n_success, "kpi-success"),
            ("ناموفق (آخرین)", n_failed, "kpi-failed"),
            ("کند الان", n_slow, "kpi-slow"),
        ]
        cards = [
            html.Div([
                html.Div(lbl, className="kpi-label"),
                html.Div(str(val), className=f"kpi-number {cls}"),
            ], className="kpi-card")
            for lbl, val, cls in items
        ]
        grid = html.Div(cards, style={
            "display": "grid", "gridTemplateColumns": "repeat(5,1fr)", "gap": "16px"
        })
        ts = f"آخرین بروزرسانی: {datetime.now().strftime('%H:%M:%S')}"
        return grid, ts
    except Exception as e:
        return html.Div(f"خطا در اتصال: {e}", style={"color": "#fc8181"}), "خطا"


# ── Running Jobs Progress Bars ─────────────────────────────────────────────────
@app.callback(Output("running-section", "children"), Input("interval", "n_intervals"))
def update_running(n):
    try:
        running = db.get_running_jobs()
        history = db.get_job_history()
        stats = calculations.calc_job_stats(history)
        if not running:
            return html.Div("هیچ جابی در حال اجرا نیست ✓",
                            style={"color": "#4a5568", "padding": "12px"})
        rows = []
        for r in running:
            p = calculations.calc_progress(r["job_id"], r["start_execution_date"], stats)
            if p["percent"] is None:
                pct, cls = 50, "progress-normal"
                lbl = f"elapsed: {calculations.fmt_seconds(p['elapsed'])} | میانگین نامشخص"
            elif p["is_very_slow"]:
                pct = min(100, p["percent"])
                cls = "progress-veryslow"
                lbl = (f"{p['percent']}% | ⚠ بسیار کند! | "
                       f"elapsed: {calculations.fmt_seconds(p['elapsed'])} | "
                       f"avg: {calculations.fmt_seconds(p['avg'])}")
            elif p["is_slow"]:
                pct = min(100, p["percent"])
                cls = "progress-slow"
                lbl = (f"{p['percent']}% | 🟠 کند | "
                       f"elapsed: {calculations.fmt_seconds(p['elapsed'])} | "
                       f"avg: {calculations.fmt_seconds(p['avg'])}")
            else:
                pct = p["percent"]
                cls = "progress-normal"
                lbl = (f"{p['percent']}% | "
                       f"~{calculations.fmt_seconds(p['remaining'])} مانده | "
                       f"avg: {calculations.fmt_seconds(p['avg'])}")
            rows.append(html.Div([
                html.Div([
                    html.Span(r["name"], style={"fontWeight": "600", "marginRight": "10px"}),
                    html.Span(lbl, style={"color": "#718096", "fontSize": "0.85rem"}),
                ], style={"marginBottom": "6px"}),
                html.Div(
                    html.Div(style={"width": f"{min(pct, 100)}%", "minWidth": "4px"},
                             className=f"progress-bar-fill {cls}"),
                    className="progress-bar-bg"
                ),
            ], className="job-row"))
        return rows
    except Exception as e:
        return html.Div(f"خطا: {e}", style={"color": "#fc8181"})


# ── Gantt Timeline ─────────────────────────────────────────────────────────────
@app.callback(Output("gantt-chart", "figure"), Input("interval", "n_intervals"))
def update_gantt(n):
    COLORS = {
        "Succeeded": "#68d391", "Failed": "#fc8181",
        "Retry": "#b794f4", "Canceled": "#a0aec0", "Running": "#63b3ed",
    }
    empty_layout = dict(
        paper_bgcolor="#1e2130", plot_bgcolor="#161929",
        font={"color": "#a0aec0"}, height=200,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
    )
    try:
        history = db.get_job_history()
        running = db.get_running_jobs()
        fig = go.Figure()
        for h in history:
            start = h["start_dt"]
            dur_h = max(h["duration_seconds"], 1) / 3600
            color = COLORS.get(h["status_label"], "#a0aec0")
            fig.add_trace(go.Bar(
                x=[dur_h], y=[h["name"]], base=[start.timestamp() / 3600],
                orientation="h", marker_color=color, showlegend=False,
                hovertemplate=(
                    f"<b>{h['name']}</b><br>"
                    f"شروع: {start.strftime('%Y-%m-%d %H:%M')}<br>"
                    f"مدت: {calculations.fmt_seconds(h['duration_seconds'])}<br>"
                    f"وضعیت: {h['status_label']}<extra></extra>"
                ),
            ))
        now = datetime.now()
        for r in running:
            elapsed = max((now - r["start_execution_date"]).total_seconds(), 1)
            fig.add_trace(go.Bar(
                x=[elapsed / 3600], y=[r["name"]],
                base=[r["start_execution_date"].timestamp() / 3600],
                orientation="h", marker_color=COLORS["Running"], showlegend=False,
                hovertemplate=(
                    f"<b>{r['name']}</b><br>در حال اجرا<br>"
                    f"elapsed: {calculations.fmt_seconds(elapsed)}<extra></extra>"
                ),
            ))
        for lbl, clr in COLORS.items():
            fig.add_trace(go.Bar(x=[None], y=[None], marker_color=clr,
                                 name=lbl, showlegend=True))
        job_names = list(dict.fromkeys(
            [h["name"] for h in history] + [r["name"] for r in running]
        ))
        fig.update_layout(
            barmode="overlay",
            paper_bgcolor="#1e2130", plot_bgcolor="#161929",
            font={"color": "#a0aec0", "size": 11},
            xaxis={"gridcolor": "#2d3250", "title": "زمان (ساعت از epoch)"},
            yaxis={"gridcolor": "#2d3250", "autorange": "reversed"},
            height=max(300, len(job_names) * 28 + 100),
            margin={"l": 200, "r": 20, "t": 20, "b": 40},
            legend={"bgcolor": "#1e2130", "bordercolor": "#2d3250"},
        )
        return fig
    except Exception as e:
        fig = go.Figure()
        fig.update_layout(**empty_layout,
                          annotations=[{"text": f"خطا: {e}", "showarrow": False,
                                        "xref": "paper", "yref": "paper", "x": 0.5, "y": 0.5}])
        return fig


# ── Jobs Table ────────────────────────────────────────────────────────────────
@app.callback(Output("jobs-table", "children"), Input("interval", "n_intervals"))
def update_table(n):
    try:
        jobs = db.get_all_jobs()
        history = db.get_job_history()
        running = db.get_running_jobs()
        stats = calculations.calc_job_stats(history)
        running_ids = {r["job_id"] for r in running}
        latest = {}
        for h in sorted(history, key=lambda x: (x["run_date"], x["run_time"])):
            latest[h["job_id"]] = h
        BADGE = {
            "Succeeded": ("✅ موفق", "badge-success"),
            "Failed": ("❌ ناموفق", "badge-failed"),
            "Retry": ("🔵 Retry", "badge-retry"),
            "Canceled": ("⚫ کنسل", "badge-canceled"),
        }
        header = html.Div([
            html.Div("نام Job", style={"flex": "3", "fontWeight": "600", "color": "#718096"}),
            html.Div("آخرین اجرا", style={"flex": "2", "fontWeight": "600", "color": "#718096"}),
            html.Div("مدت / میانگین", style={"flex": "2", "fontWeight": "600", "color": "#718096"}),
            html.Div("وضعیت", style={"flex": "1", "fontWeight": "600", "color": "#718096"}),
            html.Div("جزئیات", style={"flex": "1", "fontWeight": "600", "color": "#718096"}),
        ], style={"display": "flex", "padding": "8px 16px", "borderBottom": "1px solid #2d3250"})
        rows = [header]
        for j in jobs:
            jid = j["job_id"]
            h = latest.get(jid)
            if jid in running_ids:
                status_el = html.Span("🟡 در حال اجرا", className="status-badge badge-running")
                last_run, dur_str = "الان", "—"
            elif h:
                lbl, badge = BADGE.get(h["status_label"], (h["status_label"], "badge-canceled"))
                status_el = html.Span(lbl, className=f"status-badge {badge}")
                last_run = h["start_dt"].strftime("%m/%d %H:%M")
                avg = stats.get(jid, {}).get("avg")
                dur_str = calculations.fmt_seconds(h["duration_seconds"])
                if avg:
                    dur_str += f" / {calculations.fmt_seconds(avg)}"
            else:
                status_el = html.Span("— بدون سابقه", className="status-badge badge-canceled")
                last_run, dur_str = "—", "—"
            rows.append(html.Div([
                html.Div(j["name"],
                         style={"flex": "3", "overflow": "hidden",
                                "textOverflow": "ellipsis", "whiteSpace": "nowrap"}),
                html.Div(last_run, style={"flex": "2", "color": "#718096"}),
                html.Div(dur_str, style={"flex": "2", "color": "#718096"}),
                html.Div(status_el, style={"flex": "1"}),
                html.Div(
                    html.Button("🔍", id={"type": "drill-btn", "index": jid}, n_clicks=0,
                                style={"background": "none", "border": "none",
                                       "cursor": "pointer", "fontSize": "1.1rem", "color": "#63b3ed"}),
                    style={"flex": "1"}
                ),
            ], style={"display": "flex", "alignItems": "center",
                      "padding": "8px 16px", "borderBottom": "1px solid #1a1f35"}))
        return rows
    except Exception as e:
        return html.Div(f"خطا: {e}", style={"color": "#fc8181"})


# ── Drill-Down — select job ───────────────────────────────────────────────────
@app.callback(
    Output("selected-job-store", "data"),
    Input({"type": "drill-btn", "index": dash.ALL}, "n_clicks"),
    State({"type": "drill-btn", "index": dash.ALL}, "id"),
    prevent_initial_call=True,
)
def select_job(n_clicks_list, ids):
    ctx = callback_context
    if not ctx.triggered:
        return None
    prop_id = ctx.triggered[0]["prop_id"]
    id_dict = json.loads(prop_id.split(".")[0])
    return id_dict["index"]


# ── Drill-Down — close ────────────────────────────────────────────────────────
@app.callback(
    Output("selected-job-store", "data", allow_duplicate=True),
    Input("close-drilldown", "n_clicks"),
    prevent_initial_call=True,
)
def close_drilldown(n):
    return None


# ── Drill-Down — render ───────────────────────────────────────────────────────
@app.callback(
    Output("drilldown-section", "children"),
    Input("selected-job-store", "data"),
    Input("interval", "n_intervals"),
)
def update_drilldown(job_id, n):
    if not job_id:
        return html.Div()
    try:
        step_history = db.get_step_history(job_id)
        all_history = db.get_job_history()
        job_history = [h for h in all_history if h["job_id"] == job_id]
        if not job_history:
            return html.Div("تاریخچه‌ای یافت نشد",
                            style={"color": "#4a5568", "padding": "16px"})
        job_name = job_history[0]["name"]

        succeeded = [h for h in job_history if h["run_status"] == 1]
        trend_fig = go.Figure()
        if succeeded:
            avg_dur = statistics.mean(h["duration_seconds"] for h in succeeded)
            trend_fig.add_trace(go.Scatter(
                x=[h["start_dt"] for h in succeeded],
                y=[h["duration_seconds"] for h in succeeded],
                mode="lines+markers", name="مدت (ثانیه)",
                line={"color": "#63b3ed"},
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>%{y}s<extra></extra>",
            ))
            trend_fig.add_hline(
                y=avg_dur, line_dash="dash", line_color="#f6ad55",
                annotation_text=f"میانگین: {calculations.fmt_seconds(avg_dur)}",
            )
        trend_fig.update_layout(
            paper_bgcolor="#1e2130", plot_bgcolor="#161929",
            font={"color": "#a0aec0"}, height=220,
            margin={"l": 40, "r": 20, "t": 20, "b": 40},
            xaxis={"gridcolor": "#2d3250"},
            yaxis={"gridcolor": "#2d3250", "title": "ثانیه"},
        )

        step_avgs = {}
        for s in step_history:
            if s["run_status"] == 1:
                step_avgs.setdefault(s["step_id"], []).append(s["duration_seconds"])
        step_avg_map = {sid: statistics.mean(durs) for sid, durs in step_avgs.items() if durs}

        if step_history:
            last_key = max(s["run_date"] * 1000000 + s["run_time"] for s in step_history)
            last_steps = [s for s in step_history
                          if s["run_date"] * 1000000 + s["run_time"] >= last_key - 10000]
        else:
            last_steps = []

        SBADGE = {
            "Succeeded": ("✅", "badge-success"), "Failed": ("❌", "badge-failed"),
            "Canceled": ("⚫", "badge-canceled"), "Retry": ("🔵", "badge-retry"),
        }
        step_rows = []
        for s in sorted(last_steps, key=lambda x: x["step_id"]):
            avg_s = step_avg_map.get(s["step_id"])
            pct = (s["duration_seconds"] / avg_s * 100) if avg_s and avg_s > 0 else 100
            bar_cls = ("progress-veryslow" if pct > 150
                       else "progress-slow" if pct > 110 else "progress-normal")
            icon, badge = SBADGE.get(s["status_label"], ("—", "badge-canceled"))
            step_rows.append(html.Div([
                html.Div([
                    html.Span(f"Step {s['step_id']}: {s['step_name']}",
                              style={"fontWeight": "500", "marginRight": "8px"}),
                    html.Span(icon, className=f"status-badge {badge}"),
                    html.Span(
                        f"  {calculations.fmt_seconds(s['duration_seconds'])}"
                        + (f" / avg {calculations.fmt_seconds(avg_s)}" if avg_s else ""),
                        style={"color": "#718096", "fontSize": "0.83rem", "marginLeft": "8px"},
                    ),
                ], style={"marginBottom": "5px"}),
                html.Div(
                    html.Div(style={"width": f"{min(pct, 100)}%", "minWidth": "4px"},
                             className=f"progress-bar-fill {bar_cls}"),
                    className="progress-bar-bg",
                ),
            ], style={"marginBottom": "10px"}))

        return html.Div([
            html.Div([
                html.Div(f"🔍 جزئیات: {job_name}", className="section-title"),
                html.Button("✕ بستن", id="close-drilldown",
                            style={"background": "none", "border": "1px solid #2d3250",
                                   "color": "#a0aec0", "borderRadius": "6px",
                                   "padding": "4px 12px", "cursor": "pointer"}),
            ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "16px"}),
            dcc.Graph(figure=trend_fig, config={"displayModeBar": False}),
            html.Div("Steps آخرین اجرا:",
                     style={"margin": "16px 0 8px", "color": "#a0aec0", "fontWeight": "600"}),
            html.Div(step_rows if step_rows
                     else html.Div("step جداگانه‌ای ثبت نشده", style={"color": "#4a5568"})),
        ], style={"background": "#1e2130", "borderRadius": "10px", "padding": "20px",
                  "border": "1px solid #2d3250", "marginTop": "24px"})
    except Exception as e:
        return html.Div(f"خطا در drill-down: {e}", style={"color": "#fc8181"})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8050)
