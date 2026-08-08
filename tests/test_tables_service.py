"""Unit tests for Tables & Growth service (deltas / growers)."""
from modules.tables.service import (
    attach_deltas,
    build_tables_payload,
    pick_growers,
    pick_top_tables,
    rollup_databases,
)


def test_rollup_databases():
    tables = [
        {"database_name": "A", "size_mb": 10, "row_count": 100, "is_heap": True},
        {"database_name": "A", "size_mb": 5, "row_count": 50, "is_heap": False},
        {"database_name": "B", "size_mb": 100, "row_count": 1, "is_heap": False},
    ]
    dbs = rollup_databases(tables)
    assert dbs[0]["database_name"] == "B"
    assert dbs[1]["total_size_mb"] == 15
    assert dbs[1]["heap_count"] == 1


def test_attach_deltas_and_growers():
    current = [
        {
            "database_name": "db",
            "schema_name": "dbo",
            "table_name": "T1",
            "size_mb": 120,
            "row_count": 1000,
        },
        {
            "database_name": "db",
            "schema_name": "dbo",
            "table_name": "T2",
            "size_mb": 10,
            "row_count": 10,
        },
    ]
    prior = {
        ("db", "dbo", "T1"): {"size_mb": 100, "row_count": 900},
        ("db", "dbo", "T2"): {"size_mb": 10, "row_count": 10},
    }
    with_d = attach_deltas(current, {7: prior})
    assert with_d[0]["delta_mb_7d"] == 20
    assert with_d[0]["delta_rows_7d"] == 100
    growers = pick_growers(with_d, window_days=7)
    assert len(growers) == 1
    assert growers[0]["table_name"] == "T1"


def test_build_tables_payload():
    raw = {
        "source": "catalog",
        "history_available": True,
        "latest_capture_date": "2026-08-08",
        "tables": [
            {
                "database_name": "db",
                "schema_name": "dbo",
                "table_name": "Big",
                "size_mb": 500,
                "row_count": 1,
                "is_heap": 0,
            }
        ],
        "history_by_window": {
            "7": [
                {
                    "database_name": "db",
                    "schema_name": "dbo",
                    "table_name": "Big",
                    "size_mb": 400,
                    "row_count": 1,
                }
            ]
        },
        "errors": {},
    }
    payload = build_tables_payload(raw)
    assert payload["source"] == "catalog"
    assert payload["top_tables"][0]["delta_mb_7d"] == 100
    assert payload["growers"][0]["table_name"] == "Big"
    assert pick_top_tables(payload["top_tables"], top=1)[0]["size_mb"] == 500
