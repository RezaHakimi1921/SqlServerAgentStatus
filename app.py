import statistics
import json
from datetime import datetime

import dash
from dash import dcc, html, Input, Output, State, callback_context
import plotly.graph_objects as go

import db
import calculations

app = dash.Dash(__name__, title="SQL Agent Monitor", suppress_callback_exceptions=True)

# ── Layout ─────────────────────────────────────────────────────────────────────
app.layout = html.Div([
    dcc.Store(id="selected-job-store"),
    dcc.Interval(id="interval", interval=60000, n_intervals=0),

    # Header
    html.Div([
        html.Div([
            html.Span("🖥", style={"fontSize": "1.4rem", "marginRight": "10px"}),
            html.Span("SQL Server Agent Monitor", style={"fontSize": "1.2rem", "fontWeight": "700", "color": "#e2e8f0"}),
        ], style={"display": "flex", "alignItems": "center"}),
        html.Div([
            html.Span(id="conn-status", style={"marginRight": "20px", "fontSize": "0.85rem"}),
            html.Span(id="last-update", style={"color": "#4a5568", "fontSize": "0.82rem"}),
        ], style={"display": "flex", "alignItems": "center"}),
    ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center",
              "padding": "14px 28px", "borderBottom": "1px solid #2d3250",
              "backgroundColor": "#0d1117", "position": "sticky", "top": "0", "zIndex": "100"}),

    # KPI row
    html.Div(id="kpi-row", style={"padding": "20px 28px 0"}),

    # Tabs
    html.Div([
        dcc.Tabs(id="tabs", value="running", children=[
            dcc.Tab(label="⚡ در حال اجرا", value="running",
                    style={"color": "#718096", "backgroundColor": "#0d1117", "border": "none", "padding": "10px 20px"},
                    selected_style={"color": "#63b3ed", "backgroundColor": "#161929", "border": "none",
                                    "borderBottom": "2px solid #63b3ed", "padding": "10px 20px"}),
            dcc.Tab(label="📋 همه جاب‌ها", value="jobs",
                    style={"color": "#718096", "backgroundColor": "#0d1117", "border": "none", "padding": "10px 20px"},
                    selected_style={"color": "#63b3ed", "backgroundColor": "#161929", "border": "none",
                                    "borderBottom": "2px solid #63b3ed", "padding": "10px 20px"}),
            dcc.Tab(label="📅 Timeline", value="timeline",
                    style={"color": "#718096", "backgroundColor": "#0d1117", "border": "none", "padding": "10px 20px"},
                    selected_style={"color": "#63b3ed", "backgroundColor": "#161929", "border": "none",
                                    "borderBottom": "2px solid #63b3ed", "padding": "10px 20px"}),
            dcc.Tab(label="🔍 جزئیات Job", value="detail", id="detail-tab",
                    style={"color": "#718096", "backgroundColor": "#0d1117", "border": "none", "padding": "10px 20px"},
                    selected_style={"color": "#a78bfa", "backgroundColor": "#161929", "border": "none",
                                    "borderBottom": "2px solid #a78bfa", "padding": "10px 20px"}),
        ], style={"borderBottom": "1px solid #2d3250"}),
        html.Div(id="tab-content", style={"padding": "24px 28px"}),
    ], style={"marginTop": "16px"}),

], style={"minHeight": "100vh", "backgroundColor": "#0d1117", "color": "#e0e0e0",
          "fontFamily": "'Segoe UI', sans-serif"})


# ── Helper: error card ─────────────────────────────────────────────────────────
def err_card(msg):
    return html.Div([
        html.Div("⚠ خطا در اتصال به SQL Server", style={"fontWeight": "700", "color": "#fc8181", "marginBottom": "8px"}),
        html.Code(str(msg), style={"color": "#feb2b2", "fontSize": "0.82rem", "whiteSpace": "pre-wrap"}),
    ], style={"background": "#3b1c1c", "border": "1px solid #9b2c2c", "borderRadius": "10px",
              "padding": "20px", "marginBottom": "16px"})


def badge(text, cls):
    colors = {
        "success": ("#1c4532", "#68d391"), "failed": ("#3b1c1c", "#fc8181"),
        "running": ("#1a365d", "#63b3ed"), "slow": ("#3d2b0a", "#f6ad55"),
        "veryslow": ("#3b1c1c", "#fc8181"), "canceled": ("#1a202c", "#718096"),
        "retry": ("#2a2050", "#b794f4"),
    }
    bg, fg = colors.get(cls, ("#1a202c", "#a0aec0"))
    return html.Span(text, style={"background": bg, "color": fg, "padding": "2px 10px",
                                  "borderRadius": "12px", "fontSize": "0.78rem", "fontWeight": "600"})


def fmt_bar(pct, cls_name):
    color = {"normal": "linear-gradient(90deg,#3182ce,#63b3ed)",
             "slow": "linear-gradient(90deg,#c05621,#f6ad55)",
             "veryslow": "linear-gradient(90deg,#c53030,#fc8181)"}.get(cls_name, "#3182ce")
    return html.Div(
        html.Div(style={"width": f"{min(pct, 100)}%", "minWidth": "4px", "height": "100%",
                        "borderRadius": "6px", "background": color, "transition": "width .5s"}),
        style={"background": "#2d3250", "borderRadius": "6px", "height": "18px", "overflow": "hidden"}
    )


# ── KPI row ────────────────────────────────────────────────────────────────────
@app.callback(
    Output("kpi-row", "children"),
    Output("last-update", "children"),
    Output("conn-status", "children"),
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
        n_slow = sum(1 for r in running
                     if calculations.calc_progress(r["job_id"], r["start_execution_date"], stats)["is_slow"])

        def kpi(label, val, color):
            return html.Div([
                html.Div(str(val), style={"fontSize": "2.2rem", "fontWeight": "800", "color": color, "lineHeight": "1"}),
                html.Div(label, style={"color": "#718096", "fontSize": "0.78rem", "marginTop": "4px"}),
            ], style={"background": "#161929", "border": "1px solid #2d3250", "borderRadius": "10px",
                      "padding": "16px 20px", "minWidth": "120px"})

        row = html.Div([
            kpi("کل جاب‌ها", len(jobs), "#a0aec0"),
            kpi("در حال اجرا", len(running), "#63b3ed"),
            kpi("موفق (آخرین)", n_success, "#68d391"),
            kpi("ناموفق (آخرین)", n_failed, "#fc8181"),
            kpi("کند الان", n_slow, "#f6ad55"),
        ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap"})

        conn = html.Span("🟢 متصل", style={"color": "#68d391", "fontSize": "0.82rem"})
        ts = f"بروزرسانی: {datetime.now().strftime('%H:%M:%S')}"
        return row, ts, conn
    except Exception as e:
        conn = html.Span("🔴 قطع", style={"color": "#fc8181", "fontSize": "0.82rem"})
        return err_card(e), "", conn


# ── Tab content ────────────────────────────────────────────────────────────────
@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "value"),
    Input("interval", "n_intervals"),
    Input("selected-job-store", "data"),
)
def render_tab(tab, n, job_id):
    if tab == "running":
        return render_running()
    if tab == "jobs":
        return render_jobs_table()
    if tab == "timeline":
        return render_timeline()
    if tab == "detail":
        return render_detail(job_id)
    return html.Div()


# ── Tab: Running Jobs ──────────────────────────────────────────────────────────
def render_running():
    try:
        running = db.get_running_jobs()
        history = db.get_job_history()
        stats = calculations.calc_job_stats(history)

        if not running:
            return html.Div([
                html.Div("✓", style={"fontSize": "3rem", "color": "#68d391", "textAlign": "center"}),
                html.Div("هیچ جابی در حال اجرا نیست",
                         style={"textAlign": "center", "color": "#4a5568", "marginTop": "8px"}),
            ], style={"padding": "60px 0"})

        cards = []
        for r in running:
            p = calculations.calc_progress(r["job_id"], r["start_execution_date"], stats)
            if p["percent"] is None:
                pct, bar_cls = 50, "normal"
                status_txt = f"elapsed: {calculations.fmt_seconds(p['elapsed'])}"
                status_badge = badge("در حال اجرا", "running")
            elif p["is_very_slow"]:
                pct, bar_cls = p["percent"], "veryslow"
                status_txt = f"{p['percent']}% | ⚠ بسیار کند | elapsed: {calculations.fmt_seconds(p['elapsed'])} | avg: {calculations.fmt_seconds(p['avg'])}"
                status_badge = badge("⚠ بسیار کند", "veryslow")
            elif p["is_slow"]:
                pct, bar_cls = p["percent"], "slow"
                status_txt = f"{p['percent']}% | کند | elapsed: {calculations.fmt_seconds(p['elapsed'])} | avg: {calculations.fmt_seconds(p['avg'])}"
                status_badge = badge("🟠 کند", "slow")
            else:
                pct, bar_cls = p["percent"], "normal"
                status_txt = f"{p['percent']}% | ~{calculations.fmt_seconds(p['remaining'])} مانده | avg: {calculations.fmt_seconds(p['avg'])}"
                status_badge = badge("🟢 در حال اجرا", "running")

            started = r["start_execution_date"].strftime("%H:%M:%S") if r["start_execution_date"] else "—"

            cards.append(html.Div([
                html.Div([
                    html.Span(r["name"], style={"fontWeight": "700", "fontSize": "1rem"}),
                    status_badge,
                ], style={"display": "flex", "alignItems": "center", "gap": "10px", "marginBottom": "10px"}),

                fmt_bar(pct if pct is not None else 50, bar_cls),

                html.Div([
                    html.Span(status_txt, style={"color": "#718096", "fontSize": "0.82rem"}),
                    html.Span(f"شروع: {started}", style={"color": "#4a5568", "fontSize": "0.8rem"}),
                ], style={"display": "flex", "justifyContent": "space-between", "marginTop": "6px"}),

                # Step-level progress
                html.Div(id={"type": "step-progress", "index": r["job_id"]},
                         style={"marginTop": "12px"}),

            ], style={"background": "#161929", "border": "1px solid #2d3250", "borderRadius": "10px",
                      "padding": "18px 20px", "marginBottom": "12px"}))

        return html.Div(cards)
    except Exception as e:
        return err_card(e)


# ── Tab: Jobs Table ────────────────────────────────────────────────────────────
def render_jobs_table():
    try:
        jobs = db.get_all_jobs()
        history = db.get_job_history()
        running = db.get_running_jobs()
        stats = calculations.calc_job_stats(history)
        running_ids = {r["job_id"] for r in running}

        latest = {}
        for h in sorted(history, key=lambda x: (x["run_date"], x["run_time"])):
            latest[h["job_id"]] = h

        STATUS_MAP = {
            "Succeeded": ("✅ موفق", "success"),
            "Failed": ("❌ ناموفق", "failed"),
            "Retry": ("🔵 Retry", "retry"),
            "Canceled": ("⚫ کنسل", "canceled"),
        }

        header = html.Div([
            html.Div("نام Job", style={"flex": "3", "color": "#4a5568", "fontWeight": "600", "fontSize": "0.8rem"}),
            html.Div("آخرین اجرا", style={"flex": "2", "color": "#4a5568", "fontWeight": "600", "fontSize": "0.8rem"}),
            html.Div("مدت اجرا", style={"flex": "1.5", "color": "#4a5568", "fontWeight": "600", "fontSize": "0.8rem"}),
            html.Div("میانگین", style={"flex": "1.5", "color": "#4a5568", "fontWeight": "600", "fontSize": "0.8rem"}),
            html.Div("وضعیت", style={"flex": "2", "color": "#4a5568", "fontWeight": "600", "fontSize": "0.8rem"}),
            html.Div("جزئیات", style={"flex": "1", "color": "#4a5568", "fontWeight": "600", "fontSize": "0.8rem"}),
        ], style={"display": "flex", "padding": "8px 16px", "borderBottom": "1px solid #2d3250",
                  "textTransform": "uppercase", "letterSpacing": ".05em"})

        rows = [header]
        for j in jobs:
            jid = j["job_id"]
            h = latest.get(jid)
            stat = stats.get(jid, {})

            if jid in running_ids:
                status_el = badge("🟡 در حال اجرا", "running")
                last_run = "الان"
                dur_str = "—"
                avg_str = calculations.fmt_seconds(stat.get("avg")) if stat else "—"
            elif h:
                lbl, cls = STATUS_MAP.get(h["status_label"], (h["status_label"], "canceled"))
                status_el = badge(lbl, cls)
                last_run = h["start_dt"].strftime("%m/%d %H:%M")
                dur_str = calculations.fmt_seconds(h["duration_seconds"])
                avg_str = calculations.fmt_seconds(stat.get("avg")) if stat else "—"
            else:
                status_el = badge("— بدون سابقه", "canceled")
                last_run = "—"
                dur_str = "—"
                avg_str = "—"

            rows.append(html.Div([
                html.Div(j["name"], style={"flex": "3", "overflow": "hidden", "textOverflow": "ellipsis",
                                           "whiteSpace": "nowrap", "fontSize": "0.9rem"}),
                html.Div(last_run, style={"flex": "2", "color": "#718096", "fontSize": "0.88rem"}),
                html.Div(dur_str, style={"flex": "1.5", "color": "#a0aec0", "fontSize": "0.88rem"}),
                html.Div(avg_str, style={"flex": "1.5", "color": "#718096", "fontSize": "0.88rem"}),
                html.Div(status_el, style={"flex": "2"}),
                html.Div(
                    html.Button("🔍 باز کن", id={"type": "drill-btn", "index": jid}, n_clicks=0,
                                style={"background": "#1a365d", "border": "none", "color": "#63b3ed",
                                       "borderRadius": "6px", "padding": "4px 10px",
                                       "cursor": "pointer", "fontSize": "0.8rem"}),
                    style={"flex": "1"}
                ),
            ], style={"display": "flex", "alignItems": "center", "padding": "10px 16px",
                      "borderBottom": "1px solid #1a202c",
                      "transition": "background .15s"}))

        return html.Div(rows, style={"background": "#161929", "borderRadius": "10px",
                                     "border": "1px solid #2d3250", "overflow": "hidden"})
    except Exception as e:
        return err_card(e)


# ── Tab: Timeline ──────────────────────────────────────────────────────────────
def render_timeline():
    try:
        history = db.get_job_history()
        running = db.get_running_jobs()

        if not history and not running:
            return html.Div("داده‌ای برای نمایش وجود ندارد", style={"color": "#4a5568", "padding": "40px",
                                                                      "textAlign": "center"})

        COLORS = {"Succeeded": "#68d391", "Failed": "#fc8181",
                  "Retry": "#b794f4", "Canceled": "#718096", "Running": "#63b3ed"}

        fig = go.Figure()

        for h in history:
            start_ms = int(h["start_dt"].timestamp() * 1000)
            dur_ms = max(h["duration_seconds"] * 1000, 60000)
            color = COLORS.get(h["status_label"], "#718096")
            fig.add_trace(go.Bar(
                x=[dur_ms], y=[h["name"]], base=[start_ms],
                orientation="h", marker_color=color, showlegend=False,
                hovertemplate=(
                    f"<b>{h['name']}</b><br>"
                    f"شروع: {h['start_dt'].strftime('%Y-%m-%d %H:%M:%S')}<br>"
                    f"مدت: {calculations.fmt_seconds(h['duration_seconds'])}<br>"
                    f"وضعیت: {h['status_label']}<extra></extra>"
                ),
            ))

        now = datetime.now()
        for r in running:
            start_ms = int(r["start_execution_date"].timestamp() * 1000)
            elapsed_ms = max(int((now - r["start_execution_date"]).total_seconds() * 1000), 60000)
            fig.add_trace(go.Bar(
                x=[elapsed_ms], y=[r["name"]], base=[start_ms],
                orientation="h", marker_color=COLORS["Running"], showlegend=False,
                hovertemplate=(
                    f"<b>{r['name']}</b><br>در حال اجرا<br>"
                    f"elapsed: {calculations.fmt_seconds((now - r['start_execution_date']).total_seconds())}"
                    f"<extra></extra>"
                ),
            ))

        for lbl, clr in COLORS.items():
            fig.add_trace(go.Bar(x=[None], y=[None], marker_color=clr, name=lbl, showlegend=True))

        job_names = list(dict.fromkeys([h["name"] for h in history] + [r["name"] for r in running]))
        fig.update_layout(
            barmode="overlay",
            paper_bgcolor="#161929", plot_bgcolor="#0d1117",
            font={"color": "#a0aec0", "size": 11},
            xaxis={"type": "date", "gridcolor": "#2d3250", "title": ""},
            yaxis={"gridcolor": "#2d3250", "autorange": "reversed", "tickfont": {"size": 10}},
            height=max(350, len(job_names) * 30 + 100),
            margin={"l": 10, "r": 20, "t": 20, "b": 40},
            legend={"bgcolor": "#161929", "bordercolor": "#2d3250", "orientation": "h",
                    "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        )

        return dcc.Graph(figure=fig, config={"displayModeBar": False},
                         style={"borderRadius": "10px", "overflow": "hidden"})
    except Exception as e:
        return err_card(e)


# ── Tab: Job Detail ────────────────────────────────────────────────────────────
def render_detail(job_id):
    if not job_id:
        return html.Div([
            html.Div("🔍", style={"fontSize": "3rem", "textAlign": "center", "marginBottom": "12px"}),
            html.Div("از تب «همه جاب‌ها» روی «باز کن» کلیک کن",
                     style={"textAlign": "center", "color": "#4a5568"}),
        ], style={"padding": "60px 0"})

    try:
        step_history = db.get_step_history(job_id)
        all_history = db.get_job_history()
        job_history = [h for h in all_history if h["job_id"] == job_id]

        if not job_history:
            return html.Div("تاریخچه‌ای یافت نشد", style={"color": "#4a5568", "padding": "40px"})

        job_name = job_history[0]["name"]
        succeeded = [h for h in job_history if h["run_status"] == 1]

        # Trend chart
        trend_fig = go.Figure()
        if succeeded:
            avg_dur = statistics.mean(h["duration_seconds"] for h in succeeded)
            trend_fig.add_trace(go.Scatter(
                x=[h["start_dt"] for h in succeeded],
                y=[h["duration_seconds"] for h in succeeded],
                mode="lines+markers", name="مدت (ثانیه)",
                line={"color": "#63b3ed", "width": 2},
                marker={"size": 6},
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>%{y:.0f}s<extra></extra>",
            ))
            trend_fig.add_hline(y=avg_dur, line_dash="dash", line_color="#f6ad55",
                                annotation_text=f"avg: {calculations.fmt_seconds(avg_dur)}",
                                annotation_font_color="#f6ad55")

        # Failed markers
        failed = [h for h in job_history if h["run_status"] == 0]
        if failed:
            trend_fig.add_trace(go.Scatter(
                x=[h["start_dt"] for h in failed], y=[0] * len(failed),
                mode="markers", name="Failed",
                marker={"symbol": "x", "color": "#fc8181", "size": 10},
                hovertemplate="%{x|%Y-%m-%d %H:%M}<br>❌ Failed<extra></extra>",
            ))

        trend_fig.update_layout(
            paper_bgcolor="#161929", plot_bgcolor="#0d1117",
            font={"color": "#a0aec0"}, height=240,
            margin={"l": 50, "r": 20, "t": 20, "b": 40},
            xaxis={"gridcolor": "#2d3250"},
            yaxis={"gridcolor": "#2d3250", "title": "ثانیه"},
            legend={"bgcolor": "#161929"},
        )

        # Steps از آخرین اجرا
        step_avgs = {}
        for s in step_history:
            if s["run_status"] == 1:
                step_avgs.setdefault(s["step_id"], []).append(s["duration_seconds"])
        step_avg_map = {sid: statistics.mean(durs) for sid, durs in step_avgs.items() if durs}

        if step_history:
            last_key = max(s["run_date"] * 1000000 + s["run_time"] for s in step_history)
            last_steps = sorted(
                [s for s in step_history if s["run_date"] * 1000000 + s["run_time"] >= last_key - 10000],
                key=lambda x: x["step_id"]
            )
        else:
            last_steps = []

        SBADGE = {"Succeeded": ("✅ موفق", "success"), "Failed": ("❌ ناموفق", "failed"),
                  "Canceled": ("⚫ کنسل", "canceled"), "Retry": ("🔵 Retry", "retry")}

        step_rows = []
        for s in last_steps:
            avg_s = step_avg_map.get(s["step_id"])
            pct = (s["duration_seconds"] / avg_s * 100) if avg_s and avg_s > 0 else 100
            bar_cls = "veryslow" if pct > 150 else "slow" if pct > 110 else "normal"
            lbl, bcls = SBADGE.get(s["status_label"], (s["status_label"], "canceled"))

            step_rows.append(html.Div([
                html.Div([
                    html.Span(f"Step {s['step_id']}: ", style={"color": "#4a5568", "fontSize": "0.82rem"}),
                    html.Span(s["step_name"], style={"fontWeight": "600", "marginRight": "10px"}),
                    badge(lbl, bcls),
                    html.Span(
                        f"  {calculations.fmt_seconds(s['duration_seconds'])}"
                        + (f"  /  avg {calculations.fmt_seconds(avg_s)}" if avg_s else ""),
                        style={"color": "#718096", "fontSize": "0.82rem", "marginLeft": "10px"}
                    ),
                ], style={"display": "flex", "alignItems": "center", "marginBottom": "6px",
                          "flexWrap": "wrap", "gap": "4px"}),
                fmt_bar(pct, bar_cls),
            ], style={"marginBottom": "14px"}))

        # History table آخرین ۲۰ اجرا
        hist_rows = [html.Div([
            html.Div("تاریخ", style={"flex": "2", "color": "#4a5568", "fontSize": "0.78rem", "fontWeight": "600"}),
            html.Div("مدت", style={"flex": "1", "color": "#4a5568", "fontSize": "0.78rem", "fontWeight": "600"}),
            html.Div("وضعیت", style={"flex": "1", "color": "#4a5568", "fontSize": "0.78rem", "fontWeight": "600"}),
        ], style={"display": "flex", "padding": "6px 12px", "borderBottom": "1px solid #2d3250"})]

        HMAP = {"Succeeded": ("✅", "success"), "Failed": ("❌", "failed"),
                "Canceled": ("⚫", "canceled"), "Retry": ("🔵", "retry")}

        for h in job_history[:20]:
            icon, bcls = HMAP.get(h["status_label"], ("—", "canceled"))
            hist_rows.append(html.Div([
                html.Div(h["start_dt"].strftime("%Y/%m/%d %H:%M"),
                         style={"flex": "2", "color": "#a0aec0", "fontSize": "0.85rem"}),
                html.Div(calculations.fmt_seconds(h["duration_seconds"]),
                         style={"flex": "1", "color": "#718096", "fontSize": "0.85rem"}),
                html.Div(badge(icon + " " + h["status_label"], bcls), style={"flex": "1"}),
            ], style={"display": "flex", "alignItems": "center", "padding": "7px 12px",
                      "borderBottom": "1px solid #1a202c"}))

        return html.Div([
            html.Div(f"🔍 {job_name}",
                     style={"fontSize": "1.1rem", "fontWeight": "700", "color": "#e2e8f0", "marginBottom": "20px"}),

            html.Div("📈 روند مدت اجرا", style={"color": "#718096", "fontSize": "0.8rem",
                                                "fontWeight": "600", "marginBottom": "8px",
                                                "textTransform": "uppercase", "letterSpacing": ".05em"}),
            dcc.Graph(figure=trend_fig, config={"displayModeBar": False}),

            html.Div("🪜 Steps آخرین اجرا", style={"color": "#718096", "fontSize": "0.8rem",
                                                    "fontWeight": "600", "margin": "20px 0 12px",
                                                    "textTransform": "uppercase", "letterSpacing": ".05em"}),
            html.Div(
                step_rows if step_rows else html.Div("step جداگانه‌ای ثبت نشده", style={"color": "#4a5568"}),
                style={"background": "#0d1117", "borderRadius": "8px", "padding": "16px",
                       "border": "1px solid #2d3250"}
            ),

            html.Div("📜 آخرین ۲۰ اجرا", style={"color": "#718096", "fontSize": "0.8rem",
                                                  "fontWeight": "600", "margin": "20px 0 12px",
                                                  "textTransform": "uppercase", "letterSpacing": ".05em"}),
            html.Div(hist_rows, style={"background": "#161929", "borderRadius": "8px",
                                       "border": "1px solid #2d3250", "overflow": "hidden"}),
        ])
    except Exception as e:
        return err_card(e)


# ── Drill-down: select job and switch to detail tab ────────────────────────────
@app.callback(
    Output("selected-job-store", "data"),
    Output("tabs", "value"),
    Input({"type": "drill-btn", "index": dash.ALL}, "n_clicks"),
    State({"type": "drill-btn", "index": dash.ALL}, "id"),
    prevent_initial_call=True,
)
def select_job(n_clicks_list, ids):
    ctx = callback_context
    if not ctx.triggered or not any(n_clicks_list):
        return dash.no_update, dash.no_update
    prop_id = ctx.triggered[0]["prop_id"]
    id_dict = json.loads(prop_id.split(".")[0])
    return id_dict["index"], "detail"


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)
