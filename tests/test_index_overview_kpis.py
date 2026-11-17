"""Unit tests for Indexes Overview v1 KPI pure builder."""
from modules.indexes.service import compute_overview_kpis


def test_kpis_missing_impact_sums_scores():
    k = compute_overview_kpis(
        {
            "totals": {"missing_suggestions": 2, "high_frag": 0},
            "unused": [{"writes": 50000, "size_mb": 10}],
            "write_heavy": [],
            "missing_by_table": [
                {"impact_score": 1000, "avg_user_impact": 50},
                {"impact_score": 500},
            ],
            "duplicates": [{"database_name": "D", "table_name": "T"}],
            "frag_loaded": False,
        }
    )
    assert k["missing_impact"]["display"] == "int"
    assert k["missing_impact"]["value"] == 1500
    assert k["dead_unused_writes"]["value"] == 1
    assert k["dead_unused_writes"]["writes"] == 50000
    assert k["duplicate_debt"]["value"] == 1
    assert k["high_frag"]["display"] == "dash"
    assert k["high_frag"]["value"] is None


def test_kpis_write_waste_includes_write_heavy():
    k = compute_overview_kpis(
        {
            "totals": {"unused_with_writes": 0, "write_heavy": 1, "unused_write_ops": 0},
            "unused": [{"writes": 0}],
            "write_heavy": [{"writes": 2967055, "reads": 440}],
            "missing_by_table": [],
            "duplicates": [],
            "frag_loaded": False,
        }
    )
    assert k["dead_unused_writes"]["value"] == 1
    assert k["dead_unused_writes"]["write_heavy"] == 1
    assert k["dead_unused_writes"]["sub_key"] == "write_waste_sub"


def test_kpis_high_frag_when_loaded():
    k = compute_overview_kpis(
        {
            "totals": {"high_frag": 12},
            "frag_loaded": True,
            "unused": [],
            "missing_by_table": [],
            "duplicates": [],
        }
    )
    assert k["high_frag"]["display"] == "int"
    assert k["high_frag"]["value"] == 12


def test_kpis_missing_impact_peak_pct():
    k = compute_overview_kpis(
        {
            "totals": {"missing_suggestions": 2},
            "missing_by_table": [
                {"impact_score": 1000, "avg_user_impact": 50},
                {"impact_score": 500, "avg_user_impact": 94.6},
            ],
            "unused": [],
            "duplicates": [],
            "frag_loaded": False,
        }
    )
    assert k["missing_impact"]["display_mode"] == "pct"
    assert k["missing_impact"]["peak_impact_pct"] == 94.6


def test_kpis_no_consolidation_key():
    k = compute_overview_kpis(
        {"totals": {}, "unused": [], "missing_by_table": [], "duplicates": []}
    )
    assert "consolidation" not in k
    assert set(k) == {
        "missing_impact",
        "high_frag",
        "dead_unused_writes",
        "duplicate_debt",
    }
