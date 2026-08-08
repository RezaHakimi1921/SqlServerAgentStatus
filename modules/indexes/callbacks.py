"""Index Intelligence callbacks — Overview · Triage · Table Explorer."""
from __future__ import annotations

from dash import ALL, Input, Output, State, ctx, html, no_update

from core.logging_setup import get_logger
from core.permissions import INDEX_PERMISSIONS_HINT
from core.providers.sqlserver_provider import get_provider
from modules.indexes.constants import (
    INDEX_DB_ALL,
    INDEX_TABLE_SEARCH_MIN_CHARS,
)
from modules.indexes.layout import (
    _tab_cls,
    db_label,
    db_option_values,
    render_db_options,
    render_explorer,
    render_explorer_idle,
    render_frag_status,
    render_search_results,
    render_selected_table,
)
from modules.indexes.panels import (
    render_catalog_status,
    render_explorer_table_list,
    render_overview,
    render_triage_detail,
    render_triage_rail,
    render_triage_subbar,
    triage_badge_children,
)
from modules.indexes.service import (
    apply_frag_to_payload,
    build_overview_payload,
)
from modules.indexes.triage import filter_triage_findings, triage_filter_counts

log = get_logger("sqlmonitor.indexes.ui")

_TOAST_HIDDEN = "toast-item toast-refresh hidden"
_TOAST_REFRESH = "toast-item toast-refresh"
_TOAST_ERROR = "toast-item toast-refresh is-error"


def _default_database(names: list[str]) -> str | None:
    # Explorer mockup defaults to All (catalog-wide list).
    return INDEX_DB_ALL


def _panel_cls(tab: str, name: str) -> str:
    return "indexes-panel" if tab == name else "indexes-panel hidden"


def _visible_tables(
    cache: dict | None,
    query: str,
    sort_key: str,
    selected: dict | None = None,
) -> list[dict]:
    tables = list((cache or {}).get("tables") or [])
    cache_db = (cache or {}).get("database") or ""
    q = (query or "").strip().lower()
    if q:
        tables = [
            t
            for t in tables
            if q in str(t.get("full_name") or "").lower()
            or q in str(t.get("table_name") or "").lower()
            or q in str(t.get("database_name") or cache_db or "").lower()
        ]

    def sort_val(t):
        if sort_key == "schema":
            return str(t.get("schema_name") or "").lower()
        if sort_key == "rows":
            try:
                return -float(t.get("row_count") or 0)
            except (TypeError, ValueError):
                return 0
        if sort_key == "heap":
            return 0 if t.get("is_heap") else 1
        return str(t.get("table_name") or "").lower()

    visible = sorted(tables, key=sort_val)[:500]
    if selected and selected.get("table"):
        sel_schema = selected.get("schema") or "dbo"
        sel_table = selected.get("table")
        sel_db = selected.get("database")

        def _is_sel(t: dict) -> bool:
            return (
                (t.get("schema_name") or "dbo") == sel_schema
                and (t.get("table_name") or "") == sel_table
                and (not sel_db or (t.get("database_name") or cache_db) == sel_db)
            )

        if not any(_is_sel(t) for t in visible):
            pinned = next((t for t in ((cache or {}).get("tables") or []) if _is_sel(t)), None)
            if pinned is None:
                pinned = {
                    "database_name": sel_db or cache_db,
                    "schema_name": sel_schema,
                    "table_name": sel_table,
                    "full_name": selected.get("full_name") or f"{sel_schema}.{sel_table}",
                }
            visible = [pinned] + visible[:499]
    return visible


def register_indexes_callbacks(app):
    # Tab switch — only on real clicks (never on initial 0-click fire)
    @app.callback(
        Output("store-indexes-tab", "data"),
        Input("indexes-tab-overview", "n_clicks"),
        Input("indexes-tab-triage", "n_clicks"),
        Input("indexes-tab-explorer", "n_clicks"),
        Input("btn-indexes-goto-triage", "n_clicks"),
        State("store-indexes-tab", "data"),
        prevent_initial_call=True,
    )
    def switch_tab(_o, _t, _e, _goto, current):
        trig = ctx.triggered_id
        if not trig or not ctx.triggered:
            return no_update
        try:
            clicked = int(ctx.triggered[0].get("value") or 0)
        except (TypeError, ValueError):
            clicked = 0
        if clicked <= 0:
            return no_update
        if trig == "indexes-tab-explorer":
            return "explorer"
        if trig == "indexes-tab-overview":
            return "overview"
        if trig in ("indexes-tab-triage", "btn-indexes-goto-triage"):
            return "triage"
        return current or "overview"

    @app.callback(
        Output("indexes-tab-overview", "className"),
        Output("indexes-tab-triage", "className"),
        Output("indexes-tab-explorer", "className"),
        Output("indexes-panel-overview", "className"),
        Output("indexes-panel-triage", "className"),
        Output("indexes-panel-explorer", "className"),
        Input("store-indexes-tab", "data"),
        prevent_initial_call=False,
    )
    def paint_tabs(tab):
        tab = tab or "overview"
        return (
            _tab_cls(tab == "overview"),
            _tab_cls(tab == "triage"),
            _tab_cls(tab == "explorer"),
            _panel_cls(tab, "overview"),
            _panel_cls(tab, "triage"),
            _panel_cls(tab, "explorer"),
        )

    @app.callback(
        Output("indexes-toast-refresh", "className"),
        Output("indexes-toast-refresh", "children"),
        Input("btn-indexes-refresh", "n_clicks"),
        State("store-module", "data"),
        prevent_initial_call=True,
    )
    def show_refresh_toast(_n, module):
        if module != "indexes":
            return no_update, no_update
        return _TOAST_REFRESH, [
            html.Span(className="refresh-spinner"),
            html.Span("Refreshing…"),
        ]

    # Catalog confirm modal open/close
    @app.callback(
        Output("indexes-catalog-modal", "className"),
        Input("btn-indexes-catalog-refresh", "n_clicks"),
        Input("indexes-catalog-cancel", "n_clicks"),
        Input("indexes-catalog-modal-close", "n_clicks"),
        State("store-module", "data"),
        prevent_initial_call=True,
    )
    def toggle_catalog_modal(_open, _cancel, _close, module):
        trig = ctx.triggered_id
        if trig == "btn-indexes-catalog-refresh":
            if module != "indexes":
                return no_update
            return "modal-overlay"
        return "modal-overlay hidden"

    _CATALOG_PARTS = (
        ("tables", "Tables", "Row counts, heap flags, sizes"),
        ("index_defs", "Index definitions", "Keys, includes, filters"),
        ("index_stats", "Index states", "Reads, writes, size from DMV"),
    )

    def _render_catalog_parts_ui(selected: list | None):
        sel = set(selected or [])
        cards = []
        for key, title, desc in _CATALOG_PARTS:
            on = key in sel
            cards.append(
                html.Button(
                    [
                        html.Span(className=f"idx-check{' is-on' if on else ''}"),
                        html.Div(
                            className="idx-opt-copy",
                            children=[
                                html.Span(title, className="idx-opt-title"),
                                html.Span(desc, className="idx-opt-desc"),
                            ],
                        ),
                    ],
                    id={"type": "indexes-catalog-part", "key": key},
                    className=f"idx-opt-card{' is-on' if on else ''}",
                    n_clicks=0,
                    type="button",
                )
            )
        return cards

    def _render_catalog_scope_ui(scope: str | None):
        scope = scope or "all"
        cards = []
        for key, label in (("all", "All databases"), ("selected", "Selected DB")):
            on = scope == key
            cards.append(
                html.Button(
                    [
                        html.Span(className=f"idx-radio{' is-on' if on else ''}"),
                        html.Span(label, className="idx-opt-title"),
                    ],
                    id={"type": "indexes-catalog-scope", "key": key},
                    className=f"idx-opt-card idx-scope-card{' is-on' if on else ''}",
                    n_clicks=0,
                    type="button",
                )
            )
        return cards

    @app.callback(
        Output("indexes-catalog-parts", "data"),
        Output("indexes-catalog-parts-ui", "children"),
        Input({"type": "indexes-catalog-part", "key": ALL}, "n_clicks"),
        State("indexes-catalog-parts", "data"),
        prevent_initial_call=True,
    )
    def toggle_catalog_parts(n_clicks, current):
        if not ctx.triggered_id or not any(n_clicks or []):
            return no_update, no_update
        key = ctx.triggered_id.get("key")
        selected = list(current or [])
        if key in selected:
            selected = [k for k in selected if k != key]
        else:
            selected.append(key)
        # Keep stable order
        order = [k for k, _, _ in _CATALOG_PARTS]
        selected = [k for k in order if k in selected]
        return selected, _render_catalog_parts_ui(selected)

    @app.callback(
        Output("indexes-catalog-scope", "data"),
        Output("indexes-catalog-scope-ui", "children"),
        Input({"type": "indexes-catalog-scope", "key": ALL}, "n_clicks"),
        State("indexes-catalog-scope", "data"),
        prevent_initial_call=True,
    )
    def toggle_catalog_scope(n_clicks, current):
        if not ctx.triggered_id or not any(n_clicks or []):
            return no_update, no_update
        key = ctx.triggered_id.get("key") or "all"
        if key == current:
            return no_update, no_update
        return key, _render_catalog_scope_ui(key)

    # Instant feedback when user confirms catalog rebuild (server may take minutes)
    app.clientside_callback(
        """
        function(n) {
            if (!n) {
                return [
                    window.dash_clientside.no_update,
                    window.dash_clientside.no_update,
                    window.dash_clientside.no_update,
                    window.dash_clientside.no_update,
                    window.dash_clientside.no_update
                ];
            }
            return [
                'modal-overlay hidden',
                '',
                'Rebuilding index catalog… this can take several minutes',
                'toast-item toast-refresh',
                [
                    {namespace:'dash_html_components', type:'Span', props:{className:'refresh-spinner'}},
                    {namespace:'dash_html_components', type:'Span', props:{children:'Rebuilding catalog…'}}
                ]
            ];
        }
        """,
        Output("indexes-catalog-modal", "className", allow_duplicate=True),
        Output("indexes-overview-loading", "className", allow_duplicate=True),
        Output("indexes-overview-loading-text", "children", allow_duplicate=True),
        Output("indexes-toast-refresh", "className", allow_duplicate=True),
        Output("indexes-toast-refresh", "children", allow_duplicate=True),
        Input("indexes-catalog-confirm", "n_clicks"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("indexes-catalog-status", "children"),
        Input("store-module", "data"),
        Input("store-indexes-catalog-version", "data"),
        prevent_initial_call=True,
    )
    def load_catalog_status(module, _ver):
        if module != "indexes":
            return no_update
        try:
            status = get_provider().get_index_catalog_status()
            return render_catalog_status(status)
        except Exception as ex:
            log.debug("catalog status failed: %s", ex)
            return render_catalog_status({"available": False, "reason": str(ex)})

    @app.callback(
        Output("indexes-toast-refresh", "className", allow_duplicate=True),
        Output("indexes-toast-refresh", "children", allow_duplicate=True),
        Output("indexes-catalog-modal", "className", allow_duplicate=True),
        Output("store-indexes-catalog-job", "data"),
        Output("indexes-catalog-poll", "disabled"),
        Output("indexes-overview-loading", "className", allow_duplicate=True),
        Output("indexes-overview-loading-text", "children", allow_duplicate=True),
        Input("indexes-catalog-confirm", "n_clicks"),
        State("indexes-catalog-scope", "data"),
        State("indexes-catalog-parts", "data"),
        State("indexes-db-dropdown", "data"),
        State("store-module", "data"),
        prevent_initial_call=True,
    )
    def confirm_catalog_refresh(_n, scope, parts, selected_db, module):
        """Start catalog refresh in a background thread — never block the Dash worker."""
        from modules.indexes.catalog_jobs import start_catalog_refresh

        if module != "indexes":
            return (no_update,) * 7
        selected = set(parts or [])
        want_tables = "tables" in selected
        want_defs = "index_defs" in selected
        want_stats = "index_stats" in selected
        if not (want_tables or want_defs or want_stats):
            return (
                _TOAST_ERROR,
                "Select at least one catalog part to update.",
                "modal-overlay",
                no_update,
                no_update,
                "hidden",
                no_update,
            )
        db = None
        if (scope or "all") == "selected":
            db = (selected_db or "").strip() or None
            if not db or db == INDEX_DB_ALL:
                return (
                    _TOAST_ERROR,
                    "Select a database in Table Explorer first, or choose All databases.",
                    "modal-overlay",
                    no_update,
                    no_update,
                    "hidden",
                    no_update,
                )
        job_id = start_catalog_refresh(
            db,
            tables=want_tables,
            index_defs=want_defs,
            index_stats=want_stats,
        )
        return (
            _TOAST_REFRESH,
            [
                html.Span(className="refresh-spinner"),
                html.Span("Catalog refresh started — UI stays responsive…"),
            ],
            "modal-overlay hidden",
            job_id,
            False,
            "",
            "Rebuilding index catalog… this can take several minutes",
        )

    @app.callback(
        Output("indexes-toast-refresh", "className", allow_duplicate=True),
        Output("indexes-toast-refresh", "children", allow_duplicate=True),
        Output("store-indexes-catalog-version", "data"),
        Output("store-indexes-overview", "data", allow_duplicate=True),
        Output("store-indexes-table-cache", "data", allow_duplicate=True),
        Output("indexes-catalog-poll", "disabled", allow_duplicate=True),
        Output("store-indexes-catalog-job", "data", allow_duplicate=True),
        Output("indexes-overview-loading", "className", allow_duplicate=True),
        Input("indexes-catalog-poll", "n_intervals"),
        State("store-indexes-catalog-job", "data"),
        State("store-indexes-catalog-version", "data"),
        prevent_initial_call=True,
    )
    def poll_catalog_job(_n, job_id, version):
        from modules.indexes.catalog_jobs import get_catalog_job

        job = get_catalog_job(job_id)
        if not job or job.get("status") == "running":
            return (no_update,) * 8
        if job.get("status") == "error":
            return (
                _TOAST_ERROR,
                job.get("error") or "Catalog refresh failed",
                no_update,
                no_update,
                no_update,
                True,
                None,
                "hidden",
            )
        return (
            _TOAST_REFRESH,
            [
                html.Span(className="refresh-spinner"),
                html.Span("Catalog updated — reloading…"),
            ],
            int(version or 0) + 1,
            None,
            None,
            True,
            None,
            "",
        )

    # Prefetch all tables for selected DB (catalog-first) for instant typeahead
    @app.callback(
        Output("store-indexes-table-cache", "data"),
        Output("indexes-table-cache-hint", "children"),
        Input("indexes-db-dropdown", "data"),
        Input("store-indexes-catalog-version", "data"),
        State("store-module", "data"),
        prevent_initial_call=True,
    )
    def load_table_cache(database, _ver, module):
        if module != "indexes" or not database:
            return None, ""
        try:
            raw = get_provider().list_tables(database, all_for_db=True)
            tables = raw.get("tables") or []
            source = raw.get("source") or "live"
            # Ensure each row has database_name for All / DATABASE column
            if database != INDEX_DB_ALL:
                for t in tables:
                    t.setdefault("database_name", database)
            cache = {
                "database": database,
                "tables": tables,
                "source": source,
                "count": len(tables),
            }
            if not tables:
                if database == INDEX_DB_ALL:
                    hint = "No catalog tables yet — run Update catalog first."
                else:
                    hint = "No tables found for this database."
            elif source == "catalog":
                from core.formatters import fmt_int

                scope = "all databases" if database == INDEX_DB_ALL else "catalog"
                hint = f"Loaded {fmt_int(len(tables))} tables from {scope} — search is local/fast."
            else:
                from core.formatters import fmt_int

                hint = f"Loaded {fmt_int(len(tables))} tables (live) — catalog empty for this DB."
            return cache, hint
        except Exception as ex:
            log.exception("table cache load failed")
            return None, f"Could not preload tables: {ex}"

    # Enter Indexes → DB list once + custom dark picker
    @app.callback(
        Output("indexes-db-dropdown", "data"),
        Output("indexes-db-label", "children"),
        Output("indexes-db-options", "children"),
        Output("store-indexes-db-list", "data"),
        Output("store-indexes-db-filtered", "data"),
        Input("store-module", "data"),
        State("store-indexes-db-list", "data"),
        State("indexes-db-dropdown", "data"),
        prevent_initial_call=True,
    )
    def load_databases(module, db_list, current_db):
        if module != "indexes":
            return (no_update,) * 5
        if db_list is not None and db_list.get("databases") is not None:
            names = list(db_list.get("databases") or [])
            value = (
                current_db
                if current_db == INDEX_DB_ALL or (current_db and current_db in names)
                else _default_database(names)
            )
            return (
                value,
                db_label(value),
                render_db_options(names, value),
                no_update,
                db_option_values(names),
            )
        try:
            raw = get_provider().list_user_databases()
            names = list(raw.get("databases") or [])
            value = (
                current_db
                if current_db == INDEX_DB_ALL or (current_db and current_db in names)
                else _default_database(names)
            )
            return (
                value,
                db_label(value),
                render_db_options(names, value),
                {"databases": names},
                db_option_values(names),
            )
        except Exception as ex:
            log.exception("load databases failed")
            return None, "All", html.Div(str(ex)), {"databases": [], "error": str(ex)}, [INDEX_DB_ALL]

    # Toggle DB panel
    app.clientside_callback(
        """
        function(n_toggle, open) {
            const ctx = dash_clientside.callback_context;
            if (!ctx || !ctx.triggered || !ctx.triggered.length) {
                return [window.dash_clientside.no_update, window.dash_clientside.no_update];
            }
            const next = !open;
            return [next, next ? 'indexes-db-panel' : 'indexes-db-panel hidden'];
        }
        """,
        Output("store-indexes-db-open", "data"),
        Output("indexes-db-panel", "className"),
        Input("indexes-db-toggle", "n_clicks"),
        State("store-indexes-db-open", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("indexes-db-options", "children", allow_duplicate=True),
        Output("store-indexes-db-filtered", "data", allow_duplicate=True),
        Input("indexes-db-filter", "value"),
        State("store-indexes-db-list", "data"),
        State("indexes-db-dropdown", "data"),
        prevent_initial_call=True,
    )
    def filter_databases(filter_text, db_list, selected):
        names = list((db_list or {}).get("databases") or [])
        filtered = db_option_values(names, filter_text or "")
        return render_db_options(names, selected, filter_text or ""), filtered

    @app.callback(
        Output("indexes-db-dropdown", "data", allow_duplicate=True),
        Output("indexes-db-label", "children", allow_duplicate=True),
        Output("indexes-db-panel", "className", allow_duplicate=True),
        Output("store-indexes-db-open", "data", allow_duplicate=True),
        Output("indexes-db-filter", "value"),
        Input({"type": "indexes-db-hit", "index": ALL}, "n_clicks"),
        State("store-indexes-db-filtered", "data"),
        prevent_initial_call=True,
    )
    def select_database(n_clicks, filtered):
        if not ctx.triggered_id or not filtered or not any(n_clicks or []):
            return (no_update,) * 5
        idx = ctx.triggered_id.get("index")
        if idx is None or idx >= len(filtered):
            return (no_update,) * 5
        name = filtered[idx]
        return name, db_label(name), "indexes-db-panel hidden", False, ""

    # Overview + Triage share one store
    @app.callback(
        Output("store-indexes-overview", "data"),
        Output("indexes-overview-body", "children"),
        Output("indexes-triage-subbar", "children"),
        Output("indexes-triage-rail", "children"),
        Output("indexes-triage-detail", "children"),
        Output("store-indexes-triage-visible", "data"),
        Output("store-indexes-selected-finding", "data", allow_duplicate=True),
        Output("indexes-loading", "className", allow_duplicate=True),
        Output("indexes-overview-loading", "className", allow_duplicate=True),
        Output("indexes-toast-refresh", "className", allow_duplicate=True),
        Output("indexes-toast-refresh", "children", allow_duplicate=True),
        Output("indexes-tab-triage", "children", allow_duplicate=True),
        Input("store-module", "data"),
        Input("store-indexes-tab", "data"),
        Input("btn-indexes-refresh", "n_clicks"),
        Input("btn-indexes-deep-scan", "n_clicks"),
        Input("store-indexes-catalog-version", "data"),
        State("store-indexes-overview", "data"),
        State("store-indexes-triage-filter", "data"),
        State("store-indexes-selected-finding", "data"),
        prevent_initial_call=True,
    )
    def load_overview(module, tab, _refresh, _deep, catalog_ver, existing, filt, selected_id):
        if module != "indexes":
            return (no_update,) * 12
        tab = tab or "overview"
        if tab not in ("overview", "triage"):
            return (no_update,) * 12

        trig = ctx.triggered_id
        force_refresh = trig in ("btn-indexes-refresh", "store-indexes-catalog-version")
        deep = trig == "btn-indexes-deep-scan"
        filt = filt or "all"
        hide_ov = "hidden"

        def _paint(payload, sel_id):
            findings = filter_triage_findings((payload or {}).get("findings"), filt)
            visible_ids = [f.get("id") for f in findings]
            finding = None
            if sel_id:
                for f in (payload or {}).get("findings") or []:
                    if f.get("id") == sel_id:
                        finding = f
                        break
            if finding is None and findings:
                finding = findings[0]
                sel_id = finding.get("id")
            all_findings = (payload or {}).get("findings") or []
            badge_n = triage_filter_counts(all_findings).get("critical") or 0
            return (
                payload,
                render_overview(payload),
                render_triage_subbar(payload, filt),
                render_triage_rail(payload, filt, sel_id),
                render_triage_detail(finding),
                visible_ids,
                sel_id,
                "activity-loading hidden",
                hide_ov,
                _TOAST_HIDDEN,
                no_update,
                triage_badge_children(badge_n),
            )

        if existing and not force_refresh and not deep and trig in ("store-module", "store-indexes-tab"):
            return _paint(existing, selected_id)

        # Any other non-fetch trigger must still clear a stale overlay if one is up.
        if not force_refresh and not deep and existing is not None and trig not in (
            "store-module",
            "store-indexes-tab",
        ):
            return (
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                "activity-loading hidden",
                hide_ov,
                no_update,
                no_update,
                no_update,
            )

        try:
            want_deep = bool(
                deep
                or (force_refresh and existing and existing.get("scan_mode") == "deep")
            )
            raw = get_provider().get_index_overview_snapshot(deep=want_deep)
            try:
                raw["catalog"] = get_provider().get_index_catalog_status()
            except Exception:
                raw["catalog"] = None
            payload = build_overview_payload(raw)
            return _paint(payload, None if force_refresh or deep else selected_id)
        except Exception as ex:
            log.exception("overview failed")
            err = html.Div(
                className="state-box state-error",
                children=[
                    html.H3("Could not load index overview"),
                    html.P(str(ex)),
                    html.Pre(INDEX_PERMISSIONS_HINT, className="indexes-perm-hint"),
                ],
            )
            return (
                None,
                err,
                render_triage_subbar(None, filt),
                render_triage_rail(None, filt, None),
                render_triage_detail(None),
                [],
                None,
                "activity-loading hidden",
                hide_ov,
                _TOAST_ERROR,
                f"Overview failed: {ex}",
                triage_badge_children(0),
            )

    # Immediate loading overlay for Overview/Triage (panel-local, not shell-tall).
    app.clientside_callback(
        """
        function(module, tab, n_refresh) {
            const ctx = dash_clientside.callback_context;
            const no = window.dash_clientside.no_update;
            if (!ctx || !ctx.triggered || !ctx.triggered.length) {
                return [no, no];
            }
            if (module !== 'indexes') {
                return [no, no];
            }
            const id = (ctx.triggered[0].prop_id || '').split('.')[0];
            const onFindings = !tab || tab === 'overview' || tab === 'triage';
            if (!onFindings && id !== 'btn-indexes-refresh') {
                return [no, no];
            }
            if (id === 'btn-indexes-refresh' && onFindings) {
                return ['', 'Scanning databases for index findings…'];
            }
            if (id === 'store-module' && onFindings) {
                return ['', 'Loading Object Intelligence…'];
            }
            // Tab switches reuse cached overview — do not flash/stuck the overlay.
            return [no, no];
        }
        """,
        Output("indexes-overview-loading", "className"),
        Output("indexes-overview-loading-text", "children"),
        Input("store-module", "data"),
        Input("store-indexes-tab", "data"),
        Input("btn-indexes-refresh", "n_clicks"),
        prevent_initial_call=True,
    )

    # Failsafe: dismiss overview overlay when data lands (including empty scan).
    app.clientside_callback(
        """
        function(data) {
            // Hide as soon as the store updates (null after error still clears overlay
            // via the server callback; non-null means paint finished).
            if (data === undefined) {
                return window.dash_clientside.no_update;
            }
            return 'hidden';
        }
        """,
        Output("indexes-overview-loading", "className", allow_duplicate=True),
        Input("store-indexes-overview", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("store-indexes-triage-filter", "data"),
        Input({"type": "indexes-triage-pill", "key": ALL}, "n_clicks"),
        Input("btn-indexes-clear-filter", "n_clicks"),
        State("store-indexes-triage-filter", "data"),
        prevent_initial_call=True,
    )
    def set_triage_filter(n_clicks, _clear, current):
        trig = ctx.triggered_id
        if trig == "btn-indexes-clear-filter":
            return "all"
        if not isinstance(trig, dict) or not any(n_clicks or []):
            return no_update
        return trig.get("key") or "all"

    @app.callback(
        Output("indexes-triage-subbar", "children", allow_duplicate=True),
        Output("indexes-triage-rail", "children", allow_duplicate=True),
        Output("indexes-triage-detail", "children", allow_duplicate=True),
        Output("store-indexes-triage-visible", "data", allow_duplicate=True),
        Output("store-indexes-selected-finding", "data", allow_duplicate=True),
        Output("btn-indexes-open-table", "disabled"),
        Input("store-indexes-triage-filter", "data"),
        Input({"type": "indexes-finding-card", "index": ALL}, "n_clicks"),
        State("store-indexes-overview", "data"),
        State("store-indexes-selected-finding", "data"),
        prevent_initial_call=True,
    )
    def update_triage_view(filt, card_clicks, payload, selected_id):
        if not payload:
            return (
                render_triage_subbar(None, filt or "all"),
                render_triage_rail(None, filt or "all", None),
                render_triage_detail(None),
                [],
                None,
                True,
            )
        filt = filt or "all"
        trig = ctx.triggered_id
        findings = filter_triage_findings(payload.get("findings"), filt)
        visible_ids = [f.get("id") for f in findings]

        if isinstance(trig, dict) and trig.get("type") == "indexes-finding-card" and any(card_clicks or []):
            idx = trig.get("index")
            if idx is not None and idx < len(findings):
                selected_id = findings[idx].get("id")

        finding = None
        for f in findings:
            if f.get("id") == selected_id:
                finding = f
                break
        if finding is None and findings:
            finding = findings[0]
            selected_id = finding.get("id")
        elif finding is None:
            selected_id = None

        return (
            render_triage_subbar(payload, filt),
            render_triage_rail(payload, filt, selected_id),
            render_triage_detail(finding),
            visible_ids,
            selected_id,
            not bool(finding and finding.get("table_name")),
        )

    @app.callback(
        Output("store-indexes-tab", "data", allow_duplicate=True),
        Output("indexes-db-dropdown", "data", allow_duplicate=True),
        Output("indexes-db-label", "children", allow_duplicate=True),
        Output("store-indexes-selected-table", "data", allow_duplicate=True),
        Output("indexes-selected-table", "children", allow_duplicate=True),
        Input("btn-indexes-open-table", "n_clicks"),
        State("store-indexes-selected-finding", "data"),
        State("store-indexes-overview", "data"),
        prevent_initial_call=True,
    )
    def open_finding_in_explorer(_n, finding_id, payload):
        if not finding_id or not payload:
            return (no_update,) * 5
        finding = None
        for f in payload.get("findings") or []:
            if f.get("id") == finding_id:
                finding = f
                break
        if not finding or not finding.get("table_name"):
            return (no_update,) * 5
        db = finding.get("database_name")
        sel = {
            "database": db,
            "schema": finding.get("schema_name") or "dbo",
            "table": finding.get("table_name"),
            "full_name": f"{finding.get('schema_name') or 'dbo'}.{finding.get('table_name')}",
        }
        return "explorer", db, db_label(db), sel, render_selected_table(sel)

    # Typing → cache-backed instant filter, else debounce + spinner
    app.clientside_callback(
        """
        function(value, cache) {
            const minChars = 2;
            const q = (value || '').trim();
            const tables = (cache && cache.tables) ? cache.tables : [];
            const hasCache = tables.length > 0;
            const empty = {
                namespace: 'dash_html_components',
                type: 'Div',
                props: {className: 'indexes-search-results-empty'}
            };
            if (q.length < minChars) {
                return [true, 0, 'indexes-search-spinner hidden', empty, []];
            }
            if (hasCache) {
                const ql = q.toLowerCase();
                const hits = [];
                for (let i = 0; i < tables.length && hits.length < 30; i++) {
                    const t = tables[i];
                    const fn = String(t.full_name || '').toLowerCase();
                    const tn = String(t.table_name || '').toLowerCase();
                    if (fn.indexOf(ql) >= 0 || tn.indexOf(ql) >= 0) hits.push(t);
                }
                if (!hits.length) {
                    return [true, 0, 'indexes-search-spinner hidden', {
                        namespace: 'dash_html_components',
                        type: 'Div',
                        props: {
                            className: 'indexes-search-list',
                            children: [{
                                namespace: 'dash_html_components',
                                type: 'Div',
                                props: {
                                    className: 'indexes-search-hint',
                                    children: 'No tables matching \\"' + q + '\\".'
                                }
                            }]
                        }
                    }, []];
                }
                const children = hits.map(function(t, i) {
                    const label = t.full_name || ((t.schema_name || '') + '.' + (t.table_name || ''));
                    return {
                        namespace: 'dash_html_components',
                        type: 'Button',
                        props: {
                            children: label,
                            id: {type: 'indexes-search-hit', index: i},
                            className: 'indexes-search-hit',
                            n_clicks: 0,
                            type: 'button',
                            title: label
                        }
                    };
                });
                return [true, 0, 'indexes-search-spinner hidden', {
                    namespace: 'dash_html_components',
                    type: 'Div',
                    props: {className: 'indexes-search-list', children: children}
                }, hits];
            }
            return [false, 0, 'indexes-search-spinner', {
                namespace: 'dash_html_components',
                type: 'Div',
                props: {
                    className: 'indexes-search-list is-loading',
                    children: [{
                        namespace: 'dash_html_components',
                        type: 'Div',
                        props: {
                            className: 'indexes-search-loading-row',
                            children: [
                                {namespace:'dash_html_components', type:'Span', props:{className:'indexes-search-spinner is-inline'}},
                                {namespace:'dash_html_components', type:'Span', props:{
                                    className:'indexes-search-hint',
                                    children: 'Searching tables…'
                                }}
                            ]
                        }
                    }]
                }
            }, window.dash_clientside.no_update];
        }
        """,
        Output("indexes-search-debounce", "disabled"),
        Output("indexes-search-debounce", "n_intervals"),
        Output("indexes-search-spinner", "className"),
        Output("indexes-search-results", "children", allow_duplicate=True),
        Output("store-indexes-search-results", "data", allow_duplicate=True),
        Input("indexes-table-search", "value"),
        State("store-indexes-table-cache", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("store-indexes-search-results", "data"),
        Output("indexes-search-results", "children"),
        Output("indexes-search-debounce", "disabled", allow_duplicate=True),
        Output("indexes-search-spinner", "className", allow_duplicate=True),
        Input("indexes-search-debounce", "n_intervals"),
        State("indexes-table-search", "value"),
        State("indexes-db-dropdown", "data"),
        State("store-indexes-table-cache", "data"),
        State("store-module", "data"),
        prevent_initial_call=True,
    )
    def search_tables(_n, query, database, cache, module):
        if cache and (cache.get("tables") or []):
            return (no_update,) * 4
        if module != "indexes" or not database:
            return [], render_search_results([], query or ""), True, "indexes-search-spinner hidden"
        q = (query or "").strip()
        if len(q) < INDEX_TABLE_SEARCH_MIN_CHARS:
            return [], render_search_results([], q), True, "indexes-search-spinner hidden"
        try:
            raw = get_provider().list_tables(database, search=q)
            rows = raw.get("tables") or []
            return rows, render_search_results(rows, q), True, "indexes-search-spinner hidden"
        except Exception as ex:
            log.exception("table search failed")
            return (
                [],
                html.Div(f"Search failed: {ex}", className="indexes-search-hint"),
                True,
                "indexes-search-spinner hidden",
            )

    @app.callback(
        Output("store-indexes-search-results", "data", allow_duplicate=True),
        Input("indexes-table-search", "value"),
        prevent_initial_call=True,
    )
    def clear_search_store(query):
        q = (query or "").strip()
        if len(q) < INDEX_TABLE_SEARCH_MIN_CHARS:
            return []
        return no_update

    @app.callback(
        Output("store-indexes-table-sort", "data"),
        Output("indexes-sort-schema", "className"),
        Output("indexes-sort-table", "className"),
        Output("indexes-sort-heap", "className"),
        Output("indexes-sort-rows", "className"),
        Input("indexes-sort-schema", "n_clicks"),
        Input("indexes-sort-table", "n_clicks"),
        Input("indexes-sort-heap", "n_clicks"),
        Input("indexes-sort-rows", "n_clicks"),
        State("store-indexes-table-sort", "data"),
        prevent_initial_call=True,
    )
    def set_table_sort(_s, _t, _h, _r, current):
        trig = ctx.triggered_id
        key = current or "table"
        if trig == "indexes-sort-schema":
            key = "schema"
        elif trig == "indexes-sort-table":
            key = "table"
        elif trig == "indexes-sort-heap":
            key = "heap"
        elif trig == "indexes-sort-rows":
            key = "rows"

        def cls(k):
            return "indexes-ii-pill active" if key == k else "indexes-ii-pill"

        return key, cls("schema"), cls("table"), cls("heap"), cls("rows")

    @app.callback(
        Output("indexes-explorer-table-list", "children"),
        Output("store-indexes-table-visible", "data"),
        Input("store-indexes-table-cache", "data"),
        Input("indexes-table-search", "value"),
        Input("store-indexes-table-sort", "data"),
        Input("store-indexes-selected-table", "data"),
        prevent_initial_call=True,
    )
    def render_table_list(cache, query, sort_key, selected):
        sort_key = sort_key or "table"
        visible = _visible_tables(cache, query or "", sort_key, selected)
        return (
            render_explorer_table_list(cache, selected, query or "", sort_key=sort_key),
            [
                {
                    "schema_name": t.get("schema_name"),
                    "table_name": t.get("table_name"),
                    "full_name": t.get("full_name"),
                    "database_name": t.get("database_name") or (cache or {}).get("database"),
                }
                for t in visible
            ],
        )

    @app.callback(
        Output("store-indexes-selected-table", "data"),
        Output("indexes-selected-table", "children"),
        Output("indexes-table-search", "value"),
        Output("indexes-search-results", "children", allow_duplicate=True),
        Output("btn-indexes-load-frag", "disabled"),
        Output("indexes-view-recommendations", "disabled"),
        Output("indexes-view-status", "disabled"),
        Output("indexes-explorer-subtabs-bar", "className"),
        Input({"type": "indexes-search-hit", "index": ALL}, "n_clicks"),
        Input({"type": "indexes-table-row", "index": ALL}, "n_clicks"),
        Input("indexes-table-search", "n_submit"),
        State("store-indexes-search-results", "data"),
        State("store-indexes-table-visible", "data"),
        State("indexes-db-dropdown", "data"),
        prevent_initial_call=True,
    )
    def select_table(search_clicks, row_clicks, n_submit, results, visible, database):
        if not database:
            return (no_update,) * 8
        trig = ctx.triggered_id
        t = None
        if isinstance(trig, dict) and trig.get("type") == "indexes-search-hit":
            if not results or not any(search_clicks or []):
                return (no_update,) * 8
            idx = trig.get("index")
            if idx is None or idx >= len(results):
                return (no_update,) * 8
            t = results[idx]
        elif isinstance(trig, dict) and trig.get("type") == "indexes-table-row":
            if not visible or not any(row_clicks or []):
                return (no_update,) * 8
            idx = trig.get("index")
            if idx is None or idx >= len(visible):
                return (no_update,) * 8
            t = visible[idx]
        elif trig == "indexes-table-search":
            if not n_submit or not results:
                return (no_update,) * 8
            t = results[0]
        if not t:
            return (no_update,) * 8
        row_db = t.get("database_name")
        if database == INDEX_DB_ALL:
            db = row_db
        else:
            db = database
        if not db:
            return (no_update,) * 8
        sel = {
            "database": db,
            "schema": t.get("schema_name"),
            "table": t.get("table_name"),
            "full_name": t.get("full_name"),
        }
        return (
            sel,
            render_selected_table(sel),
            # Keep filter so the selected row stays in the filtered list
            no_update,
            html.Div(),
            False,
            False,
            False,
            "indexes-explorer-subtabs-bar",
        )

    @app.callback(
        Output("store-indexes-selected-table", "data", allow_duplicate=True),
        Output("indexes-selected-table", "children", allow_duplicate=True),
        Output("store-indexes", "data", allow_duplicate=True),
        Output("indexes-explorer-body", "children", allow_duplicate=True),
        Output("indexes-table-search", "value", allow_duplicate=True),
        Output("indexes-search-results", "children", allow_duplicate=True),
        Output("btn-indexes-load-frag", "disabled", allow_duplicate=True),
        Output("indexes-view-recommendations", "disabled", allow_duplicate=True),
        Output("indexes-view-status", "disabled", allow_duplicate=True),
        Output("indexes-explorer-subtabs-bar", "className", allow_duplicate=True),
        Output("indexes-rec-count", "children", allow_duplicate=True),
        Input("indexes-db-dropdown", "data"),
        State("store-indexes-selected-table", "data"),
        prevent_initial_call=True,
    )
    def on_db_change(db, selected):
        # Keep selection when Open-in-Explorer sets DB + table together,
        # or when scope is All (selection still points at a real database).
        if selected and db:
            sel_db = selected.get("database")
            if sel_db == db or db == INDEX_DB_ALL:
                return (no_update,) * 11
        return (
            None,
            render_selected_table(None),
            None,
            render_explorer_idle(),
            "",
            html.Div(),
            True,
            True,
            True,
            "indexes-explorer-subtabs-bar is-disabled",
            "0",
        )

    @app.callback(
        Output("store-indexes-explorer-view", "data"),
        Output("indexes-view-recommendations", "className"),
        Output("indexes-view-status", "className"),
        Input("indexes-view-recommendations", "n_clicks"),
        Input("indexes-view-status", "n_clicks"),
        State("store-indexes-explorer-view", "data"),
        prevent_initial_call=True,
    )
    def switch_explorer_view(_r, _s, current):
        trig = ctx.triggered_id
        view = current or "recommendations"
        if trig == "indexes-view-status":
            view = "status"
        elif trig == "indexes-view-recommendations":
            view = "recommendations"
        rec_cls = "indexes-subtab active" if view == "recommendations" else "indexes-subtab"
        st_cls = "indexes-subtab active" if view == "status" else "indexes-subtab"
        return view, rec_cls, st_cls

    @app.callback(
        Output("store-indexes", "data"),
        Output("indexes-explorer-body", "children"),
        Output("indexes-explorer-loading", "className", allow_duplicate=True),
        Output("indexes-toast-refresh", "className", allow_duplicate=True),
        Output("indexes-toast-refresh", "children", allow_duplicate=True),
        Output("indexes-rec-count", "children"),
        Output("store-indexes-table-job", "data"),
        Output("indexes-table-poll", "disabled"),
        Input("store-indexes-selected-table", "data"),
        Input("btn-indexes-refresh", "n_clicks"),
        Input("store-indexes-explorer-view", "data"),
        State("store-indexes-tab", "data"),
        State("store-module", "data"),
        State("store-indexes", "data"),
        prevent_initial_call=True,
    )
    def load_explorer(sel, _refresh, view, tab, module, existing):
        """Kick off table intelligence in a background thread (avoid Page Unresponsive)."""
        from modules.indexes.table_jobs import start_table_intelligence

        if module != "indexes":
            return (no_update,) * 8
        tab = tab or "overview"
        view = view or "recommendations"
        trig = ctx.triggered_id

        if trig == "btn-indexes-refresh" and tab != "explorer":
            return (no_update,) * 8

        if not sel:
            return (
                None,
                render_explorer_idle(),
                "idx-ex-loading hidden",
                _TOAST_HIDDEN,
                no_update,
                "0",
                None,
                True,
            )

        if trig == "store-indexes-explorer-view" and existing:
            return (
                existing,
                render_explorer(existing, selected=sel, view=view),
                "idx-ex-loading hidden",
                _TOAST_HIDDEN,
                no_update,
                str(len(existing.get("recommendations") or [])),
                no_update,
                True,
            )

        job_id = start_table_intelligence(sel["database"], sel["schema"], sel["table"])
        return (
            no_update,
            no_update,
            "idx-ex-loading",
            _TOAST_HIDDEN,
            no_update,
            no_update,
            job_id,
            False,
        )

    @app.callback(
        Output("store-indexes", "data", allow_duplicate=True),
        Output("indexes-explorer-body", "children", allow_duplicate=True),
        Output("indexes-explorer-loading", "className", allow_duplicate=True),
        Output("indexes-toast-refresh", "className", allow_duplicate=True),
        Output("indexes-toast-refresh", "children", allow_duplicate=True),
        Output("indexes-rec-count", "children", allow_duplicate=True),
        Output("store-indexes-table-job", "data", allow_duplicate=True),
        Output("indexes-table-poll", "disabled", allow_duplicate=True),
        Input("indexes-table-poll", "n_intervals"),
        State("store-indexes-table-job", "data"),
        State("store-indexes-selected-table", "data"),
        State("store-indexes-explorer-view", "data"),
        prevent_initial_call=True,
    )
    def poll_table_job(_n, job_id, sel, view):
        from modules.indexes.table_jobs import get_table_job

        job = get_table_job(job_id)
        if not job or job.get("status") == "running":
            return (no_update,) * 8
        view = view or "recommendations"
        if job.get("status") == "error":
            err = html.Div(
                className="state-box state-error",
                children=[
                    html.H3("Could not load table intelligence"),
                    html.P(job.get("error") or "Unknown error"),
                    html.Pre(INDEX_PERMISSIONS_HINT, className="indexes-perm-hint"),
                ],
            )
            return (
                None,
                err,
                "idx-ex-loading hidden",
                _TOAST_ERROR,
                f"Load failed: {job.get('error')}",
                "0",
                None,
                True,
            )
        payload = job.get("payload") or {}
        return (
            payload,
            render_explorer(payload, selected=sel, view=view),
            "idx-ex-loading hidden",
            _TOAST_HIDDEN,
            no_update,
            str(len(payload.get("recommendations") or [])),
            None,
            True,
        )

    # Instant explorer loading — fixed overlay centered in viewport
    app.clientside_callback(
        """
        function(sel, n_refresh, module, tab) {
            const ctx = dash_clientside.callback_context;
            const no = window.dash_clientside.no_update;
            if (!ctx || !ctx.triggered || !ctx.triggered.length) {
                return [no, no];
            }
            if (module !== 'indexes') {
                return ['idx-ex-loading hidden', no];
            }
            const id = (ctx.triggered[0].prop_id || '').split('.')[0];
            if (id === 'store-module') {
                return ['idx-ex-loading hidden', no];
            }
            if (id === 'store-indexes-explorer-view') {
                return [no, no];
            }
            if (!sel) {
                return ['idx-ex-loading hidden', no];
            }
            if (id === 'store-indexes-selected-table' || (id === 'btn-indexes-refresh' && tab === 'explorer')) {
                const label = (sel.schema || '') + '.' + (sel.table || '');
                setTimeout(function() {
                    const row = document.querySelector('.indexes-ex-row.is-selected');
                    if (row && typeof row.scrollIntoView === 'function') {
                        row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
                    }
                }, 80);
                return ['idx-ex-loading', 'Loading table intelligence for ' + label + '…'];
            }
            return [no, no];
        }
        """,
        Output("indexes-explorer-loading", "className"),
        Output("indexes-explorer-loading-text", "children"),
        Input("store-indexes-selected-table", "data"),
        Input("btn-indexes-refresh", "n_clicks"),
        Input("store-module", "data"),
        State("store-indexes-tab", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("store-indexes", "data", allow_duplicate=True),
        Output("indexes-explorer-body", "children", allow_duplicate=True),
        Output("indexes-frag-status", "children"),
        Input("btn-indexes-load-frag", "n_clicks"),
        State("store-indexes", "data"),
        State("store-indexes-selected-table", "data"),
        State("store-indexes-explorer-view", "data"),
        prevent_initial_call=True,
    )
    def load_frag(n, payload, sel, view):
        if not n or not payload or not sel:
            return no_update, no_update, no_update
        frag = get_provider().get_table_index_frag(sel["database"], sel["schema"], sel["table"])
        if frag.get("errors"):
            return (
                payload,
                no_update,
                render_frag_status(frag.get("errors")),
            )
        updated = apply_frag_to_payload(dict(payload), frag.get("frag_rows") or [])
        return (
            updated,
            render_explorer(updated, selected=sel, view=view or "recommendations"),
            render_frag_status(ok=True),
        )

    # Copy script — green button feedback (no toast)
    app.clientside_callback(
        """
        function(n_clicks) {
            const ctx = dash_clientside.callback_context;
            const no = window.dash_clientside.no_update;
            if (!ctx || !ctx.triggered || !ctx.triggered.length) {
                return no;
            }
            const trig = ctx.triggered[0];
            if (!trig || !trig.value) {
                return no;
            }
            let id;
            try { id = JSON.parse(trig.prop_id.split('.')[0]); } catch (e) {
                return no;
            }
            const nodes = document.querySelectorAll('[id*="indexes-copy-payload"]');
            let text = '';
            let btn = null;
            nodes.forEach(function(el) {
                try {
                    const eid = JSON.parse(el.getAttribute('id') || '{}');
                    if (eid.index === id.index && eid.script === id.script) {
                        text = el.textContent || '';
                    }
                } catch (err) {}
            });
            document.querySelectorAll('[id*="indexes-copy-btn"]').forEach(function(el) {
                try {
                    const eid = JSON.parse(el.getAttribute('id') || '{}');
                    if (eid.index === id.index && eid.script === id.script) {
                        btn = el;
                    }
                } catch (err) {}
            });
            if (text && navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text);
            }
            if (btn) {
                btn.classList.add('is-copied');
                const prev = btn.textContent;
                btn.textContent = 'Copied';
                if (window.__idxCopyTimers && window.__idxCopyTimers[btn.id]) {
                    clearTimeout(window.__idxCopyTimers[btn.id]);
                }
                window.__idxCopyTimers = window.__idxCopyTimers || {};
                window.__idxCopyTimers[btn.id] = setTimeout(function() {
                    btn.classList.remove('is-copied');
                    btn.textContent = prev || 'Copy';
                }, 1800);
            }
            return no;
        }
        """,
        Output("indexes-copy-toast", "className"),
        Input({"type": "indexes-copy-btn", "index": ALL, "script": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
