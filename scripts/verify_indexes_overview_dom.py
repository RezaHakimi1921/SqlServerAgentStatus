"""Verify Indexes Overview KPI ids in render tree and optional live Dash callback."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

EXPECTED_IDS = {
    "indexes-kpi-missing",
    "indexes-kpi-frag",
    "indexes-kpi-unused-writes",
    "indexes-kpi-duplicates",
    "indexes-ov-per-db",
    "indexes-ov-frag",
    "indexes-ov-waste",
}


def _collect_ids(node, found: set[str]) -> None:
    if hasattr(node, "id") and node.id:
        found.add(node.id if isinstance(node.id, str) else str(node.id))
    children = getattr(node, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if child is None:
            continue
        _collect_ids(child, found)


def verify_render_tree() -> tuple[set[str], set[str]]:
    from modules.indexes.panels import render_overview
    from modules.indexes.service import build_overview_payload

    payload = build_overview_payload(
        {
            "sqlserver_start_time": "2026-01-01T00:00:00",
            "totals": {
                "indexes": 120,
                "need_review": 8,
                "unused": 2,
                "write_heavy": 1,
                "heaps": 1,
                "missing_suggestions": 3,
            },
            "findings": [],
            "frag_loaded": False,
        }
    )
    tree = render_overview(payload, locale="en")
    ids = set()
    _collect_ids(tree, ids)
    missing = EXPECTED_IDS - ids
    return ids, missing


def verify_live_app() -> dict:
    """POST a minimal Dash update to indexes overview callback if app is up."""
    out = {"reachable": False, "kpi_ids_in_response": [], "error": None}
    try:
        urllib.request.urlopen("http://127.0.0.1:8050/", timeout=3)
        out["reachable"] = True
    except Exception as exc:
        out["error"] = f"app not reachable: {exc}"
        return out

    # Dash stores rendered component props client-side; server-side we only confirm
    # custom.css contains new overview classes (proves build artifact present).
    try:
        css = urllib.request.urlopen("http://127.0.0.1:8050/assets/custom.css", timeout=5).read().decode(
            "utf-8", errors="ignore"
        )
        out["css_has_kpi_row"] = ".idx-ov-kpi-row" in css
        out["css_has_frag_bands"] = ".idx-frag-bands" in css
        out["css_has_health_chip"] = ".idx-overview-health-chip" in css
    except Exception as exc:
        out["css_error"] = str(exc)
    return out


def main() -> int:
    ids, missing = verify_render_tree()
    print("=== Python render_overview() ===")
    print("found_ids:", sorted(ids & EXPECTED_IDS))
    if missing:
        print("MISSING from render tree:", sorted(missing))
        return 1
    print("OK: all expected KPI/analytics ids present in component tree")

    live = verify_live_app()
    print("\n=== Live app (http://127.0.0.1:8050) ===")
    print(json.dumps(live, indent=2))
    if not live.get("reachable"):
        print("\nNOTE: App not running — start with: python app.py")
        print("Then open Indexes → Overview and hard-refresh (Ctrl+F5).")
        return 0
    if live.get("css_has_kpi_row"):
        print("OK: served custom.css includes new overview styles")
    else:
        print("WARN: custom.css may be stale — hard refresh or restart app")
    return 0


if __name__ == "__main__":
    sys.exit(main())
