"""Activity service — UI talks here, not to SQL directly."""
from __future__ import annotations

from core.blocking_tree import build_blocking_trees, summarize_blocking_trees
from core.providers import get_provider
from core.wait_resource import resolve_wait_objects_batch


def fetch_running_now(top: int = 100) -> dict:
    return get_provider().get_running_requests(top=top).to_dict()


def _collect_wait_items(node: dict, items: list[tuple[str, str | None]]) -> None:
    resource = node.get("wait_resource_raw")
    if resource:
        items.append((resource, node.get("wait_type")))
    for child in node.get("children") or []:
        _collect_wait_items(child, items)


def _collect_wait_items_from_trees(trees: list[dict]) -> list[tuple[str, str | None]]:
    items: list[tuple[str, str | None]] = []
    for tree in trees:
        head = tree.get("head")
        if head:
            _collect_wait_items(head, items)
    return items


def _attach_wait_objects(node: dict, amap: dict[str, str | None]) -> None:
    resource = node.get("wait_resource_raw")
    if resource:
        node["wait_object"] = amap.get(resource)
    for child in node.get("children") or []:
        _attach_wait_objects(child, amap)


def _attach_wait_objects_to_trees(trees: list[dict], amap: dict[str, str | None]) -> None:
    for tree in trees:
        head = tree.get("head")
        if head:
            _attach_wait_objects(head, amap)


def enrich_blocking_result(
    result: dict,
    *,
    executor=None,
    resolve_wait_objects: bool = True,
) -> dict:
    """Build trees, batch-resolve wait objects, merge summary. Mutates and returns result."""
    rows = result.get("rows") or []
    trees = build_blocking_trees(rows)

    items = _collect_wait_items_from_trees(trees)
    amap: dict[str, str | None] = {}
    if items and resolve_wait_objects:
        try:
            amap = resolve_wait_objects_batch(items, executor=executor)
        except Exception:
            amap = {}

    _attach_wait_objects_to_trees(trees, amap)

    with_res = sum(1 for _k, v in (amap or {}).items())
    resolved_n = sum(1 for v in (amap or {}).values() if v)
    meta = dict(result.get("meta") or {})
    if with_res and resolved_n == 0:
        meta["resolve_hint"] = (
            "Object names unresolved — grant VIEW ANY DEFINITION to the monitor login "
            "(and CONNECT on databases for KEY locks). Falling back to humanized wait_resource."
        )
    elif with_res:
        meta["resolve_hint"] = None
    result["meta"] = meta

    old_summary = dict(result.get("summary") or {})
    result["summary"] = {**old_summary, **summarize_blocking_trees(trees)}
    result["trees"] = trees
    return result


def fetch_blocking(top: int = 200, *, resolve_wait_objects: bool = True) -> dict:
    result = get_provider().get_blocking(top=top).to_dict()
    if result.get("status") not in ("ok", "empty"):
        return result
    return enrich_blocking_result(
        result,
        resolve_wait_objects=resolve_wait_objects,
    )


def fetch_session_by_id(session_id) -> dict:
    return get_provider().get_session_by_id(session_id).to_dict()


def fetch_server_resource_pulse() -> dict:
    return get_provider().get_server_resource_pulse().to_dict()
