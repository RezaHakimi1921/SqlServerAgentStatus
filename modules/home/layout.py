"""Home shell — centered tiles with neon spinning border (card stays straight)."""
from dash import html

from core.registry import list_modules


def build_home_layout():
    # Ready modules first, Coming soon next, Settings always last
    modules = sorted(
        list_modules(),
        key=lambda m: (
            2 if m["id"] == "settings" else (0 if m["status"] == "ready" else 1),
            m["title"],
        ),
    )
    tiles = []
    for m in modules:
        soon = m["status"] == "soon"
        inner = html.Div(
            className="neon-card-inner home-tile-inner",
            children=[
                html.Div(m["icon"], className="home-tile-icon"),
                html.Div(m["title"], className="home-tile-title"),
                html.Div(m["subtitle"], className="home-tile-sub"),
                html.Div(
                    "Coming soon" if soon else "Open",
                    className="home-tile-cta",
                ),
            ],
        )
        tiles.append(
            html.Button(
                className="neon-card home-tile" + (" soon" if soon else " ready"),
                id={"type": "home-tile", "module": m["id"]},
                n_clicks=0,
                disabled=soon,
                children=[
                    html.Div(className="neon-spin", **{"aria-hidden": "true"}),
                    inner,
                ],
            )
        )
    return html.Div(
        className="home-shell",
        children=[
            html.Div(className="home-hero", children=[
                html.H2("SQL Server Monitor"),
                html.P("Choose a module to start monitoring."),
            ]),
            html.Div(className="home-grid", children=tiles),
        ],
    )
