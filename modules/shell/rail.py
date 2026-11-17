"""App shell — Figma Make sidebar (RTL right rail) with brand, nav, connection, user."""
from __future__ import annotations

from dash import html

from core.i18n import module_subtitle, module_title, t
from core.registry import list_modules


def icon(name: str) -> html.Span:
    """SVG icon via CSS mask (color inherits from currentColor)."""
    return html.Span(
        className=f"rail-ico rail-ico-{name}",
        **{"aria-hidden": "true"},
    )


_icon = icon

ICON_BY_MODULE = {
    "home": "home",
    "jobs": "jobs",
    "activity": "activity",
    "insights": "insights",
    "tables": "tables",
    "indexes": "indexes",
    "docs": "docs",
    "settings": "settings",
    "disk": "disk",
    "waits": "waits",
}
_ICON_BY_MODULE = ICON_BY_MODULE

# Figma nav order for primary workspace (product modules still reachable)
_FIGMA_ORDER = (
    "home",
    "jobs",
    "activity",
    "insights",
    "tables",
    "indexes",
    "docs",
    "disk",
    "waits",
    "settings",
)


def build_app_rail(
    *,
    locale: str = "en",
    collapsed: bool = False,
    active: str = "home",
    connection_ok: bool = True,
    connection_age: str | None = None,
    user_name: str | None = None,
    user_role: str | None = None,
) -> html.Aside:
    """Fixed right sidebar matching Figma Make (docs/design/figma-make)."""
    by_id = {m["id"]: m for m in list_modules()}
    items = [{"id": "home", "status": "ready"}]
    for mid in _FIGMA_ORDER:
        if mid == "home":
            continue
        if mid == "settings":
            continue
        if mid in by_id:
            items.append({"id": mid, "status": by_id[mid].get("status") or "ready"})
    # Settings lives in Figma footer control — not duplicated in primary nav.

    seen: set[str] = set()
    ordered = []
    for it in items:
        if it["id"] in seen or it["id"] == "settings":
            continue
        seen.add(it["id"])
        ordered.append(it)

    buttons = []
    for it in ordered:
        mid = it["id"]
        soon = it["status"] == "soon"
        if mid == "home":
            label = "نمای کلی" if locale == "fa" else t("nav.home", locale)
            title = label
        else:
            label = module_title(mid, locale)
            title = f"{label} — {module_subtitle(mid, locale)}"
        ico = ICON_BY_MODULE.get(mid, "home")
        badge = None
        if mid == "insights":
            badge = html.B("!", className="danger")
        buttons.append(
            html.Button(
                type="button",
                id={"type": "rail-nav", "module": mid},
                n_clicks=0,
                disabled=soon,
                title=title + ((" (" + t("home.soon", locale) + ")") if soon else ""),
                className=("active" if mid == active else "") + (" is-soon" if soon else ""),
                children=[
                    icon(ico),
                    html.Span(label, className="rail-label"),
                    badge,
                    html.Span(t("home.soon", locale), className="rail-soon") if soon else None,
                ],
            )
        )

    age = connection_age or ("—" if locale == "fa" else "—")
    conn_title = "اتصال پایدار" if locale == "fa" else t("header.connected", locale)
    conn_sub = (
        f"آخرین پاسخ موفق · {age}"
        if locale == "fa"
        else f"Last successful poll · {age}"
    )
    uname = user_name or ("رضا حکیمی" if locale == "fa" else "Operator")
    urole = user_role or ("مدیر سیستم" if locale == "fa" else "System admin")
    initials = "".join(p[0] for p in uname.split()[:2]) if uname else "OP"

    return html.Aside(
        id="app-rail",
        className="sidebar app-rail" + (" is-collapsed" if collapsed else ""),
        role="navigation",
        **{"aria-label": t("nav.menu", locale)},
        children=[
            html.Div(
                className="brand",
                children=[
                    html.Div(className="brand-mark", children=[icon("jobs")]),
                    html.Div(
                        children=[
                            html.Strong("SQL Agent"),
                            html.Span(
                                "مرکز پایش عملیات" if locale == "fa" else "Operations monitor"
                            ),
                        ]
                    ),
                    html.Button(
                        type="button",
                        id="btn-rail-toggle",
                        n_clicks=0,
                        className="rail-toggle",
                        title=t("nav.collapse", locale) if not collapsed else t("nav.expand", locale),
                        children=[icon("chevrons-right" if not collapsed else "chevrons-left")],
                    ),
                ],
            ),
            html.Div(
                className="sidebar-section-label",
                children="فضای کاری" if locale == "fa" else "Workspace",
            ),
            html.Nav(className="side-nav rail-list", children=buttons),
            html.Div(className="sidebar-spacer"),
            html.Div(
                className="connection-card" + ("" if connection_ok else " is-bad"),
                children=[
                    html.Div(
                        className="connection-head",
                        children=[
                            html.Span(className="status-light"),
                            html.Strong(conn_title),
                        ],
                    ),
                    html.P(conn_sub),
                    html.Div(className="mini-progress", children=html.Span()),
                ],
            ),
            html.Button(
                type="button",
                id={"type": "rail-nav", "module": "settings"},
                n_clicks=0,
                className="sidebar-settings" + (" active" if active == "settings" else ""),
                children=[
                    icon("settings"),
                    html.Span("تنظیمات سیستم" if locale == "fa" else "System settings"),
                ],
            ),
            html.Div(
                className="user-card",
                children=[
                    html.Div(initials, className="avatar"),
                    html.Div(
                        children=[
                            html.Strong(uname),
                            html.Span(urole),
                        ]
                    ),
                ],
            ),
        ],
    )
