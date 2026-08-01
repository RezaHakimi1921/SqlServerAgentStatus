"""Activity module layouts — Running Now + Blocking + Session Lookup."""
from __future__ import annotations

from dash import dcc, html

from core.formatters import fmt_duration_hms, fmt_int, fmt_running_label
from core.wait_resource import format_wait_resource_display
from modules.activity.glossary import tip_command, tip_status, tip_wait

ACTIVITY_INTERVAL_OPTIONS = [
    {"label": "Off", "value": "0"},
    {"label": "5s", "value": "5"},
    {"label": "10s", "value": "10"},
    {"label": "30s", "value": "30"},
    {"label": "60s", "value": "60"},
]


def _fmt_ms(ms) -> str:
    """Compact clock from ms (alias for shared formatter)."""
    return fmt_duration_hms(ms)


def _fmt_running_label(ms) -> str:
    return fmt_running_label(ms)


def _short_checked(ts) -> str:
    """HH:MM:SS for empty-state 'Last checked' so refresh ticks are obvious."""
    raw = (str(ts) if ts not in (None, "") else "").strip()
    if "T" in raw:
        try:
            return raw.split("T", 1)[1][:8]
        except Exception:
            pass
    return raw or "—"


def _tip(child, text: str):
    """Hover tip bubble (Persian glossary)."""
    if not text:
        return child
    return html.Span(
        className="tip",
        children=[
            child if isinstance(child, (str, int)) else child,
            html.Span(text, className="tip-bubble"),
        ],
    )


def _status_pill(status: str, blocked: bool = False):
    raw = (status or "—").strip() or "—"
    key = raw.lower()
    if blocked or key == "blocked":
        cls = "st-blocked"
        label = "blocked" if blocked and key != "blocked" else raw
        tip_key = "blocked"
    elif key == "running":
        cls, label, tip_key = "st-running", raw, key
    elif key == "runnable":
        cls, label, tip_key = "st-runnable", raw, key
    elif key == "suspended":
        cls, label, tip_key = "st-suspended", raw, key
    elif key == "sleeping":
        cls, label, tip_key = "st-sleeping", raw, key
    else:
        cls, label, tip_key = "st-other", raw, key
    return _tip(html.Span(label, className=f"status-pill {cls}"), tip_status(tip_key))


def _command_cell(command: str | None):
    raw = command or "—"
    return _tip(html.Span(raw, className="cmd-text"), tip_command(raw if raw != "—" else None))


def _wait_cell(wait_type: str | None):
    raw = wait_type or "—"
    return _tip(html.Span(raw, className="wait-text"), tip_wait(raw if raw != "—" else None))


def _wait_class(wait_ms) -> str:
    try:
        ms = int(wait_ms or 0)
    except (TypeError, ValueError):
        return ""
    if ms >= 300_000:
        return "wait-crit"
    if ms >= 60_000:
        return "wait-hot"
    if ms >= 10_000:
        return "wait-warn"
    return ""


def _health_tone(label: str, value, tab: str) -> str:
    lab = (label or "").lower()
    try:
        if isinstance(value, str) and ":" in value:
            parts = value.split(":")
            secs = int(parts[-1]) + int(parts[-2]) * 60
            if len(parts) == 3:
                secs += int(parts[0]) * 3600
            if secs >= 300:
                return "tone-crit"
            if secs >= 60:
                return "tone-hot"
            if secs >= 10:
                return "tone-warn"
            return "tone-ok"
        num = int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        if lab in ("status",) and str(value).lower() in ("suspended", "blocked"):
            return "tone-warn"
        return "tone-ok"

    if "blast" in lab:
        return "tone-crit" if num > 0 else "tone-ok"
    if "block" in lab or "head" in lab:
        if num >= 5:
            return "tone-crit"
        if num >= 1:
            return "tone-hot"
        return "tone-ok"
    if "running" in lab or "request" in lab:
        if num >= 50:
            return "tone-hot"
        if num >= 20:
            return "tone-warn"
        return "tone-ok"
    return "tone-ok"


def _sql_btn(session_id, sql: str, kind: str = "run", index: int = 0, *, title: str = None, label: str = None):
    """Open SQL modal. `sql` may be plain text or JSON {statement,batch,copy}."""
    import json
    sid = str(session_id)
    raw = sql or ""
    has = False
    if raw.strip().startswith("{"):
        try:
            data = json.loads(raw)
            has = bool((data.get("statement") or data.get("batch") or data.get("copy") or "").strip())
        except Exception:
            has = bool(raw.strip())
    else:
        has = bool(raw.strip())
    if title is None:
        tip = "مشاهده SQL" if has else "SQL ندارد"
    else:
        tip = title  # empty string => no native tooltip
    btn_children = label if label else "📄"
    btn_kwargs = dict(
        id={"type": "activity-sql-open", "kind": kind, "sid": sid, "i": index},
        className="sql-ico-btn" + ("" if has else " empty") + (" has-label" if label else ""),
        n_clicks=0,
        disabled=not has,
    )
    if tip:
        btn_kwargs["title"] = tip
    return html.Div(className="sql-cell", children=[
        html.Button(btn_children, **btn_kwargs),
        html.Div(
            raw,
            id={"type": "activity-sql-payload", "kind": kind, "sid": sid, "i": index},
            className="sql-payload-hidden",
        ),
    ])


def _interval_chips(selected="10"):
    chips = []
    for opt in ACTIVITY_INTERVAL_OPTIONS:
        active = str(opt["value"]) == str(selected)
        chips.append(
            html.Button(
                opt["label"],
                id={"type": "activity-interval-chip", "value": opt["value"]},
                className="activity-chip" + (" active" if active else ""),
                n_clicks=0,
            )
        )
    return chips


def build_activity_layout():
    return html.Div(
        className="activity-shell",
        children=[
            html.Div(className="activity-toolbar", children=[
                html.Div(className="activity-tabs", children=[
                    html.Button("Running Now", id="activity-tab-running",
                                className="activity-tab active", n_clicks=0),
                    html.Button("Blocking", id="activity-tab-blocking",
                                className="activity-tab", n_clicks=0),
                    html.Button("Session Lookup", id="activity-tab-lookup",
                                className="activity-tab", n_clicks=0,
                                title="جستجوی یک نشست با SessionId"),
                ]),
                html.Div(className="activity-controls", children=[
                    html.Div(className="activity-interval-group", children=[
                        html.Span("Auto refresh", className="activity-ctrl-label"),
                        html.Div(
                            id="activity-interval-chips",
                            className="activity-chip-row",
                            children=_interval_chips("10"),
                        ),
                    ]),
                    html.Button(
                        [html.Span("⏸", className="ctrl-ico"), html.Span("Pause", className="ctrl-txt")],
                        id="btn-activity-pause",
                        className="activity-ctrl-btn is-live",
                        n_clicks=0,
                        title="توقف به‌روزرسانی خودکار",
                    ),
                    html.Button(
                        [html.Span("↻", className="ctrl-ico"), html.Span("Refresh", className="ctrl-txt")],
                        id="btn-activity-refresh",
                        className="activity-ctrl-btn is-refresh",
                        n_clicks=0,
                        title="تازه‌سازی الان",
                    ),
                ]),
            ]),
            dcc.Store(id="activity-refresh-interval", data="10"),
            html.Div(id="activity-health-strip", className="health-strip"),
            html.Div(id="activity-last-refresh", className="activity-meta"),
            html.Div(
                id="session-lookup-bar",
                className="session-lookup-bar",
                style={"display": "none"},
                children=[
                    html.Div(className="session-lookup-field", children=[
                        html.Label("Session ID", htmlFor="input-session-id"),
                        dcc.Input(
                            id="input-session-id",
                            type="text",
                            inputMode="numeric",
                            placeholder="e.g. 115",
                            className="form-input",
                            debounce=False,
                            n_submit=0,
                            maxLength=10,
                        ),
                    ]),
                    html.Button(
                        [html.Span("Lookup", className="ctrl-txt"),
                         html.Span("🔍", className="ctrl-ico")],
                        id="btn-session-lookup",
                        className="activity-ctrl-btn is-refresh",
                        n_clicks=0,
                        title="جستجوی نشست (یا Enter)",
                    ),
                ],
            ),
            html.Div(id="activity-body", className="activity-body"),
            html.Div(
                id="activity-loading",
                className="activity-loading hidden",
                children=[
                    html.Div(className="activity-loading-card", children=[
                        html.Div(className="activity-loading-spinner"),
                        html.Div("Loading…", className="activity-loading-text"),
                    ]),
                ],
            ),
            dcc.Interval(id="interval-activity", interval=10_000, n_intervals=0, disabled=False),
            dcc.Store(id="store-activity-tab", data="running"),
            dcc.Store(id="store-activity-running", data=None),
            dcc.Store(id="store-activity-blocking", data=None),
            dcc.Store(id="store-activity-lookup", data=None),
        ],
    )


def render_health_strip(summary: dict, severity: str = "healthy", tab: str = "running"):
    if tab == "blocking":
        cards = [
            ("Blast radius", fmt_int(summary.get("blast_radius", 0))),
            ("Head blockers", fmt_int(summary.get("head_blockers", 0))),
            ("Chain age", fmt_duration_hms((summary.get("chain_age_sec") or 0) * 1000)),
        ]
    elif tab == "lookup":
        cards = [
            ("Session", summary.get("session_id", "—")),
            ("Status", summary.get("status") or "—"),
            ("Wait", _fmt_ms(summary.get("wait_ms", 0))),
        ]
    else:
        cards = [
            ("Running Requests", summary.get("running_requests", 0)),
            ("Blocked in list", summary.get("blocked_in_list", 0)),
            ("Longest Wait", _fmt_ms(summary.get("longest_wait_ms", 0))),
        ]
    return html.Div(
        className=f"health-strip sev-border-{severity}",
        children=[
            html.Div(className=f"health-card {_health_tone(label, value, tab)}", children=[
                html.Div(str(label), className="health-card-label"),
                html.Div(str(value), className="health-card-value"),
            ])
            for label, value in cards
        ],
    )


def _state_box(kind: str, title: str, detail: str = ""):
    return html.Div(className=f"state-box state-{kind}", children=[
        html.Div("✓" if kind == "empty" else "!", className="state-icon"),
        html.H3(title),
        html.Pre(detail, className="state-pre") if detail and kind == "error" else html.P(detail or ""),
    ])


def render_running_table(result: dict):
    status = (result or {}).get("status")
    if status == "permission_denied":
        return _state_box("error", "Permission required",
                          ((result.get("meta") or {}).get("hint") or "VIEW SERVER STATE required"))
    if status == "error":
        return _state_box("error", "Could not load running requests",
                          ((result.get("meta") or {}).get("hint") or "Query failed"))
    if status in (None, "empty") or not (result or {}).get("rows"):
        ts = (result or {}).get("timestamp") or "—"
        return _state_box("empty", "No active requests", f"Last checked: {_short_checked(ts)}")

    rows = result["rows"]
    body = []
    for i, r in enumerate(rows):
        sql = r.get("sql_text") or ""
        wait_ms = int(r.get("wait_time") or 0)
        sev = r.get("severity") or "healthy"
        blocked = int(r.get("blocking_session_id") or 0) > 0
        wcls = _wait_class(wait_ms)
        sid = r.get("session_id")
        elapsed = int(r.get("total_elapsed_time") or 0)
        body.append(html.Tr(className=f"sev-row-{sev}", children=[
            html.Td(str(sid), className="col-session"),
            html.Td(_status_pill(r.get("status") or "—", blocked=blocked), className="col-status"),
            html.Td(r.get("login_name") or "—", className="col-login"),
            html.Td(r.get("host_name") or "—", className="col-host"),
            html.Td(r.get("database_name") or "—", className="col-db"),
            html.Td(_command_cell(r.get("command")), className="col-cmd"),
            html.Td(_wait_cell(r.get("wait_type")), className="col-wait-type"),
            html.Td(fmt_duration_hms(wait_ms), className=f"col-wait-time num-ltr {wcls}".strip()),
            html.Td(fmt_duration_hms(elapsed), className="col-elapsed num-ltr"),
            html.Td(_sql_btn(sid, sql, kind="run", index=i), className="col-sql-ico"),
        ]))
    return html.Div(className="activity-table-wrap", children=[
        html.Table(className="activity-table", children=[
            html.Colgroup([
                html.Col(className="col-session"),
                html.Col(className="col-status"),
                html.Col(className="col-login"),
                html.Col(className="col-host"),
                html.Col(className="col-db"),
                html.Col(className="col-cmd"),
                html.Col(className="col-wait-type"),
                html.Col(className="col-wait-time"),
                html.Col(className="col-elapsed"),
                html.Col(className="col-sql-ico"),
            ]),
            html.Thead(html.Tr([
                html.Th("Session"), html.Th("Status"), html.Th("Login"), html.Th("Host"),
                html.Th("DB"), html.Th("Command"), html.Th("Wait type"), html.Th("Wait time"),
                html.Th("Elapsed"), html.Th("SQL"),
            ])),
            html.Tbody(body),
        ])
    ])


def render_blocking_table(result: dict):
    status = (result or {}).get("status")
    if status == "permission_denied":
        return _state_box("error", "Permission required",
                          ((result.get("meta") or {}).get("hint") or "VIEW SERVER STATE required"))
    if status == "error":
        return _state_box("error", "Could not load blocking",
                          ((result.get("meta") or {}).get("hint") or "Query failed"))
    if status in (None, "empty") or not (result or {}).get("rows"):
        ts = (result or {}).get("timestamp") or "—"
        return html.Div(className="state-box state-empty", children=[
            html.Div("✓", className="state-icon"),
            html.H3("No Blocking Detected"),
            html.P(f"Last checked: {_short_checked(ts)}"),
        ])

    button_index = [0]
    cards = [
        _render_blocking_tree(tree, button_index)
        for tree in ((result or {}).get("trees") or [])
    ]
    return html.Div(className="blocking-list blk-tree-list", children=cards)


def _render_blocking_tree(tree: dict, button_index: list[int]):
    head = tree.get("head") or {}
    direct_children = tree.get("children") or head.get("children") or []
    visible = direct_children[:2]
    overflow = direct_children[2:]

    descendants = [
        _render_blocking_node(child, button_index=button_index)
        for child in visible
    ]
    if overflow:
        count = len(overflow)
        descendants.append(html.Details(className="blk-more", children=[
            html.Summary(
                f"+ {fmt_int(count)} session دیگر under this root",
                className="blk-more-summary",
            ),
            html.Div(
                className="blk-rail blk-more-rail",
                children=[
                    _render_blocking_node(child, button_index=button_index)
                    for child in overflow
                ],
            ),
        ]))

    return html.Div(className="blk-tree", children=[
        html.Div(
            f"1 session affecting {fmt_int(tree.get('blast_radius', 0))} sessions",
            className="blk-root-blast",
        ),
        _render_blocking_node(
            head,
            is_head=True,
            age_sec=tree.get("chain_age_sec"),
            button_index=button_index,
        ),
        html.Div(className="blk-rail", children=descendants),
    ])


def _render_blocking_node(
    node: dict,
    *,
    button_index: list[int],
    is_head: bool = False,
    age_sec=None,
):
    index = button_index[0]
    button_index[0] += 1
    session_id = node.get("session_id")
    sql = (node.get("sql_snippet") or "").strip()
    login = node.get("login") or "—"
    resource = format_wait_resource_display(
        node.get("wait_resource_raw"),
        node.get("wait_object"),
    )

    if is_head:
        elapsed_sec = age_sec
        if elapsed_sec is None:
            elapsed_sec = node.get("request_elapsed_sec")
        timing = f"running {fmt_running_label((elapsed_sec or 0) * 1000)}"
        title = f"{login} — head blocker"
    else:
        timing = _format_blocking_wait(node.get("wait_sec"))
        title = login

    nested = [] if is_head else (node.get("children") or [])
    return html.Div(className="blk-node-wrap", children=[
        html.Div(className="blk-node is-head" if is_head else "blk-node", children=[
            html.Div(className="blk-node-top", children=[
                html.Div(className="blk-node-who", children=[
                    html.Span(f"SPID {session_id}", className="blk-badge"),
                    html.Span(title, className="blk-login"),
                ]),
                html.Span(timing, className="blk-timing"),
            ]),
            html.Div(className="blk-sql-row", children=[
                html.Code(sql or "No SQL text", className="blk-sql" + ("" if sql else " is-empty")),
                _sql_btn(session_id, sql, kind="blktree", index=index),
            ]),
            html.Div(className="blk-obj", title=resource, children=[
                html.Span("Object", className="blk-obj-label"),
                html.Span(resource, className="blk-obj-value"),
                _tip(
                    html.Span(node.get("wait_type") or "—", className="blk-wait-type"),
                    tip_wait(node.get("wait_type")),
                ) if not is_head else None,
            ]),
        ]),
        html.Div(
            className="blk-rail blk-rail-nested",
            children=[
                _render_blocking_node(child, button_index=button_index)
                for child in nested
            ],
        ) if nested else None,
    ])


def _format_blocking_wait(wait_sec) -> str:
    try:
        seconds = max(0.0, float(wait_sec or 0))
    except (TypeError, ValueError):
        return "—"
    if seconds >= 60:
        return f"{fmt_running_label(seconds * 1000)} wait"
    precision = 0 if seconds >= 10 or seconds.is_integer() else 1
    return f"{seconds:.{precision}f}s wait"


def _chain_nodes(chain: str, blocker, blocked):
    """Render full chain like 100 → 204 → 2 with head/tail emphasis."""
    parts = [p.strip() for p in (chain or "").split("->") if p.strip()]
    if len(parts) < 2:
        parts = [str(blocker), str(blocked)]
    nodes = []
    for i, part in enumerate(parts):
        if i:
            nodes.append(html.Span("→", className="arrow"))
        cls = "sid-mid"
        if i == 0:
            cls = "sid-blocker"
        elif i == len(parts) - 1:
            cls = "sid-blocked"
        nodes.append(html.Span(part, className=cls))
    return nodes


def _profile_row(label: str, value_node, tip: str = "", *, row_class: str = ""):
    lab = html.Span(label, className="profile-lbl")
    if tip:
        lab = _tip(lab, tip)
    cls = "profile-row" + (f" {row_class}" if row_class else "")
    return html.Div(className=cls, children=[
        lab,
        html.Div(value_node, className="profile-val"),
    ])


def _highlight_batch_nodes(batch: str, statement: str):
    """Render full batch with current statement highlighted."""
    from dash import html as _html

    batch = batch or ""
    statement = (statement or "").strip()
    if not batch.strip():
        return _html.Pre("(no batch text)", className="sql-modal-pre is-batch")
    if not statement:
        return _html.Pre(batch, className="sql-modal-pre is-batch")

    idx = batch.find(statement)
    if idx < 0:
        # Tolerate minor whitespace differences
        norm_b = " ".join(batch.split())
        norm_s = " ".join(statement.split())
        nidx = norm_b.find(norm_s)
        if nidx < 0:
            return _html.Pre(batch, className="sql-modal-pre is-batch")
        # Fall back to plain batch if we can't map offsets reliably
        return _html.Pre([
            _html.Span(batch, className="sql-batch-rest"),
            _html.Span(
                "\n\n/* current statement (whitespace differed): */\n",
                className="sql-batch-note",
            ),
            _html.Span(statement, className="sql-batch-active"),
        ], className="sql-modal-pre is-batch")

    before = batch[:idx]
    mid = batch[idx:idx + len(statement)]
    after = batch[idx + len(statement):]
    return _html.Pre([
        _html.Span(before, className="sql-batch-rest") if before else None,
        _html.Span(mid, className="sql-batch-active"),
        _html.Span(after, className="sql-batch-rest") if after else None,
    ], className="sql-modal-pre is-batch")


def render_session_lookup(result: dict = None):
    """Session Lookup — profile layout (not a wall of boxes)."""
    import json

    if result is None:
        return html.Div(className="state-box", children=[
            html.Div("◎", className="state-icon"),
            html.H3("Enter a SessionId"),
            html.P("Looks up one live session (DMVs) — WhoIsActive-style snapshot for that SPID."),
        ])

    status = (result or {}).get("status")
    if status == "permission_denied":
        return _state_box(
            "error",
            "Permission required",
            ((result.get("meta") or {}).get("hint") or "VIEW SERVER STATE required"),
        )
    if status == "error":
        return _state_box(
            "error",
            "Lookup failed",
            ((result.get("meta") or {}).get("hint") or "Query failed"),
        )
    if status in (None, "empty") or not (result or {}).get("rows"):
        sid = (result or {}).get("summary", {}).get("session_id") or "?"
        return _state_box(
            "empty",
            f"Session {sid} not found",
            "No matching row in dm_exec_sessions (session may have ended).",
        )

    r = result["rows"][0]
    blocked = int(r.get("blocking_session_id") or 0) > 0
    wait_ms = int(r.get("wait_time") or 0)
    wcls = _wait_class(wait_ms)
    sid = r.get("session_id")
    active = int(r.get("has_active_request") or 0) == 1
    wall_ms = int(r.get("elapsed_wall_ms") or r.get("total_elapsed_time") or 0)
    batch_sql = r.get("sql_text") or ""
    stmt_sql = (r.get("statement_text") or "").strip()
    req_start = r.get("request_start_time") or r.get("start_time")

    stmt_payload = json.dumps({
        "statement": stmt_sql,
        "batch": batch_sql,
        "copy": stmt_sql or batch_sql,
    }, ensure_ascii=False)

    hero = html.Div(className="session-profile-hero", children=[
        html.Div(className="sph-id", children=[
            html.Span("SESSION", className="sph-kicker"),
            html.Span(str(sid), className="sph-num"),
        ]),
        html.Div(className="sph-status", children=[
            _status_pill(r.get("status") or "—", blocked=blocked),
            html.Span(
                fmt_duration_hms(wall_ms) if active else _fmt_ms(wait_ms),
                className=f"sph-wait {wcls}".strip() + (" is-running" if active else ""),
                title="Elapsed" if active else (r.get("wait_type") or ""),
            ),
        ]),
        html.Div(className="sph-who", children=[
            html.Div(r.get("login_name") or "—", className="sph-login"),
            html.Div(
                f"{r.get('host_name') or '—'}  ·  {r.get('program_name') or '—'}",
                className="sph-sub",
            ),
        ]),
        _sql_btn(sid, batch_sql, kind="look", index=0, title="مشاهده کل Batch / SP"),
    ])

    identity_rows = [
        _profile_row("Database", r.get("database_name") or "—"),
        _profile_row("Client IP", r.get("client_net_address") or "—"),
        _profile_row("Login time", r.get("login_time") or "—"),
    ]
    if active:
        identity_rows.append(_profile_row("Request start", req_start or "—"))
        identity_rows.append(_profile_row(
            "Running for",
            html.Span(
                f"{fmt_duration_hms(wall_ms)}  ({_fmt_running_label(wall_ms)})",
                className="val wait-warn num-ltr",
            ),
        ))
    else:
        identity_rows.append(_profile_row(
            "Last request start",
            r.get("last_request_start_time") or "—",
        ))
        identity_rows.append(_profile_row(
            "Last request end",
            r.get("last_request_end_time") or "—",
        ))

    identity = html.Div(className="profile-card", children=[
        html.H4("Identity"),
        *identity_rows,
    ])

    stmt_btn = _sql_btn(
        sid,
        stmt_payload,
        kind="stmt",
        index=0,
        label="مشاهده statement",
        title="",  # no tooltip on this control
    )

    request = html.Div(className="profile-card", children=[
        html.H4("Request"),
        _profile_row("Command", _command_cell(r.get("command"))),
        _profile_row(
            "Statement now",
            stmt_btn,
            row_class="is-action",
        ),
        _profile_row("Wait type", _wait_cell(r.get("wait_type"))),
        _profile_row(
            "Wait",
            html.Span(fmt_duration_hms(wait_ms), className=f"val {wcls} num-ltr".strip()),
        ),
        _profile_row(
            "Blocking session",
            html.Span(
                str(r.get("blocking_session_id") or 0),
                className="val wait-crit" if blocked else "val",
            ),
        ),
        _profile_row(
            "% complete",
            r.get("percent_complete") if r.get("percent_complete") not in (None, 0) else "—",
        ),
        _profile_row("Open tran", fmt_int(r.get("open_tran_count") or 0)),
    ])

    resources = html.Div(className="profile-card", children=[
        html.H4("Resources"),
        _profile_row("CPU", html.Span(fmt_int(r.get("cpu_time") or 0), className="num-ltr")),
        _profile_row(
            "Elapsed",
            html.Span(fmt_duration_hms(wall_ms), className="num-ltr"),
        ),
        _profile_row(
            "Elapsed (DMV ms)",
            html.Span(fmt_int(r.get("total_elapsed_time") or 0), className="num-ltr"),
        ),
        _profile_row("Reads", html.Span(fmt_int(r.get("reads") or 0), className="num-ltr")),
        _profile_row("Writes", html.Span(fmt_int(r.get("writes") or 0), className="num-ltr")),
        _profile_row("Logical reads", html.Span(fmt_int(r.get("logical_reads") or 0), className="num-ltr")),
        _profile_row(
            "Used memory",
            html.Span(fmt_int(r.get("granted_query_memory") or 0), className="num-ltr"),
        ),
    ])

    return html.Div(className="session-profile", children=[
        hero,
        html.Div(className="session-profile-grid", children=[identity, request, resources]),
    ])
