"""Activity module layouts — Running Now + Blocking + Session Lookup."""
from __future__ import annotations

from dash import dcc, html

from core.formatters import fmt_duration_hms, fmt_int, fmt_running_label
from core.wait_resource import format_wait_resource_display
from modules.activity.glossary import tip_command, tip_status, tip_wait

ACTIVITY_INTERVAL_OPTIONS = [
    {"label": "Off", "value": "0"},
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


def _tip(child, text: str, *, mode: str = "bubble"):
    """
    Hover tip.
    mode=bubble: custom tip-bubble (Lookup / cards).
    mode=title: native title only — reliable inside overflow:auto tables.
    """
    if not text:
        return child
    if mode == "title":
        return html.Span(child, className="tip tip-native", title=text)
    return html.Span(
        className="tip",
        title=text,  # native fallback when bubble is clipped by scroll parents
        children=[
            child if isinstance(child, (str, int)) else child,
            html.Span(text, className="tip-bubble"),
        ],
    )


def _status_pill(status: str, blocked: bool = False, *, tip_mode: str = "bubble"):
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
    return _tip(
        html.Span(label, className=f"status-pill {cls}"),
        tip_status(tip_key),
        mode=tip_mode,
    )


def _command_cell(command: str | None, *, tip_mode: str = "bubble"):
    raw = command or "—"
    return _tip(
        html.Span(raw, className="cmd-text"),
        tip_command(raw if raw != "—" else None),
        mode=tip_mode,
    )


def _wait_cell(wait_type: str | None, *, tip_mode: str = "bubble"):
    raw = wait_type or "—"
    return _tip(
        html.Span(raw, className="wait-text"),
        tip_wait(raw if raw != "—" else None),
        mode=tip_mode,
    )


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
    if "head" in lab or "block" in lab:
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


def _sql_view_icon():
    """Code mark for SQL column — text glyph always paints (no broken empty box)."""
    return html.Span("</>", className="sql-ico-code", **{"aria-hidden": "true"})


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
        tip = "مشاهده جزئیات SQL" if has else "SQL ندارد"
    else:
        tip = title  # empty string => no native tooltip
    # Labeled = icon + text (hero); compact = icon only (tables)
    if label:
        btn_children = [
            _sql_view_icon(),
            html.Span(label, className="sql-ico-lbl"),
        ]
        extra = " has-label is-detail"
    else:
        btn_children = [_sql_view_icon()]
        extra = " is-icon"
    btn_kwargs = dict(
        id={"type": "activity-sql-open", "kind": kind, "sid": sid, "i": index},
        className="sql-ico-btn" + ("" if has else " empty") + extra,
        n_clicks=0,
        disabled=not has,
        **{"aria-label": tip or "مشاهده جزئیات SQL"},
    )
    if tip:
        btn_kwargs["title"] = tip
    return html.Div(className="sql-cell", children=[
        html.Button(btn_children, type="button", **btn_kwargs),
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


def build_activity_layout(locale: str | None = None):
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
            # Lookup: input first (PM — search before summary; avoid SPID thrice)
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
                         html.Span("⌕", className="ctrl-ico")],
                        id="btn-session-lookup",
                        className="activity-ctrl-btn is-refresh",
                        n_clicks=0,
                        title="جستجوی نشست (یا Enter)",
                    ),
                ],
            ),
            html.Div(id="activity-health-strip", className="health-strip"),
            html.Div(id="activity-last-refresh", className="activity-meta"),
            html.Div(id="activity-body-slot", children=[
                html.Div(id="activity-body", className="activity-body"),
            ]),
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
            dcc.Store(id="store-lookup-sid", data=None),
            dcc.Store(id="store-lookup-pulse-series", data=[]),
            # WS tick store lives in app.py root (store-ws-activity-tick)
        ],
    )


def render_health_strip(summary: dict, severity: str = "healthy", tab: str = "running"):
    if tab == "blocking":
        cards = [
            ("Blast radius", fmt_int(summary.get("blast_radius", 0))),
            ("Head blockers", fmt_int(summary.get("head_blockers", 0))),
            ("Chain age", fmt_duration_hms((summary.get("chain_age_sec") or 0) * 1000)),
            ("Longest Wait", _fmt_ms(summary.get("longest_wait_ms", 0))),
        ]
    elif tab == "lookup":
        # No top KPI strip — hero + metric boxes own the glance (avoids Session/Rows thrice)
        return html.Div(className="health-strip is-empty lookup-health")
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
            html.Td(
                html.Button(
                    str(sid),
                    id={"type": "run-lookup-spid", "sid": sid},
                    n_clicks=0,
                    type="button",
                    className="blk-badge blk-spid-btn",
                    title=f"Open Session Lookup for {sid}",
                ),
                className="col-session",
            ),
            html.Td(
                _status_pill(r.get("status") or "—", blocked=blocked, tip_mode="title"),
                className="col-status",
            ),
            html.Td(r.get("login_name") or "—", className="col-login"),
            html.Td(r.get("host_name") or "—", className="col-host"),
            html.Td(r.get("database_name") or "—", className="col-db"),
            html.Td(_command_cell(r.get("command"), tip_mode="title"), className="col-cmd"),
            html.Td(_wait_cell(r.get("wait_type"), tip_mode="title"), className="col-wait-type"),
            html.Td(fmt_duration_hms(wait_ms), className=f"col-wait-time num-ltr {wcls}".strip()),
            html.Td(fmt_duration_hms(elapsed), className="col-elapsed num-ltr"),
            html.Td(
                _sql_btn(sid, sql, kind="run", index=i, title="مشاهده متن SQL"),
                className="col-sql-ico",
            ),
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
    hint = ((result or {}).get("meta") or {}).get("resolve_hint")
    children = []
    if hint:
        children.append(html.Div(className="blk-resolve-hint", children=[
            html.Div(
                "نام جدول‌ها resolve نشده — به لاگین مانیتور در سطح SERVER این دسترسی را بده "
                "(فقط روی دیتابیس master کافی نیست):"
            ),
            html.Code("GRANT VIEW ANY DEFINITION TO [YourLogin];"),
            html.Div(
                "برای KEY lockها CONNECT روی دیتابیس‌های کاربر هم لازم است. "
                "تا آن موقع wait_resource به صورت خوانا نشان داده می‌شود.",
                style={"marginTop": "6px", "opacity": "0.9"},
            ),
        ]))
    children.extend(cards)
    return html.Div(className="blocking-list blk-tree-list", children=children, **{"dir": "ltr"})


def _blocking_child_rail(children: list, button_index: list[int], *, nested: bool = False):
    """Render direct children; collapse after 2 so deep trees stay scannable."""
    if not children:
        return None
    visible = children[:2]
    overflow = children[2:]
    nodes = [
        _render_blocking_node(child, button_index=button_index)
        for child in visible
    ]
    if overflow:
        count = len(overflow)
        nodes.append(html.Details(className="blk-more", children=[
            html.Summary(
                f"+ {fmt_int(count)} more sessions",
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
    cls = "blk-rail blk-rail-nested" if nested else "blk-rail"
    return html.Div(className=cls, children=nodes)


def _render_blocking_tree(tree: dict, button_index: list[int]):
    head = tree.get("head") or {}
    direct_children = tree.get("children") or head.get("children") or []
    max_wait = tree.get("max_wait_sec")
    wait_bit = (
        f" · longest wait {_format_blocking_wait(max_wait).replace(' wait', '')}"
        if max_wait
        else ""
    )

    return html.Div(className="blk-tree", **{"dir": "ltr"}, children=[
        html.Div(
            f"1 session affecting {fmt_int(tree.get('blast_radius', 0))} sessions{wait_bit}",
            className="blk-root-blast",
        ),
        _render_blocking_node(
            head,
            is_head=True,
            age_sec=tree.get("chain_age_sec"),
            button_index=button_index,
        ),
        _blocking_child_rail(direct_children, button_index, nested=False),
    ])


def _blocking_subline(node: dict, *, is_head: bool) -> html.Div | None:
    host = (node.get("host") or "").strip()
    program = (node.get("program") or "").strip()
    db = (node.get("database_name") or "").strip()
    open_tran = int(node.get("open_tran") or 0)
    bits = []
    if host:
        bits.append(host)
    if program:
        bits.append(program if len(program) <= 42 else program[:39] + "…")
    if db:
        bits.append(db)
    if is_head or open_tran > 0:
        bits.append(f"open_tran={fmt_int(open_tran)}")
    if not bits:
        return None
    return html.Div(" · ".join(bits), className="blk-subline", title=" · ".join(bits))


def _spid_lookup_btn(session_id) -> html.Button:
    sid = str(session_id)
    return html.Button(
        f"SPID {sid}",
        id={"type": "blk-lookup-spid", "sid": sid},
        n_clicks=0,
        className="blk-badge blk-spid-btn",
        title=f"Open Session Lookup for {sid}",
        type="button",
    )


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
    cmd = (node.get("command") or "").strip()
    action_tag = _command_action_tag(cmd, sql, is_head=is_head)
    return html.Div(className="blk-node-wrap", children=[
        html.Div(className="blk-node is-head" if is_head else "blk-node", children=[
            html.Div(className="blk-node-top", children=[
                html.Div(className="blk-node-who", children=[
                    _spid_lookup_btn(session_id),
                    html.Span(title, className="blk-login"),
                    action_tag,
                ]),
                html.Span(timing, className="blk-timing"),
            ]),
            _blocking_subline(node, is_head=is_head),
            html.Div(className="blk-sql-row", children=[
                html.Code(
                    sql or ("No SQL text — idle / open transaction?" if is_head else "No SQL text"),
                    className="blk-sql" + ("" if sql else " is-empty"),
                ),
                _sql_btn(session_id, sql, kind="blktree", index=index),
            ]),
            html.Div(className="blk-obj", children=[
                html.Span("Object", className="blk-obj-label"),
                html.Span(resource or "—", className="blk-obj-value"),
                html.Span("|", className="blk-obj-sep") if not is_head else None,
                _tip(
                    html.Span(node.get("wait_type") or "—", className="blk-wait-type"),
                    tip_wait(node.get("wait_type")),
                ) if not is_head else None,
            ]),
        ]),
        _blocking_child_rail(nested, button_index, nested=True),
    ])


def extract_index_op(sql: str | None) -> dict | None:
    """
    Parse CREATE / ALTER INDEX REBUILD|REORGANIZE / DROP INDEX.
    Returns op metadata for Lookup + SQL modal cards.
    """
    import re

    if not sql or not str(sql).strip():
        return None
    text = str(sql)
    sniff = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    sniff = re.sub(r"--[^\n]*", " ", sniff)

    def _clean_ident(name: str) -> str:
        parts = []
        for p in re.split(r"\.", (name or "").strip()):
            p = p.strip()
            if p.startswith("[") and p.endswith("]"):
                p = p[1:-1]
            elif p.startswith('"') and p.endswith('"'):
                p = p[1:-1]
            if p:
                parts.append(p)
        return ".".join(parts)

    part = r"(?:\[[^\]]+\]|\"[^\"]+\"|\w+)"
    ident = rf"(?:{part}(?:\.{part}){{0,3}})"

    def _parse_with(blob: str | None) -> dict[str, str]:
        opts: dict[str, str] = {}
        if not blob:
            return opts
        for piece in re.split(r",", blob):
            piece = piece.strip()
            if not piece:
                continue
            if "=" in piece:
                k, v = piece.split("=", 1)
                opts[k.strip().upper()] = v.strip().strip("'\"")
            else:
                opts[piece.upper()] = "ON"
        return opts

    def _opt_chips(opts: dict[str, str]) -> list[str]:
        prefer = (
            "ONLINE", "MAXDOP", "SORT_IN_TEMPDB", "RESUMABLE", "FILLFACTOR",
            "DATA_COMPRESSION", "DROP_EXISTING", "PAD_INDEX", "ALLOW_ROW_LOCKS",
            "ALLOW_PAGE_LOCKS", "MAX_DURATION", "XML_COMPRESSION",
        )
        chips = []
        seen = set()
        for k in prefer:
            if k in opts:
                chips.append(f"{k}={opts[k]}" if opts[k] not in ("ON", "OFF", "") else f"{k} {opts[k]}")
                seen.add(k)
        for k, v in opts.items():
            if k in seen:
                continue
            chips.append(f"{k}={v}" if v not in ("ON", "OFF", "") else f"{k} {v}")
        return chips[:10]

    # ALTER INDEX … REBUILD / REORGANIZE
    m = re.search(
        rf"\bALTER\s+INDEX\s+({ident}|ALL)\s+ON\s+({ident})\s+(REBUILD|REORGANIZE)\b"
        rf"(?:[\s\S]*?\bWITH\s*\(([^)]*)\))?",
        sniff,
        flags=re.I,
    )
    if m:
        op = m.group(3).upper()
        opts = _parse_with(m.group(4))
        table = _clean_ident(m.group(2))
        idx = _clean_ident(m.group(1))
        return {
            "op": op.lower(),
            "action_label": f"INDEX {op}",
            "index_name": idx,
            "table": table,
            "table_short": table.split(".")[-1] if table else "",
            "kind": "",
            "columns": "",
            "include": "",
            "options": opts,
            "option_chips": _opt_chips(opts),
        }

    # DROP INDEX
    m = re.search(
        rf"\bDROP\s+INDEX\s+({ident})\s+ON\s+({ident})\b",
        sniff,
        flags=re.I,
    )
    if m:
        table = _clean_ident(m.group(2))
        return {
            "op": "drop",
            "action_label": "DROP INDEX",
            "index_name": _clean_ident(m.group(1)),
            "table": table,
            "table_short": table.split(".")[-1] if table else "",
            "kind": "",
            "columns": "",
            "include": "",
            "options": {},
            "option_chips": [],
        }

    # CREATE [UNIQUE] [CLUSTERED|NONCLUSTERED] [COLUMNSTORE] INDEX … ON … (…)
    m = re.search(
        rf"\bCREATE\s+"
        rf"(?:(UNIQUE)\s+)?"
        rf"(?:(CLUSTERED|NONCLUSTERED)\s+)?"
        rf"(?:(COLUMNSTORE)\s+)?"
        rf"INDEX\s+({ident})\s+ON\s+({ident})"
        rf"(?:\s*\(([^)]*)\))?"
        rf"(?:\s*INCLUDE\s*\(([^)]*)\))?"
        rf"(?:[\s\S]*?\bWITH\s*\(([^)]*)\))?",
        sniff,
        flags=re.I,
    )
    if m:
        bits = [b for b in (m.group(1), m.group(2), m.group(3)) if b]
        kind = " ".join(x.upper() for x in bits) or "INDEX"
        opts = _parse_with(m.group(8))
        table = _clean_ident(m.group(5))
        cols = re.sub(r"\s+", " ", (m.group(6) or "").strip())
        include = re.sub(r"\s+", " ", (m.group(7) or "").strip())
        return {
            "op": "create",
            "action_label": "CREATE INDEX",
            "index_name": _clean_ident(m.group(4)),
            "table": table,
            "table_short": table.split(".")[-1] if table else "",
            "kind": kind,
            "columns": cols,
            "include": include,
            "options": opts,
            "option_chips": _opt_chips(opts),
        }

    return None


def extract_dml_target(sql: str | None) -> dict | None:
    """
    Best-effort primary DML target: {verb, table, table_short}.
    Supports 1–4 part names (db.schema.table).
    Handles UPDATE … FROM …, UPDATE t SET, INSERT INTO, DELETE FROM, MERGE.
    """
    import re

    if not sql or not str(sql).strip():
        return None
    text = str(sql)
    sniff = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    sniff = re.sub(r"--[^\n]*", " ", sniff)

    _SCHEMA_ONLY = frozenset({
        "dbo", "sys", "guest", "INFORMATION_SCHEMA", "information_schema",
    })

    def _parts(name: str) -> list[str]:
        out = []
        for p in re.split(r"\.", name.strip()):
            p = p.strip()
            if p.startswith("[") and p.endswith("]"):
                p = p[1:-1]
            elif p.startswith('"') and p.endswith('"'):
                p = p[1:-1]
            if p:
                out.append(p)
        return out

    def _clean(name: str) -> str:
        return ".".join(_parts(name))

    # db.schema.table or schema.table or table (up to 4 parts)
    part = r"(?:\[[^\]]+\]|\"[^\"]+\"|\w+)"
    ident = rf"(?:{part}(?:\.{part}){{0,3}})"

    patterns = [
        # UPDATE TOP (@n) alias SET … FROM db.schema.Table
        (
            "UPDATE",
            rf"\bUPDATE\b(?:\s+TOP\s*\([^)]*\))?\s+{ident}\s+SET\b[\s\S]*?\bFROM\b\s+({ident})",
        ),
        # UPDATE dbo.Table SET
        (
            "UPDATE",
            rf"\bUPDATE\b(?:\s+TOP\s*\([^)]*\))?\s+({ident})\s+SET\b",
        ),
        ("INSERT", rf"\bINSERT\b\s+INTO\s+({ident})"),
        ("DELETE", rf"\bDELETE\b\s+FROM\s+({ident})"),
        ("DELETE", rf"\bDELETE\b\s+({ident})\s+FROM\b"),
        ("MERGE", rf"\bMERGE\b\s+(?:INTO\s+)?({ident})"),
        ("TRUNCATE", rf"\bTRUNCATE\b\s+TABLE\s+({ident})"),
    ]
    for verb, pat in patterns:
        m = re.search(pat, sniff, flags=re.I)
        if not m:
            continue
        table = _clean(m.group(1))
        if not table:
            continue
        parts = _parts(table)
        leaf = parts[-1] if parts else ""
        # Skip bare aliases / incomplete captures (…CustomerClub.dbo)
        if verb == "UPDATE" and len(parts) == 1 and len(leaf) <= 2:
            continue
        if leaf.lower() in {s.lower() for s in _SCHEMA_ONLY}:
            continue
        return {
            "verb": verb,
            "table": table,
            "table_short": leaf,
        }
    return None


def _sql_highlight_nodes(sql: str, *, emphasize_table: str | None = None):
    """Tokenize SQL for dark IDE-style colors (keywords / strings / vars / target table)."""
    import re

    if not sql:
        return [html.Span("(empty)", className="sql-tok-muted")]

    keywords = {
        "ADD", "ALL", "ALTER", "AND", "ANY", "AS", "ASC", "AUTHORIZATION", "BACKUP", "BEGIN",
        "BETWEEN", "BREAK", "BROWSE", "BULK", "BY", "CASCADE", "CASE", "CHECK", "CHECKPOINT",
        "CLOSE", "CLUSTERED", "COALESCE", "COLLATE", "COLUMN", "COMMIT", "COMPUTE", "CONSTRAINT",
        "CONTAINS", "CONTINUE", "CONVERT", "CREATE", "CROSS", "CURRENT", "CURRENT_DATE",
        "CURRENT_TIME", "CURRENT_TIMESTAMP", "CURSOR", "DATABASE", "DBCC", "DEALLOCATE",
        "DECLARE", "DEFAULT", "DELETE", "DENY", "DESC", "DISK", "DISTINCT", "DISTRIBUTED",
        "DOUBLE", "DROP", "DUMP", "ELSE", "END", "ERRLVL", "ESCAPE", "EXCEPT", "EXEC",
        "EXECUTE", "EXISTS", "EXIT", "EXTERNAL", "FETCH", "FILE", "FILLFACTOR", "FOR",
        "FOREIGN", "FREETEXT", "FROM", "FULL", "FUNCTION", "GOTO", "GRANT", "GROUP", "HAVING",
        "HOLDLOCK", "IDENTITY", "IF", "IN", "INDEX", "INNER", "INSERT", "INTERSECT", "INTO",
        "IS", "JOIN", "KEY", "KILL", "LEFT", "LIKE", "LINENO", "LOAD", "MERGE", "NATIONAL",
        "NOCHECK", "NONCLUSTERED", "NOT", "NULL", "NULLIF", "OF", "OFF", "OFFSETS", "ON",
        "OPEN", "OPTION", "OR", "ORDER", "OUTER", "OVER", "PERCENT", "PLAN", "PRECISION",
        "PRIMARY", "PRINT", "PROC", "PROCEDURE", "PUBLIC", "RAISERROR", "READ", "READTEXT",
        "RECONFIGURE", "REFERENCES", "REPLICATION", "RESTORE", "RESTRICT", "RETURN",
        "REVERT", "REVOKE", "RIGHT", "ROLLBACK", "ROWCOUNT", "ROWGUIDCOL", "RULE", "SAVE",
        "SCHEMA", "SECURITYAUDIT", "SELECT", "SEMANTICKEYPHRASETABLE",
        "SEMANTICSIMILARITYDETAILSTABLE", "SEMANTICSIMILARITYTABLE", "SESSION_USER", "SET",
        "SETUSER", "SHUTDOWN", "SOME", "STATISTICS", "SYSTEM_USER", "TABLE", "TABLESAMPLE",
        "TEXTSIZE", "THEN", "TO", "TOP", "TRAN", "TRANSACTION", "TRIGGER", "TRUNCATE",
        "TRY_CONVERT", "TSEQUAL", "UNION", "UNIQUE", "UPDATE", "UPDATETEXT", "USE", "USER",
        "VALUES", "VARYING", "VIEW", "WAITFOR", "WHEN", "WHERE", "WHILE", "WITH", "WITHIN",
        "WRITETEXT",
    }

    emp = (emphasize_table or "").strip()
    emp_parts = [p.lower() for p in emp.split(".") if p] if emp else []
    emp_leaf = emp_parts[-1] if emp_parts else ""

    token_re = re.compile(
        r"(--[^\n]*|/\*[\s\S]*?\*/|"
        r"N?'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|"
        r"\[[^\]]*\]|"
        r"@@?\w+|"
        r"\b\d+(?:\.\d+)?\b|"
        r"\b[A-Za-z_][\w]*\b|"
        r"\s+|.)"
    )

    nodes = []
    for tok in token_re.findall(sql):
        if not tok:
            continue
        if tok.startswith("--") or tok.startswith("/*"):
            nodes.append(html.Span(tok, className="sql-tok-comment"))
        elif tok.startswith("'") or tok.startswith("N'") or tok.startswith('"'):
            nodes.append(html.Span(tok, className="sql-tok-string"))
        elif tok.startswith("@"):
            nodes.append(html.Span(tok, className="sql-tok-var"))
        elif tok[:1].isdigit():
            nodes.append(html.Span(tok, className="sql-tok-num"))
        elif tok.startswith("["):
            inner = tok[1:-1]
            cls = "sql-tok-table" if emp_leaf and inner.lower() == emp_leaf else "sql-tok-ident"
            nodes.append(html.Span(tok, className=cls))
        elif re.fullmatch(r"[A-Za-z_][\w]*", tok):
            up = tok.upper()
            if up in keywords:
                nodes.append(html.Span(tok, className="sql-tok-kw"))
            elif emp_leaf and tok.lower() == emp_leaf:
                nodes.append(html.Span(tok, className="sql-tok-table"))
            else:
                nodes.append(html.Span(tok, className="sql-tok-ident"))
        else:
            nodes.append(html.Span(tok, className="sql-tok-punct"))
    return nodes


def _sql_statement_panel(sql: str | None, *, target: dict | None = None):
    """Statement box with target-table header + syntax colors."""
    text = (sql or "").strip()
    table = (target or {}).get("table") if target else None
    short = (target or {}).get("table_short") if target else None
    verb = (target or {}).get("verb") if target else None
    head = None
    if verb and table:
        head = html.Div(className="sql-stmt-head", children=[
            html.Span(verb, className="sql-stmt-verb"),
            html.Span("·", className="sql-stmt-dot"),
            html.Span(short or table, className="sql-stmt-table num-ltr"),
            html.Span(table, className="sql-stmt-table-full num-ltr") if short and short != table else None,
        ])
    elif table:
        head = html.Div(className="sql-stmt-head", children=[
            html.Span(table, className="sql-stmt-table num-ltr"),
        ])
    body = (
        _sql_highlight_nodes(text, emphasize_table=table)
        if text
        else [html.Span("(statement not available — session may be Sleeping)", className="sql-tok-muted")]
    )
    return html.Div(className="sql-stmt-panel", children=[
        head,
        html.Pre(body, className="sql-modal-pre is-statement has-tokens"),
    ])


def render_index_op_panel(idx: dict | None):
    """Compact cards: what index op, on which table, WITH options."""
    if not idx:
        return None
    chips = [
        html.Span(c, className="index-opt-chip")
        for c in (idx.get("option_chips") or [])
    ]
    facts = []
    if idx.get("kind"):
        facts.append(("Type", idx["kind"]))
    if idx.get("index_name"):
        facts.append(("Index", idx["index_name"]))
    if idx.get("table"):
        facts.append(("Table", idx["table"]))
    if idx.get("columns"):
        facts.append(("Key cols", idx["columns"]))
    if idx.get("include"):
        facts.append(("INCLUDE", idx["include"]))

    fact_nodes = [
        html.Div(className="index-fact", children=[
            html.Span(lab, className="index-fact-lbl"),
            html.Span(val, className="index-fact-val num-ltr"),
        ])
        for lab, val in facts
    ]
    return html.Div(className="index-op-panel", children=[
        html.Div(className="index-op-head", children=[
            html.Span(idx.get("action_label") or "INDEX", className="index-op-action"),
            html.Span(
                "در حال ساخت / نگهداری ایندکس",
                className="index-op-hint",
            ),
        ]),
        html.Div(className="index-fact-grid", children=fact_nodes) if fact_nodes else None,
        html.Div(className="index-opt-row", children=chips) if chips else None,
    ])


def _command_action_tag(command: str | None, sql: str | None, *, is_head: bool = False):
    """Bright action chip: CREATE INDEX / UPDATE dbo.T / SELECT / IDLE …"""
    import re

    raw = (command or "").strip().upper()
    text = (sql or "").lstrip()
    # Strip block/line comments for keyword sniff
    sniff = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    sniff = re.sub(r"--[^\n]*", " ", sniff)
    sniff_u = sniff.upper()
    index_op = extract_index_op(text)
    target = extract_dml_target(text)

    def from_sql() -> tuple[str, str] | None:
        if index_op:
            return index_op.get("action_label") or "CREATE INDEX", "ddl"
        for key, t in (
            ("MERGE", "write"),
            ("UPDATE", "write"),
            ("INSERT", "write"),
            ("DELETE", "write"),
            ("TRUNCATE", "write"),
            ("SELECT", "read"),
            ("EXECUTE", "exec"),
            ("EXEC ", "exec"),
            ("CREATE", "ddl"),
            ("ALTER", "ddl"),
            ("DROP", "ddl"),
            ("BACKUP", "maint"),
            ("RESTORE", "maint"),
            ("WAITFOR", "idle"),
        ):
            if re.search(rf"(^|\s){re.escape(key.strip())}\b", sniff_u):
                label = "EXECUTE" if key.startswith("EXEC") else key.strip()
                return label, t
        return None

    inferred = from_sql()
    label = None
    tone = "other"

    if index_op and (
        not raw
        or raw in ("SLEEPING", "AWAITING COMMAND", "SLEEPING / OPEN TRAN", "CREATE", "ALTER", "DROP", "EXECUTE", "EXEC")
        or raw.startswith("CREATE")
        or raw.startswith("ALTER")
    ):
        label, tone = index_op.get("action_label") or "CREATE INDEX", "ddl"
    elif not raw or raw in ("SLEEPING", "AWAITING COMMAND", "SLEEPING / OPEN TRAN"):
        if inferred:
            label, tone = inferred
        elif is_head and (not sniff_u.strip()):
            label, tone = "IDLE + OPEN TRAN", "idle"
        else:
            label, tone = "SLEEPING", "idle"
    elif raw in ("EXECUTE", "EXEC") and inferred and inferred[0] not in ("EXECUTE",):
        # SP running — show the real DML/DDL inside when visible in text
        label, tone = inferred
    else:
        for key, t in (
            ("UPDATE", "write"), ("INSERT", "write"), ("DELETE", "write"),
            ("MERGE", "write"), ("SELECT", "read"), ("EXECUTE", "exec"),
            ("CREATE", "ddl"), ("ALTER", "ddl"), ("DROP", "ddl"),
            ("TRUNCATE", "write"), ("BACKUP", "maint"), ("RESTORE", "maint"),
            ("WAITFOR", "idle"),
        ):
            if raw == key or raw.startswith(key + " ") or raw.startswith(key):
                label, tone = key, t
                break
        if label is None:
            if inferred:
                label, tone = inferred
            else:
                label, tone = (raw[:18] + "…") if len(raw) > 18 else raw, "other"
        # Prefer precise index label over bare CREATE/ALTER
        if index_op and label in ("CREATE", "ALTER", "DROP"):
            label, tone = index_op.get("action_label") or label, "ddl"

    # Append short table name on write chips (full name in tip / title)
    chip_title = None
    if index_op:
        chip_title = " · ".join(
            x for x in (
                index_op.get("action_label"),
                index_op.get("kind"),
                index_op.get("index_name"),
                index_op.get("table"),
            ) if x
        )
        short_tbl = index_op.get("table_short") or ""
        if short_tbl and short_tbl.upper() not in (label or "").upper():
            label = f"{label} {short_tbl}"
    elif (
        target
        and target.get("table")
        and label in ("UPDATE", "INSERT", "DELETE", "MERGE", "TRUNCATE")
    ):
        short = target.get("table_short") or target["table"].split(".")[-1]
        chip_title = f"{label} {target['table']}"
        label = f"{label} {short}"

    tip_key = "AWAITING COMMAND" if label == "IDLE + OPEN TRAN" else (target or {}).get("verb") or label
    if tip_key not in (
        "UPDATE", "INSERT", "DELETE", "MERGE", "TRUNCATE", "SELECT", "EXECUTE",
        "CREATE", "ALTER", "DROP", "BACKUP", "RESTORE", "WAITFOR", "AWAITING COMMAND",
    ):
        tip_key = (label.split()[0] if label else label)
    tip = tip_command(tip_key if tip_key != "CREATE INDEX" else "CREATE")
    if label == "IDLE + OPEN TRAN":
        tip = "تراکنش باز مانده بدون درخواست فعال — معمولاً علت Head Blocker است."
    elif index_op:
        bits = [
            index_op.get("action_label") or "INDEX",
            index_op.get("kind"),
            f"ایندکس: {index_op['index_name']}" if index_op.get("index_name") else "",
            f"جدول: {index_op['table']}" if index_op.get("table") else "",
        ]
        if index_op.get("option_chips"):
            bits.append(" · ".join(index_op["option_chips"][:4]))
        tip = " — ".join(b for b in bits if b)
    elif target and target.get("table"):
        tip = (tip or "DML") + f" — جدول هدف: \u200e{target['table']}"
    return _tip(
        html.Span(label, className=f"blk-action tone-{tone}", title=chip_title or label),
        tip,
    )


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


def _time_val(text, kind: str = "login") -> html.Span:
    """Semantic clock colors: login (past) / request (start) / now (live)."""
    cls = {
        "login": "val num-ltr val-time-login",
        "request": "val num-ltr val-time-request",
        "now": "val num-ltr val-time-now",
        "end": "val num-ltr val-time-login",
    }.get(kind, "val num-ltr val-time-login")
    return html.Span(text or "—", className=cls)


def _format_client_endpoint(r: dict):
    """
    Which SQL Server this Lookup is on.

    Prefer the configured connection target (Settings / SQL_SERVER) — that is the
    host the monitor is watching (e.g. 192.168.210.125). Session local_net_address
    can be another NIC / Shared Memory null and previously showed the wrong IP.
    """
    from core.connection import active_server_info

    try:
        info = active_server_info() or {}
        configured = (info.get("server") or info.get("name") or "").strip()
    except Exception:
        configured = ""

    instance = (str(r.get("instance_name") or "")).strip()
    machine = (str(r.get("machine_name") or "")).strip()
    monitor_ip = (str(r.get("monitor_local_address") or "")).strip()
    sess_ip = (str(r.get("local_net_address") or "")).strip()
    lport = r.get("local_tcp_port")

    primary = configured or monitor_ip or sess_ip or instance or "—"

    # Secondary: instance name if different from primary host string
    sub_bits = []
    if instance and instance.lower() not in primary.lower():
        sub_bits.append(instance)
    elif machine and machine.lower() not in primary.lower():
        sub_bits.append(machine)
    # Only mention listen IP when it differs from configured target (multi-NIC)
    listen = monitor_ip or sess_ip
    if listen and configured and listen not in configured and listen != primary:
        port_s = f":{lport}" if lport not in (None, "", 0, "0") else ""
        sub_bits.append(f"listen {listen}{port_s}")

    children = [
        html.Span(primary, className="val num-ltr client-ip-server"),
    ]
    if sub_bits:
        children.append(
            html.Div(" · ".join(sub_bits), className="client-ip-server-sub num-ltr")
        )
    tip = (
        "آدرس سروری که مانیتور به آن وصل است (تنظیمات SQL_SERVER). "
        "اگر اشتباه است، در Settings همان IP سرور (مثلاً …125) را تنظیم کن."
    )
    return _tip(html.Div(children, className="client-ip-block"), tip)


def _highlight_batch_nodes(batch: str, statement: str):
    """Render full batch with current statement highlighted + syntax colors."""
    from dash import html as _html

    batch = batch or ""
    statement = (statement or "").strip()
    target = extract_dml_target(statement or batch)
    table = (target or {}).get("table")

    if not batch.strip():
        return _html.Pre("(no batch text)", className="sql-modal-pre is-batch has-tokens")
    if not statement:
        return _html.Pre(
            _sql_highlight_nodes(batch, emphasize_table=table),
            className="sql-modal-pre is-batch has-tokens",
        )

    idx = batch.find(statement)
    if idx < 0:
        return _html.Pre([
            _html.Span(
                _sql_highlight_nodes(batch, emphasize_table=table),
                className="sql-batch-rest",
            ),
            _html.Span(
                "\n\n/* current statement (whitespace differed): */\n",
                className="sql-batch-note",
            ),
            _html.Span(
                _sql_highlight_nodes(statement, emphasize_table=table),
                className="sql-batch-active",
            ),
        ], className="sql-modal-pre is-batch has-tokens")

    before = batch[:idx]
    mid = batch[idx:idx + len(statement)]
    after = batch[idx + len(statement):]
    return _html.Pre([
        _html.Span(
            _sql_highlight_nodes(before, emphasize_table=table),
            className="sql-batch-rest",
        ) if before else None,
        _html.Span(
            _sql_highlight_nodes(mid, emphasize_table=table),
            className="sql-batch-active",
        ),
        _html.Span(
            _sql_highlight_nodes(after, emphasize_table=table),
            className="sql-batch-rest",
        ) if after else None,
    ], className="sql-modal-pre is-batch has-tokens")


def render_request_ended_note(*, end_ts=None, open_tran: int = 0):
    """
    Compact neutral note: request is no longer running.
    DMVs cannot tell successful finish apart from user Cancel (SSMS Stop).
    """
    warn = int(open_tran or 0) > 0
    end_disp = end_ts or "—"
    title = "تراکنش هنوز باز است" if warn else "دیگر در حال اجرا نیست"
    sub = (
        f"پایان request: {end_disp} · open_tran={fmt_int(open_tran)}"
        if warn
        else f"تمام یا Cancel · پایان request: {end_disp}"
    )
    tip = (
        "Request در DMV بسته شده، ولی open transaction مانده — "
        "ممکن است Cancel ناقص یا idle با تراکنش باز باشد."
        if warn
        else (
            "از sys.dm_exec_requests دیگر فعال نیست. "
            "اتمام موفق و Cancel کاربر (مثلاً Stop در SSMS) از این DMV یکسان دیده می‌شوند؛ "
            "بنابراین «موفق تمام شد» ادعا نمی‌کنیم."
        )
    )
    return html.Div(
        className="session-ended-note" + (" is-warn" if warn else ""),
        title=tip,
        children=[
            html.Span("ENDED", className="session-ended-badge"),
            html.Div(className="session-ended-copy", children=[
                html.Span(title, className="session-ended-title"),
                html.Span(sub, className="session-ended-sub num-ltr"),
            ]),
        ],
    )


def render_session_lookup(result: dict = None, pulse_series: list | None = None):
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

    obj_schema = (r.get("sql_object_schema") or "").strip()
    obj_name = (r.get("sql_object_name") or "").strip()
    sql_object = f"{obj_schema}.{obj_name}" if obj_schema and obj_name else (obj_name or "")

    open_tran = int(r.get("open_tran_count") or 0)

    stmt_payload = json.dumps({
        "statement": stmt_sql,
        "batch": batch_sql,
        "copy": stmt_sql or batch_sql,
        "progress": r.get("progress") or {},
        "command": r.get("command"),
        "percent_complete": r.get("percent_complete"),
        "status": r.get("status"),
        "has_active_request": active,
        "sql_object": sql_object,
        "last_request_end_time": r.get("last_request_end_time"),
        "open_tran_count": open_tran,
    }, ensure_ascii=False)

    action_tag = _command_action_tag(r.get("command"), stmt_sql or batch_sql, is_head=False)

    status_key = (r.get("status") or "").strip().lower()
    is_executing = active and status_key not in ("sleeping", "dormant", "background", "")
    progress = r.get("progress") or {}
    # Sleeping ≠ success. Cancel in SSMS also ends the request the same way in DMVs.
    request_ended = (
        (not is_executing)
        and status_key in ("sleeping", "dormant", "")
        and bool(r.get("last_request_end_time"))
    )

    eta = compute_finish_eta(
        rows_done=int(progress.get("rows_done") or 0),
        rows_est=int(progress.get("rows_est") or 0),
        elapsed_ms=wall_ms,
        percent_complete=r.get("percent_complete"),
        status=r.get("status"),
        has_active_request=active,
    )

    # Hero: who + status; statement opens from the doc icon (no separate Request CTA)
    hero = html.Div(
        className="session-profile-hero" + (" is-ended" if request_ended else ""),
        children=[
            html.Div(className="sph-top", children=[
                html.Div(className="sph-id", children=[
                    html.Span("SESSION", className="sph-kicker"),
                    html.Span(str(sid), className="sph-num"),
                ]),
                html.Div(className="sph-status", children=[
                    _status_pill(r.get("status") or "—", blocked=blocked),
                    (
                        html.Span(
                            "ENDED",
                            className="status-pill st-ended"
                            + (" is-open-tran" if open_tran > 0 else ""),
                            title=(
                                "دیگر request فعال نیست. DMV بین اتمام موفق و Cancel "
                                "(مثل Stop در SSMS) فرق نمی‌گذارد."
                            ),
                        )
                        if request_ended else None
                    ),
                    action_tag,
                    html.Span(
                        fmt_duration_hms(wall_ms) if is_executing else _fmt_ms(wait_ms),
                        className=(
                            f"sph-wait {wcls}".strip()
                            + (" is-running" if status_key == "running" else "")
                            + (" is-suspended" if status_key == "suspended" else "")
                        ),
                    ),
                ]),
                html.Div(className="sph-who", children=[
                    html.Div(r.get("login_name") or "—", className="sph-login"),
                    html.Div(
                        f"{r.get('host_name') or '—'}  ·  {r.get('program_name') or '—'}",
                        className="sph-sub",
                    ),
                    html.Div(
                        r.get("database_name") or "—",
                        className="sph-db",
                    ),
                ]),
                _sql_btn(
                    sid,
                    stmt_payload,
                    kind="stmt",
                    index=0,
                    label="جزئیات SQL",
                    title="مشاهده Statement، Batch و پیشرفت کوئری",
                ),
            ]),
            (
                render_request_ended_note(
                    end_ts=r.get("last_request_end_time"),
                    open_tran=open_tran,
                )
                if request_ended else None
            ),
        ],
    )

    from datetime import datetime

    identity_rows = [
        _profile_row("SQL Server", _format_client_endpoint(r)),
        _profile_row("Login time", _time_val(r.get("login_time"), "login")),
    ]
    if active:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        identity_rows.append(_profile_row(
            "Request start",
            _time_val(req_start, "request"),
        ))
        identity_rows.append(_profile_row(
            "Current time",
            _time_val(now_str, "now"),
        ))
        identity_rows.append(_profile_row(
            "Elapsed",
            html.Span(fmt_duration_hms(wall_ms), className="val num-ltr val-elapsed"),
        ))
    else:
        identity_rows.append(_profile_row(
            "Last request start",
            _time_val(r.get("last_request_start_time"), "request"),
        ))
        identity_rows.append(_profile_row(
            "Last request end",
            _time_val(r.get("last_request_end_time"), "end"),
        ))

    identity = html.Div(className="profile-card", children=[
        html.H4("Identity"),
        *identity_rows,
    ])

    rows_done = int(progress.get("rows_done") or 0)
    rows_est = int(progress.get("rows_est") or 0)
    bar_state = compute_progress_bar_state(
        rows_done=rows_done,
        rows_est=rows_est,
        percent_complete=r.get("percent_complete"),
        status=r.get("status"),
        has_active_request=active,
    )
    prog_lbl = bar_state.get("label") or "—"
    index_op = extract_index_op(stmt_sql or batch_sql)

    # Request = progress KPIs (statement lives on hero icon)
    request_rows = []
    if index_op:
        request_rows.extend([
            _profile_row(
                "Index op",
                html.Span(
                    index_op.get("action_label") or "INDEX",
                    className="val index-op-inline",
                ),
                tip="عملیات ایندکس از متن SQL خوانده شده (CREATE / REBUILD / REORGANIZE).",
            ),
            _profile_row(
                "Index",
                html.Span(
                    index_op.get("index_name") or "—",
                    className="val num-ltr",
                ),
            ) if index_op.get("index_name") else None,
            _profile_row(
                "On table",
                html.Span(index_op.get("table") or "—", className="val num-ltr"),
            ) if index_op.get("table") else None,
            _profile_row(
                "Index type",
                html.Span(index_op.get("kind") or "—", className="val num-ltr"),
            ) if index_op.get("kind") else None,
            _profile_row(
                "WITH",
                html.Span(
                    ", ".join(index_op.get("option_chips") or []) or "—",
                    className="val num-ltr index-with-inline",
                ),
            ) if index_op.get("option_chips") else None,
        ])
        request_rows = [x for x in request_rows if x is not None]

    request_rows.extend([
        _profile_row(
            "Rows done",
            html.Span(fmt_int(rows_done), className="val num-ltr"),
        ),
        _profile_row(
            "Rows est.",
            html.Span(fmt_int(rows_est) if rows_est else "—", className="val num-ltr"),
        ),
        _profile_row(
            "Progress",
            html.Span(prog_lbl, className="val num-ltr progress-inline"),
        ),
    ])
    if eta is not None:
        request_rows.append(_profile_row(
            "Est. finish",
            _render_finish_eta_value(eta),
        ))
    else:
        request_rows.append(_profile_row(
            "Est. finish",
            html.Span("—", className="val eta-muted"),
        ))
    if r.get("wait_type") and is_executing:
        request_rows.append(_profile_row(
            "Wait type",
            html.Span(r.get("wait_type") or "—", className="val num-ltr wait-text"),
            tip=tip_wait(r.get("wait_type")),
        ))
    if wait_ms > 0:
        request_rows.append(_profile_row(
            "Wait",
            html.Span(fmt_duration_hms(wait_ms), className=f"val {wcls} num-ltr".strip()),
        ))
    if blocked:
        request_rows.append(_profile_row(
            "Blocking session",
            html.Span(str(r.get("blocking_session_id") or 0), className="val wait-crit"),
        ))
    if open_tran > 0:
        request_rows.append(_profile_row("Open tran", fmt_int(open_tran)))

    request = html.Div(className="profile-card", children=[
        html.H4("Request"),
        *request_rows,
    ])

    resources = html.Div(className="profile-card", children=[
        html.H4("Resources"),
        _profile_row("CPU", html.Span(fmt_int(r.get("cpu_time") or 0), className="num-ltr")),
        _profile_row("Reads", html.Span(fmt_int(r.get("reads") or 0), className="num-ltr")),
        _profile_row("Writes", html.Span(fmt_int(r.get("writes") or 0), className="num-ltr")),
        _profile_row("Logical reads", html.Span(fmt_int(r.get("logical_reads") or 0), className="num-ltr")),
        _profile_row(
            "Used memory",
            html.Span(fmt_int(r.get("granted_query_memory") or 0), className="num-ltr"),
        ),
    ])

    # Hero → optional index panel → Identity | Request | Resources → charts
    profile_children = [
        hero,
        render_index_op_panel(index_op) if index_op else None,
        html.Div(className="session-profile-grid", children=[identity, request, resources]),
    ]
    charts = render_server_pulse_charts(pulse_series or [], has_session=True)
    if charts is not None:
        profile_children.append(charts)

    return html.Div(className="session-profile", children=profile_children)


def compute_finish_eta(
    *,
    rows_done: int = 0,
    rows_est: int = 0,
    elapsed_ms: int = 0,
    percent_complete=None,
    status: str | None = None,
    has_active_request: bool = True,
    now=None,
) -> dict | None:
    """
    Approximate wall-clock finish time from row throughput or DMV %.

    Returns None when not running / not enough signal.
    mode: eta | exceeded
    """
    from datetime import datetime, timedelta

    status_key = (status or "").strip().lower()
    still_running = bool(has_active_request) and status_key not in (
        "sleeping", "dormant", "background", "",
    )
    if not still_running:
        return None

    try:
        elapsed_ms = max(0, int(elapsed_ms or 0))
    except (TypeError, ValueError):
        return None
    # Need a few seconds of signal or ETA is noise
    if elapsed_ms < 3_000:
        return None

    rows_done = max(0, int(rows_done or 0))
    rows_est = max(0, int(rows_est or 0))
    clock = now if isinstance(now, datetime) else datetime.now()

    dmv_pct = None
    try:
        if percent_complete not in (None, "", 0, 0.0):
            dmv_pct = float(percent_complete)
    except (TypeError, ValueError):
        dmv_pct = None

    if rows_est > 0 and rows_done > rows_est:
        return {
            "mode": "exceeded",
            "finish_clock": None,
            "remaining_ms": None,
            "remaining_label": None,
            "confidence": "low",
            "source": "rows",
            "tip": (
                "برآورد پلن رد شده — سرعت فعلی دیگر برای ساعت اتمام قابل‌اعتماد نیست. "
                "Progress و Rows done را دنبال کن."
            ),
        }

    remaining_ms = None
    source = None

    if rows_est > 0 and rows_done > 0 and rows_done < rows_est:
        rate = rows_done / (elapsed_ms / 1000.0)
        if rate > 0:
            remaining_ms = int(((rows_est - rows_done) / rate) * 1000)
            source = "rows"
    elif dmv_pct is not None and 0 < dmv_pct < 100:
        # elapsed / pct = total → remaining = total - elapsed
        remaining_ms = int(elapsed_ms * (100.0 - dmv_pct) / dmv_pct)
        source = "percent"

    if remaining_ms is None:
        return None
    # Cap absurd ETAs (bad estimates) — still show but mark low confidence
    remaining_ms = max(0, remaining_ms)
    if remaining_ms > 7 * 24 * 3_600_000:
        return None

    finish_at = clock + timedelta(milliseconds=remaining_ms)
    # Medium once we have meaningful progress + time
    confidence = "medium" if (
        elapsed_ms >= 30_000 and (
            (source == "rows" and rows_done >= max(100, int(rows_est * 0.02)))
            or (source == "percent" and dmv_pct is not None and dmv_pct >= 5)
        )
    ) else "low"

    return {
        "mode": "eta",
        "finish_clock": finish_at.strftime("%H:%M:%S"),
        "remaining_ms": remaining_ms,
        "remaining_label": fmt_running_label(remaining_ms),
        "confidence": confidence,
        "source": source,
        "tip": (
            "تخمین تقریبی از سرعت فعلی ردیف‌ها (یا ٪ پیشرفت). "
            "اگر پلن اشتباه باشد یا کوئری بعداً کند/سریع شود، ساعت عوض می‌شود."
        ),
    }


def _render_finish_eta_value(eta: dict):
    """Sky/cyan forecast accent — distinct from wait (amber) and primary (teal)."""
    if eta.get("mode") == "exceeded":
        return _tip(
            html.Span("Estimate exceeded — ETA unknown", className="val eta-exceeded"),
            eta.get("tip") or "",
        )
    clock = eta.get("finish_clock") or "—"
    left = eta.get("remaining_label") or ""
    conf = eta.get("confidence") or "low"
    approx = "≈ " if conf == "low" else "~ "
    text = f"{approx}{clock}"
    if left:
        text = f"{text}  ({left} left)"
    return _tip(
        html.Span(text, className=f"val eta-finish conf-{conf} num-ltr"),
        eta.get("tip") or "",
    )


def compute_progress_bar_state(
    *,
    rows_done: int = 0,
    rows_est: int = 0,
    percent_complete=None,
    status: str | None = None,
    has_active_request: bool = True,
) -> dict:
    """
    Derive progress-bar display from live session status + row counts.

    Never claim 100%/complete while the request is still executing.
    When rows_done exceeds plan estimate, stretch the denominator so the bar
    stays just under 100% and keeps moving (or mark estimate-exceeded).
    """
    status_key = (status or "").strip().lower()
    still_running = bool(has_active_request) and status_key not in (
        "sleeping", "dormant", "background", "",
    )
    finished = (not has_active_request) or status_key in ("sleeping", "dormant")

    dmv_pct = None
    try:
        if percent_complete not in (None, "", 0, 0.0):
            dmv_pct = float(percent_complete)
    except (TypeError, ValueError):
        dmv_pct = None

    rows_done = max(0, int(rows_done or 0))
    rows_est = max(0, int(rows_est or 0))
    exceeded = rows_est > 0 and rows_done > rows_est

    if finished and not still_running:
        # Request gone — success and Cancel look the same in DMVs; don't claim 100%.
        if rows_est > 0 and rows_done > 0:
            fill = min(100.0, (rows_done / float(rows_est)) * 100.0)
            label = "ended" if fill >= 99.5 else f"{fill:.0f}% · ended"
        else:
            fill = None
            label = "ended"
        return {
            "mode": "ended",
            "fill_pct": fill,
            "label": label,
            "note": "Request ended (finish or Cancel — DMV cannot tell apart).",
            "exceeded": False,
        }

    if dmv_pct is not None and dmv_pct > 0 and not exceeded:
        fill = min(99.0, dmv_pct) if still_running else min(100.0, dmv_pct)
        if still_running and fill >= 100:
            fill = 99.0
        return {
            "mode": "running",
            "fill_pct": fill,
            "label": f"{fill:.0f}%",
            "note": None,
            "exceeded": False,
        }

    if rows_est <= 0 and rows_done <= 0:
        return {
            "mode": "unknown",
            "fill_pct": None,
            "label": None,
            "note": "No row estimate yet — watching live status.",
            "exceeded": False,
        }

    if exceeded:
        # (a) stretch estimate so bar stays under 100% while still running
        effective_est = max(float(rows_est), rows_done * 1.15)
        fill = (rows_done / effective_est) * 100.0
        if still_running:
            fill = min(97.0, fill)
        return {
            "mode": "exceeded",
            "fill_pct": fill,
            "label": f"{(rows_done / rows_est):.1f}× est.",
            "note": "Estimate exceeded — still running" if still_running else "Estimate exceeded",
            "exceeded": True,
        }

    if rows_est > 0:
        fill = (rows_done / rows_est) * 100.0
        if still_running:
            fill = min(99.0, fill)
        return {
            "mode": "running",
            "fill_pct": fill,
            "label": f"{fill:.0f}%",
            "note": None,
            "exceeded": False,
        }

    return {
        "mode": "unknown",
        "fill_pct": None,
        "label": None,
        "note": "Rows accumulating — no plan estimate.",
        "exceeded": False,
    }


def _kpi_profile_card(title: str, value_node, *, extra_class: str = "", sub: str = "", tip: str = ""):
    """Same chrome as Identity/Request/Resources — one metric per card."""
    head = html.H4(title)
    if tip:
        head = _tip(head, tip)
    kids = [head, html.Div(value_node, className="kpi-card-value num-ltr")]
    if sub:
        kids.append(html.Div(sub, className="kpi-card-sub num-ltr"))
    return html.Div(
        className=f"profile-card is-kpi {extra_class}".strip(),
        children=kids,
    )


def _render_lookup_kpi_cards(
    progress: dict | None,
    *,
    percent_complete=None,
    status: str | None = None,
    has_active_request: bool = True,
    eta: dict | None = None,
):
    """Rows / Progress / Est. finish as profile-cards (under hero)."""
    progress = progress or {}
    rows_done = int(progress.get("rows_done") or 0)
    rows_est = int(progress.get("rows_est") or 0)
    bar_state = compute_progress_bar_state(
        rows_done=rows_done,
        rows_est=rows_est,
        percent_complete=percent_complete,
        status=status,
        has_active_request=has_active_request,
    )
    fill = bar_state.get("fill_pct")
    if rows_done <= 0 and rows_est <= 0 and fill is None and not eta:
        return None

    prog_val = bar_state.get("label") or ("—" if fill is None else f"{float(fill):.0f}%")

    if eta and eta.get("mode") == "eta" and eta.get("finish_clock"):
        conf = eta.get("confidence") or "low"
        approx = "≈" if conf == "low" else "~"
        eta_val = html.Span(
            f"{approx} {eta['finish_clock']}",
            className="eta-finish",
        )
        eta_sub = f"{eta.get('remaining_label')} left" if eta.get("remaining_label") else ""
        eta_tip = eta.get("tip") or ""
        eta_cls = "is-eta"
    elif eta and eta.get("mode") == "exceeded":
        eta_val = html.Span("past estimate", className="eta-exceeded")
        eta_sub = ""
        eta_tip = eta.get("tip") or ""
        eta_cls = "is-eta"
    else:
        eta_val = "—"
        eta_sub = "needs more samples"
        eta_tip = "وقتی Rows یا ٪ پیشرفت کافی باشد، ساعت تقریبی اتمام اینجا می‌آید."
        eta_cls = "is-eta is-muted"

    return html.Div(className="session-profile-grid is-kpi", children=[
        _kpi_profile_card("Rows done", fmt_int(rows_done)),
        _kpi_profile_card("Rows est.", fmt_int(rows_est) if rows_est else "—"),
        _kpi_profile_card("Progress", prog_val, extra_class="is-pct"),
        _kpi_profile_card(
            "Est. finish",
            eta_val,
            extra_class=eta_cls,
            sub=eta_sub,
            tip=eta_tip,
        ),
    ])


def _render_row_metric_boxes(
    progress: dict | None,
    *,
    percent_complete=None,
    status: str | None = None,
    has_active_request: bool = True,
    eta: dict | None = None,
):
    """Compact strip for Statement modal (Lookup uses profile KPI cards)."""
    progress = progress or {}
    rows_done = int(progress.get("rows_done") or 0)
    rows_est = int(progress.get("rows_est") or 0)
    bar_state = compute_progress_bar_state(
        rows_done=rows_done,
        rows_est=rows_est,
        percent_complete=percent_complete,
        status=status,
        has_active_request=has_active_request,
    )
    fill = bar_state.get("fill_pct")
    if rows_done <= 0 and rows_est <= 0 and fill is None and not eta:
        return None

    items = [
        html.Div(className="progress-stat is-hero", children=[
            html.Span("Rows done", className="progress-stat-lbl"),
            html.Span(fmt_int(rows_done), className="progress-stat-val num-ltr"),
        ]),
        html.Div(className="progress-stat is-hero", children=[
            html.Span("Rows est.", className="progress-stat-lbl"),
            html.Span(fmt_int(rows_est) if rows_est else "—", className="progress-stat-val num-ltr"),
        ]),
        html.Div(className="progress-stat is-hero is-pct", children=[
            html.Span("Progress", className="progress-stat-lbl"),
            html.Span(
                bar_state.get("label") or ("—" if fill is None else f"{float(fill):.0f}%"),
                className="progress-stat-val num-ltr",
            ),
        ]),
    ]
    if eta and eta.get("mode") == "eta" and eta.get("finish_clock"):
        left = eta.get("remaining_label") or ""
        conf = eta.get("confidence") or "low"
        approx = "≈" if conf == "low" else "~"
        val = f"{approx} {eta['finish_clock']}"
        if left:
            val = f"{val}\n{left} left"
        items.append(html.Div(
            className="progress-stat is-hero is-eta",
            title=eta.get("tip") or "Approximate finish time",
            children=[
                html.Span("Est. finish", className="progress-stat-lbl"),
                html.Span(val, className="progress-stat-val num-ltr eta-finish"),
            ],
        ))
    return html.Div(className="progress-stats is-hero-strip", children=items)


def _render_session_progress_card(
    progress: dict | None,
    *,
    scope: str = "session",
    percent_complete=None,
    statement: str | None = None,
    status: str | None = None,
    has_active_request: bool = True,
    mode: str = "full",
):
    """
    Row progress from query profiles.

    mode:
      - full: legacy (stats + optional statement + bar) — avoided in new UI
      - bar: progress bar only at bottom (no SQL snippet, no duplicate row boxes)
      - metrics: just the hero metric boxes
    """
    progress = progress or {}
    rows_done = int(progress.get("rows_done") or 0)
    rows_est = int(progress.get("rows_est") or 0)
    operators = int(progress.get("operators") or 0)
    messages = list(progress.get("messages") or [])

    if mode == "metrics":
        return _render_row_metric_boxes(
            progress,
            percent_complete=percent_complete,
            status=status,
            has_active_request=has_active_request,
        )

    bar_state = compute_progress_bar_state(
        rows_done=rows_done,
        rows_est=rows_est,
        percent_complete=percent_complete,
        status=status,
        has_active_request=has_active_request,
    )

    has_bar = bar_state.get("fill_pct") is not None
    has_stats = operators > 0 or rows_done > 0 or rows_est > 0
    if scope == "session" and mode == "bar" and not has_bar and not messages:
        return None
    if scope == "session" and mode == "full" and not has_bar and not has_stats and not messages:
        return None

    if scope == "statement":
        title = "Statement progress"
        sub = "Live row progress (dm_exec_query_profiles)."
    else:
        title = "Progress"
        sub = "Rows processed vs plan estimate."

    show_stats = mode == "full"
    show_statement = mode == "full" and bool(statement)

    stat_items = []
    if show_stats:
        if operators > 0 or (scope == "statement" and has_stats):
            stat_items.append(html.Div(className="progress-stat", children=[
                html.Span("Operators", className="progress-stat-lbl"),
                html.Span(fmt_int(operators), className="progress-stat-val num-ltr"),
            ]))
        if rows_done > 0 or has_bar:
            stat_items.append(html.Div(className="progress-stat", children=[
                html.Span("Rows done", className="progress-stat-lbl"),
                html.Span(fmt_int(rows_done), className="progress-stat-val num-ltr"),
            ]))
        if rows_est > 0:
            stat_items.append(html.Div(className="progress-stat", children=[
                html.Span("Rows est.", className="progress-stat-lbl"),
                html.Span(fmt_int(rows_est), className="progress-stat-val num-ltr"),
            ]))

    stats = html.Div(className="progress-stats", children=stat_items) if stat_items else None

    # Statement SQL is shown above in the modal — never repeat it inside progress
    stmt_block = None
    if show_statement and statement:
        snippet = statement.strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "…"
        stmt_block = html.Pre(snippet, className="progress-stmt-snippet")

    bar = None
    note = None
    fill = bar_state.get("fill_pct")
    bar_mode = bar_state.get("mode") or "unknown"
    if fill is not None:
        bar = html.Div(className=f"progress-bar-track is-{bar_mode}", children=[
            html.Div(
                className=f"progress-bar-fill is-{bar_mode}",
                style={"width": f"{min(100.0, float(fill)):.1f}%"},
            ),
            html.Span(bar_state.get("label") or "", className="progress-bar-lbl"),
        ])
    if bar_state.get("note") and has_bar:
        note = html.P(bar_state["note"], className=f"progress-bar-note is-{bar_mode}")

    if mode == "bar" and not has_bar and not messages:
        return None

    children = [
        html.H4(title),
        html.P(sub, className="session-progress-sub"),
        stmt_block,
        stats,
        bar,
        note,
    ]
    if messages:
        children.extend([
            html.Div("Message history", className="progress-msg-title"),
            html.Div(className="progress-msg-list", children=[
                html.Div(className="progress-msg", children=[
                    html.Span(str(m.get("ts") or "")[:19], className="progress-msg-ts num-ltr"),
                    html.Span(m.get("message") or "", className="progress-msg-text"),
                ])
                for m in messages[-40:]
            ]),
        ])

    return html.Div(
        className=(
            "session-progress-card"
            + (" is-statement" if scope == "statement" else "")
            + (" is-bar-only" if mode == "bar" else "")
        ),
        children=[c for c in children if c is not None],
    )


_MIN_CHART_SAMPLES = 5
# Absolute thresholds only — never last/peak (that always false-fires near the window max).
_HOT_CPU_PCT = 80.0
_HOT_SESSION_READS_SEC = 50_000.0
_HOT_SESSION_WRITES_SEC = 10_000.0
_HOT_PLE_SEC_LOW = 300.0  # low PLE is bad; high PLE is healthy


def _last_num(vals) -> float | None:
    for v in reversed(vals or []):
        if v is not None:
            return float(v)
    return None


def _panel_is_hot(panel_key: str, server_ys, session_ys) -> bool:
    """
    Alert styling only for real stress — not 'near peak of short window'.
    - CPU: server CPU % >= 80
    - Reads/Writes: session rate above absolute floors
    - PLE: only when PLE is dangerously low (high PLE is OK)
    """
    if panel_key == "cpu":
        cpu = _last_num(server_ys)
        return cpu is not None and cpu >= _HOT_CPU_PCT
    if panel_key == "reads":
        r = _last_num(session_ys)
        return r is not None and r >= _HOT_SESSION_READS_SEC
    if panel_key == "writes":
        w = _last_num(session_ys)
        return w is not None and w >= _HOT_SESSION_WRITES_SEC
    if panel_key == "ple":
        ple = _last_num(server_ys)
        return ple is not None and 0 < ple < _HOT_PLE_SEC_LOW
    return False


def _dual_line_figure(
    xs,
    server_ys,
    session_ys,
    *,
    server_label: str,
    session_label: str,
    server_color: str,
    session_color: str,
):
    """Single line chart with server + session (shared time; dual Y for scale)."""
    import plotly.graph_objs as go

    fig = go.Figure()
    s_n = sum(1 for v in server_ys if v is not None)
    t_n = sum(1 for v in session_ys if v is not None)
    warm = max(s_n, t_n) < _MIN_CHART_SAMPLES

    def add_series(ys, label, color, yaxis=None, force_markers=False):
        n = sum(1 for v in ys if v is not None)
        if n == 0:
            return
        if warm or n < _MIN_CHART_SAMPLES or force_markers:
            last_i = last_v = None
            for i, v in enumerate(ys):
                if v is not None:
                    last_i, last_v = i, v
            if last_i is not None:
                fig.add_trace(go.Scatter(
                    x=[xs[last_i]], y=[last_v], mode="markers",
                    name=label,
                    marker=dict(color=color, size=8),
                    yaxis=yaxis,
                    # Unified hover already shows time — avoid repeating timestamp
                    hovertemplate="%{y:,.0f}<extra>" + label + "</extra>",
                ))
        else:
            fig.add_trace(go.Scatter(
                x=xs, y=ys, name=label, mode="lines+markers",
                line=dict(color=color, width=2.5),
                marker=dict(size=5, color=color),
                yaxis=yaxis,
                hovertemplate="%{y:,.0f}<extra>" + label + "</extra>",
            ))

    add_series(server_ys, server_label, server_color)
    add_series(session_ys, session_label, session_color, yaxis="y2")

    if warm:
        fig.add_annotation(
            text="warming up…",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=11, color="#64748b"),
        )

    fig.update_layout(
        margin=dict(l=52, r=64, t=40, b=36),
        height=250,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15,23,42,0.55)",
        font=dict(color="#e2e8f0", size=10),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.06, x=0,
            font=dict(size=11, color="#e2e8f0"), bgcolor="rgba(0,0,0,0)",
            itemsizing="constant",
            traceorder="normal",
        ),
        xaxis=dict(
            type="date", showgrid=False, zeroline=False,
            tickfont=dict(size=9, color="#94a3b8"),
            tickformat="%H:%M:%S", nticks=4,
            automargin=True,
        ),
        yaxis=dict(
            title=dict(text=server_label, font=dict(size=9, color=server_color), standoff=6),
            showgrid=True, gridcolor="rgba(148,163,184,0.18)", zeroline=False,
            tickfont=dict(size=9, color=server_color), nticks=3,
            separatethousands=True, tickformat="~s",
            automargin=True,
            fixedrange=True,
        ),
        yaxis2=dict(
            title=dict(text=session_label, font=dict(size=9, color=session_color), standoff=6),
            overlaying="y", side="right", showgrid=False, zeroline=False,
            tickfont=dict(size=9, color=session_color), nticks=3,
            separatethousands=True, tickformat="~s",
            automargin=True,
            fixedrange=True,
        ),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="rgba(15, 23, 42, 0.96)",
            bordercolor="#64748b",
            font=dict(color="#f8fafc", size=12, family="Consolas, monospace"),
            align="left",
        ),
        uirevision="pulse",
    )
    return fig


def render_server_pulse_charts(series: list | None, *, has_session: bool = False):
    """One dual-line chart per metric (server + session). Hidden until a session is looked up."""
    if not has_session:
        return None
    series = _dedupe_pulse_series_by_second(series or [])
    if not series:
        return None

    from datetime import datetime, timezone

    xs = []
    for s in series:
        try:
            xs.append(datetime.fromtimestamp(float(s.get("_ts")), tz=timezone.utc).astimezone().replace(tzinfo=None))
        except Exception:
            xs.append(None)

    def col(key):
        return [float(s[key]) if s.get(key) is not None else None for s in series]

    n = len(series)
    last = series[-1]
    panels = [
        ("cpu", "CPU", "cpu_pct", "session_cpu_rate", "#34d399", "#fb923c",
         "Server CPU %", "Session CPU /s",
         None if last.get("cpu_pct") is None else f"{int(last['cpu_pct'])}%"),
        ("reads", "Reads", "page_reads_sec", "session_reads_rate", "#60a5fa", "#fb923c",
         "Server reads/s", "Session reads/s",
         None if last.get("page_reads_sec") is None else fmt_int(round(float(last["page_reads_sec"])))),
        ("writes", "Writes", "page_writes_sec", "session_writes_rate", "#fbbf24", "#fb923c",
         "Server writes/s", "Session writes/s",
         None if last.get("page_writes_sec") is None else fmt_int(round(float(last["page_writes_sec"])))),
        ("ple", "PLE / Rows", "page_life_expectancy", "session_rows_done", "#a78bfa", "#fb923c",
         "Server PLE (sec)", "Session rows done",
         None),
    ]

    cards = []
    for key, title, skey, tkey, scolor, tcolor, slabel, tlabel, disp in panels:
        s_ys, t_ys = col(skey), col(tkey)
        hot = _panel_is_hot(key, s_ys, t_ys)
        if key == "ple":
            ple_v = last.get("page_life_expectancy")
            rows_v = last.get("session_rows_done")
            bits = []
            if ple_v is not None:
                bits.append(f"PLE {fmt_int(ple_v)}")
            if rows_v is not None:
                bits.append(f"rows {fmt_int(int(rows_v))}")
            disp = " · ".join(bits) if bits else "—"
        elif disp is None and last.get(skey) is not None:
            disp = fmt_int(round(float(last[skey]))) if key != "cpu" else f"{int(last[skey])}%"
        fig = _dual_line_figure(
            xs, s_ys, t_ys,
            server_label=slabel, session_label=tlabel,
            server_color=scolor, session_color=tcolor,
        )
        cards.append(html.Div(
            className="session-pulse-card is-chart" + (" is-hot" if hot else ""),
            children=[
                html.Div(className="session-pulse-top", children=[
                    html.Span(title, className="session-pulse-lbl"),
                    html.Span(disp or "—", className="session-pulse-val num-ltr"),
                ]),
                dcc.Graph(
                    figure=fig,
                    config={"displayModeBar": False, "responsive": True},
                    className="session-pulse-graph",
                ),
            ],
        ))

    meta = f"{n} samples"
    if n < _MIN_CHART_SAMPLES:
        meta += f" · need {_MIN_CHART_SAMPLES}+ for trend"
    else:
        meta += " · server + session"

    return html.Div(className="session-pulse", children=[
        html.Div(className="session-pulse-head", children=[
            html.H4("Live resource charts"),
            html.Span(meta, className="session-pulse-meta"),
        ]),
        html.P(
            "Same chart: green/blue/yellow/purple = server · orange = this session. "
            "Red frame only when CPU ≥ 80%, session IO is extreme, or PLE is critically low.",
            className="session-pulse-legend",
        ),
        html.Div(className="session-pulse-grid is-charts", children=cards),
    ])


def _dedupe_pulse_series_by_second(series: list | None) -> list:
    """Keep last sample per wall-clock second so X labels stay unique."""
    out: list = []
    last_sec = None
    for s in series or []:
        try:
            sec = int(float(s.get("_ts") or 0))
        except (TypeError, ValueError):
            sec = None
        if sec is not None and sec == last_sec and out:
            out[-1] = s
        else:
            out.append(s)
            last_sec = sec
    return out


def _append_pulse_sample(
    series: list | None,
    pulse_result: dict | None,
    *,
    session_row: dict | None = None,
    limit: int = 48,
) -> list:
    from datetime import datetime, timezone

    series = list(series or [])
    summary = (pulse_result or {}).get("summary") or {}
    if (pulse_result or {}).get("status") != "ok" and not session_row:
        return _dedupe_pulse_series_by_second(series)[-limit:]

    now = datetime.now(timezone.utc).timestamp()
    raw_reads = summary.get("page_reads_sec")
    raw_writes = summary.get("page_writes_sec")
    reads_rate = writes_rate = None
    sess_cpu_rate = sess_reads_rate = sess_writes_rate = None
    sess_rows = None

    prev = series[-1] if series else None
    # Merge into last point if < 1.2s — prevents duplicate HH:MM:SS on charts
    if prev and (now - float(prev.get("_ts") or 0)) < 1.2:
        replace_last = True
        dt = max(0.001, now - float(prev.get("_ts") or now))
        # Use previous-previous for rate baseline when replacing
        baseline = series[-2] if len(series) >= 2 else None
        if baseline:
            dt = max(0.001, now - float(baseline.get("_ts") or now))
            prev = baseline
        else:
            dt = 1.0
    else:
        replace_last = False
        dt = max(0.001, now - float((prev or {}).get("_ts") or now)) if prev else 1.0

    if prev and raw_reads is not None and prev.get("_raw_reads") is not None:
        reads_rate = max(0.0, (float(raw_reads) - float(prev["_raw_reads"])) / dt)
    if prev and raw_writes is not None and prev.get("_raw_writes") is not None:
        writes_rate = max(0.0, (float(raw_writes) - float(prev["_raw_writes"])) / dt)

    if session_row:
        cpu = session_row.get("cpu_time")
        rd = session_row.get("reads")
        wr = session_row.get("writes")
        prog = session_row.get("progress") or {}
        try:
            sess_rows = int(prog.get("rows_done") or 0)
        except (TypeError, ValueError):
            sess_rows = 0
        if prev and cpu is not None and prev.get("_sess_cpu") is not None:
            sess_cpu_rate = max(0.0, (float(cpu) - float(prev["_sess_cpu"])) / dt)
        if prev and rd is not None and prev.get("_sess_reads") is not None:
            sess_reads_rate = max(0.0, (float(rd) - float(prev["_sess_reads"])) / dt)
        if prev and wr is not None and prev.get("_sess_writes") is not None:
            sess_writes_rate = max(0.0, (float(wr) - float(prev["_sess_writes"])) / dt)

    sample = {
        "_ts": now,
        "_raw_reads": raw_reads,
        "_raw_writes": raw_writes,
        "_sess_cpu": (session_row or {}).get("cpu_time"),
        "_sess_reads": (session_row or {}).get("reads"),
        "_sess_writes": (session_row or {}).get("writes"),
        "cpu_pct": summary.get("cpu_pct"),
        "page_reads_sec": reads_rate,
        "page_writes_sec": writes_rate,
        "page_life_expectancy": summary.get("page_life_expectancy"),
        "session_cpu_rate": sess_cpu_rate,
        "session_reads_rate": sess_reads_rate,
        "session_writes_rate": sess_writes_rate,
        "session_rows_done": sess_rows,
    }
    if replace_last and series:
        series[-1] = sample
    else:
        series.append(sample)
    return _dedupe_pulse_series_by_second(series)[-limit:]
