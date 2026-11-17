"""Index health service unit tests (Tasks 1–3)."""
from modules.indexes.constants import (
    INDEX_CAP_MISSING,
    INDEX_CONFIDENCE_SCRIPT_MIN,
    INDEX_WRITE_HEAVY_MIN_WRITES,
    INDEX_WRITE_HEAVY_MIN_DIFF,
    INDEX_WRITE_HEAVY_MIN_RATIO,
)
from modules.indexes.service import (
    _gated_scripts,
    assign_confidence,
    build_disable_drop_script,
    build_index_health,
    classify_usage_row,
    group_exact_duplicates,
    is_write_heavy,
    quotename,
)


def test_write_heavy_rejects_near_equal():
    assert is_write_heavy(reads=1000, writes=1100) is False


def test_write_heavy_accepts_large_diff():
    assert is_write_heavy(reads=1000, writes=1000 + INDEX_WRITE_HEAVY_MIN_DIFF) is True


def test_write_heavy_accepts_ratio():
    reads = 100
    writes = reads * INDEX_WRITE_HEAVY_MIN_RATIO
    assert writes >= INDEX_WRITE_HEAVY_MIN_WRITES
    assert is_write_heavy(reads=reads, writes=writes) is True


def test_write_heavy_requires_min_writes():
    assert is_write_heavy(reads=1, writes=50) is False


def test_unused_reads_zero_not_write_heavy():
    assert classify_usage_row({"reads": 0, "writes": 5_000_000, "eligible": True}) == "unused"


def test_mutual_exclusion():
    assert classify_usage_row({"reads": 0, "writes": 10_000, "eligible": True}) != "write_heavy"


# --- Task 2: confidence, duplicates, scripts ---


def test_duplicate_heap_always_high():
    c, _, score = assign_confidence("duplicate", uptime_days=1)
    assert c == "high"
    assert score >= 70
    c, _, score = assign_confidence("heap", uptime_days=1)
    assert c == "high"
    assert score >= 70


def test_unused_low_when_short_uptime():
    c, reason, score = assign_confidence("unused", uptime_days=2, writes=1_000_000)
    assert c in ("low", "medium")
    assert score < 70
    assert "restart" in reason.lower() or "2" in reason


def test_missing_at_most_medium():
    c, _, score = assign_confidence("missing", uptime_days=30)
    assert c in ("medium", "low")
    assert c != "high"
    assert score < 70


def test_exact_duplicate_group():
    rows = [
        {
            "object_id": 1,
            "schema_name": "dbo",
            "table_name": "T",
            "index_name": "IX_A",
            "key_cols": "A,B",
            "include_cols": "C",
            "filter_def": "",
        },
        {
            "object_id": 1,
            "schema_name": "dbo",
            "table_name": "T",
            "index_name": "IX_B",
            "key_cols": "A,B",
            "include_cols": "C",
            "filter_def": "",
        },
        {
            "object_id": 1,
            "schema_name": "dbo",
            "table_name": "T",
            "index_name": "IX_C",
            "key_cols": "A",
            "include_cols": "",
            "filter_def": "",
        },
    ]
    groups = group_exact_duplicates(rows)
    assert len(groups) == 1
    assert len(groups[0]["members"]) == 2
    assert len(groups[0]["excess"]) == 1


def test_script_quotes_and_review_header():
    s = build_disable_drop_script("dbo", "My Table", "IX_x")
    assert "REVIEW ONLY" in s
    assert "[My Table]" in s or quotename("My Table") in s
    assert "DISABLE" in s and "DROP INDEX" in s
    assert s.count("DROP INDEX") == 1
    # DROP must stay commented until DBA validates DISABLE
    assert "-- DROP INDEX" in s
    assert "Uncomment DROP" in s


# --- Task 3: build_index_health assembly ---


def _base_raw(**overrides):
    raw = {
        "database_name": "TestDb",
        "sqlserver_start_time": None,
        "usage_rows": [],
        "heap_rows": [],
        "inventory_rows": [],
        "missing_rows": [],
        "errors": {},
    }
    raw.update(overrides)
    return raw


def test_build_uptime_insufficient_when_start_time_missing():
    out = build_index_health(_base_raw())
    assert out["uptime"]["insufficient"] is True
    assert out["uptime"]["uptime_days"] == 0.0
    assert out["uptime"]["sqlserver_start_time"] is None


def test_build_mutual_exclusion_unused_vs_write_heavy():
    usage_rows = [
        {
            "schema_name": "dbo",
            "table_name": "T",
            "index_name": "IX_unused",
            "object_id": 1,
            "reads": 0,
            "writes": 10_000,
            "size_mb": 5.0,
            "eligible": True,
        },
        {
            "schema_name": "dbo",
            "table_name": "T",
            "index_name": "IX_write_heavy",
            "object_id": 2,
            "reads": 100,
            "writes": 100 + INDEX_WRITE_HEAVY_MIN_DIFF,
            "size_mb": 3.0,
            "eligible": True,
        },
    ]
    out = build_index_health(_base_raw(usage_rows=usage_rows))
    assert out["summary"]["unused"] == 1
    assert out["summary"]["write_heavy"] == 1
    categories_by_index = {f["index_name"]: f["category"] for f in out["findings"]}
    assert categories_by_index["IX_unused"] == "unused"
    assert categories_by_index["IX_write_heavy"] == "write_heavy"
    # never both categories for the same index
    assert {f["index_name"] for f in out["findings"] if f["category"] == "unused"}.isdisjoint(
        {f["index_name"] for f in out["findings"] if f["category"] == "write_heavy"}
    )


def test_build_reviewable_index_space_sums_unused_and_duplicate_excess():
    usage_rows = [
        {
            "schema_name": "dbo",
            "table_name": "T",
            "index_name": "IX_unused",
            "object_id": 1,
            "reads": 0,
            "writes": 10,
            "size_mb": 5.0,
            "eligible": True,
        },
    ]
    inventory_rows = [
        {"object_id": 2, "schema_name": "dbo", "table_name": "U", "index_name": "IX_A",
         "key_cols": "A", "include_cols": "", "filter_def": "", "is_unique": False,
         "type": "NONCLUSTERED", "size_mb": 2.0},
        {"object_id": 2, "schema_name": "dbo", "table_name": "U", "index_name": "IX_B",
         "key_cols": "A", "include_cols": "", "filter_def": "", "is_unique": False,
         "type": "NONCLUSTERED", "size_mb": 3.0},
    ]
    out = build_index_health(_base_raw(usage_rows=usage_rows, inventory_rows=inventory_rows))
    assert out["summary"]["duplicate_excess"] == 1
    assert out["summary"]["reviewable_index_space_mb"] == 5.0 + 3.0


def test_build_reviewable_index_space_none_when_unknown():
    usage_rows = [
        {
            "schema_name": "dbo",
            "table_name": "T",
            "index_name": "IX_unused",
            "object_id": 1,
            "reads": 0,
            "writes": 10,
            "size_mb": None,
            "eligible": True,
        },
    ]
    out = build_index_health(_base_raw(usage_rows=usage_rows))
    assert out["summary"]["reviewable_index_space_mb"] is None


def test_build_heap_findings_have_no_scripts_and_high_confidence():
    heap_rows = [
        {"schema_name": "dbo", "table_name": "H", "object_id": 5, "size_mb": 12.0},
    ]
    out = build_index_health(_base_raw(heap_rows=heap_rows))
    heap_finding = next(f for f in out["findings"] if f["category"] == "heap")
    assert heap_finding["confidence"] == "high"
    assert heap_finding["scripts"] == []


def test_build_missing_recommendation_wording():
    missing_rows = [
        {"object_id": 1, "schema_name": "dbo", "table_name": "T1", "impact_score": 100,
         "equality_columns": "a", "inequality_columns": None, "included_columns": None,
         "user_seeks": 10, "avg_user_impact": 50, "avg_total_user_cost": 2.0},
    ]
    out = build_index_health(_base_raw(missing_rows=missing_rows))
    finding = next(f for f in out["findings"] if f["category"] == "missing")
    assert finding["severity"] == "info"
    assert "optimizer suggestion" in finding["recommendation"].lower()
    assert "not a recommendation" in finding["recommendation"].lower()


def test_build_caps_missing_before_needing_extra_tables():
    raw = _base_raw(
        inventory_rows=[
            {"object_id": 1, "schema_name": "dbo", "table_name": "T1", "index_name": "IX1",
             "key_cols": "a", "include_cols": "", "filter_def": "", "is_unique": False,
             "type": "NONCLUSTERED"},
        ],
        missing_rows=[
            {"object_id": 1, "schema_name": "dbo", "table_name": "T1", "impact_score": 100,
             "equality_columns": "a", "inequality_columns": None, "included_columns": None,
             "user_seeks": 10, "avg_user_impact": 50, "avg_total_user_cost": 2.0},
        ]
        + [
            {"object_id": 999, "schema_name": "dbo", "table_name": "Other", "impact_score": 1,
             "equality_columns": "z", "inequality_columns": None, "included_columns": None,
             "user_seeks": 1, "avg_user_impact": 1, "avg_total_user_cost": 1.0},
        ]
        * 30,
    )
    out = build_index_health(raw)
    assert out["summary"]["missing"] <= INDEX_CAP_MISSING
    assert out["summary"]["missing_total"] == 31
    for f in out["findings"]:
        if f["category"] == "missing" and f["table_name"] == "T1":
            assert f["table_indexes"]


def test_gated_scripts_blocks_below_70():
    scripts, blocked = _gated_scripts(55, [{"label": "Copy", "tsql": "SELECT 1"}])
    assert scripts == []
    assert blocked and str(INDEX_CONFIDENCE_SCRIPT_MIN) in blocked


def test_gated_scripts_allows_at_70():
    scripts, blocked = _gated_scripts(70, [{"label": "Copy", "tsql": "SELECT 1"}])
    assert len(scripts) == 1
    assert blocked is None
