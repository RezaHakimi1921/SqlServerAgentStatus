"""Blocking tree layout component tests."""
from dash.development.base_component import Component

from modules.activity.layout import render_blocking_table, render_health_strip


def _walk(node):
    if isinstance(node, Component):
        yield node
        children = getattr(node, "children", None)
        if children is not None:
            yield from _walk(children)
    elif isinstance(node, (list, tuple)):
        for child in node:
            yield from _walk(child)


def _text(node) -> str:
    parts = []
    for item in _walk(node):
        children = getattr(item, "children", None)
        if isinstance(children, (str, int, float)):
            parts.append(str(children))
    return " ".join(parts)


def _node(session_id, *, children=None):
    return {
        "session_id": session_id,
        "login": f"login-{session_id}",
        "sql_snippet": f"SELECT {session_id}",
        "command": "SELECT",
        "wait_sec": 12.5,
        "wait_type": "LCK_M_X",
        "wait_resource_raw": "KEY: 5:72057594000000000 (abc)",
        "wait_object": None,
        "children": children or [],
    }


def test_blocking_health_strip_uses_blast_head_and_chain_age():
    strip = render_health_strip(
        {"blast_radius": 8, "head_blockers": 2, "chain_age_sec": 125},
        tab="blocking",
    )

    assert "Blast radius 8" in _text(strip)
    assert "Head blockers 2" in _text(strip)
    assert "Chain age 00:02:05" in _text(strip)


def test_blocking_table_renders_tree_and_collapses_children_after_two():
    children = [_node(201), _node(202), _node(203)]
    head = _node(100, children=children)
    result = {
        "status": "ok",
        "rows": [{"blocker_session_id": 100, "blocked_session_id": 201}],
        "trees": [{
            "head_session_id": 100,
            "head": head,
            "children": children,
            "blast_radius": 3,
            "chain_age_sec": 125,
            "blocked_spids": [201, 202, 203],
        }],
    }

    rendered = render_blocking_table(result)
    classes = {getattr(item, "className", "") for item in _walk(rendered)}
    tags = {item.__class__.__name__ for item in _walk(rendered)}
    text = _text(rendered)

    assert "blk-tree" in classes
    assert "Details" in tags
    assert "login-100 — head blocker" in text
    assert "+ 1 more sessions" in text
    assert text.count("login-201") == 1
