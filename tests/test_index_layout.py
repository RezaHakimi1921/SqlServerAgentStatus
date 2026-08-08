"""Layout smoke tests for Index Intelligence three-tab UI."""
from modules.indexes.layout import (
    build_indexes_layout,
    render_explorer,
    render_search_results,
    render_selected_table,
)
from modules.indexes.panels import (
    render_overview,
    render_overview_idle,
    render_triage_detail,
    render_triage_rail,
)


def _ids(node, found=None):
    found = found if found is not None else set()
    if hasattr(node, "id") and node.id:
        found.add(node.id if isinstance(node.id, str) else str(node.id))
    children = getattr(node, "children", None)
    if children is None:
        return found
    if not isinstance(children, (list, tuple)):
        children = [children]
    for c in children:
        _ids(c, found)
    return found


def test_shell_has_three_tab_ids():
    layout = build_indexes_layout()
    ids = _ids(layout)
    assert "indexes-tab-overview" in ids
    assert "indexes-tab-triage" in ids
    assert "indexes-tab-explorer" in ids
    assert "indexes-db-toggle" in ids
    assert "indexes-table-search" in ids
    assert "btn-indexes-refresh" in ids
    assert "btn-indexes-deep-scan" in ids
    assert "btn-indexes-catalog-refresh" in ids
    assert "btn-indexes-goto-triage" in ids
    assert "btn-indexes-open-table" in ids
    assert "store-indexes-table-cache" in ids
    assert "store-indexes-triage-filter" in ids
    assert "indexes-overview-body" in ids
    assert "indexes-triage-rail" in ids
    assert "indexes-triage-detail" in ids
    assert "indexes-explorer-body" in ids
    assert "indexes-explorer-table-list" in ids
    assert "indexes-explorer-loading" in ids
    assert "indexes-view-recommendations" in ids
    assert "indexes-view-status" in ids
    assert "store-indexes" in ids
    assert "indexes-table-dropdown" not in ids


def test_shell_defaults_to_overview():
    layout = build_indexes_layout()
    # store-indexes-tab default
    found = []

    def walk(n):
        if getattr(n, "id", None) == "store-indexes-tab":
            found.append(getattr(n, "data", None))
        children = getattr(n, "children", None) or []
        if not isinstance(children, (list, tuple)):
            children = [children]
        for c in children:
            walk(c)

    walk(layout)
    assert found == ["overview"]


def test_index_type_css_colors():
    from modules.indexes.layout import index_type_css

    assert "is-heap" in index_type_css("HEAP")
    assert "is-clustered" in index_type_css("CLUSTERED")
    assert "is-nonclustered" in index_type_css("NONCLUSTERED")
    assert "is-columnstore" in index_type_css("CLUSTERED COLUMNSTORE")


def test_overview_idle_not_blank():
    idle = render_overview_idle()
    assert idle is not None


def test_render_overview_and_search():
    overview = render_overview(
        {
            "uptime": {"insufficient": False, "uptime_days": 40},
            "databases_scanned": 2,
            "databases_available": 5,
            "databases_scanned_list": ["SalesDB", "OtherDB"],
            "source": "catalog",
            "scan_mode": "quick",
            "findings": [],
            "totals": {
                "indexes": 100,
                "need_review": 10,
                "unused": 3,
                "write_heavy": 2,
                "heaps": 1,
                "missing_suggestions": 4,
            },
            "sections": {
                "write_heavy": [
                    {
                        "database_name": "SalesDB",
                        "schema_name": "dbo",
                        "table_name": "Facture",
                        "index_name": "IX_Date",
                        "writes": 45000000,
                        "reads": 100,
                        "size_mb": 12,
                    }
                ],
                "unused": [],
                "heaps": [],
                "missing_by_table": [],
            },
        }
    )
    assert overview is not None
    assert render_search_results([], "f") is not None
    assert render_search_results(
        [{"full_name": "dbo.Facture", "schema_name": "dbo", "table_name": "Facture"}],
        "fac",
    )
    assert render_selected_table({"database": "SalesDB", "schema": "dbo", "table": "Facture"})
    assert render_triage_rail(None, "all", None) is not None
    assert render_triage_detail(None) is not None


def test_render_explorer_recommendations_grouped():
    payload = {
        "database_name": "SalesDB",
        "schema_name": "dbo",
        "table_name": "Facture",
        "is_heap": False,
        "table_meta": {
            "row_count": 1000,
            "size_mb": 10,
            "clustered_index_name": "PK",
            "primary_key_name": "PK",
        },
        "health": {
            "indexes": 2,
            "unused": 1,
            "write_heavy": 0,
            "duplicate": 0,
            "possible_consolidation": 1,
            "missing_patterns": 0,
            "health": "needs_optimization",
        },
        "recommendations": [
            {
                "category": "REMOVE_CANDIDATE",
                "problem": "IX_a unused",
                "why": "zero reads",
                "evidence": {"reads": 0, "writes": 10},
                "suggested_action": "review",
                "risk": "medium",
                "scripts": [{"label": "Copy", "tsql": "-- REVIEW ONLY\n"}],
            },
            {
                "category": "CONSOLIDATE",
                "problem": "prefix overlap",
                "why": "shorter is prefix",
                "evidence": {"kind": "prefix_overlap"},
                "suggested_action": "keep longer",
                "risk": "medium",
                "scripts": [],
            },
        ],
        "inventory": [
            {
                "index_id": 2,
                "index_name": "IX_a",
                "type_desc": "NONCLUSTERED",
                "tags": ["Unused"],
                "key_cols": "a",
                "include_cols": "",
                "filter_def": "",
                "metrics": {"usage": {"reads": 0, "writes": 10}, "storage": {"size_mb": 1}},
            }
        ],
        "relationships": [],
        "missing_intelligence": [],
        "uptime": {"insufficient": False, "uptime_days": 40},
    }
    sel = {"database": "SalesDB", "schema": "dbo", "table": "Facture"}
    advice = render_explorer(payload, selected=sel, view="recommendations")
    status = render_explorer(payload, selected=sel, view="status")
    assert advice is not None
    assert status is not None
