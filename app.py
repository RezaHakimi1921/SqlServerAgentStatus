import os
from datetime import datetime, timedelta

import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go
from dotenv import load_dotenv

load_dotenv()

from db import get_all_data, get_step_history
from calculations import enrich_history, calc_job_stats, calc_progress, fmt_seconds

REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL", "60000"))
DASH_HOST = os.getenv("DASH_HOST", "0.0.0.0")
DASH_PORT = int(os.getenv("DASH_PORT", "8050"))

app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "SQL Server Agent Monitor"

STATUS_LABEL = {0: "ناموفق", 1: "موفق", 2: "تلاش مجدد", 3: "لغو شده"}
STATUS_COLOR = {0: "#e74c3c", 1: "#2ecc71", 2: "#f39c12", 3: "#95a5a6"}

def kpi_card(title, value, color="#e0e0e0", bg="#1a1d2e"):
    return html.Div([
        html.Div(str(value), style={"fontSize": "32px", "fontWeight": "bold", "color": color, "lineHeight": "1"}),
        html.Div(title, style={"fontSize": "12px", "color": "#888", "marginTop": "4px"}),
    ], style={"background": bg, "borderRadius": "10px", "padding": "16px 24px",
              "flex": "1", "minWidth": "130px", "border": "1px solid #2d3250"})

app.layout = html.Div([
    dcc.Store(id="store-data"),
    dcc.Store(id="store-error"),
    dcc.Interval(id="interval", interval=REFRESH_INTERVAL, n_intervals=0),

    html.Div([
        html.H1("SQL Server Agent Monitor", style={"margin": "0", "fontSize": "20px"}),
        html.Span(id="last-update", style={"fontSize": "12px", "color": "#888"}),
    ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center",
              "padding": "12px 20px", "background": "#1a1d2e", "borderBottom": "1px solid #2d3250"}),

    html.Div(id="error-banner"),

    # ── KPI cards ──
    html.Div(id="kpi-bar", style={"display": "flex", "gap": "12px",
                                   "padding": "16px 20px", "flexWrap": "wrap"}),

    dcc.Tabs(id="tabs", value="running", children=[
        dcc.Tab(label="⚡ در حال اجرا", value="running"),
        dcc.Tab(label="📋 همه جاب‌ها", value="all"),
        dcc.Tab(label="📊 Gantt", value="gantt"),
        dcc.Tab(label="🔍 جزئیات Job", value="detail"),
    ], style={"background": "#0f1117"}),

    html.Div(id="tab-content", style={"padding": "16px"}),
], style={"background": "#0f1117", "minHeight": "100vh", "color": "#e0e0e0",
          "fontFamily": "Segoe UI, Tahoma, sans-serif"})

# ── Fetch data ────────────────────────────────────────────────────────────────
@app.callback(
    Output("store-data", "data"),
    Output("store-error", "data"),
    Output("last-update", "children"),
    Input("interval", "n_intervals"),
)
def fetch_data(_):
    try:
        running_raw, history_raw = get_all_data()
        history = enrich_history(history_raw)

        def dt_str(v):
            return v.isoformat() if isinstance(v, datetime) else v

        def serialize(rows):
            return [{k: dt_str(v) for k, v in r.items()} for r in rows]

        now_str = datetime.now().strftime("%H:%M:%S")
        return {"running": serialize(running_raw), "history": serialize(history)}, None, f"آخرین بروزرسانی: {now_str}"
    except Exception as e:
        return dash.no_update, str(e), f"خطا: {datetime.now().strftime('%H:%M:%S')}"

# ── Error banner ──────────────────────────────────────────────────────────────
@app.callback(Output("error-banner", "children"), Input("store-error", "data"))
def show_error(err):
    if not err:
        return None
    return html.Div([
        html.Strong("⚠ خطا در اتصال به SQL Server"),
        html.P(str(err), style={"margin": "4px 0 0", "fontSize": "12px"}),
    ], style={"background": "#5a1a1a", "border": "1px solid #e74c3c",
              "borderRadius": "6px", "padding": "10px 16px", "margin": "8px 16px"})

# ── KPI bar ───────────────────────────────────────────────────────────────────
@app.callback(Output("kpi-bar", "children"), Input("store-data", "data"))
def render_kpi(data):
    if not data:
        return []
    running = data.get("running", [])
    history = data.get("history", [])

    latest = {}
    for h in history:
        if h["job_id"] not in latest:
            latest[h["job_id"]] = h

    total = len(latest)
    succeeded = sum(1 for h in latest.values() if h["run_status"] == 1)
    failed = sum(1 for h in latest.values() if h["run_status"] == 0)
    n_running = len(running)

    today = datetime.now().date().isoformat()
    failed_today = sum(
        1 for h in history
        if h["run_status"] == 0 and (h.get("start_dt") or "")[:10] == today
    )

    return [
        kpi_card("کل جاب‌ها", total),
        kpi_card("در حال اجرا", n_running, color="#3498db", bg="#0d1b2a"),
        kpi_card("آخرین اجرا موفق", succeeded, color="#2ecc71", bg="#0d1f15"),
        kpi_card("آخرین اجرا ناموفق", failed, color="#e74c3c", bg="#1f0d0d"),
        kpi_card("ناموفق امروز", failed_today, color="#f39c12", bg="#1f160d"),
    ]

# ── Tab router ────────────────────────────────────────────────────────────────
@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "value"),
    Input("store-data", "data"),
)
def render_tab(tab, data):
    if not data:
        return html.P("در حال بارگذاری...", style={"color": "#888"})

    def parse_dt(s):
        if s and isinstance(s, str):
            try:
                return datetime.fromisoformat(s)
            except Exception:
                return None
        return s

    running = []
    for r in data.get("running", []):
        row = dict(r)
        row["start_dt"] = parse_dt(r.get("start_dt"))
        running.append(row)

    history = []
    for h in data.get("history", []):
        row = dict(h)
        row["start_dt"] = parse_dt(h.get("start_dt"))
        row["end_dt"] = parse_dt(h.get("end_dt"))
        history.append(row)

    job_stats = calc_job_stats(history)

    if tab == "running":
        return render_running(running, job_stats)
    elif tab == "all":
        return render_all(history)
    elif tab == "gantt":
        return render_gantt(history, running)
    elif tab == "detail":
        return render_detail_selector(history)
    return html.P("نامعلوم")

# ── Running tab ───────────────────────────────────────────────────────────────
def render_running(running, job_stats):
    if not running:
        return html.P("هیچ جابی در حال اجرا نیست.", style={"color": "#888"})

    cards = []
    for r in running:
        start = r.get("start_dt")
        elapsed = (datetime.now() - start).total_seconds() if start else 0
        pct, remaining, is_slow, is_very_slow = calc_progress(r["job_id"], start, job_stats)

        if is_very_slow:
            badge_style = {"background": "#8b0000"}
            badge_text = "خیلی کند"
            bar_color = "#e74c3c"
        elif is_slow:
            badge_style = {"background": "#b8860b"}
            badge_text = "کند"
            bar_color = "#f39c12"
        else:
            badge_style = {"background": "#1a6b3c"}
            badge_text = "در حال اجرا"
            bar_color = "#2ecc71"

        badge_style.update({"color": "#fff", "padding": "2px 8px",
                             "borderRadius": "4px", "fontSize": "11px"})
        bar_pct = pct if pct is not None else 0

        cards.append(html.Div([
            html.Div([
                html.Span(r["name"], style={"fontWeight": "bold", "fontSize": "14px"}),
                html.Span(badge_text, style=badge_style),
            ], style={"display": "flex", "gap": "10px", "alignItems": "center", "marginBottom": "8px"}),
            html.Div([
                html.Span(f"شروع: {start.strftime('%H:%M:%S') if start else '-'}"),
                html.Span(f"سپری: {fmt_seconds(elapsed)}"),
                html.Span(f"باقیمانده: {fmt_seconds(remaining)}" if remaining is not None else ""),
            ], style={"display": "flex", "gap": "20px", "fontSize": "12px",
                      "color": "#aaa", "marginBottom": "8px"}),
            html.Div(html.Div(style={
                "width": f"{bar_pct}%", "height": "8px", "borderRadius": "4px",
                "background": bar_color, "transition": "width 0.5s",
            }), style={"background": "#2d3250", "borderRadius": "4px", "height": "8px"}),
            html.Div(f"{bar_pct}%", style={"fontSize": "11px", "color": "#888",
                                            "marginTop": "4px", "textAlign": "right"}),
        ], style={"background": "#1a1d2e", "borderRadius": "8px", "padding": "14px",
                  "marginBottom": "10px", "border": "1px solid #2d3250"}))
    return html.Div(cards)

# ── All jobs tab ──────────────────────────────────────────────────────────────
def render_all(history):
    latest = {}
    for h in history:
        if h["job_id"] not in latest:
            latest[h["job_id"]] = h

    rows = []
    for i, h in enumerate(latest.values()):
        status = h["run_status"]
        start = h.get("start_dt")
        rows.append(html.Tr([
            html.Td(h["name"], style={"padding": "8px 12px"}),
            html.Td(html.Span(STATUS_LABEL.get(status, "نامعلوم"),
                              style={"background": STATUS_COLOR.get(status, "#888"),
                                     "color": "#fff", "padding": "2px 8px",
                                     "borderRadius": "4px", "fontSize": "12px"}),
                    style={"padding": "8px 12px"}),
            html.Td(start.strftime("%Y/%m/%d %H:%M") if start else "-",
                    style={"padding": "8px 12px", "fontSize": "13px", "color": "#aaa"}),
            html.Td(fmt_seconds(h.get("duration_seconds")), style={"padding": "8px 12px"}),
        ], style={"borderBottom": "1px solid #2d3250",
                  "background": "#1a1d2e" if i % 2 == 0 else "#0f1117"}))

    header = html.Tr([
        html.Th(t, style={"padding": "10px 12px", "textAlign": "right",
                           "background": "#2d3250", "color": "#ccc", "fontSize": "13px"})
        for t in ["نام جاب", "وضعیت", "آخرین اجرا", "مدت"]
    ])
    return html.Div(
        html.Table([html.Thead(header), html.Tbody(rows)],
                   style={"width": "100%", "borderCollapse": "collapse", "fontSize": "14px"}),
        style={"overflowX": "auto"})

# ── Gantt tab ─────────────────────────────────────────────────────────────────
def render_gantt(history, running):
    today = datetime.now().date()
    now = datetime.now()

    bars = [h for h in history
            if h.get("start_dt") and h.get("end_dt")
            and h["start_dt"].date() == today
            and not h["name"].lower().startswith("cdc.")]

    running_bars = [r for r in running
                    if r.get("start_dt") and not r["name"].lower().startswith("cdc.")]

    all_names = sorted({b["name"] for b in bars} | {r["name"] for r in running_bars})

    if not all_names:
        return html.P("امروز داده‌ای برای نمایش وجود ندارد.", style={"color": "#888"})

    fig = go.Figure()
    color_map = {0: "#e74c3c", 1: "#2ecc71", 2: "#f39c12", 3: "#95a5a6"}

    for b in bars:
        color = color_map.get(b["run_status"], "#888")
        dur = fmt_seconds(b.get("duration_seconds"))
        fig.add_trace(go.Bar(
            x=[(b["end_dt"] - b["start_dt"]).total_seconds() * 1000],
            y=[b["name"]],
            base=[b["start_dt"].timestamp() * 1000],
            orientation="h",
            marker_color=color,
            marker_line_width=0,
            width=0.5,
            hovertemplate=(
                f"<b>{b['name']}</b><br>"
                f"شروع: {b['start_dt'].strftime('%H:%M:%S')}<br>"
                f"پایان: {b['end_dt'].strftime('%H:%M:%S')}<br>"
                f"مدت: {dur}<br>"
                f"وضعیت: {STATUS_LABEL.get(b['run_status'], '?')}<extra></extra>"
            ),
            showlegend=False,
        ))

    for r in running_bars:
        start = r["start_dt"]
        elapsed_ms = (now - start).total_seconds() * 1000
        fig.add_trace(go.Bar(
            x=[elapsed_ms],
            y=[r["name"]],
            base=[start.timestamp() * 1000],
            orientation="h",
            marker_color="#3498db",
            marker_line_width=0,
            width=0.5,
            hovertemplate=(
                f"<b>{r['name']}</b><br>"
                f"شروع: {start.strftime('%H:%M:%S')}<br>"
                f"در حال اجرا...<extra></extra>"
            ),
            showlegend=False,
        ))

    day_start = datetime.combine(today, datetime.min.time())
    fig.update_layout(
        barmode="overlay",
        plot_bgcolor="#0f1117",
        paper_bgcolor="#0f1117",
        font={"color": "#e0e0e0", "size": 11},
        xaxis={"type": "date",
               "range": [day_start.timestamp() * 1000, (now + timedelta(hours=1)).timestamp() * 1000],
               "tickformat": "%H:%M", "gridcolor": "#2d3250", "title": "زمان"},
        yaxis={"categoryorder": "array", "categoryarray": list(reversed(all_names)),
               "gridcolor": "#2d3250", "automargin": True},
        height=max(400, len(all_names) * 35 + 100),
        margin={"l": 200, "r": 20, "t": 30, "b": 50},
        bargap=0.3,
    )

    legend = [
        html.Span("● موفق", style={"color": "#2ecc71", "marginRight": "16px"}),
        html.Span("● ناموفق", style={"color": "#e74c3c", "marginRight": "16px"}),
        html.Span("● در حال اجرا", style={"color": "#3498db", "marginRight": "16px"}),
        html.Span("● لغو/تلاش", style={"color": "#f39c12"}),
    ]
    return html.Div([
        html.Div(legend, style={"marginBottom": "8px", "fontSize": "12px"}),
        dcc.Graph(figure=fig, config={"displayModeBar": False},
                  style={"borderRadius": "8px", "overflow": "hidden"}),
    ])

# ── Detail tab ────────────────────────────────────────────────────────────────
def render_detail_selector(history):
    job_names = {}
    for h in history:
        if h["job_id"] not in job_names:
            job_names[h["job_id"]] = h["name"]

    options = [{"label": name, "value": jid}
               for jid, name in sorted(job_names.items(), key=lambda x: x[1])]
    return html.Div([
        dcc.Dropdown(id="job-select", options=options,
                     placeholder="یک جاب انتخاب کنید...",
                     style={"color": "#000", "marginBottom": "16px"}),
        html.Div(id="job-detail-content"),
    ])

@app.callback(
    Output("job-detail-content", "children"),
    Input("job-select", "value"),
    prevent_initial_call=True,
)
def show_job_detail(job_id):
    if not job_id:
        return None
    try:
        steps = get_step_history(job_id)
    except Exception as e:
        return html.Div(f"خطا: {e}", style={"color": "#e74c3c"})

    if not steps:
        return html.P("سابقه step-level یافت نشد.", style={"color": "#888"})

    from calculations import parse_run_datetime, parse_run_duration

    rows = []
    for s in steps:
        dt = parse_run_datetime(s["run_date"], s["run_time"])
        dur = parse_run_duration(s["run_duration"])
        status = s["run_status"]
        rows.append(html.Tr([
            html.Td(str(s["step_id"]), style={"padding": "6px 10px", "color": "#888"}),
            html.Td(s["step_name"], style={"padding": "6px 10px"}),
            html.Td(dt.strftime("%m/%d %H:%M:%S") if dt else "-",
                    style={"padding": "6px 10px", "fontSize": "12px", "color": "#aaa"}),
            html.Td(fmt_seconds(dur), style={"padding": "6px 10px"}),
            html.Td(html.Span(STATUS_LABEL.get(status, "نامعلوم"),
                              style={"background": STATUS_COLOR.get(status, "#888"),
                                     "color": "#fff", "padding": "2px 6px",
                                     "borderRadius": "4px", "fontSize": "11px"}),
                    style={"padding": "6px 10px"}),
        ], style={"borderBottom": "1px solid #2d3250"}))

    header = html.Tr([
        html.Th(t, style={"padding": "8px 10px", "background": "#2d3250",
                           "color": "#ccc", "fontSize": "12px"})
        for t in ["Step", "نام", "زمان", "مدت", "وضعیت"]
    ])
    return html.Table([html.Thead(header), html.Tbody(rows)],
                      style={"width": "100%", "borderCollapse": "collapse", "fontSize": "13px"})

if __name__ == "__main__":
    print("Testing SQL Server connection...")
    try:
        from db import get_connection
        conn = get_connection()
        conn.close()
        print("Connected OK")
    except Exception as e:
        print(f"Connection failed: {e}")
    app.run(debug=False, host=DASH_HOST, port=DASH_PORT)
