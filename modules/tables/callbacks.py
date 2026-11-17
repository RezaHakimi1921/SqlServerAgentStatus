"""Tables & Growth callbacks — dual panels + pagination (Figma)."""
from __future__ import annotations

from dash import ALL, Input, Output, State, ctx, html, no_update

from core.i18n import normalize_locale, t
from core.logging_setup import get_logger
from core.providers.sqlserver_provider import get_provider
from modules.tables.constants import TABLES_HISTORY_RETENTION_DAYS
from modules.tables.layout import (
    page_slice_meta,
    render_all_tables,
    render_header_status,
    render_overview,
    render_pagination_info,
    render_tables_db_options,
    render_tables_meta,
    render_tables_type_options,
    tables_db_option_values,
    tables_type_label,
)
from modules.tables.service import build_tables_payload, filter_sort_tables

log = get_logger("sqlmonitor.tables.ui")


def _load_payload(*, force: bool = False) -> dict:
    raw = get_provider().get_table_growth_snapshot(force=force)
    return build_tables_payload(raw)


def register_tables_callbacks(app):
    # Instant tab switch (no server round-trip / no heavy re-render)
    app.clientside_callback(
        """
        function(nOv, nAll, current) {
            const ctx = dash_clientside.callback_context;
            let section = current || 'overview';
            if (ctx && ctx.triggered && ctx.triggered.length) {
                const id = (ctx.triggered[0].prop_id || '').split('.')[0];
                if (id === 'tables-tab-all') section = 'tables';
                if (id === 'tables-tab-overview') section = 'overview';
            }
            const ovTab = 'tables-subtab' + (section === 'overview' ? ' is-active' : '');
            const allTab = 'tables-subtab' + (section === 'tables' ? ' is-active' : '');
            const toolbar = 'tables-all-controls' + (section === 'tables' ? '' : ' hidden');
            const ovPanel = 'tables-panel-host' + (section === 'overview' ? '' : ' hidden');
            const allPanel = 'tables-panel-host' + (section === 'tables' ? '' : ' hidden');
            const pager = 'tables-pagination' + (section === 'tables' ? '' : ' hidden');
            return [section, ovTab, allTab, toolbar, ovPanel, allPanel, pager];
        }
        """,
        Output("store-tables-section", "data"),
        Output("tables-tab-overview", "className"),
        Output("tables-tab-all", "className"),
        Output("tables-all-toolbar", "className"),
        Output("tables-panel-overview", "className"),
        Output("tables-panel-all", "className"),
        Output("tables-pagination", "className"),
        Input("tables-tab-overview", "n_clicks"),
        Input("tables-tab-all", "n_clicks"),
        State("store-tables-section", "data"),
        prevent_initial_call=False,
    )

    @app.callback(
        Output("store-tables-page", "data", allow_duplicate=True),
        Output("store-tables-window", "data"),
        Output("tables-win-1d", "className"),
        Output("tables-win-7d", "className"),
        Output("tables-win-30d", "className"),
        Output({"type": "tables-sort", "key": "delta_mb"}, "children"),
        Input("tables-win-1d", "n_clicks"),
        Input("tables-win-7d", "n_clicks"),
        Input("tables-win-30d", "n_clicks"),
        State("store-tables-window", "data"),
        State("store-locale", "data"),
        prevent_initial_call=True,
    )
    def switch_window(n1, n7, n30, current, locale):
        tid = ctx.triggered_id
        if tid not in ("tables-win-1d", "tables-win-7d", "tables-win-30d"):
            return (no_update,) * 6
        window = current or "7d"
        loc = normalize_locale(locale)
        if tid == "tables-win-1d":
            window = "1d"
        elif tid == "tables-win-7d":
            window = "7d"
        elif tid == "tables-win-30d":
            window = "30d"

        def cls(w):
            return "tables-win-btn" + (" is-active" if window == w else "")

        return (
            1,
            window,
            cls("1d"),
            cls("7d"),
            cls("30d"),
            t("tables.sort.delta_mb", loc, window=window),
        )

    @app.callback(
        Output("store-tables-sort", "data"),
        Output({"type": "tables-sort", "key": ALL}, "className"),
        Input({"type": "tables-sort", "key": ALL}, "n_clicks"),
        State("store-tables-sort", "data"),
        State({"type": "tables-sort", "key": ALL}, "id"),
        prevent_initial_call=False,
    )
    def switch_sort(_clicks, current, ids):
        tid = ctx.triggered_id
        sort = current or "size_mb"
        if isinstance(tid, dict) and tid.get("key"):
            sort = tid["key"]
        classes = [
            "tables-sort-btn" + (" is-active" if (i or {}).get("key") == sort else "")
            for i in (ids or [])
        ]
        return sort, classes

    app.clientside_callback(
        """
        function(n_toggle, open) {
            const next = !open;
            return [
                next,
                next ? 'tables-db-panel' : 'tables-db-panel hidden',
                false,
                'tables-db-panel hidden',
            ];
        }
        """,
        Output("store-tables-db-open", "data"),
        Output("tables-db-panel", "className"),
        Output("store-tables-type-open", "data", allow_duplicate=True),
        Output("tables-type-panel", "className", allow_duplicate=True),
        Input("tables-db-toggle", "n_clicks"),
        State("store-tables-db-open", "data"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(n_toggle, open) {
            const next = !open;
            return [
                next,
                next ? 'tables-db-panel' : 'tables-db-panel hidden',
                false,
                'tables-db-panel hidden',
            ];
        }
        """,
        Output("store-tables-type-open", "data"),
        Output("tables-type-panel", "className"),
        Output("store-tables-db-open", "data", allow_duplicate=True),
        Output("tables-db-panel", "className", allow_duplicate=True),
        Input("tables-type-toggle", "n_clicks"),
        State("store-tables-type-open", "data"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("tables-db-options", "children"),
        Input("tables-db-filter-q", "value"),
        Input("store-tables-db-names", "data"),
        Input("store-tables-db", "data"),
        prevent_initial_call=False,
    )
    def filter_db_options(query, names, selected):
        return render_tables_db_options(
            names or ["All"],
            selected=selected or "All",
            query=query or "",
        )

    @app.callback(
        Output("store-tables-db", "data"),
        Output("tables-db-label", "children"),
        Output("store-tables-db-open", "data", allow_duplicate=True),
        Output("tables-db-panel", "className", allow_duplicate=True),
        Output("tables-db-filter-q", "value"),
        Output("store-tables-type-open", "data", allow_duplicate=True),
        Output("tables-type-panel", "className", allow_duplicate=True),
        Input({"type": "tables-db-hit", "index": ALL}, "n_clicks"),
        State("store-tables-db-names", "data"),
        State("tables-db-filter-q", "value"),
        prevent_initial_call=True,
    )
    def pick_db(_clicks, names, query):
        tid = ctx.triggered_id
        if not isinstance(tid, dict) or tid.get("type") != "tables-db-hit":
            return (no_update,) * 7
        if not any(_clicks or []):
            return (no_update,) * 7
        idx = tid.get("index")
        values = tables_db_option_values(names or ["All"], query or "")
        if idx is None or idx < 0 or idx >= len(values):
            return (no_update,) * 7
        value = values[idx] or "All"
        return (
            value,
            value,
            False,
            "tables-db-panel hidden",
            "",
            False,
            "tables-db-panel hidden",
        )

    @app.callback(
        Output("store-tables-type", "data"),
        Output("tables-type-label", "children"),
        Output("tables-type-panel", "children"),
        Output("store-tables-type-open", "data", allow_duplicate=True),
        Output("tables-type-panel", "className", allow_duplicate=True),
        Output("store-tables-db-open", "data", allow_duplicate=True),
        Output("tables-db-panel", "className", allow_duplicate=True),
        Input({"type": "tables-type-hit", "key": ALL}, "n_clicks"),
        State("store-locale", "data"),
        prevent_initial_call=True,
    )
    def pick_type(_clicks, locale):
        tid = ctx.triggered_id
        if not isinstance(tid, dict) or tid.get("type") != "tables-type-hit":
            return (no_update,) * 7
        if not any(_clicks or []):
            return (no_update,) * 7
        loc = normalize_locale(locale)
        key = str(tid.get("key") or "all").strip().lower() or "all"
        label = tables_type_label(key, loc)
        return (
            key,
            label,
            render_tables_type_options(selected=key, locale=loc),
            False,
            "tables-db-panel hidden",
            False,
            "tables-db-panel hidden",
        )

    # Live search: keystrokes arm a short debounce; paint uses store (not Enter).
    app.clientside_callback(
        """
        function(value) {
            return [false, 0];
        }
        """,
        Output("tables-search-debounce", "disabled"),
        Output("tables-search-debounce", "n_intervals"),
        Input("tables-search", "value"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(n, value) {
            if (!n) {
                return [window.dash_clientside.no_update, window.dash_clientside.no_update];
            }
            return [value || "", true];
        }
        """,
        Output("store-tables-search", "data"),
        Output("tables-search-debounce", "disabled", allow_duplicate=True),
        Input("tables-search-debounce", "n_intervals"),
        State("tables-search", "value"),
        prevent_initial_call=True,
    )

    # Enter applies immediately (no wait for debounce tick).
    app.clientside_callback(
        """
        function(n_submit, value) {
            if (!n_submit) {
                return [window.dash_clientside.no_update, window.dash_clientside.no_update];
            }
            return [value || "", true];
        }
        """,
        Output("store-tables-search", "data", allow_duplicate=True),
        Output("tables-search-debounce", "disabled", allow_duplicate=True),
        Input("tables-search", "n_submit"),
        State("tables-search", "value"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("store-tables-page", "data"),
        Input("btn-tables-page-prev", "n_clicks"),
        Input("btn-tables-page-next", "n_clicks"),
        Input("store-tables-search", "data"),
        Input("store-tables-db", "data"),
        Input("store-tables-type", "data"),
        Input("store-tables-sort", "data"),
        Input("store-tables-window", "data"),
        Input("store-tables", "data"),
        State("store-tables-page", "data"),
        prevent_initial_call=True,
    )
    def paginate(prev, nxt, _search, _db, _type, _sort, _window, _payload, page):
        tid = ctx.triggered_id
        page = page or 1
        if tid == "btn-tables-page-prev":
            return max(1, page - 1)
        if tid == "btn-tables-page-next":
            return page + 1
        return 1

    _LOADING_SHOW = "tables-loading-overlay view-center-loading"
    _LOADING_HIDE = "tables-loading-overlay view-center-loading hidden"

    @app.callback(
        Output("store-tables", "data"),
        Output("tables-meta", "children"),
        Output("tables-history-pill", "children"),
        Output("tables-source-badge", "children"),
        Output("tables-captured-date", "children"),
        Output("tables-history-pill", "className"),
        Output("tables-source-badge", "className"),
        Output("store-tables-db-names", "data"),
        Output("tables-loading", "className"),
        Input("btn-tables-refresh", "n_clicks"),
        Input("btn-tables-capture", "n_clicks"),
        Input("store-module", "data"),
        State("store-tables", "data"),
        State("store-locale", "data"),
        prevent_initial_call=False,
        running=[
            (Output("tables-loading", "className"), _LOADING_SHOW, _LOADING_HIDE),
        ],
    )
    def load_tables(_refresh, _capture, module, existing, locale):
        """Manual-only after first open: Refresh / Capture refetch; no auto interval."""
        loc = normalize_locale(locale)
        if module != "tables":
            return (no_update,) * 9

        capture_msg = None
        triggered = ctx.triggered_id
        force = triggered in ("btn-tables-refresh", "btn-tables-capture")
        # Keep last snapshot when returning to the page — user refreshes deliberately.
        if (
            not force
            and triggered == "store-module"
            and isinstance(existing, dict)
            and (existing.get("tables") is not None or existing.get("errors"))
        ):
            return (no_update,) * 9
        try:
            if triggered == "btn-tables-capture":
                result = get_provider().capture_objsize_history(
                    retention_days=int(TABLES_HISTORY_RETENTION_DAYS),
                )
                if result.get("ok"):
                    n = int(result.get("rows_captured") or 0)
                    src = result.get("source") or "?"
                    days = int(result.get("history_day_count") or 0)
                    capture_msg = f"Captured {n:,} rows ({src})"
                    if n <= 0:
                        capture_msg += (
                            " — nothing written. Check EXECUTE on "
                            "insight.USP_Insight_ObjSize_Capture and "
                            "INSERT/DELETE on insight.ObjSize_History."
                        )
                    elif days < 2:
                        capture_msg += (
                            " · First snapshot day saved. Growth (1d/7d/30d) appears "
                            "after tomorrow’s capture (or keep the daily job)."
                        )
                else:
                    capture_msg = f"Capture failed: {result.get('error') or 'unknown'}"
                    if result.get("permissions_hint"):
                        capture_msg += f" — {result['permissions_hint']}"
            payload = _load_payload(force=force)
        except Exception as ex:
            log.exception("load tables failed")
            err_payload = {"errors": {"load": str(ex)}, "tables": [], "databases": []}
            return (
                err_payload,
                str(ex),
                f"● {t('common.error', loc)}",
                t("common.none", loc),
                "",
                "tables-history-pill is-warn",
                "tables-source-badge",
                ["All"],
                _LOADING_HIDE,
            )

        hist, src, date = render_header_status(payload, locale=loc)
        hist_cls = (
            "tables-history-pill is-ok"
            if payload.get("history_available")
            else "tables-history-pill is-warn"
        )
        src_name = (payload.get("source") or "live").lower()
        src_cls = (
            "tables-source-badge is-catalog"
            if src_name == "catalog"
            else "tables-source-badge is-live"
        )
        db_names = ["All"] + list(payload.get("db_names") or [])
        return (
            payload,
            render_tables_meta(payload, capture_msg),
            hist,
            src,
            date,
            hist_cls,
            src_cls,
            db_names,
            _LOADING_HIDE,
        )

    # Overview: only data + window (tab switch does not re-render)
    @app.callback(
        Output("tables-panel-overview", "children"),
        Input("store-tables", "data"),
        Input("store-tables-window", "data"),
        State("store-module", "data"),
        State("store-locale", "data"),
        prevent_initial_call=False,
    )
    def paint_overview(payload, window, module, locale):
        from modules.tables.layout import render_tables_loading

        if module != "tables":
            return no_update
        loc = normalize_locale(locale)
        if payload is None:
            return render_tables_loading(locale=loc)
        return render_overview(payload, window=window or "7d", locale=loc)

    # All Tables: filters / page (not section switch)
    @app.callback(
        Output("tables-panel-all", "children"),
        Output("tables-pagination-info", "children"),
        Output("tables-page-pos", "children"),
        Output("btn-tables-page-prev", "disabled"),
        Output("btn-tables-page-next", "disabled"),
        Input("store-tables", "data"),
        Input("store-tables-window", "data"),
        Input("store-tables-sort", "data"),
        Input("store-tables-db", "data"),
        Input("store-tables-type", "data"),
        Input("store-tables-search", "data"),
        Input("store-tables-page", "data"),
        State("store-module", "data"),
        State("store-locale", "data"),
        prevent_initial_call=False,
    )
    def paint_all(payload, window, sort, database, type_status, search, page, module, locale):
        loc = normalize_locale(locale)
        if module != "tables":
            return (no_update,) * 5
        if payload is None:
            from modules.tables.layout import render_tables_loading

            return (
                render_tables_loading(locale=loc),
                "",
                "—",
                True,
                True,
            )
        days = 7
        w = (window or "7d").strip().lower()
        if w == "1d":
            days = 1
        elif w == "30d":
            days = 30
        type_key = (type_status or "all").strip().lower() or "all"
        tables = payload.get("tables") or []
        filtered = filter_sort_tables(
            tables,
            database=database or "All",
            search=search or "",
            sort=sort or "size_mb",
            window_days=days,
            type_status=type_key,
        )
        total = len(filtered)
        page, total_pages, _start, start_n, end_n = page_slice_meta(total, page or 1)
        page = min(page, total_pages)
        return (
            render_all_tables(
                payload,
                window=window or "7d",
                search=search or "",
                database=database or "All",
                sort=sort or "size_mb",
                page=page,
                type_status=type_key,
                locale=loc,
            ),
            render_pagination_info(total, page, total_pages, start_n, end_n, locale=loc),
            f"{page} / {total_pages}",
            page <= 1,
            page >= total_pages or total == 0,
        )
