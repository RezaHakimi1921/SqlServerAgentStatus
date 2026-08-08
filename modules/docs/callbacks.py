"""Docs module — one topic per page; sidebar + pager + hash deep-link."""
from __future__ import annotations

from dash import ALL, Input, Output, State, callback_context, no_update

from modules.docs.layout import DOCS_PAGE_IDS, DOCS_PAGES, build_docs_page


def _normalize_page(page: str | None) -> str:
    p = (page or "").strip().lower().lstrip("#")
    if p.startswith("docs-sec-"):
        p = p[len("docs-sec-"):]
    if p.startswith("docs-page-"):
        p = p[len("docs-page-"):]
    if p not in DOCS_PAGE_IDS:
        return "overview"
    return p


def _neighbors(page: str) -> tuple[str | None, str | None, int]:
    page = _normalize_page(page)
    idx = DOCS_PAGE_IDS.index(page)
    prev_id = DOCS_PAGE_IDS[idx - 1] if idx > 0 else None
    next_id = DOCS_PAGE_IDS[idx + 1] if idx < len(DOCS_PAGE_IDS) - 1 else None
    return prev_id, next_id, idx


def register_docs_callbacks(app):
    @app.callback(
        Output("store-docs-page", "data"),
        Input({"type": "docs-nav", "page": ALL}, "n_clicks"),
        Input("docs-pager-prev", "n_clicks"),
        Input("docs-pager-next", "n_clicks"),
        Input("docs-url", "hash"),
        State("store-docs-page", "data"),
        prevent_initial_call=True,
    )
    def set_docs_page(_nav, _prev, _next, url_hash, current):
        trig = callback_context.triggered_id
        cur = _normalize_page(current)
        if isinstance(trig, dict) and trig.get("type") == "docs-nav":
            page = _normalize_page(trig.get("page"))
            return no_update if page == cur else page
        if trig == "docs-pager-prev":
            prev_id, _, _ = _neighbors(cur)
            return no_update if not prev_id else prev_id
        if trig == "docs-pager-next":
            _, next_id, _ = _neighbors(cur)
            return no_update if not next_id else next_id
        if trig == "docs-url":
            raw = (url_hash or "").lstrip("#")
            if not raw:
                return no_update
            page = _normalize_page(raw)
            return no_update if page == cur else page
        return no_update

    @app.callback(
        Output("docs-page-host", "children"),
        Output({"type": "docs-nav", "page": ALL}, "className"),
        Output("docs-pager-prev", "children"),
        Output("docs-pager-prev", "disabled"),
        Output("docs-pager-prev", "className"),
        Output("docs-pager-next", "children"),
        Output("docs-pager-next", "disabled"),
        Output("docs-pager-next", "className"),
        Output("docs-pager-pos", "children"),
        Output("docs-url", "hash"),
        Input("store-docs-page", "data"),
        State({"type": "docs-nav", "page": ALL}, "id"),
        State("docs-url", "hash"),
    )
    def render_docs_page(page, nav_ids, current_hash):
        page = _normalize_page(page)
        prev_id, next_id, idx = _neighbors(page)
        labels = dict(DOCS_PAGES)

        body = build_docs_page(page)
        classes = [
            "docs-nav-link" + (" is-active" if (item.get("page") if isinstance(item, dict) else None) == page else "")
            for item in (nav_ids or [])
        ]

        prev_lbl = f"→ {labels[prev_id]}" if prev_id else "→"
        next_lbl = f"{labels[next_id]} ←" if next_id else "←"
        prev_cls = "docs-pager-btn" + ("" if prev_id else " is-disabled")
        next_cls = "docs-pager-btn" + ("" if next_id else " is-disabled")
        pos = f"{idx + 1} / {len(DOCS_PAGE_IDS)}"

        want_hash = f"#docs-sec-{page}"
        hash_out = no_update if (current_hash or "") == want_hash else want_hash

        return (
            body,
            classes,
            prev_lbl,
            not bool(prev_id),
            prev_cls,
            next_lbl,
            not bool(next_id),
            next_cls,
            pos,
            hash_out,
        )
