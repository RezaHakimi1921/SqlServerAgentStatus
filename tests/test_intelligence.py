"""Unit tests for Index Intelligence analysis engine."""
from modules.indexes.intelligence import (
    analyze_missing,
    analyze_relationships,
    build_recommendations,
    summarize_health,
)


def _idx(name, *, index_id=2, keys="", includes="", filt="", reads=0, writes=0, **extra):
    row = {
        "index_id": index_id,
        "index_name": name,
        "key_cols": keys,
        "include_cols": includes,
        "filter_def": filt,
        "reads": reads,
        "writes": writes,
        "is_unique": False,
        "is_primary_key": False,
        "is_unique_constraint": False,
        "is_disabled": False,
        "is_hypothetical": False,
        "size_mb": 5.0,
        "page_count": 100,
        "avg_fragmentation_in_percent": None,
        "type_desc": "NONCLUSTERED",
    }
    row.update(extra)
    return row


def test_exact_duplicate_relationship():
    indexes = [
        _idx("IX_A", keys="CustomerId", includes="Amount,Status"),
        _idx("IX_B", index_id=3, keys="CustomerId", includes="Status,Amount"),
    ]
    rels = analyze_relationships(indexes)
    kinds = [r["kind"] for r in rels]
    assert "exact_duplicate" in kinds


def test_covered_by_relationship():
    indexes = [
        _idx("IX_Wide", keys="CustomerId", includes="Amount,Date,Status"),
        _idx("IX_Narrow", index_id=3, keys="CustomerId", includes="Amount"),
    ]
    rels = analyze_relationships(indexes)
    covered = [r for r in rels if r["kind"] == "covered_by"]
    assert covered
    assert covered[0]["index_a"] == "IX_Wide"
    assert covered[0]["index_b"] == "IX_Narrow"


def test_prefix_overlap_relationship():
    indexes = [
        _idx("IX_Long", keys="CustomerId,CreateDate", includes="Amount"),
        _idx("IX_Short", index_id=3, keys="CustomerId", includes=""),
    ]
    rels = analyze_relationships(indexes)
    prefix = [r for r in rels if r["kind"] == "prefix_overlap"]
    assert prefix
    assert prefix[0]["index_a"] == "IX_Long"
    assert prefix[0]["index_b"] == "IX_Short"


def test_missing_extend_existing():
    indexes = [_idx("IX_Customer", keys="CustomerId", includes="Date")]
    missing = [
        {
            "equality_columns": "CustomerId",
            "inequality_columns": None,
            "included_columns": "Date, Amount",
            "user_seeks": 100,
            "impact_score": 50,
        }
    ]
    out = analyze_missing(missing, indexes, schema="dbo", table="Facture")
    assert out[0]["action"] == "extend_existing"
    assert out[0]["related_index"] == "IX_Customer"


def test_missing_ignore_near_duplicate():
    indexes = [_idx("IX_Customer", keys="CustomerId", includes="Date,Amount")]
    missing = [
        {
            "equality_columns": "CustomerId",
            "inequality_columns": None,
            "included_columns": "Date",
            "user_seeks": 10,
            "impact_score": 5,
        }
    ]
    out = analyze_missing(missing, indexes, schema="dbo", table="Facture")
    assert out[0]["action"] == "ignore_near_duplicate"


def test_recommendations_remove_and_consolidate():
    indexes = [
        _idx("IX_Unused", keys="Email", reads=0, writes=50000),
        _idx("IX_Long", index_id=3, keys="CustomerId,CreateDate", includes="Amount", reads=100, writes=10),
        _idx("IX_Short", index_id=4, keys="CustomerId", includes="", reads=50, writes=5),
    ]
    rels = analyze_relationships(indexes)
    miss = []
    recs = build_recommendations(
        indexes,
        rels,
        miss,
        schema="dbo",
        table="Facture",
        uptime_days=40,
        is_heap=False,
    )
    cats = {r["category"] for r in recs}
    assert "REMOVE_CANDIDATE" in cats
    assert "CONSOLIDATE" in cats
    health = summarize_health(indexes, rels, miss, is_heap=False)
    assert health["unused"] >= 1
    assert health["health"] == "needs_optimization"
