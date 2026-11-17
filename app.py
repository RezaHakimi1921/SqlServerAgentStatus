import math
import os
from datetime import datetime, timedelta

import dash
from dash import dcc, html, Input, Output, State, ALL, ctx
from dotenv import load_dotenv

load_dotenv()

from flask import request

from config import (
    is_configured, load_config, resolve_password, save_config,
    save_locale, save_refresh_minutes, test_connection,
)
from core.i18n import DEFAULT_LOCALE, module_title, normalize_locale, t
from modules.shell import build_app_rail
from db import (
    get_running_jobs, get_dashboard_batch, get_jobs_lite,
    get_step_runs_grouped, get_job_step_definitions, invalidate_batch_cache,
)
from calculations import (
    calc_progress, build_gantt_rows,
    fmt_duration_hms, job_category, parse_run_datetime, parse_run_duration, fmt_seconds,
    GANTT_DAY_MINUTES,
)
from core.connection import active_server_info
from core.logging_setup import setup_logging
from core.version import APP_VERSION_LABEL
from modules.home.layout import build_home_layout
from modules.activity.layout import build_activity_layout
from modules.activity.callbacks import register_activity_callbacks
from modules.insights.layout import build_insights_layout
from modules.insights.callbacks import register_insights_callbacks
from modules.indexes.layout import build_indexes_layout
from modules.indexes.callbacks import register_indexes_callbacks
from modules.tables.layout import build_tables_layout
from modules.tables.callbacks import register_tables_callbacks
from modules.docs.layout import build_docs_layout
from modules.docs.callbacks import register_docs_callbacks
from modules.settings.layout import build_settings_layout, render_metric_schedule_editor
from core.insight import collector_enabled, run_due_collectors, tick_interval_ms
from core.insight.schedule import reset_schedule_to_defaults, save_schedule

setup_logging()
_server_info = active_server_info()

REFRESH_OPTIONS = [
    {"label": "1 min", "value": "1"},
    {"label": "5 min", "value": "5"},
    {"label": "10 min", "value": "10"},
    {"label": "30 min", "value": "30"},
    {"label": "60 min", "value": "60"},
]

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_VALID_REFRESH = frozenset({1, 5, 10, 30, 60})

_cfg = load_config()
REFRESH_MINUTES = _cfg.get("refresh_minutes", 5)
DASH_HOST = os.getenv("DASH_HOST", "127.0.0.1")
DASH_PORT = int(os.getenv("DASH_PORT", "8050"))
PAGE_SIZE = 15
GANTT_HOURS = 24
GANTT_BASE_CELL = 90

STATUS_UI = {
    "running": "Running",
    "error": "Error",
    "success": "Succeeded",
    "failed": "Failed",
    "idle": "Idle",
    "pending": "…",
}

ICONS = {
    "cog": "⚙", "bell": "🔔", "close": "✕", "refresh": "↻",
    "list": "☰", "gantt": "▥", "report": "📄", "search": "🔍",
    "dots": "⋮", "clock": "⏱", "play": "▶", "warn": "⚠",
    "ok": "✓", "fail": "✗", "pause": "⏸", "shield": "🛡",
    "zoom-in": "+", "zoom-out": "−", "chev-r": "›", "chev-l": "‹",
    "db": "🗄", "pause": "⏸", "play": "▶", "snapshot": "📷",
    "book": "▤",
}


def Ico(name, extra_class=""):
    cls = "ico" + (f" {extra_class}" if extra_class else "")
    return html.Span(ICONS.get(name, "•"), className=cls, **{"aria-hidden": "true"})

_REALTIME_WS = False
try:
    import flask_socketio  # noqa: F401

    _REALTIME_WS = True
except ImportError:
    pass

_REALTIME_SCRIPT_BLOCK = (
    """
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <script>window.__SM_REALTIME_WS__ = true;</script>
    <script src="/assets/activity_ws.js"></script>
"""
    if _REALTIME_WS
    else "<script>window.__SM_REALTIME_WS__ = false;</script>"
)

app = dash.Dash(__name__, suppress_callback_exceptions=True, title="Data Agent Monitor")
app.title = "Data Agent Monitor"

_UI_LOCALE = normalize_locale(load_config().get("locale") or DEFAULT_LOCALE)
_UI_DIR = "rtl" if _UI_LOCALE == "fa" else "ltr"

app.index_string = """<!DOCTYPE html>
<html lang="__UI_LANG__" dir="__UI_DIR__">
<head>""".replace("__UI_LANG__", _UI_LOCALE).replace("__UI_DIR__", _UI_DIR) + """
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@200;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
    <style>
      /* Instant first paint — before Dash/React hydrates */
      #boot-splash {
        position: fixed; inset: 0; z-index: 99999;
        display: flex; align-items: center; justify-content: center;
        background: #0c0e14; color: #e8eaef;
        font-family: Vazirmatn, Segoe UI, Tahoma, sans-serif;
      }
      #boot-splash.hidden { display: none !important; }
      #boot-splash .boot-card {
        text-align: center; padding: 48px 40px;
        display: flex; flex-direction: column; align-items: center; gap: 14px;
      }
      #boot-splash .boot-spin {
        width: 48px; height: 48px;
        border: 3px solid rgba(61, 217, 182, 0.15);
        border-top-color: #3dd9b6;
        border-radius: 50%;
        animation: boot-spin 0.8s linear infinite;
      }
      #boot-splash h2 { margin: 0; font-size: 22px; font-weight: 800; }
      #boot-splash .boot-title {
        margin: 0; font-size: 15px; font-weight: 600; color: #3dd9b6;
        animation: boot-pulse 1.4s ease-in-out infinite;
      }
      #boot-splash .boot-sub { margin: 0; font-size: 13px; color: #8b90a0; }
      @keyframes boot-spin { to { transform: rotate(360deg); } }
      @keyframes boot-pulse {
        0%, 100% { opacity: 0.55; } 50% { opacity: 1; }
      }
      html, body { background: #0c0e14; margin: 0; }
    </style>
</head>
<body>
    <div id="boot-splash" aria-live="polite">
      <div class="boot-card">
        <div class="boot-spin"></div>
        <h2>Data Agent Monitor</h2>
        <p class="boot-title">Starting application…</p>
        <p class="boot-sub">Loading UI — connecting to SQL Server</p>
      </div>
    </div>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
    __REALTIME_SCRIPTS__
    <script src="/assets/gantt.js"></script>
    <script>
      (function () {
        var boot = document.getElementById('boot-splash');
        if (!boot) return;
        function hideBoot() {
          boot.classList.add('hidden');
        }
        // Hand off when React splash or main shell is in the DOM
        var tries = 0;
        var timer = setInterval(function () {
          tries++;
          var appSplash = document.getElementById('app-splash');
          var shell = document.querySelector('.app-container');
          if (appSplash || shell) {
            // If React splash is already hidden, drop boot; else keep boot
            // until React splash exists, then hide boot (React owns loading).
            if (appSplash) hideBoot();
            else if (shell && tries > 4) hideBoot();
            if (appSplash || tries > 80) clearInterval(timer);
          }
          if (tries > 120) { hideBoot(); clearInterval(timer); }
        }, 50);
        window.__hideBootSplash = hideBoot;
      })();
    </script>
</body>
</html>""".replace("__REALTIME_SCRIPTS__", _REALTIME_SCRIPT_BLOCK)


def _serialize_rows(rows):
    def dt_str(v):
        return v.isoformat() if isinstance(v, datetime) else v
    return [{k: dt_str(v) for k, v in r.items()} for r in rows]


def _parse_dt(s):
    if s and isinstance(s, str):
        try:
            return datetime.fromisoformat(s)
        except Exception:
            return None
    return s


def _enrich_run_row(h):
    row = dict(h)
    dt = parse_run_datetime(h["run_date"], h["run_time"])
    dur = h.get("duration_seconds")
    if dur is None:
        dur = parse_run_duration(h.get("run_duration") or 0)
    row["start_dt"] = dt
    row["duration_seconds"] = dur
    row["end_dt"] = (dt + timedelta(seconds=dur)) if dt else None
    return row


def build_jobs_overview(all_jobs, running, latest_runs, job_stats, failure_map=None, today_fail_map=None, stats_ready=False):
    failure_map = failure_map or {}
    today_fail_map = today_fail_map or {}
    job_stats = job_stats or {}
    running_map = {r["job_id"]: r for r in running}
    latest = {h["job_id"]: h for h in latest_runs}

    overview = []
    for j in all_jobs:
        jid = j["job_id"]
        name = j["name"]
        cat = job_category(name)

        if jid in running_map:
            start = running_map[jid].get("start_dt")
            pct, _, _, _ = calc_progress(str(jid).lower(), start, job_stats)
            elapsed = (datetime.now() - start).total_seconds() if start else 0
            overview.append({
                "job_id": jid, "name": name, "category": cat,
                "status": "running",
                "progress": pct,
                "progressLoading": not stats_ready,
                "duration": fmt_duration_hms(elapsed),
                "nextRun": "—", "steps": "Running",
            })
        elif not j.get("enabled", True):
            overview.append({
                "job_id": jid, "name": name, "category": cat,
                "status": "idle", "progress": 0, "progressLoading": False,
                "duration": "—", "nextRun": "—", "steps": "Idle",
            })
        elif jid in latest:
            h = latest[jid]
            rs = h["run_status"]
            status = {0: "error", 1: "success", 2: "failed", 3: "idle"}.get(rs, "idle")
            progress = 100 if rs == 1 else (0 if rs == 0 else 78)
            fail = failure_map.get(jid) or today_fail_map.get(jid) or {}
            msg = fail.get("message") or h.get("message") or ""
            step = fail.get("step_name") or ""
            had_error_today = jid in today_fail_map
            # Lookback failures count for Error filter / notifications (not only "today")
            had_recent_error = had_error_today or jid in failure_map or status == "error"
            if had_error_today and not msg:
                msg = today_fail_map[jid].get("message") or ""
                step = step or today_fail_map[jid].get("step_name") or ""
            overview.append({
                "job_id": jid, "name": name, "category": cat,
                "status": status, "progress": progress, "progressLoading": False,
                "duration": fmt_duration_hms(h.get("duration_seconds")),
                "nextRun": "—",
                "steps": (msg[:80] if msg else STATUS_UI.get(status, "")),
                "failedStep": step,
                "errorMessage": msg,
                "hadErrorToday": had_recent_error,
            })
        elif jid in failure_map or jid in today_fail_map:
            # Step failure in lookback but no outcome row yet (fast path / history lag)
            fail = failure_map.get(jid) or today_fail_map[jid]
            overview.append({
                "job_id": jid, "name": name, "category": cat,
                "status": "error", "progress": 0, "progressLoading": False,
                "duration": "—", "nextRun": "—",
                "steps": (fail.get("message") or "")[:80],
                "failedStep": fail.get("step_name") or "",
                "errorMessage": fail.get("message") or "",
                "hadErrorToday": True,
            })
        else:
            overview.append({
                "job_id": jid, "name": name, "category": cat,
                "status": "idle" if latest_runs else "pending",
                "progress": 0, "progressLoading": False,
                "duration": "—", "nextRun": "—",
                "steps": "…" if not latest_runs else "No history",
            })
    return overview


def _parse_refresh_minutes(raw):
    """Parse refresh interval from select value or Persian label like '۱۰ دقیقه'."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    s = str(raw).strip().translate(_PERSIAN_DIGITS)
    if s.isdigit():
        return int(s)
    import re
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None


def _run_status_duration_line(status_key, status_label, total_sec, *, compact=False):
    """Single-line status + duration with explicit labels."""
    dur = fmt_duration_hms(total_sec)
    unit = "" if compact else html.Span(" (h:m:s)", className="dur-unit")
    return html.Div(className="run-status-dur-line", children=[
        html.Span("Status:", className="meta-lbl"),
        html.Span(status_label, className=f"meta-status status-{status_key}"),
        html.Span("|", className="meta-sep", **{"aria-hidden": "true"}),
        html.Span("Duration:", className="meta-lbl"),
        html.Span(dur, className="meta-dur"),
        unit,
    ])


def _parse_grouped_runs(grouped_rows):
    """Parse SQL rows into ordered list of run dicts with steps."""
    runs_map = {}
    run_order = []
    for row in grouped_rows or []:
        iid = row["instance_id"]
        if iid not in runs_map:
            dt = parse_run_datetime(row["job_run_date"], row["job_run_time"])
            job_st = row.get("job_run_status", 1)
            status_key = {0: "error", 1: "success", 2: "failed", 3: "idle"}.get(job_st, "idle")
            job_dur = parse_run_duration(row.get("job_run_duration") or 0)
            runs_map[iid] = {
                "dt": dt, "status_key": status_key, "job_dur": job_dur, "steps": [],
            }
            run_order.append(iid)
        runs_map[iid]["steps"].append(row)
        if row.get("run_status") == 0:
            runs_map[iid]["status_key"] = "error"
    return [runs_map[iid] for iid in run_order]


def _run_total_seconds(run):
    if run.get("job_dur"):
        return run["job_dur"]
    return sum(parse_run_duration(s.get("run_duration") or 0) for s in run.get("steps", []))


def _build_job_summary_card(job_info, latest_run):
    status = job_info.get("status", "idle")
    st_label = STATUS_UI.get(status, status)
    last_dt = "—"
    last_dur = job_info.get("duration", "—")
    n_steps = "—"
    run_status = "—"

    if latest_run:
        dt = latest_run.get("dt")
        last_dt = dt.strftime("%Y/%m/%d  %H:%M:%S") if dt else "—"
        total_sec = _run_total_seconds(latest_run)
        last_dur = fmt_duration_hms(total_sec) if total_sec else "—"
        n_steps = str(len(latest_run.get("steps", [])))
        run_status = STATUS_UI.get(latest_run.get("status_key"), "—")

    return html.Div(className="job-summary-card", children=[
        html.Div("Job summary", className="job-summary-title"),
        html.Div(className="job-summary-grid", children=[
            html.Div([
                html.Span("Current status", className="job-summary-lbl"),
                html.Span(st_label, className=f"job-summary-val status-{status}"),
            ], className="job-summary-item"),
            html.Div([
                html.Span("Last run", className="job-summary-lbl"),
                html.Span(last_dt, className="job-summary-val"),
            ], className="job-summary-item"),
            html.Div([
                html.Span("Total duration", className="job-summary-lbl"),
                html.Span(last_dur, className="job-summary-val dur"),
            ], className="job-summary-item"),
            html.Div([
                html.Span("Last run result", className="job-summary-lbl"),
                html.Span(run_status, className="job-summary-val"),
            ], className="job-summary-item"),
            html.Div([
                html.Span("Step count", className="job-summary-lbl"),
                html.Span(n_steps, className="job-summary-val"),
            ], className="job-summary-item"),
        ]),
    ])


def _build_step_rows_table(steps, show_message=False):
    status_labels = {0: "Failed", 1: "Succeeded", 2: "Retry", 3: "Canceled"}
    rows = []
    for s in steps:
        dur = parse_run_duration(s.get("run_duration") or 0)
        st = s.get("run_status", 1)
        row_cls = "step-failed" if st == 0 else ""
        msg = (s.get("message") or "").strip()
        cells = [
            html.Td(str(s["step_id"]), className=f"col-step {row_cls}"),
            html.Td(s["step_name"], className=f"col-name {row_cls}", title=s["step_name"]),
            html.Td(
                html.Div(className="step-result-line", children=[
                    html.Span(status_labels.get(st, "?"), className=f"step-status {row_cls}"),
                    html.Span("·", className="step-sep", **{"aria-hidden": "true"}),
                    html.Span(fmt_duration_hms(dur), className="step-dur", title="h:m:s"),
                ]),
                className=f"col-result {row_cls}",
            ),
        ]
        if show_message:
            cells.append(html.Td(
                (msg[:80] + "…") if len(msg) > 80 else (msg or "—"),
                className=f"col-msg {row_cls}", title=msg,
            ))
        rows.append(html.Tr(cells))
    headers = [
        html.Th("#", className="col-step"),
        html.Th("Step / SP name", className="col-name"),
        html.Th("Status / duration (h:m:s)", className="col-result"),
    ]
    if show_message:
        headers.append(html.Th("Message", className="col-msg"))
    return html.Table(className="detail-table run-steps-table", children=[
        html.Thead(html.Tr(headers)),
        html.Tbody(rows),
    ])


def _build_latest_run_section(latest_run):
    if not latest_run or not latest_run.get("steps"):
        return None
    dt = latest_run.get("dt")
    dt_label = dt.strftime("%Y/%m/%d  %H:%M:%S") if dt else "—"
    total_sec = _run_total_seconds(latest_run)
    st_label = STATUS_UI.get(latest_run.get("status_key"), "—")
    return html.Div(className="latest-run-section", children=[
        html.Div(className="job-def-title", children=[
            html.Span("▶", className="ico"),
            " Latest run — step details",
            html.Span(f" ({dt_label})", className="job-def-count"),
        ]),
        html.Div(className="latest-run-meta", children=[
            _run_status_duration_line(
                latest_run.get("status_key", "idle"), st_label, total_sec,
            ),
        ]),
        _build_step_rows_table(latest_run["steps"], show_message=True),
    ])


def _build_job_definition_section(definitions, latest_run=None):
    if not definitions:
        return None
    last_step_map = {}
    if latest_run:
        for s in latest_run.get("steps", []):
            last_step_map[s["step_id"]] = s

    rows = []
    for d in definitions:
        sub = d.get("subsystem") or "—"
        sid = d["step_id"]
        last = last_step_map.get(sid)
        if last:
            dur = fmt_duration_hms(parse_run_duration(last.get("run_duration") or 0))
            st = {0: "Failed", 1: "Succeeded", 2: "Retry", 3: "Canceled"}.get(last.get("run_status", 1), "—")
            result_cell = html.Td(
                html.Div(className="step-result-line", children=[
                    html.Span(st, className="step-status"),
                    html.Span("·", className="step-sep", **{"aria-hidden": "true"}),
                    html.Span(dur, className="step-dur", title="h:m:s"),
                ]),
                className="col-result",
            )
        else:
            result_cell = html.Td("—", className="col-result muted")
        rows.append(html.Tr([
            html.Td(str(sid), className="col-step"),
            html.Td(d["step_name"], className="col-name", title=d["step_name"]),
            html.Td(sub, className="col-subsystem"),
            result_cell,
        ]))
    return html.Div(className="job-def-section", children=[
        html.Div(className="job-def-title", children=[
            html.Span("📋", className="ico"),
            " Job definition — Steps / SPs",
            html.Span(f" ({len(definitions)} steps)", className="job-def-count"),
        ]),
        html.Table(className="detail-table job-def-table", children=[
            html.Thead(html.Tr([
                html.Th("#", className="col-step"),
                html.Th("Step / SP name", className="col-name"),
                html.Th("Type", className="col-subsystem"),
                html.Th("Last status / duration (h:m:s)", className="col-result"),
            ])),
            html.Tbody(rows),
        ]),
    ])


def _build_grouped_runs_section(runs_list, empty_ok=False):
    """Older runs list. If empty_ok=True, return None instead of empty message."""
    if not runs_list:
        if empty_ok:
            return None
        return html.Div(className="run-history-section", children=[
            html.Div(className="job-def-title", children=[
                html.Span("🕐", className="ico"), " Previous run history",
            ]),
            html.P(
                "No run history in msdb — history may be purged or the job has not run yet.",
                className="history-empty-hint",
            ),
        ])

    status_labels = {0: "Failed", 1: "Succeeded", 2: "Retry", 3: "Canceled"}
    run_blocks = []
    total = len(runs_list)

    for idx, run in enumerate(runs_list):
        dt = run["dt"]
        dt_label = dt.strftime("%Y/%m/%d  %H:%M:%S") if dt else "—"
        n_steps = len(run["steps"])
        st_label = STATUS_UI.get(run["status_key"], run["status_key"])
        total_dur = _run_total_seconds(run)

        summary = html.Div(className="run-summary-line", children=[
            html.Span(f"Run {total - idx}", className="run-instance-num"),
            html.Span(dt_label, className="run-instance-time"),
            _run_status_duration_line(run["status_key"], st_label, total_dur, compact=True),
            html.Span(f"{n_steps} Step", className="run-summary-steps"),
        ])

        run_blocks.append(html.Details(
            className="run-instance",
            open=False,
            children=[
                html.Summary(className="run-instance-summary", children=[summary]),
                _build_step_rows_table(run["steps"], show_message=True),
            ],
        ))

    return html.Div(className="run-history-section", children=[
        html.Div(className="job-def-title", children=[
            html.Span("🕐", className="ico"),
            " Previous run history",
            html.Span(f" ({total} runs)", className="job-def-count"),
        ]),
        html.P(
            "Click a run to see each Step/SP duration.",
            className="history-hint",
        ),
        html.Div(className="run-instances-list", children=run_blocks),
    ])


def _detail_modal():
    return html.Div(
        id="detail-modal",
        className="modal-overlay hidden",
        children=[
            html.Div(className="modal-content modal-detail", children=[
                html.Div(className="modal-header", children=[
                    html.H2(id="detail-modal-title", children="Job details"),
                    html.Div(className="modal-header-actions", children=[
                        html.Button(
                            "Copy",
                            id="btn-job-detail-copy",
                            className="btn-ghost sql-copy-btn",
                            n_clicks=0,
                            title="Copy error / details text",
                        ),
                        html.Button(Ico("close"), id="btn-close-detail",
                                    className="modal-close", n_clicks=0, title="Close"),
                    ]),
                ]),
                html.Div(id="detail-modal-body", className="detail-modal-body"),
                dcc.Store(id="store-job-error-copy-text", data=""),
                dcc.Store(id="store-detail-job-id", data=None),
                html.Div(id="job-error-copy-toast", className="sql-copy-toast"),
            ]),
        ],
    )


def _activity_sql_modal():
    """Must live at app root (not inside module-panel) so position:fixed centers correctly."""
    return html.Div(
        id="activity-sql-modal",
        className="modal-overlay hidden",
        children=[
            html.Div(className="modal-content modal-sql", children=[
                html.Div(className="modal-header", children=[
                    html.H2(id="activity-sql-modal-title", children="SQL"),
                    html.Div(className="modal-header-actions", children=[
                        html.Button(
                            "Copy",
                            id="btn-activity-sql-copy",
                            className="btn-ghost sql-copy-btn",
                            n_clicks=0,
                            title="Copy SQL to clipboard",
                        ),
                        html.Button("×", id="btn-activity-sql-close",
                                    className="modal-close", n_clicks=0, title="Close"),
                    ]),
                ]),
                html.Div(id="activity-sql-modal-body", className="sql-modal-body"),
                dcc.Store(id="store-activity-sql-copy-text", data=""),
                dcc.Store(id="store-sql-copy-feedback", data=""),
                html.Div(id="sql-copy-toast", className="sql-copy-toast"),
            ]),
        ],
    )



app.layout = html.Div([
    dcc.Store(id="store-running"),
    dcc.Store(id="store-latest-runs"),
    dcc.Store(id="store-all-jobs"),
    dcc.Store(id="store-job-stats"),
    dcc.Store(id="store-today-runs"),
    dcc.Store(id="store-failures"),
    dcc.Store(id="store-latest-failures"),
    dcc.Store(id="store-overview"),
    dcc.Store(id="store-gantt"),
    dcc.Store(id="store-error"),
    dcc.Store(id="store-view", data="list"),
    dcc.Store(id="store-filter", data="all"),
    dcc.Store(id="store-search", data=""),
    dcc.Store(id="store-page", data=1),
    dcc.Store(id="store-gantt-filter", data="all"),
    dcc.Store(id="store-gantt-zoom", data=100),
    dcc.Store(id="store-paused", data=False),
    dcc.Store(id="store-snapshot-at", data=None),
    dcc.Store(id="store-data-loaded", data=False),
    dcc.Store(id="store-refresh-minutes", data=REFRESH_MINUTES),
    dcc.Store(id="store-module", data=("settings" if not is_configured() else "home")),
    dcc.Store(id="store-locale", data=_UI_LOCALE),
    dcc.Store(id="store-rail-collapsed", data=False),
    dcc.Store(id="store-jobs-phase", data="idle"),
    dcc.Store(id="store-insight-tick", data=0),
    dcc.Store(id="store-boot-bridge", data=0),
    dcc.Store(id="store-ws-activity-tick", data=None),
    html.Div(id="locale-dir-sync", style={"display": "none"}),
    dcc.Interval(
        id="interval-refresh",
        interval=REFRESH_MINUTES * 60 * 1000,
        n_intervals=0,
        disabled=True,  # Jobs-only; enabled by disable_intervals when module == jobs
    ),
    dcc.Interval(
        id="interval-insight",
        interval=tick_interval_ms(),
        n_intervals=0,
        disabled=True,  # Enabled only on live modules via disable_intervals
    ),

    html.Div(
        id="app-splash",
        className="app-splash" if is_configured() else "app-splash hidden",
        children=[
            html.Div(className="app-splash-card", children=[
                html.Div(className="app-splash-spinner"),
                html.H2(t("app.name", _UI_LOCALE)),
                html.P(t("app.starting", _UI_LOCALE), className="app-splash-title"),
                html.P(t("app.loading_sql", _UI_LOCALE), className="app-splash-sub"),
            ]),
        ],
    ),

    html.Div(id="app-shell", className="app-container app-shell", children=[
        html.Header(className="topbar app-header animate-in", children=[
            html.Div(className="server-select header-right", children=[
                html.Button(
                    html.Span("⌂", className="home-ico"),
                    id="btn-goto-home",
                    className="icon-button home-btn",
                    n_clicks=0,
                    title=t("nav.home", _UI_LOCALE),
                ),
                html.Div(Ico("db", "logo-ico"), className="logo-icon brand-mark"),
                html.Div(children=[
                    html.Small(
                        id="header-module-label",
                        className="header-module-label",
                        children=t("header.scope", _UI_LOCALE),
                    ),
                    html.B(id="header-server-line", children=(
                        f"{_server_info.get('name') or t('header.all_servers', _UI_LOCALE)} · "
                        f"{t('header.connected', _UI_LOCALE) if _server_info.get('configured') else t('header.not_configured', _UI_LOCALE)}"
                    )),
                ]),
                html.Span(
                    APP_VERSION_LABEL,
                    id="chrome-app-version",
                    className="app-version-badge",
                    title=t("app.version", _UI_LOCALE),
                ),
                html.Span(t("app.name", _UI_LOCALE), id="chrome-app-title", className="sr-only"),
            ]),
            html.Div(className="topbar-actions header-left", children=[
                html.Div(id="live-indicator", className="live-pill live-indicator", children=[
                    html.Span(className="live-dot"),
                    t("header.live", _UI_LOCALE),
                ]),
                html.Div(className="notif-wrap", children=[
                    html.Button(
                        [Ico("bell"), html.Span(id="notif-badge", className="notif-badge")],
                        id="btn-notifications", className="icon-button has-badge notif-btn", n_clicks=0,
                        title=t("header.notifications", _UI_LOCALE),
                    ),
                ]),
                html.Button(
                    Ico("book"), id="btn-open-docs", n_clicks=0,
                    className="icon-button", title=t("header.docs", _UI_LOCALE),
                ),
                html.Button(
                    Ico("cog"), id="btn-open-settings", n_clicks=0,
                    className="icon-button", title=t("header.settings", _UI_LOCALE),
                ),
                html.Button(
                    [Ico("pause"), " ", t("header.pause", _UI_LOCALE)],
                    id="btn-pause", className="button secondary", n_clicks=0,
                    title=t("header.pause", _UI_LOCALE),
                ),
                html.Button(
                    [Ico("refresh"), " ", t("header.refresh", _UI_LOCALE)],
                    id="btn-refresh", className="refresh-button button primary", n_clicks=0,
                    title=t("header.refresh", _UI_LOCALE),
                ),
            ]),
        ]),

        html.Div(id="module-home", className="module-panel" + (" active" if is_configured() else ""), children=[
            build_home_layout(_UI_LOCALE),
        ]),

        html.Div(id="module-activity", className="module-panel", children=[
            build_activity_layout(_UI_LOCALE),
        ]),

        html.Div(id="module-insights", className="module-panel", children=[
            build_insights_layout(_UI_LOCALE),
        ]),

        html.Div(id="module-indexes", className="module-panel", children=[
            build_indexes_layout(_UI_LOCALE),
        ]),

        html.Div(id="module-tables", className="module-panel", children=[
            build_tables_layout(_UI_LOCALE),
        ]),

        html.Div(id="module-docs", className="module-panel", children=[
            build_docs_layout(_UI_LOCALE),
        ]),

        html.Div(
            id="module-settings",
            className="module-panel" + ("" if is_configured() else " active"),
            children=[build_settings_layout(_UI_LOCALE)],
        ),

        html.Div(id="module-jobs", className="module-panel", children=[
        html.Div(id="error-banner"),
        dcc.Store(id="jobs-refresh-interval", data="10"),

        html.Div(id="list-panel", className="view-panel active", children=[
            dcc.Loading(
                id="loading-main",
                type="circle",
                color="#0c7c59",
                parent_style={"minHeight": "320px"},
                children=html.Div(className="list-panel-inner content", children=[
                    html.Div(className="page-heading", children=[
                        html.Div(children=[
                            html.Div(className="eyebrow", children=t("jobs.eyebrow", _UI_LOCALE)),
                            html.H1(t("jobs.page_title", _UI_LOCALE)),
                            html.P(t("jobs.page_sub", _UI_LOCALE)),
                        ]),
                        html.Div(className="heading-actions", children=[
                            html.Div(id="jobs-toolbar", className="jobs-toolbar jobs-toolbar-inline", children=[
                                html.Div(id="jobs-interval-chips", className="activity-chip-row status-filters", children=[
                                    html.Button("Off", id={"type": "jobs-interval-chip", "value": "0"},
                                                className="activity-chip", n_clicks=0),
                                    html.Button("5s", id={"type": "jobs-interval-chip", "value": "5"},
                                                className="activity-chip", n_clicks=0),
                                    html.Button("10s", id={"type": "jobs-interval-chip", "value": "10"},
                                                className="activity-chip active", n_clicks=0),
                                    html.Button("30s", id={"type": "jobs-interval-chip", "value": "30"},
                                                className="activity-chip", n_clicks=0),
                                    html.Button("60s", id={"type": "jobs-interval-chip", "value": "60"},
                                                className="activity-chip", n_clicks=0),
                                ]),
                                html.Button(
                                    [Ico("pause"), " ", t("header.pause", _UI_LOCALE)],
                                    id="btn-jobs-pause",
                                    className="button secondary",
                                    n_clicks=0,
                                    title=t("header.pause", _UI_LOCALE),
                                ),
                                html.Button(
                                    [Ico("refresh"), " ", t("header.refresh", _UI_LOCALE)],
                                    id="btn-jobs-refresh",
                                    className="button primary",
                                    n_clicks=0,
                                    title=t("header.refresh", _UI_LOCALE),
                                ),
                            ]),
                        ]),
                    ]),
                    html.Section(id="stats-grid", className="stats-grid", **{"aria-label": "Status summary"}),
                    html.Section(className="workspace-card", children=[
                        html.Div(className="section-head", children=[
                            html.Div(children=[
                                html.H2(t("jobs.workspace_title", _UI_LOCALE)),
                                html.P(t("jobs.workspace_sub", _UI_LOCALE)),
                            ]),
                            html.Div(className="view-tabs", role="tablist", children=[
                                html.Button(
                                    [
                                        Ico("list"),
                                        " ",
                                        html.Span(t("jobs.tab.list", _UI_LOCALE), id="jobs-tab-list-label"),
                                        " ",
                                        html.Span(id="main-tab-badge", className="tab-badge"),
                                    ],
                                    id={"type": "main-tab", "view": "list"},
                                    className="active",
                                    n_clicks=0,
                                ),
                                html.Button(
                                    [
                                        Ico("gantt"),
                                        " ",
                                        html.Span(t("jobs.tab.gantt", _UI_LOCALE), id="jobs-tab-gantt-label"),
                                    ],
                                    id={"type": "main-tab", "view": "gantt"},
                                    n_clicks=0,
                                ),
                            ]),
                        ]),
                        html.Div(className="toolbar animate-in", children=[
                            html.Div(id="filter-tabs", className="toolbar-right status-filters", role="tablist"),
                            html.Div(className="toolbar-left toolbar-tools", children=[
                                html.Div(className="search search-box", children=[
                                    Ico("search", "search-ico"),
                                    dcc.Input(
                                        id="search-input",
                                        className="search-input",
                                        type="text",
                                        placeholder=t("jobs.placeholder.search", _UI_LOCALE),
                                        debounce=True,
                                    ),
                                ]),
                            ]),
                        ]),
                        html.Div(className="table-scroll", children=[
                            html.Main(className="jobs-container animate-in", **{"aria-label": "Job list"}, children=[
                                html.Div(className="jobs-header", role="row", children=[
                                    html.Div(t("jobs.col.name", _UI_LOCALE), role="columnheader"),
                                    html.Div(t("jobs.col.status", _UI_LOCALE), role="columnheader"),
                                    html.Div(t("jobs.col.progress", _UI_LOCALE), role="columnheader"),
                                    html.Div(t("jobs.col.duration", _UI_LOCALE), role="columnheader"),
                                    html.Div(t("jobs.col.next", _UI_LOCALE), role="columnheader"),
                                    html.Div(role="columnheader"),
                                ]),
                                html.Div(id="jobs-body", role="rowgroup", children=[
                                    html.Div(className="view-center-loading", children=[
                                        html.Div(className="activity-loading-spinner"),
                                        html.Div(t("jobs.loading", _UI_LOCALE), className="view-center-loading-text"),
                                        html.Div(t("jobs.loading_sub", _UI_LOCALE), className="view-center-loading-sub"),
                                    ]),
                                ]),
                                html.Div(id="pagination-bar", className="pagination-bar table-foot"),
                            ]),
                        ]),
                    ]),
                ]),
            ),
        ]),

        html.Div(id="gantt-panel", className="view-panel", children=[
            html.Div(className="gantt-wrapper gantt-shell workspace-card", children=[
                html.Div(className="gantt-toolbar section-head", children=[
                    html.Div(className="gantt-toolbar-right", children=[
                        html.Button("All", id={"type": "gantt-filter", "filter": "all"},
                                    className="gantt-filter-chip active", n_clicks=0),
                        html.Button([html.Span(className="chip-dot running"), " Running"],
                                    id={"type": "gantt-filter", "filter": "running"},
                                    className="gantt-filter-chip", n_clicks=0),
                        html.Button([html.Span(className="chip-dot error"), " Error"],
                                    id={"type": "gantt-filter", "filter": "error"},
                                    className="gantt-filter-chip", n_clicks=0),
                        html.Button([html.Span(className="chip-dot success"), " Succeeded"],
                                    id={"type": "gantt-filter", "filter": "success"},
                                    className="gantt-filter-chip", n_clicks=0),
                        html.Button([html.Span(className="chip-dot failed"), " Failed"],
                                    id={"type": "gantt-filter", "filter": "failed"},
                                    className="gantt-filter-chip", n_clicks=0),
                    ]),
                    html.Div(className="gantt-toolbar-left", children=[
                        html.Span(className="gantt-day-label", id="gantt-day-label"),
                        html.Button(Ico("zoom-out"), id="btn-gantt-zoom-out",
                                    className="gantt-zoom-btn", n_clicks=0, title="Zoom out"),
                        html.Span("100%", id="gantt-zoom-label", className="gantt-zoom-label"),
                        html.Button(Ico("zoom-in"), id="btn-gantt-zoom-in",
                                    className="gantt-zoom-btn", n_clicks=0, title="Zoom in"),
                    ]),
                ]),
                html.Div(id="gantt-chart-area"),
            ]),
        ]),
        ]),  # end module-jobs

        html.Div(
            id="app-rail-host",
            children=[
                build_app_rail(
                    locale=_UI_LOCALE,
                    collapsed=False,
                    active=("settings" if not is_configured() else "home"),
                )
            ],
        ),
    ]),

    # Toasts at app root so position:fixed is viewport-relative (not trapped by module animation)
    dcc.Interval(id="interval-toast-dismiss", interval=3200, n_intervals=0, max_intervals=1, disabled=True),
    html.Div(id="jobs-toast-stack", className="toast-stack", children=[
        html.Div(
            id="refresh-status-bar",
            className="toast-item toast-refresh hidden",
            children=[
                html.Span(className="refresh-spinner"),
                html.Span(id="refresh-status-text", children="Refreshing…"),
            ],
        ),
        html.Div(id="freeze-banner", className="toast-item toast-pause hidden"),
        html.Div(id="indexes-toast-refresh", className="toast-item toast-refresh hidden"),
        html.Div(id="indexes-copy-toast", className="toast-item toast-refresh hidden"),
    ]),

    _detail_modal(),
    _activity_sql_modal(),
    html.Div(
        id="indexes-catalog-modal",
        className="modal-overlay hidden",
        children=[
            html.Div(
                className="indexes-catalog-modal-content",
                dir="ltr",
                children=[
                    html.Div(className="indexes-catalog-modal-header", children=[
                        html.Div([
                            html.H2("Update catalog"),
                            html.P("SmartMonitorDB · insight", className="indexes-catalog-modal-sub"),
                        ]),
                        html.Button(
                            "×",
                            id="indexes-catalog-modal-close",
                            className="indexes-catalog-close",
                            n_clicks=0,
                            type="button",
                            title="Close",
                            **{"aria-label": "Close"},
                        ),
                    ]),
                    html.Div(className="indexes-catalog-modal-body", children=[
                        html.Div(className="indexes-catalog-parts", children=[
                            html.Div("WHAT TO REFRESH", className="indexes-catalog-section-label"),
                            html.Div(
                                id="indexes-catalog-parts-ui",
                                className="indexes-catalog-parts-list",
                                children=[
                                    html.Button(
                                        [
                                            html.Span(className="idx-check is-on"),
                                            html.Div(className="idx-opt-copy", children=[
                                                html.Span("Tables", className="idx-opt-title"),
                                                html.Span(
                                                    "Row counts, heap flags, sizes",
                                                    className="idx-opt-desc",
                                                ),
                                            ]),
                                        ],
                                        id={"type": "indexes-catalog-part", "key": "tables"},
                                        className="idx-opt-card is-on",
                                        n_clicks=0,
                                        type="button",
                                    ),
                                    html.Button(
                                        [
                                            html.Span(className="idx-check is-on"),
                                            html.Div(className="idx-opt-copy", children=[
                                                html.Span("Index definitions", className="idx-opt-title"),
                                                html.Span(
                                                    "Keys, includes, filters",
                                                    className="idx-opt-desc",
                                                ),
                                            ]),
                                        ],
                                        id={"type": "indexes-catalog-part", "key": "index_defs"},
                                        className="idx-opt-card is-on",
                                        n_clicks=0,
                                        type="button",
                                    ),
                                    html.Button(
                                        [
                                            html.Span(className="idx-check is-on"),
                                            html.Div(className="idx-opt-copy", children=[
                                                html.Span("Index states", className="idx-opt-title"),
                                                html.Span(
                                                    "Reads, writes, size from DMV",
                                                    className="idx-opt-desc",
                                                ),
                                            ]),
                                        ],
                                        id={"type": "indexes-catalog-part", "key": "index_stats"},
                                        className="idx-opt-card is-on",
                                        n_clicks=0,
                                        type="button",
                                    ),
                                ],
                            ),
                        ]),
                        html.Div(className="indexes-catalog-scope", children=[
                            html.Div("SCOPE", className="indexes-catalog-section-label"),
                            html.Div(
                                id="indexes-catalog-scope-ui",
                                className="indexes-catalog-scope-list",
                                children=[
                                    html.Button(
                                        [
                                            html.Span(className="idx-radio is-on"),
                                            html.Span("All databases", className="idx-opt-title"),
                                        ],
                                        id={"type": "indexes-catalog-scope", "key": "all"},
                                        className="idx-opt-card idx-scope-card is-on",
                                        n_clicks=0,
                                        type="button",
                                    ),
                                    html.Button(
                                        [
                                            html.Span(className="idx-radio"),
                                            html.Span("Selected DB", className="idx-opt-title"),
                                        ],
                                        id={"type": "indexes-catalog-scope", "key": "selected"},
                                        className="idx-opt-card idx-scope-card",
                                        n_clicks=0,
                                        type="button",
                                    ),
                                ],
                            ),
                        ]),
                    ]),
                    html.Div(className="indexes-catalog-modal-actions", children=[
                        html.Button(
                            "Cancel",
                            id="indexes-catalog-cancel",
                            className="indexes-catalog-btn-cancel",
                            n_clicks=0,
                            type="button",
                        ),
                        html.Button(
                            "Confirm refresh",
                            id="indexes-catalog-confirm",
                            className="indexes-catalog-btn-confirm",
                            n_clicks=0,
                            type="button",
                        ),
                    ]),
                    dcc.Store(
                        id="indexes-catalog-parts",
                        data=["tables", "index_defs", "index_stats"],
                    ),
                    dcc.Store(id="indexes-catalog-scope", data="all"),
                ],
            ),
        ],
    ),
    html.Div(
        id="notif-modal",
        className="modal-overlay hidden",
        children=[
            html.Div(className="modal-content notif-modal-content", children=[
                html.Div(className="modal-header", children=[
                    html.H2([Ico("bell"), " Job Errors"]),
                    html.Button(Ico("close"), id="btn-close-notif",
                                className="modal-close", n_clicks=0, title="Close"),
                ]),
                html.Div(id="notif-panel-body", className="notif-modal-body"),
            ]),
        ],
    ),
])


# ── Module shell (Home / Jobs / Activity / Insights / Settings) ───────────────
@app.callback(
    Output("store-module", "data"),
    Input({"type": "home-tile", "module": ALL, "slot": ALL}, "n_clicks"),
    Input({"type": "rail-nav", "module": ALL}, "n_clicks"),
    Input("btn-goto-home", "n_clicks"),
    Input("btn-open-settings", "n_clicks"),
    Input("btn-open-docs", "n_clicks"),
    State("store-module", "data"),
    prevent_initial_call=True,
)
def switch_module(tile_clicks, rail_clicks, home_click, settings_click, docs_click, current):
    triggered = ctx.triggered_id
    if not ctx.triggered:
        return dash.no_update
    # Ignore remounts of pattern-matching buttons (value 0 / None after rail rebuild)
    trig_val = ctx.triggered[0].get("value")
    if trig_val in (None, 0) and triggered not in (
        "btn-goto-home", "btn-open-settings", "btn-open-docs",
    ):
        return dash.no_update
    if triggered == "btn-goto-home":
        return "home"
    if triggered == "btn-open-settings":
        return "settings"
    if triggered == "btn-open-docs":
        return "docs"
    if isinstance(triggered, dict) and triggered.get("type") in ("home-tile", "rail-nav"):
        mid = triggered.get("module")
        if mid == "home":
            return "home"
        if mid in ("jobs", "activity", "insights", "indexes", "tables", "docs", "settings"):
            return mid
    return dash.no_update


@app.callback(
    Output("store-rail-collapsed", "data"),
    Input("btn-rail-toggle", "n_clicks"),
    Input("store-module", "data"),
    State("store-rail-collapsed", "data"),
    prevent_initial_call=True,
)
def toggle_rail(n_clicks, module, collapsed):
    """Collapse the menu when entering a module; Home expands it again."""
    trig = ctx.triggered_id
    if trig == "store-module":
        return (module or "home") != "home"
    if not n_clicks:
        return dash.no_update
    return not bool(collapsed)


@app.callback(
    Output("app-rail-host", "children"),
    Output("app-shell", "className"),
    Input("store-module", "data"),
    Input("store-locale", "data"),
    Input("store-rail-collapsed", "data"),
)
def sync_rail(module, locale, collapsed):
    loc = normalize_locale(locale)
    mid = module or "home"
    collapsed = bool(collapsed)
    return (
        build_app_rail(locale=loc, collapsed=collapsed, active=mid),
        "app-container app-shell" + (" is-rail-collapsed" if collapsed else ""),
    )


app.clientside_callback(
    """
    function(locale) {
        var loc = (locale || 'en').toLowerCase();
        var isFa = loc.indexOf('fa') === 0;
        var html = document.documentElement;
        html.lang = isFa ? 'fa' : 'en';
        html.dir = isFa ? 'rtl' : 'ltr';
        return '';
    }
    """,
    Output("locale-dir-sync", "children"),
    Input("store-locale", "data"),
)


@app.callback(
    Output("store-locale", "data"),
    Output("locale-message", "children"),
    Output("locale-message", "className"),
    Input({"type": "locale-chip", "value": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def change_locale(n_clicks):
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict) or triggered.get("type") != "locale-chip":
        return dash.no_update, dash.no_update, dash.no_update
    if not any(n_clicks or []):
        return dash.no_update, dash.no_update, dash.no_update
    loc = save_locale(triggered.get("value") or "en")
    return loc, t("settings.lang.saved", loc), "setup-message ok"


@app.callback(
    Output("module-home", "children"),
    Output("module-settings", "children"),
    Output("jobs-tab-list-label", "children"),
    Output("jobs-tab-gantt-label", "children"),
    Output("chrome-app-title", "children"),
    Output("chrome-app-version", "title"),
    Output("btn-goto-home", "title"),
    Output("btn-pause", "title"),
    Output("btn-pause", "children", allow_duplicate=True),
    Output("btn-notifications", "title"),
    Output("btn-open-docs", "title"),
    Output("btn-open-settings", "title"),
    Output("btn-refresh", "title"),
    Output("btn-refresh", "children"),
    Output("header-server-line", "children"),
    # Indexes chrome only — never remount Indexes/Activity/Tables (wipes table cache)
    Output("indexes-tab-overview", "children"),
    Output("indexes-tab-explorer", "children"),
    Output("btn-indexes-refresh", "children"),
    Output("btn-indexes-catalog-refresh", "children"),
    Output("indexes-rec-label", "children"),
    Output("indexes-view-status", "children"),
    Output("btn-indexes-load-frag", "children"),
    Output("indexes-table-search", "placeholder"),
    Output("indexes-loading-text", "children"),
    Input("store-locale", "data"),
    State("store-paused", "data"),
    prevent_initial_call=True,
)
def apply_locale_chrome(locale, paused):
    """Refresh chrome labels. Do NOT remount Activity/Indexes/Tables — that wipes stores."""
    loc = normalize_locale(locale)
    info = active_server_info()
    server_line = (
        f"{t('header.server', loc)}: {info.get('name') or '—'}  ·  "
        f"{t('header.connected', loc) if info.get('configured') else t('header.not_configured', loc)}"
    )
    pause_children = (
        [Ico("play"), " " + t("header.resume", loc)]
        if paused else
        [Ico("pause"), " " + t("header.pause", loc)]
    )
    return (
        build_home_layout(loc),
        build_settings_layout(loc),
        t("jobs.tab.list", loc),
        t("jobs.tab.gantt", loc),
        t("app.name", loc),
        t("app.version", loc),
        t("nav.home", loc),
        t("header.resume", loc) if paused else t("header.pause", loc),
        pause_children,
        t("header.notifications", loc),
        t("header.docs", loc),
        t("header.settings", loc),
        t("header.refresh", loc),
        [Ico("refresh"), " " + t("header.refresh", loc)],
        server_line,
        t("indexes.tab.overview", loc),
        t("indexes.tab.explorer", loc),
        t("header.refresh", loc),
        t("indexes.btn.update_catalog", loc),
        t("indexes.view.recommendations", loc),
        t("indexes.view.status", loc),
        t("indexes.btn.load_frag", loc),
        t("indexes.placeholder.search", loc),
        t("indexes.loading", loc),
    )


@app.callback(
    Output("module-home", "className"),
    Output("module-jobs", "className"),
    Output("module-activity", "className"),
    Output("module-insights", "className"),
    Output("module-indexes", "className"),
    Output("module-tables", "className"),
    Output("module-docs", "className"),
    Output("module-settings", "className"),
    Output("header-module-label", "children"),
    Output("btn-refresh", "style"),
    Output("btn-pause", "style"),
    Output("btn-goto-home", "className"),
    Output("btn-open-settings", "className"),
    Output("btn-open-docs", "className"),
    Input("store-module", "data"),
    State("store-locale", "data"),
)
def show_module(module, locale):
    module = module or "home"
    loc = normalize_locale(locale)
    home_cls = "module-panel active" if module == "home" else "module-panel"
    jobs_cls = "module-panel active" if module == "jobs" else "module-panel"
    act_cls = "module-panel active" if module == "activity" else "module-panel"
    ins_cls = "module-panel active" if module == "insights" else "module-panel"
    idx_cls = "module-panel active" if module == "indexes" else "module-panel"
    tbl_cls = "module-panel active" if module == "tables" else "module-panel"
    docs_cls = "module-panel active" if module == "docs" else "module-panel"
    set_cls = "module-panel active" if module == "settings" else "module-panel"
    if module in ("home", "settings"):
        label = t("header.scope", loc)
    else:
        label = module_title(module, loc)
    chrome = {"display": "none"}
    home_btn = "icon-button home-btn" + (" is-active" if module == "home" else "")
    settings_btn = "icon-button" + (" is-active" if module == "settings" else "")
    docs_btn = "icon-button" + (" is-active" if module == "docs" else "")
    return (
        home_cls, jobs_cls, act_cls, ins_cls, idx_cls, tbl_cls, docs_cls, set_cls,
        label, chrome, chrome, home_btn, settings_btn, docs_btn,
    )


register_activity_callbacks(app)
register_insights_callbacks(app)
register_indexes_callbacks(app)
register_tables_callbacks(app)
register_docs_callbacks(app)


# ── Insight Metric Store collector (independent of Jobs UI refresh) ────────────
@app.callback(
    Output("store-insight-tick", "data"),
    Input("interval-insight", "n_intervals"),
    State("store-paused", "data"),
    prevent_initial_call=False,
)
def insight_collector_tick(n, paused):
    """Base tick (~10s). Each metric runs only when its own interval is due."""
    if paused:
        return dash.no_update
    try:
        run_due_collectors()
    except Exception:
        from core.logging_setup import get_logger
        get_logger("sqlmonitor.insight").exception("insight tick failed")
    return n or 0


# ── Data fetch (Jobs: lite first → full history/gantt in background) ───────────
@app.callback(
    Output("store-running", "data"),
    Output("store-latest-runs", "data"),
    Output("store-all-jobs", "data"),
    Output("store-job-stats", "data"),
    Output("store-today-runs", "data"),
    Output("store-failures", "data"),
    Output("store-latest-failures", "data"),
    Output("store-error", "data"),
    Output("store-data-loaded", "data"),
    Output("store-jobs-phase", "data"),
    Output("refresh-status-bar", "className"),
    Input("interval-refresh", "n_intervals"),
    Input("btn-refresh", "n_clicks"),
    Input("btn-jobs-refresh", "n_clicks"),
    Input("store-module", "data"),
    Input("store-jobs-phase", "data"),
    State("store-paused", "data"),
    prevent_initial_call=False,
)
def fetch_all_data(_, __, ___, module, phase, paused):
    hidden = "toast-item toast-refresh hidden"
    nu = dash.no_update
    tid = ctx.triggered_id
    mid = (module or "").strip().lower()

    # Page-scoped: never hit Jobs SQL / stores when another module is active.
    if mid != "jobs":
        if tid == "store-module":
            # Leaving Jobs — reset phase so a later visit starts clean.
            return (nu,) * 9 + ("idle", hidden)
        return (nu,) * 10 + (hidden,)

    if not is_configured():
        return (nu,) * 7 + (None, False, "idle", hidden)

    # Manual refresh always allowed; auto-tick respects pause
    refresh_btns = ("btn-refresh", "btn-jobs-refresh")
    if paused and tid not in refresh_btns and tid != "store-module" and not (
        tid == "store-jobs-phase" and phase == "lite"
    ):
        return (nu,) * 10 + (hidden,)

    if tid in refresh_btns:
        invalidate_batch_cache()

    try:
        # Opening Jobs / early refresh → today outcomes + gantt (fast); stats later
        if tid == "store-module" or (tid in refresh_btns and phase != "full"):
            running = get_running_jobs()
            all_jobs, recent_fail, latest_outcomes, today_runs, latest_fail = get_jobs_lite()
            return (
                _serialize_rows(running),
                _serialize_rows(latest_outcomes),
                _serialize_rows(all_jobs),
                {},
                _serialize_rows(today_runs),
                _serialize_rows(recent_fail),
                _serialize_rows(latest_fail),
                None,
                True,
                "lite",
                hidden,
            )

        # After lite paint → load multi-day stats for progress averages
        if tid == "store-jobs-phase":
            if phase != "lite":
                return (nu,) * 10 + (hidden,)
            running = get_running_jobs()
            latest, all_jobs, job_stats, today, today_fail, latest_fail = get_dashboard_batch(
                use_cache=True,
            )
            return (
                _serialize_rows(running),
                _serialize_rows(latest),
                _serialize_rows(all_jobs),
                job_stats,
                _serialize_rows(today),
                _serialize_rows(today_fail),
                _serialize_rows(latest_fail),
                None,
                True,
                "full",
                hidden,
            )

        # Interval / refresh while already full
        if phase == "full":
            running = get_running_jobs()
            latest, all_jobs, job_stats, today, today_fail, latest_fail = get_dashboard_batch(
                use_cache=(tid not in refresh_btns),
            )
            return (
                _serialize_rows(running),
                _serialize_rows(latest),
                _serialize_rows(all_jobs),
                job_stats,
                _serialize_rows(today),
                _serialize_rows(today_fail),
                _serialize_rows(latest_fail),
                None,
                True,
                "full",
                hidden,
            )

        return (nu,) * 10 + (hidden,)
    except Exception as e:
        return (nu,) * 7 + (str(e), False, phase or "idle", hidden)


@app.callback(
    Output("app-splash", "className"),
    Input("store-data-loaded", "data"),
    Input("store-error", "data"),
    Input("store-module", "data"),
)
def toggle_app_splash(data_loaded, error, module):
    """Show splash immediately on boot; hide once app is ready or non-Jobs module paints."""
    if not is_configured():
        return "app-splash hidden"
    if error:
        return "app-splash hidden"
    # Jobs waits for first data batch
    if module == "jobs":
        return "app-splash hidden" if data_loaded else "app-splash"
    # Non-Jobs modules: hide splash (docs is static — never waits on SQL)
    if module in ("home", "activity", "insights", "indexes", "tables", "settings", "docs"):
        return "app-splash hidden"
    # Initial boot (module not yet resolved): keep splash up
    return "app-splash"


app.clientside_callback(
    """
    function(splashCls) {
        try {
            if (window.__hideBootSplash) { window.__hideBootSplash(); }
            var boot = document.getElementById('boot-splash');
            if (boot) boot.classList.add('hidden');
        } catch (e) {}
        return Date.now();
    }
    """,
    Output("store-boot-bridge", "data"),
    Input("app-splash", "className"),
    prevent_initial_call=False,
)


@app.callback(
    Output("refresh-status-bar", "className", allow_duplicate=True),
    Output("refresh-status-text", "children", allow_duplicate=True),
    Input("btn-refresh", "n_clicks"),
    Input("btn-jobs-refresh", "n_clicks"),
    State("store-module", "data"),
    prevent_initial_call=True,
)
def show_refresh_bar(_, __, module):
    """Only manual Refresh shows a toast — auto-interval must not leave it stuck."""
    if module != "jobs":
        return "toast-item toast-refresh hidden", dash.no_update
    return "toast-item toast-refresh", "Refreshing…"


@app.callback(
    Output("refresh-status-bar", "className", allow_duplicate=True),
    Input("store-overview", "data"),
    Input("store-gantt", "data"),
    Input("store-error", "data"),
    prevent_initial_call=True,
)
def hide_refresh_toast_after_data(_, __, ___):
    """Always dismiss Refresh toast once any jobs data round-trip finishes."""
    return "toast-item toast-refresh hidden"


@app.callback(
    Output("setup-refresh-interval", "data"),
    Output({"type": "settings-refresh-chip", "value": ALL}, "className"),
    Input({"type": "settings-refresh-chip", "value": ALL}, "n_clicks"),
    Input("store-module", "data"),
    State({"type": "settings-refresh-chip", "value": ALL}, "id"),
    State("setup-refresh-interval", "data"),
    prevent_initial_call=False,
)
def settings_refresh_chips(n_clicks, module, ids, current):
    triggered = ctx.triggered_id
    selected = str(current or load_config().get("refresh_minutes", 5))
    if triggered == "store-module" and module == "settings":
        selected = str(load_config().get("refresh_minutes", 5))
    elif isinstance(triggered, dict) and triggered.get("type") == "settings-refresh-chip":
        if any(n_clicks or []):
            selected = str(triggered.get("value") or selected)
    classes = [
        "activity-chip active" if str(i.get("value")) == selected else "activity-chip"
        for i in (ids or [])
    ]
    return selected, classes


@app.callback(
    Output("interval-refresh", "interval"),
    Output("store-refresh-minutes", "data"),
    Output("setup-refresh-message", "children"),
    Output("setup-refresh-message", "className"),
    Input("btn-save-refresh", "n_clicks"),
    State("setup-refresh-interval", "data"),
    State("store-module", "data"),
    prevent_initial_call=True,
)
def update_refresh_interval(save_refresh_clicks, minutes, module):
    if not save_refresh_clicks:
        return (dash.no_update,) * 4
    parsed = _parse_refresh_minutes(minutes)
    if parsed not in _VALID_REFRESH:
        return dash.no_update, dash.no_update, "Invalid refresh interval.", "setup-message err"
    save_refresh_minutes(parsed)
    msg = f"✓ Auto refresh: every {parsed} min (saved — persists after restart)"
    if module == "jobs":
        return dash.no_update, parsed, msg, "setup-message ok"
    return parsed * 60 * 1000, parsed, msg, "setup-message ok"


@app.callback(
    Output("settings-panel-connection", "className"),
    Output("settings-panel-language", "className"),
    Output("settings-panel-metrics", "className"),
    Output("settings-panel-refresh", "className"),
    Output("settings-nav-connection", "className"),
    Output("settings-nav-language", "className"),
    Output("settings-nav-metrics", "className"),
    Output("settings-nav-refresh", "className"),
    Output("store-settings-tab", "data"),
    Input("settings-nav-connection", "n_clicks"),
    Input("settings-nav-language", "n_clicks"),
    Input("settings-nav-metrics", "n_clicks"),
    Input("settings-nav-refresh", "n_clicks"),
    Input("store-module", "data"),
    prevent_initial_call=False,
)
def switch_settings_tab(_c, _lang, _m, _r, module):
    triggered = ctx.triggered_id
    tab = "connection"
    if triggered == "settings-nav-language":
        tab = "language"
    elif triggered == "settings-nav-metrics":
        tab = "metrics"
    elif triggered == "settings-nav-refresh":
        tab = "refresh"
    elif triggered in ("settings-nav-connection", "store-module", None):
        tab = "connection"

    def panel(name):
        return "settings-panel" if tab == name else "settings-panel hidden"

    def nav(name):
        return "settings-nav-btn is-active" if tab == name else "settings-nav-btn"

    return (
        panel("connection"),
        panel("language"),
        panel("metrics"),
        panel("refresh"),
        nav("connection"),
        nav("language"),
        nav("metrics"),
        nav("refresh"),
        tab,
    )


@app.callback(
    Output("settings-metric-schedule", "children"),
    Input("store-module", "data"),
    Input("btn-reset-metric-schedule", "n_clicks"),
    Input("settings-nav-metrics", "n_clicks"),
    prevent_initial_call=False,
)
def load_metric_schedule_editor(module, _reset, _nav):
    triggered = ctx.triggered_id
    if triggered == "btn-reset-metric-schedule":
        try:
            reset_schedule_to_defaults()
        except Exception:
            pass
        return render_metric_schedule_editor()
    if triggered == "store-module" and module != "settings":
        return dash.no_update
    return render_metric_schedule_editor()


@app.callback(
    Output("metric-schedule-msg", "children"),
    Output("metric-schedule-msg", "className"),
    Output("interval-insight", "interval", allow_duplicate=True),
    Input("btn-save-metric-schedule", "n_clicks"),
    Input("btn-reset-metric-schedule", "n_clicks"),
    State({"type": "metric-interval", "name": ALL}, "value"),
    State({"type": "metric-interval", "name": ALL}, "id"),
    State({"type": "metric-enabled", "name": ALL}, "value"),
    State({"type": "metric-enabled", "name": ALL}, "id"),
    prevent_initial_call=True,
)
def save_or_reset_metric_schedule(_save, _reset, intervals, interval_ids, enabled_vals, enabled_ids):
    triggered = ctx.triggered_id
    if triggered == "btn-reset-metric-schedule":
        try:
            # Actual reset already attempted in load_metric_schedule_editor;
            # re-call is cheap and ensures message reflects DB state.
            n = reset_schedule_to_defaults()
            return (
                f"✓ Reset {n} metric(s) to code defaults",
                "setup-message ok",
                tick_interval_ms(),
            )
        except Exception as ex:
            return f"Reset failed: {ex}", "setup-message err", dash.no_update

    if not _save:
        return dash.no_update, dash.no_update, dash.no_update
    updates = {}
    for val, iid in zip(intervals or [], interval_ids or []):
        name = iid.get("name")
        try:
            sec = max(10, int(val or 10))
        except (TypeError, ValueError):
            sec = 10
        updates[name] = {"interval_sec": sec, "enabled": True}
    for val, iid in zip(enabled_vals or [], enabled_ids or []):
        name = iid.get("name")
        if name in updates:
            updates[name]["enabled"] = bool(val) and ("1" in (val or []))
    try:
        n = save_schedule(updates)
        return (
            f"✓ Saved {n} metric interval(s) to SmartMonitorDB",
            "setup-message ok",
            tick_interval_ms(),
        )
    except Exception as ex:
        return f"Save failed: {ex}", "setup-message err", dash.no_update


@app.callback(
    Output("jobs-refresh-interval", "data"),
    Output({"type": "jobs-interval-chip", "value": ALL}, "className"),
    Output("interval-refresh", "interval", allow_duplicate=True),
    Input({"type": "jobs-interval-chip", "value": ALL}, "n_clicks"),
    State({"type": "jobs-interval-chip", "value": ALL}, "id"),
    State("jobs-refresh-interval", "data"),
    prevent_initial_call=True,
)
def set_jobs_interval(n_clicks, ids, current):
    if not any(n_clicks or []):
        return dash.no_update, dash.no_update, dash.no_update
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict):
        return dash.no_update, dash.no_update, dash.no_update
    value = str(triggered.get("value", current or "10"))
    chips = [
        "activity-chip active" if str(i.get("value")) == value else "activity-chip"
        for i in (ids or [])
    ]
    sec = int(value) if value.isdigit() else 10
    interval_ms = (sec * 1000) if sec > 0 else 60_000
    return value, chips, interval_ms


@app.callback(
    Output("interval-refresh", "interval", allow_duplicate=True),
    Input("store-module", "data"),
    State("jobs-refresh-interval", "data"),
    State("store-refresh-minutes", "data"),
    prevent_initial_call=True,
)
def sync_interval_on_module(module, jobs_iv, minutes):
    if module == "jobs":
        sec = int(jobs_iv or 10)
        return (sec * 1000) if sec > 0 else 60_000
    return (minutes or REFRESH_MINUTES) * 60 * 1000


# ── Pause ─────────────────────────────────────────────────────────────────────
@app.callback(
    Output("store-paused", "data", allow_duplicate=True),
    Output("store-snapshot-at", "data", allow_duplicate=True),
    Output("btn-pause", "children"),
    Output("btn-pause", "className"),
    Output("btn-jobs-pause", "children"),
    Output("btn-jobs-pause", "className"),
    Output("btn-activity-pause", "children"),
    Output("btn-activity-pause", "className"),
    Input("btn-pause", "n_clicks"),
    Input("btn-jobs-pause", "n_clicks"),
    Input("btn-activity-pause", "n_clicks"),
    State("store-paused", "data"),
    State("store-locale", "data"),
    prevent_initial_call=True,
)
def toggle_pause(_, __, ___, paused, locale):
    loc = normalize_locale(locale)
    pause_lbl = t("header.pause", loc)
    resume_lbl = t("header.resume", loc)
    jobs_live = [Ico("pause"), " ", pause_lbl]
    jobs_paused = [Ico("play"), " ", resume_lbl]
    activity_live = [
        html.Span("⏸", className="ctrl-ico"),
        html.Span(pause_lbl, className="ctrl-txt"),
    ]
    activity_paused = [
        html.Span("▶", className="ctrl-ico"),
        html.Span(resume_lbl, className="ctrl-txt"),
    ]
    if paused:
        return (
            False, None,
            [Ico("pause"), " ", pause_lbl], "button secondary",
            jobs_live, "button secondary",
            activity_live, "activity-ctrl-btn is-live",
        )
    return (
        True, None,
        [Ico("play"), " ", resume_lbl], "button secondary pause-active",
        jobs_paused, "button secondary pause-active",
        activity_paused, "activity-ctrl-btn is-paused",
    )


@app.callback(
    Output("interval-refresh", "disabled"),
    Output("interval-insights", "disabled"),
    Output("interval-insight", "disabled"),
    Input("store-paused", "data"),
    Input("store-module", "data"),
    Input("jobs-refresh-interval", "data"),
)
def disable_intervals(paused, module, jobs_iv):
    """Only the active module may poll; Jobs/Insights/collector stay off elsewhere."""
    paused = bool(paused)
    mid = (module or "").strip().lower()
    jobs_off = mid != "jobs" or paused or str(jobs_iv or "10") == "0"
    insights_off = mid != "insights" or paused
    # Collector: live ops modules only (not Jobs UI refresh — separate interval).
    live_collector = mid in ("home", "activity", "insights")
    collector_off = paused or (not collector_enabled()) or (not live_collector)
    return jobs_off, insights_off, collector_off


@app.callback(
    Output("freeze-banner", "children"),
    Output("freeze-banner", "className"),
    Output("live-indicator", "children"),
    Output("live-indicator", "className"),
    Input("store-paused", "data"),
    Input("store-snapshot-at", "data"),
    Input("store-locale", "data"),
)
def update_freeze_ui(paused, snapshot_at, locale):
    loc = normalize_locale(locale)
    if not paused:
        return (
            None, "toast-item toast-pause hidden",
            [html.Span(className="live-dot"), t("header.live", loc)],
            "live-pill live-indicator",
        )
    return (
        t("toast.paused", loc),
        "toast-item toast-pause",
        [html.Span(className="live-dot"), " ", t("header.paused", loc)],
        "live-pill live-indicator paused pause-mode",
    )


@app.callback(
    Output("interval-toast-dismiss", "disabled"),
    Output("interval-toast-dismiss", "n_intervals"),
    Input("freeze-banner", "className"),
    Input("refresh-status-bar", "className"),
    Input("indexes-toast-refresh", "className"),
    prevent_initial_call=True,
)
def arm_toast_auto_dismiss(pause_cls, refresh_cls, indexes_cls):
    """When a top toast becomes visible, start a one-shot dismiss timer."""
    pause_shown = bool(pause_cls) and "hidden" not in str(pause_cls)
    refresh_shown = bool(refresh_cls) and "hidden" not in str(refresh_cls)
    indexes_shown = bool(indexes_cls) and "hidden" not in str(indexes_cls)
    if pause_shown or refresh_shown or indexes_shown:
        return False, 0
    return True, 0


@app.callback(
    Output("freeze-banner", "className", allow_duplicate=True),
    Output("refresh-status-bar", "className", allow_duplicate=True),
    Output("indexes-toast-refresh", "className", allow_duplicate=True),
    Input("interval-toast-dismiss", "n_intervals"),
    State("freeze-banner", "className"),
    State("refresh-status-bar", "className"),
    State("indexes-toast-refresh", "className"),
    prevent_initial_call=True,
)
def dismiss_top_toasts(n, pause_cls, refresh_cls, indexes_cls):
    if not n:
        return dash.no_update, dash.no_update, dash.no_update
    out_pause = (
        "toast-item toast-pause hidden"
        if pause_cls and "hidden" not in str(pause_cls)
        else dash.no_update
    )
    out_refresh = (
        "toast-item toast-refresh hidden"
        if refresh_cls and "hidden" not in str(refresh_cls)
        else dash.no_update
    )
    out_indexes = (
        "toast-item toast-refresh hidden"
        if indexes_cls and "hidden" not in str(indexes_cls)
        else dash.no_update
    )
    return out_pause, out_refresh, out_indexes


@app.callback(
    Output("store-overview", "data"),
    Input("store-running", "data"),
    Input("store-latest-runs", "data"),
    Input("store-all-jobs", "data"),
    Input("store-latest-failures", "data"),
    Input("store-failures", "data"),
    Input("store-job-stats", "data"),
    Input("store-jobs-phase", "data"),
)
def merge_overview(running_data, latest_data, all_jobs_data, latest_failures, today_failures, job_stats_data, phase):
    if not all_jobs_data:
        return []
    running = []
    for r in running_data or []:
        row = dict(r)
        row["start_dt"] = _parse_dt(r.get("start_dt"))
        running.append(row)
    latest = []
    for h in latest_data or []:
        row = dict(h)
        if row.get("duration_seconds") is None:
            row["duration_seconds"] = parse_run_duration(row.get("run_duration") or 0)
        latest.append(row)
    all_jobs = [dict(j) for j in all_jobs_data]
    failure_map = {f["job_id"]: f for f in (latest_failures or [])}
    # Keep first (latest) failure per job — today_failures ordered newest first
    today_fail_map = {}
    for f in (today_failures or []):
        jid = f.get("job_id")
        if jid and jid not in today_fail_map:
            today_fail_map[jid] = f
    job_stats = job_stats_data or {}
    # Normalize keys to lowercase strings for UUID matching
    job_stats_norm = {str(k).lower(): v for k, v in job_stats.items()}
    return build_jobs_overview(
        all_jobs, running, latest, job_stats_norm, failure_map, today_fail_map,
        stats_ready=(phase == "full"),
    )


@app.callback(
    Output("store-gantt", "data"),
    Input("store-running", "data"),
    Input("store-today-runs", "data"),
    Input("store-job-stats", "data"),
    Input("store-view", "data"),
)
def merge_gantt(running_data, today_data, job_stats_data, view):
    if view != "gantt":
        return dash.no_update
    # None = still fetching → UI shows center loader
    if today_data is None:
        return None
    running = []
    for r in running_data or []:
        row = dict(r)
        row["start_dt"] = _parse_dt(r.get("start_dt"))
        running.append(row)
    today = [_enrich_run_row(h) for h in (today_data or [])]
    job_stats = job_stats_data or {}
    return build_gantt_rows(today, running, job_stats)


# ── Error banner ──────────────────────────────────────────────────────────────
@app.callback(Output("error-banner", "children"), Input("store-error", "data"))
def show_error(err):
    if not err:
        return None
    return html.Div([
        html.I(className="fas fa-exclamation-triangle", style={"marginLeft": "8px"}),
        " Connection error: ", html.Strong(str(err)),
    ], className="error-banner")


# ── Stats + filter tabs + notification badge ──────────────────────────────────
def _count_by_status(jobs):
    counts = {"running": 0, "error": 0, "success": 0, "failed": 0, "idle": 0}
    for j in jobs:
        st = j.get("status") or "idle"
        if st == "running":
            counts["running"] += 1
        elif st == "pending":
            counts["idle"] += 1
        elif st == "error" or j.get("hadErrorToday"):
            counts["error"] += 1
        elif st == "success":
            counts["success"] += 1
        elif st == "failed":
            counts["failed"] += 1
        else:
            counts["idle"] += 1
    return counts


@app.callback(
    Output("stats-grid", "children"),
    Output("filter-tabs", "children"),
    Input("store-overview", "data"),
)
def render_stats_and_filters(jobs):
    jobs = jobs or []
    counts = _count_by_status(jobs)
    total = len(jobs)
    enabled = sum(1 for j in jobs if j.get("steps") != "Idle")

    # Figma Make: 4 primary cards (running / success / failed / duration-style idle summary)
    attention = counts["error"] + counts["failed"]
    stat_defs = [
        ("running", counts["running"], t("jobs.stat.running", _UI_LOCALE),
         t("jobs.stat.running_sub", _UI_LOCALE, n=enabled), "play", "up"),
        ("success", counts["success"], t("jobs.stat.success", _UI_LOCALE),
         t("jobs.stat.success_sub", _UI_LOCALE), "ok", ""),
        ("failed", attention, t("jobs.stat.attention", _UI_LOCALE),
         t("jobs.stat.attention_sub", _UI_LOCALE, n=counts["failed"]), "warn", "down"),
        ("idle", counts["idle"], t("jobs.stat.idle", _UI_LOCALE),
         t("jobs.stat.idle_sub", _UI_LOCALE), "pause", ""),
    ]
    stats = []
    for i, (key, val, label, sub, icon, trend) in enumerate(stat_defs):
        card_key = "failed" if key == "failed" else ("duration" if key == "idle" else key)
        spark = html.Div(
            className="spark bars",
            children=[html.I(style={"height": f"{h}px"}) for h in (5, 8, 6, 12, 9, 15, 13, 18, 14, 20, 17, 22)],
        ) if key == "running" else (
            html.Div(className="incident-mini", children=[html.Span(), html.Span(), html.I(), html.I()])
            if key == "failed" else None
        )
        stats.append(html.Button(
            type="button",
            id={"type": "stat-card", "filter": key},
            className=f"stat-card {card_key} animate-in",
            n_clicks=0,
            children=[
                html.Div(className="stat-top", children=[
                    html.Span(Ico(icon), className="stat-icon"),
                    html.Span(sub, className=("trend " + trend).strip()),
                ]),
                html.Strong(str(val)),
                html.Span(label),
                html.Small(sub),
                spark,
            ],
        ))

    tab_defs = [
        ("all", t("jobs.filter.all", _UI_LOCALE), None, None),
        ("running", t("jobs.filter.running", _UI_LOCALE), counts["running"], "running-count"),
        ("error", t("jobs.filter.error", _UI_LOCALE), counts["error"], "error-count"),
        ("success", t("jobs.filter.success", _UI_LOCALE), counts["success"], "success-count"),
        ("failed", t("jobs.filter.failed", _UI_LOCALE), counts["failed"], "failed-count"),
    ]
    tabs = []
    for key, label, cnt, cnt_cls in tab_defs:
        children = [label]
        if cnt is not None:
            children = [label, html.Span(str(cnt), className=f"count {cnt_cls}")]
        tabs.append(html.Button(
            id={"type": "filter-tab", "filter": key},
            className="filter-tab",
            n_clicks=0,
            children=children,
        ))

    return stats, tabs


@app.callback(
    Output("notif-modal", "className"),
    Input("btn-notifications", "n_clicks"),
    Input("btn-close-notif", "n_clicks"),
    State("notif-modal", "className"),
    prevent_initial_call=True,
)
def toggle_notif_modal(open_clicks, close_clicks, current):
    triggered = ctx.triggered_id
    if triggered == "btn-close-notif":
        return "modal-overlay hidden"
    if triggered == "btn-notifications":
        if current and "hidden" not in current:
            return "modal-overlay hidden"
        return "modal-overlay"
    return dash.no_update


@app.callback(
    Output("notif-panel-body", "children"),
    Input("store-failures", "data"),
)
def render_notif_panel(failures):
    if not failures:
        return html.Div("✓ No job errors in the last 7 days.", className="notif-empty")

    # Group by job + step so identical recurring failures collapse to one row
    groups = {}
    for f in failures:
        name = f.get("name") or "?"
        step = f.get("step_name") or f"Step {f.get('step_id', '?')}"
        msg = (f.get("message") or "No message").strip()
        key = (name, step)
        dt = parse_run_datetime(f.get("run_date"), f.get("run_time"))
        g = groups.get(key)
        if not g:
            groups[key] = {
                "name": name,
                "step": step,
                "msg": msg,
                "count": 1,
                "first_dt": dt,
                "last_dt": dt,
            }
        else:
            g["count"] += 1
            if dt and (g["last_dt"] is None or dt > g["last_dt"]):
                g["last_dt"] = dt
                g["msg"] = msg  # keep latest message text
            if dt and (g["first_dt"] is None or dt < g["first_dt"]):
                g["first_dt"] = dt

    ordered = sorted(
        groups.values(),
        key=lambda g: g["last_dt"] or datetime.min,
        reverse=True,
    )
    items = []
    for g in ordered:
        last = g["last_dt"]
        first = g["first_dt"]
        last_str = last.strftime("%Y/%m/%d %H:%M:%S") if last else "—"
        if g["count"] > 1 and first and last and first != last:
            time_line = f"{g['count']}×  ·  last {last_str}"
        elif g["count"] > 1:
            time_line = f"{g['count']}×  ·  {last_str}"
        else:
            time_line = last_str
        items.append(html.Div(className="notif-item" + (" notif-item-multi" if g["count"] > 1 else ""), children=[
            html.Div(className="notif-item-top", children=[
                html.Strong(g["name"], className="notif-job"),
                html.Span(time_line, className="notif-time"),
            ]),
            html.Div(g["step"], className="notif-step"),
            html.Div(g["msg"][:300], className="notif-msg", title=g["msg"]),
        ]))
    return items


@app.callback(
    Output("notif-badge", "children"),
    Output("notif-badge", "style"),
    Input("store-failures", "data"),
)
def update_notif_badge(failures):
    if not failures:
        return "", {"display": "none"}
    keys = {(f.get("name"), f.get("step_name") or f.get("step_id")) for f in failures}
    n = len(keys)
    style = {"display": "flex"} if n > 0 else {"display": "none"}
    return str(n), style


@app.callback(Output("main-tab-badge", "children"), Input("store-overview", "data"))
def update_main_tab_badge(jobs):
    return str(len(jobs or []))


# ── Main view tabs ────────────────────────────────────────────────────────────
@app.callback(
    Output("list-panel", "className"),
    Output("gantt-panel", "className"),
    Output({"type": "main-tab", "view": ALL}, "className"),
    Output("store-view", "data"),
    Output("gantt-chart-area", "children", allow_duplicate=True),
    Output("gantt-day-label", "children", allow_duplicate=True),
    Input({"type": "main-tab", "view": ALL}, "n_clicks"),
    State({"type": "main-tab", "view": ALL}, "id"),
    prevent_initial_call=True,
)
def switch_main_view(_, tab_ids):
    triggered = ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return (dash.no_update,) * 6
    view = triggered["view"]
    list_cls = "view-panel active" if view == "list" else "view-panel"
    gantt_cls = "view-panel active" if view == "gantt" else "view-panel"
    tab_classes = [
        "active" if tab["view"] == view else "" for tab in tab_ids
    ]
    if view == "gantt":
        today_str = datetime.now().strftime("%Y-%m-%d")
        loading = html.Div(className="view-center-loading", children=[
            html.Div(className="activity-loading-spinner"),
            html.Div("Loading Gantt…", className="view-center-loading-text"),
            html.Div("Fetching today’s job runs from 00:00", className="view-center-loading-sub"),
        ])
        return list_cls, gantt_cls, tab_classes, view, loading, f"Today: {today_str}"
    return list_cls, gantt_cls, tab_classes, view, dash.no_update, dash.no_update


# ── Filter / search / page state ──────────────────────────────────────────────
@app.callback(
    Output("store-filter", "data"),
    Output("store-page", "data", allow_duplicate=True),
    Input({"type": "filter-tab", "filter": ALL}, "n_clicks"),
    Input({"type": "stat-card", "filter": ALL}, "n_clicks"),
    State({"type": "filter-tab", "filter": ALL}, "id"),
    State({"type": "stat-card", "filter": ALL}, "id"),
    prevent_initial_call=True,
)
def set_filter(tab_clicks, stat_clicks, tab_ids, stat_ids):
    triggered = ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return dash.no_update, dash.no_update
    f = triggered.get("filter")
    if f:
        return f, 1
    return dash.no_update, dash.no_update


@app.callback(Output("store-search", "data"), Input("search-input", "value"))
def set_search(value):
    return (value or "").strip()


@app.callback(
    Output("store-page", "data", allow_duplicate=True),
    Input("store-search", "data"),
    prevent_initial_call=True,
)
def reset_page_on_search(_):
    return 1


@app.callback(
    Output({"type": "filter-tab", "filter": ALL}, "className"),
    Input("store-filter", "data"),
    State({"type": "filter-tab", "filter": ALL}, "id"),
)
def highlight_filter_tab(active, ids):
    return [
        "filter-tab active" if i["filter"] == active else "filter-tab"
        for i in ids
    ]


@app.callback(
    Output({"type": "stat-card", "filter": ALL}, "className"),
    Input("store-filter", "data"),
    State({"type": "stat-card", "filter": ALL}, "id"),
)
def highlight_stat_card(active, ids):
    out = []
    for i in ids:
        key = i["filter"]
        tone = "failed" if key == "failed" else ("duration" if key == "idle" else key)
        selected = " selected" if key == active else ""
        out.append(f"stat-card {tone} animate-in{selected}")
    return out


# ── Jobs list + pagination ──────────────────────────────────────────────────────
def _status_badge(status, had_error_today=False):
    display = status
    if had_error_today and status != "running":
        display = "error"
    pulse = html.Span(className="pulse-dot") if display == "running" else None
    children = [c for c in [pulse, STATUS_UI.get(display, display)] if c is not None]
    return html.Span(children, className=f"status-badge {display}")


def _progress_cell(job):
    """Progress bar, loading spinner (stats pending), or em-dash when unknown."""
    if job.get("progressLoading") and job.get("status") == "running":
        return html.Div(className="progress-loading", children=[
            html.Span(className="progress-mini-spinner", title="Loading progress…"),
            html.Span("…", className="progress-text muted"),
        ])
    pct = job.get("progress")
    if pct is None:
        return html.Div(className="progress-cell-inner", children=[
            html.Div(className="progress-bar-wrapper progress-unknown"),
            html.Span("—", className="progress-text muted"),
        ])
    pct = min(100, max(0, int(pct)))
    return html.Div(className="progress-cell-inner", children=[
        html.Div(
            html.Div(
                className=f"progress-bar-fill {job.get('status') or 'idle'}",
                style={"width": f"{pct}%"},
            ),
            className="progress-bar-wrapper",
        ),
        html.Span(f"{pct}%", className="progress-text"),
    ])


@app.callback(
    Output("jobs-body", "children"),
    Output("pagination-bar", "children"),
    Input("store-overview", "data"),
    Input("store-filter", "data"),
    Input("store-search", "data"),
    Input("store-page", "data"),
    Input("store-data-loaded", "data"),
    Input("store-all-jobs", "data"),
    State("store-module", "data"),
)
def render_jobs(jobs, filt, search, page, data_loaded, all_jobs_data, module):
    if (module or "").strip().lower() != "jobs":
        return dash.no_update, dash.no_update

    if is_configured() and not data_loaded and all_jobs_data is None:
        return (
            html.Div(className="view-center-loading", children=[
                html.Div(className="activity-loading-spinner"),
                html.Div("Loading jobs…", className="view-center-loading-text"),
                html.Div("Fetching Agent job status & history", className="view-center-loading-sub"),
            ]),
            [],
        )

    jobs = jobs or []
    page = page or 1

    filtered = jobs
    if filt == "error":
        filtered = [j for j in filtered if j.get("status") == "error" or j.get("hadErrorToday")]
    elif filt == "success":
        # Had a step error today → belongs in Error, not Succeeded
        filtered = [
            j for j in filtered
            if j.get("status") == "success" and not j.get("hadErrorToday")
        ]
    elif filt == "failed":
        filtered = [
            j for j in filtered
            if j.get("status") == "failed" and not j.get("hadErrorToday")
        ]
    elif filt and filt != "all":
        filtered = [j for j in filtered if j["status"] == filt]
    if search:
        s = search.lower()
        filtered = [j for j in filtered if s in j["name"].lower()]

    total = len(filtered)
    if total == 0:
        if not jobs and data_loaded:
            msg = "No jobs found"
        else:
            msg = "No jobs match this filter"
        empty = html.Div(className="empty-state", children=[
            html.I(className="fas fa-search"),
            html.Div(msg),
        ])
        return empty, _pagination_bar(0, 1, 1)

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(1, min(page, total_pages))
    start = (page - 1) * PAGE_SIZE
    page_jobs = filtered[start:start + PAGE_SIZE]

    rows = []
    for job in page_jobs:
        st = job.get("status") or "idle"
        symbol_tone = "failed" if (st in ("failed", "error") or job.get("hadErrorToday")) else (
            "retry" if st == "retry" else ("disabled" if st in ("idle", "disabled") else "")
        )
        name_block = html.Div(
            className="job-name",
            title=job["name"],
            children=[
                html.Span(className=("job-symbol " + symbol_tone).strip(), children=Ico("db", "tiny-ico")),
                html.Div(children=[
                    html.B(job["name"]),
                    html.Small(f"{job.get('category') or '—'} · {job.get('owner') or ''}".rstrip(" ·")),
                ]),
            ],
        )
        show_err = (
            (st == "error" or job.get("hadErrorToday"))
            and (job.get("failedStep") or job.get("errorMessage"))
        )
        name_cell_children = [name_block]
        if show_err:
            err_parts = []
            if job.get("failedStep"):
                err_parts.append(html.Span(f"SP/Step: {job['failedStep']}", className="err-step"))
            if job.get("errorMessage"):
                err_parts.append(html.Span(job["errorMessage"][:120], className="err-msg",
                                           title=job.get("errorMessage", "")))
            name_cell_children.append(html.Div(err_parts, className="job-error-line"))

        rows.append(html.Div(className="job-row", role="row", children=[
            html.Div(className="job-name-cell", role="gridcell", children=name_cell_children),
            html.Div(_status_badge(st, job.get("hadErrorToday")), role="gridcell"),
            html.Div(className="progress-cell", role="gridcell", children=_progress_cell(job)),
            html.Div([
                Ico("clock", "tiny-ico"),
                f" {job['duration']}",
            ], className="time-cell", role="gridcell", **{"dir": "ltr"}),
            html.Div(job.get("nextRun", "—"), className="next-run-cell", role="gridcell"),
            html.Div(role="gridcell", children=[
                html.Button(
                    Ico("dots"),
                    id={"type": "job-detail-btn", "job_id": job["job_id"]},
                    className="action-btn icon-button", n_clicks=0, title="Job details",
                ),
            ]),
        ]))

    return rows, _pagination_bar(total, page, total_pages)


def _pagination_bar(total, page, total_pages):
    start_n = (page - 1) * PAGE_SIZE + 1 if total else 0
    end_n = min(page * PAGE_SIZE, total)
    return [
        html.Div(
            ["Showing ", html.Strong(str(start_n)), " to ", html.Strong(str(end_n)),
             " of ", html.Strong(str(total)), " jobs"],
            className="pagination-info",
        ),
        html.Div(className="pagination-controls", children=[
            html.Button(Ico("chev-r"), id="btn-page-prev",
                        className="page-btn", n_clicks=0, disabled=(page <= 1),
                        title="Previous page"),
            html.Span(f"{page} / {total_pages}", className="page-btn",
                      style={"border": "none", "cursor": "default"}),
            html.Button(Ico("chev-l"), id="btn-page-next",
                        className="page-btn", n_clicks=0, disabled=(page >= total_pages),
                        title="Next page"),
        ]),
    ]


@app.callback(
    Output("store-page", "data"),
    Input("btn-page-prev", "n_clicks"),
    Input("btn-page-next", "n_clicks"),
    State("store-page", "data"),
    prevent_initial_call=True,
)
def paginate(prev, nxt, page):
    triggered = ctx.triggered_id
    page = page or 1
    if triggered == "btn-page-prev":
        return max(1, page - 1)
    if triggered == "btn-page-next":
        return page + 1
    return dash.no_update


# ── Gantt ─────────────────────────────────────────────────────────────────────
@app.callback(
    Output("store-gantt-filter", "data"),
    Input({"type": "gantt-filter", "filter": ALL}, "n_clicks"),
    State({"type": "gantt-filter", "filter": ALL}, "id"),
    prevent_initial_call=True,
)
def set_gantt_filter(_, ids):
    triggered = ctx.triggered_id
    if triggered and isinstance(triggered, dict):
        return triggered["filter"]
    return dash.no_update


@app.callback(
    Output({"type": "gantt-filter", "filter": ALL}, "className"),
    Input("store-gantt-filter", "data"),
    State({"type": "gantt-filter", "filter": ALL}, "id"),
)
def highlight_gantt_filter(active, ids):
    return [
        "gantt-filter-chip active" if i["filter"] == active else "gantt-filter-chip"
        for i in ids
    ]


@app.callback(
    Output("store-gantt-zoom", "data"),
    Output("gantt-zoom-label", "children"),
    Input("btn-gantt-zoom-in", "n_clicks"),
    Input("btn-gantt-zoom-out", "n_clicks"),
    State("store-gantt-zoom", "data"),
    prevent_initial_call=True,
)
def gantt_zoom(zin, zout, zoom):
    triggered = ctx.triggered_id
    zoom = zoom or 100
    if triggered == "btn-gantt-zoom-in":
        zoom = min(200, zoom + 20)
    elif triggered == "btn-gantt-zoom-out":
        zoom = max(40, zoom - 20)
    return zoom, f"{zoom}%"


@app.callback(
    Output("gantt-chart-area", "children"),
    Output("gantt-day-label", "children"),
    Input("store-gantt", "data"),
    Input("store-gantt-filter", "data"),
    Input("store-gantt-zoom", "data"),
    Input("store-view", "data"),
)
def render_gantt_chart(gantt_rows, gantt_filter, zoom, view):
    if view != "gantt":
        return dash.no_update, dash.no_update
    today_str = datetime.now().strftime("%Y-%m-%d")
    day_label = f"Today: {today_str}"

    # Fetching / switching into Gantt before data is ready
    if gantt_rows is None:
        loading = html.Div(className="view-center-loading", children=[
            html.Div(className="activity-loading-spinner"),
            html.Div("Loading Gantt…", className="view-center-loading-text"),
            html.Div("Fetching today’s job runs from 00:00", className="view-center-loading-sub"),
        ])
        return loading, day_label

    gantt_rows = gantt_rows or []
    zoom = max(40, min(200, zoom or 100))
    cell_w = GANTT_BASE_CELL * (zoom / 100)
    total_w = GANTT_HOURS * cell_w

    if gantt_filter and gantt_filter != "all":
        gantt_rows = [
            r for r in gantt_rows
            if any(b["status"] == gantt_filter for b in r.get("bars", []))
        ]

    if not gantt_rows:
        empty = html.Div(className="empty-state", style={"padding": "48px"}, children=[
            Ico("gantt"),
            html.Div("No runs to show for today"),
        ])
        return empty, day_label

    time_cells = [
        html.Div(f"{h:02d}:00", className="gantt-time-cell", style={"width": f"{cell_w}px"})
        for h in range(GANTT_HOURS)
    ]
    grid_lines = [
        html.Div(className="gantt-grid-line", style={"left": f"{h * cell_w}px"})
        for h in range(GANTT_HOURS + 1)
    ]

    now = datetime.now()
    now_min = now.hour * 60 + now.minute + now.second / 60
    now_left = (now_min / GANTT_DAY_MINUTES) * total_w

    label_rows = [html.Div("Job name", className="gantt-label-header")]
    gantt_row_els = []

    for row in gantt_rows:
        label_rows.append(html.Div(className="gantt-label-row", children=[
            html.Span(className=f"gantt-label-status-dot {row['row_status']}"),
            html.Span(row["name"], className="gantt-label-name", title=row["name"]),
        ]))

        bars = []
        for bar in row.get("bars", []):
            left = (bar["start_min"] / GANTT_DAY_MINUTES) * total_w
            width = max(
                ((bar["end_min"] - bar["start_min"]) / GANTT_DAY_MINUTES) * total_w, 6
            )
            tip = (
                f"{row['name']}\n"
                f"{bar['start_str']} → {bar['end_str']}\n"
                f"{STATUS_UI.get(bar['status'], bar['status'])} — {bar['duration_str']}"
            )
            bars.append(html.Div(
                className=f"gantt-bar {bar['status']}",
                style={"left": f"{left}px", "width": f"{width}px"},
                title=tip,
                children=[
                    html.Div(className="gantt-bar-progress",
                             style={"width": f"{bar['progress']}%"}),
                ],
            ))
        gantt_row_els.append(html.Div(className="gantt-row", children=bars))

    chart = html.Div(className="gantt-chart", children=[
        html.Div(className="gantt-area", children=[
            html.Div(
                id="gantt-timeline-scroll",
                className="gantt-timeline-wrapper",
                title="Drag to pan the timeline",
                children=[
                    html.Div(className="gantt-timeline", style={"width": f"{total_w}px"}, children=[
                        html.Div(className="gantt-time-header", children=time_cells),
                        html.Div(className="gantt-grid", children=grid_lines),
                        html.Div(className="gantt-rows", children=gantt_row_els),
                        html.Div(
                            id="gantt-now-line",
                            className="gantt-now-line",
                            style={"left": f"{now_left}px"},
                        ),
                    ]),
                ],
            ),
            html.Div(id="gantt-labels", className="gantt-labels", children=label_rows),
        ]),
    ])
    return chart, f"Today: {today_str}"


# ── Settings (module page) ─────────────────────────────────────────────────────
def _is_local_request() -> bool:
    addr = request.remote_addr
    return addr in (None, "127.0.0.1", "::1")


@app.callback(
    Output("setup-message", "children", allow_duplicate=True),
    Output("setup-message", "className", allow_duplicate=True),
    Output("header-server-line", "children"),
    Input("btn-test-connection", "n_clicks"),
    Input("btn-save-connection", "n_clicks"),
    State("setup-server", "value"),
    State("setup-database", "value"),
    State("setup-user", "value"),
    State("setup-password", "value"),
    State("setup-driver", "value"),
    prevent_initial_call=True,
)
def setup_feedback(test_clicks, save_clicks, server, database, user, password, driver):
    def _server_line():
        info = active_server_info()
        return (
            f"Server: {info.get('name') or '—'}  ·  "
            f"{'Connected' if info.get('configured') else 'Not configured'}"
        )

    if not _is_local_request():
        return (
            "Connection settings can only be changed from this machine.",
            "setup-message err",
            dash.no_update,
        )
    if not server or not user:
        return (
            "Server and Username are required.",
            "setup-message err",
            dash.no_update,
        )
    if not driver or str(driver).strip() == "":
        driver = load_config().get("driver") or "17"
    resolved = resolve_password(server, user, password)
    if not resolved:
        hint = (
            "Password is required — or leave blank to use the stored password."
            if is_configured() else "Password is required."
        )
        return hint, "setup-message err", dash.no_update
    try:
        ok, msg = test_connection(server, user, resolved, database, driver)
        if ctx.triggered_id == "btn-save-connection" and ok:
            save_config(server, user, resolved, database, driver)
            return "Connection saved.", "setup-message ok", _server_line()
        return (
            msg,
            "setup-message ok" if ok else "setup-message err",
            dash.no_update,
        )
    except Exception as ex:
        return f"Connection failed: {ex}", "setup-message err", dash.no_update


# ── Detail modal (open instantly with loader, then fetch body) ─────────────────
def _detail_loading_body(job_name=""):
    return html.Div(className="detail-loading", children=[
        html.Div(className="activity-loading-spinner"),
        html.Div("Loading job details…", className="detail-loading-text"),
        html.Div(job_name or "", className="detail-loading-sub"),
    ])


@app.callback(
    Output("detail-modal", "className"),
    Output("detail-modal-title", "children"),
    Output("detail-modal-body", "children"),
    Output("store-detail-job-id", "data"),
    Output("store-job-error-copy-text", "data"),
    Output("btn-job-detail-copy", "className"),
    Input({"type": "job-detail-btn", "job_id": ALL}, "n_clicks"),
    Input("btn-close-detail", "n_clicks"),
    State("store-overview", "data"),
    prevent_initial_call=True,
)
def open_detail_modal(detail_clicks, close_click, overview):
    triggered = ctx.triggered_id
    if triggered == "btn-close-detail":
        return (
            "modal-overlay hidden", dash.no_update, dash.no_update,
            None, "", "btn-ghost sql-copy-btn",
        )
    if isinstance(triggered, dict) and triggered.get("type") == "job-detail-btn":
        if not any(c for c in detail_clicks if c):
            return (dash.no_update,) * 6
        job_id = triggered["job_id"]
        job_name = job_id
        for j in overview or []:
            if j["job_id"] == job_id:
                job_name = j["name"]
                break
        return (
            "modal-overlay",
            job_name,
            _detail_loading_body(job_name),
            job_id,
            "",
            "btn-ghost sql-copy-btn",
        )
    return (dash.no_update,) * 6


@app.callback(
    Output("detail-modal-body", "children", allow_duplicate=True),
    Output("store-job-error-copy-text", "data", allow_duplicate=True),
    Input("store-detail-job-id", "data"),
    State("store-overview", "data"),
    prevent_initial_call=True,
)
def load_detail_body(job_id, overview):
    if not job_id:
        return dash.no_update, dash.no_update
    job_name = job_id
    job_info = {}
    for j in overview or []:
        if j["job_id"] == job_id:
            job_name = j["name"]
            job_info = j
            break
    try:
        definitions = get_job_step_definitions(job_id)
        grouped = get_step_runs_grouped(job_id, max_runs=20, since_days=None)
    except Exception as e:
        return (
            html.Div(f"Error: {e}", style={"color": "var(--accent-error)"}),
            str(e),
        )

    runs_list = _parse_grouped_runs(grouped)
    latest = runs_list[0] if runs_list else None
    older = runs_list[1:] if len(runs_list) > 1 else []

    body_parts = [_build_job_summary_card(job_info, latest)]

    if job_info.get("status") == "error" or job_info.get("hadErrorToday"):
        err_msg = job_info.get("errorMessage") or "—"
        body_parts.append(html.Div(className="detail-error-box", children=[
            html.Div("⚠ Latest error details", className="detail-error-title"),
            html.Div(f"Step/SP: {job_info.get('failedStep') or '—'}", className="detail-error-step"),
            html.Pre(err_msg, className="detail-error-msg"),
        ]))
        copy_text = (
            "Job: " + str(job_name) + "\n"
            + "Step/SP: " + str(job_info.get("failedStep") or "—") + "\n"
            + str(err_msg)
        )
    else:
        copy_text = "Job: " + str(job_name)

    latest_sec = _build_latest_run_section(latest)
    if latest_sec:
        body_parts.append(latest_sec)

    older_sec = _build_grouped_runs_section(older, empty_ok=True)
    if older_sec:
        body_parts.append(older_sec)
    elif not latest:
        body_parts.append(_build_grouped_runs_section([]))

    def_section = _build_job_definition_section(definitions, latest)
    if def_section:
        body_parts.append(def_section)

    if not definitions and not runs_list:
        body_parts.append(html.P(
            "No step definition found for this job.",
            style={"color": "var(--text-muted)"},
        ))

    return html.Div(className="detail-modal-inner", children=body_parts), copy_text


app.clientside_callback(
    """
    function(n, text) {
        if (!n) {
            return window.dash_clientside.no_update;
        }
        var t = (typeof text === 'string') ? text : (text || '');
        var cls = 'btn-ghost sql-copy-btn';
        if (t && navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(t);
            cls = 'btn-ghost sql-copy-btn is-copied';
        }
        if (window.__sqlCopyToastTimer) clearTimeout(window.__sqlCopyToastTimer);
        window.__sqlCopyToastTimer = setTimeout(function() {
            var btn = document.getElementById('btn-activity-sql-copy');
            if (btn) btn.className = 'btn-ghost sql-copy-btn';
        }, 1800);
        return cls;
    }
    """,
    Output("btn-activity-sql-copy", "className"),
    Input("btn-activity-sql-copy", "n_clicks"),
    State("store-activity-sql-copy-text", "data"),
    prevent_initial_call=True,
)

app.clientside_callback(
    """
    function(n, text) {
        if (!n) {
            return window.dash_clientside.no_update;
        }
        var t = (typeof text === 'string') ? text : String(text || '');
        var cls = 'btn-ghost sql-copy-btn';
        if (t && navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(t);
            cls = 'btn-ghost sql-copy-btn is-copied';
        }
        if (window.__jobCopyToastTimer) clearTimeout(window.__jobCopyToastTimer);
        window.__jobCopyToastTimer = setTimeout(function() {
            var btn = document.getElementById('btn-job-detail-copy');
            if (btn) btn.className = 'btn-ghost sql-copy-btn';
        }, 1800);
        return cls;
    }
    """,
    Output("btn-job-detail-copy", "className", allow_duplicate=True),
    Input("btn-job-detail-copy", "n_clicks"),
    State("store-job-error-copy-text", "data"),
    prevent_initial_call=True,
)


def _stop_previous_app_processes(port: int) -> None:
    """Close leftover `python app.py` / listeners on DASH_PORT before this process binds."""
    import subprocess
    import sys
    import time

    me = os.getpid()
    to_kill: set[int] = set()

    def _add(pid: int) -> None:
        if pid and pid != me and pid not in to_kill:
            to_kill.add(pid)

    try:
        if sys.platform == "win32":
            net = subprocess.check_output(
                ["netstat", "-ano", "-p", "tcp"],
                text=True,
                errors="replace",
            )
            suffix = f":{port}"
            for line in net.splitlines():
                parts = line.split()
                if len(parts) < 5 or parts[-2].upper() != "LISTENING":
                    continue
                local = parts[1]
                if local.endswith(suffix):
                    try:
                        _add(int(parts[-1]))
                    except ValueError:
                        pass
        else:
            try:
                ss = subprocess.check_output(
                    ["ss", "-lptn", f"sport = :{port}"],
                    text=True,
                    errors="replace",
                )
                import re

                for m in re.finditer(r"pid=(\d+)", ss):
                    _add(int(m.group(1)))
            except (FileNotFoundError, subprocess.CalledProcessError):
                pass
    except (subprocess.CalledProcessError, OSError) as ex:
        print(f"Could not scan previous processes: {ex}")
        return

    if not to_kill:
        print(f"No previous app.py on port {port} — starting a single new process.")
        return

    print(
        "Stopping previous processes so one new process can start "
        f"(port {port}, PIDs: {', '.join(str(p) for p in sorted(to_kill))})…"
    )
    for pid in sorted(to_kill):
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                os.kill(pid, 15)
        except OSError:
            pass
    time.sleep(1.2)
    print("Previous processes closed.")


if __name__ == "__main__":
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    _stop_previous_app_processes(DASH_PORT)

    if is_configured():
        print("Testing SQL Server connection...")
        try:
            from db import get_connection
            conn = get_connection()
            conn.close()
            print("Connected OK")
        except Exception as e:
            print(f"Connection failed: {e}")
    else:
        print("No .env — open http://localhost:%s and configure in Settings." % DASH_PORT)

    from core.realtime import init_realtime, run_server

    init_realtime(app)
    if _REALTIME_WS:
        print("Realtime: Socket.IO activity ticks enabled (Interval fallback kept)")
    else:
        print("Realtime: Socket.IO disabled — pip install flask-socketio for Activity WS ticks")
    run_server(app, host=DASH_HOST, port=DASH_PORT, debug=False)
