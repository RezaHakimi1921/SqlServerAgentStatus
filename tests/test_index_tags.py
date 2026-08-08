"""Unit tests for table-scoped index tagging (v1.1 tag glance)."""
from datetime import datetime, timedelta, timezone

from modules.indexes.constants import (
    INDEX_HIGH_FRAG_MIN_PAGES,
    INDEX_HIGH_FRAG_PCT,
    INDEX_WRITE_HEAVY_MIN_DIFF,
    INDEX_WRITE_HEAVY_MIN_WRITES,
)
from modules.indexes.service import build_table_index_tags, tag_index_row


def _idx(**kw):
    base = {
        "index_id": 2,
        "index_name": "IX_a",
        "type_desc": "NONCLUSTERED",
        "is_unique": False,
        "is_primary_key": False,
        "is_unique_constraint": False,
        "is_disabled": False,
        "is_hypothetical": False,
        "has_filter": False,
        "filter_def": "",
        "reads": 10,
        "writes": 10,
        "size_mb": 1.0,
        "page_count": 100,
        "avg_fragmentation_in_percent": 0.0,
        "key_cols": "a",
        "include_cols": "",
    }
    base.update(kw)
    return base


def test_unused_tag():
    tags = tag_index_row(_idx(reads=0, writes=5000))
    assert "Unused" in tags
    assert "OK" not in tags
    assert "Write-heavy" not in tags


def test_write_heavy_tag():
    tags = tag_index_row(
        _idx(
            reads=100,
            writes=max(INDEX_WRITE_HEAVY_MIN_WRITES, 100 + INDEX_WRITE_HEAVY_MIN_DIFF),
        )
    )
    assert "Write-heavy" in tags
    assert "Unused" not in tags


def test_ok_when_healthy():
    tags = tag_index_row(_idx(reads=1000, writes=100))
    assert "OK" in tags
    assert "Unused" not in tags


def test_high_frag():
    tags = tag_index_row(
        _idx(
            avg_fragmentation_in_percent=INDEX_HIGH_FRAG_PCT + 1,
            page_count=INDEX_HIGH_FRAG_MIN_PAGES,
            reads=100,
            writes=10,
        )
    )
    assert "High frag" in tags
    assert "OK" not in tags


def test_high_frag_ignores_small_indexes():
    tags = tag_index_row(
        _idx(
            avg_fragmentation_in_percent=90,
            page_count=10,
            reads=100,
            writes=10,
        )
    )
    assert "High frag" not in tags
    assert "OK" in tags


def test_duplicate_names():
    tags = tag_index_row(_idx(index_name="IX_dup"), duplicate_names={"IX_dup"})
    assert "Duplicate" in tags


def test_unique_and_filtered_structural():
    tags = tag_index_row(
        _idx(is_unique=True, has_filter=True, filter_def="x=1", reads=0, writes=0)
    )
    # unique NC is not eligible for Unused
    assert "Unused" not in tags
    assert "Unique" in tags
    assert "Filtered" in tags
    assert "OK" in tags


def test_disabled_not_ok():
    tags = tag_index_row(_idx(is_disabled=True, reads=100, writes=10))
    assert "Disabled" in tags
    assert "OK" not in tags


def test_build_table_index_tags_summary_and_heap():
    raw = {
        "database_name": "RasBankAccountingCloud",
        "schema_name": "dbo",
        "table_name": "T",
        "sqlserver_start_time": datetime.now(timezone.utc) - timedelta(days=30),
        "is_heap": True,
        "index_rows": [
            _idx(index_name="IX_unused", reads=0, writes=9000),
            _idx(index_name="IX_ok", reads=500, writes=10, key_cols="b"),
            _idx(
                index_name="IX_a",
                key_cols="x",
                include_cols="y",
                reads=5,
                writes=5,
            ),
            _idx(
                index_name="IX_b",
                key_cols="x",
                include_cols="y",
                reads=5,
                writes=5,
            ),
        ],
        "missing_rows": [],
        "errors": {},
    }
    out = build_table_index_tags(raw)
    assert out["is_heap"] is True
    assert out["summary_tag_counts"]["Unused"] >= 1
    assert out["summary_tag_counts"]["Duplicate"] >= 2
    assert out["summary_tag_counts"]["OK"] >= 1
    names = {r["index_name"] for r in out["indexes"]}
    assert "IX_unused" in names
