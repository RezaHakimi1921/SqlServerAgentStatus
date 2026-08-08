"""Build nested blocking trees from DMV edge rows."""
from __future__ import annotations

from typing import Any


def _edge_key(row: dict) -> tuple:
    return (
        row.get("blocked_session_id"),
        row.get("blocker_session_id"),
        row.get("wait_resource"),
        row.get("chain_display"),
    )


def _dedupe_edges(rows: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for row in rows:
        blocker = int(row["blocker_session_id"])
        blocked = int(row["blocked_session_id"])
        if blocker == blocked:
            continue
        key = _edge_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _head_node(session_id: int, edge: dict) -> dict:
    return {
        "session_id": session_id,
        "login": edge.get("blocker_login") or "—",
        "host": edge.get("blocker_host") or "",
        "program": edge.get("blocker_program") or "",
        "database_name": edge.get("database_name") or "",
        "open_tran": _safe_int(edge.get("blocker_open_tran")) or 0,
        "sql_snippet": edge.get("blocker_sql") or "",
        "command": edge.get("blocker_command") or "",
        "request_elapsed_sec": _safe_int(edge.get("request_elapsed_sec")),
        "wait_sec": None,
        "wait_type": None,
        "wait_resource_raw": None,
        "wait_object": None,
        "is_head": True,
        "children": [],
    }


def _child_node(session_id: int, edge: dict) -> dict:
    wait_sec = edge.get("wait_seconds")
    if wait_sec is None and edge.get("wait_time") is not None:
        wait_sec = float(edge["wait_time"]) / 1000.0
    return {
        "session_id": session_id,
        "login": edge.get("blocked_login") or "—",
        "host": edge.get("blocked_host") or "",
        "program": edge.get("blocked_program") or "",
        "database_name": edge.get("database_name") or "",
        "open_tran": 0,
        "sql_snippet": edge.get("blocked_sql") or "",
        "command": edge.get("blocked_command") or "",
        "request_elapsed_sec": _safe_int(edge.get("request_elapsed_sec")),
        "wait_sec": wait_sec,
        "wait_type": edge.get("wait_type"),
        "wait_resource_raw": edge.get("wait_resource"),
        "wait_object": edge.get("wait_object"),
        "is_head": False,
        "children": [],
    }


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _subtree_metrics(node: dict) -> tuple[set[int], int, float]:
    """Return (blocked_spids, chain_age_sec, max_wait_sec) for a built node subtree."""
    blocked: set[int] = set()
    ages: list[int] = []
    waits: list[float] = []

    def walk(n: dict, *, is_root_head: bool = False) -> None:
        elapsed = _safe_int(n.get("request_elapsed_sec"))
        if elapsed is not None:
            ages.append(elapsed)
        if not is_root_head:
            blocked.add(int(n["session_id"]))
            try:
                w = n.get("wait_sec")
                if w is not None:
                    waits.append(float(w))
            except (TypeError, ValueError):
                pass
        for child in n.get("children") or []:
            walk(child)

    walk(node, is_root_head=True)
    chain_age = max(ages) if ages else 0
    max_wait = max(waits) if waits else 0.0
    return blocked, chain_age, max_wait


def _build_subtree(
    session_id: int,
    *,
    children_map: dict[int, list[tuple[int, dict]]],
    edge_lookup: dict[tuple[int, int], dict],
    path: set[int],
    as_head: bool,
) -> dict | None:
    if session_id in path:
        return None

    path = set(path)
    path.add(session_id)

    if as_head:
        # Prefer an edge where this session is the blocker.
        sample_edge = None
        for blocked_id, edge in children_map.get(session_id, []):
            if int(edge["blocker_session_id"]) == session_id:
                sample_edge = edge
                break
        if sample_edge is None:
            # Cycle-only root: use any edge where session appears as blocker.
            for (blocker, _blocked), edge in edge_lookup.items():
                if blocker == session_id:
                    sample_edge = edge
                    break
        if sample_edge is None:
            return None
        node = _head_node(session_id, sample_edge)
    else:
        parent_candidates = [
            edge
            for (blocker, blocked), edge in edge_lookup.items()
            if blocked == session_id
        ]
        if not parent_candidates:
            return None
        node = _child_node(session_id, parent_candidates[0])
        # Intermediate blocker: open_tran lives on edges where this session is blocker
        for _bid, edge in children_map.get(session_id, []):
            ot = _safe_int(edge.get("blocker_open_tran"))
            if ot is not None:
                node["open_tran"] = ot
                break

    child_ids: list[int] = []
    seen_child: set[int] = set()
    for blocked_id, _edge in children_map.get(session_id, []):
        bid = int(blocked_id)
        if bid in seen_child:
            continue
        seen_child.add(bid)
        child_ids.append(bid)

    for child_id in child_ids:
        child_edge = edge_lookup.get((session_id, child_id))
        if child_edge is None:
            continue
        if child_id in path:
            continue
        child = _build_subtree(
            child_id,
            children_map=children_map,
            edge_lookup=edge_lookup,
            path=path,
            as_head=False,
        )
        if child is not None:
            node["children"].append(child)

    return node


def build_blocking_trees(rows: list[dict]) -> list[dict]:
    """Build nested blocking trees from edge rows."""
    edges = _dedupe_edges(rows)
    if not edges:
        return []

    children_map: dict[int, list[tuple[int, dict]]] = {}
    edge_lookup: dict[tuple[int, int], dict] = {}
    blockers: set[int] = set()
    blocked_set: set[int] = set()

    for edge in edges:
        blocker = int(edge["blocker_session_id"])
        blocked = int(edge["blocked_session_id"])
        blockers.add(blocker)
        blocked_set.add(blocked)
        children_map.setdefault(blocker, []).append((blocked, edge))
        edge_lookup[(blocker, blocked)] = edge

    natural_roots = blockers - blocked_set
    reachable: set[int] = set()
    for root in natural_roots:
        stack = [root]
        while stack:
            sid = stack.pop()
            if sid in reachable:
                continue
            reachable.add(sid)
            for child_id, _ in children_map.get(sid, []):
                stack.append(int(child_id))

    # Blockers caught in cycles (blocked but unreachable from a natural root).
    cycle_roots = blockers - reachable
    root_ids = sorted(natural_roots | cycle_roots)

    trees: list[dict] = []
    seen_roots: set[int] = set()

    for root_id in root_ids:
        if root_id not in blockers or root_id in seen_roots:
            continue
        seen_roots.add(root_id)

        head = _build_subtree(
            root_id,
            children_map=children_map,
            edge_lookup=edge_lookup,
            path=set(),
            as_head=True,
        )
        if head is None:
            continue

        blocked_spids, chain_age_sec, max_wait_sec = _subtree_metrics(head)
        trees.append(
            {
                "head_session_id": root_id,
                "head": head,
                "children": head.get("children") or [],
                "blast_radius": len(blocked_spids),
                "chain_age_sec": chain_age_sec,
                "max_wait_sec": max_wait_sec,
                "blocked_spids": sorted(blocked_spids),
            }
        )

    # Worst blast / longest wait first (ops scan)
    trees.sort(
        key=lambda t: (
            int(t.get("blast_radius") or 0),
            float(t.get("max_wait_sec") or 0),
            int(t.get("chain_age_sec") or 0),
        ),
        reverse=True,
    )
    return trees


def summarize_blocking_trees(trees: list[dict]) -> dict:
    """Aggregate global blast radius, head count, max chain age, longest wait."""
    all_blocked: set[int] = set()
    max_age = 0
    max_wait = 0.0
    for tree in trees:
        spids = tree.get("blocked_spids") or []
        all_blocked.update(int(s) for s in spids)
        max_age = max(max_age, int(tree.get("chain_age_sec") or 0))
        max_wait = max(max_wait, float(tree.get("max_wait_sec") or 0))
    return {
        "head_blockers": len(trees),
        "blast_radius": len(all_blocked),
        "chain_age_sec": max_age,
        "longest_wait_ms": int(max_wait * 1000),
    }
