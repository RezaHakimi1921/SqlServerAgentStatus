"""Unit tests for Tables & Growth service (deltas / growers / filter)."""
from datetime import date

from modules.tables.service import (
    as_bit,
    attach_deltas,
    build_tables_payload,
    compose_deleted_tables,
    delta_tone,
    filter_sort_tables,
    pick_growers,
    pick_prior_capture_date,
    pick_top_tables,
    positive_delta_mean,
    rollup_databases,
)


def test_delta_tone_relative_to_mean():
    # mean=5 → hot at ≥10, warm at ≥6.25, ok at 6, muted at 3
    assert delta_tone(10, 5.0, floor=1.0) == "hot"
    assert delta_tone(7, 5.0, floor=1.0) == "warm"
    assert delta_tone(6, 5.0, floor=1.0) == "ok"
    assert delta_tone(3, 5.0, floor=1.0) == "ok"  # still positive growth, below warm
    assert delta_tone(0, 5.0, floor=1.0) == "muted"
    assert delta_tone(-896, 5.0, floor=1.0) == "drop"
    assert positive_delta_mean(
        [{"delta_mb_7d": 2}, {"delta_mb_7d": 8}, {"delta_mb_7d": 0}, {"is_deleted": True, "delta_mb_7d": 99}],
        "delta_mb_7d",
    ) == 5.0


def test_pick_prior_capture_date_prefers_target_then_falls_back():
    latest = date(2026, 8, 8)
    dates = [date(2026, 8, 7), date(2026, 8, 8)]
    # Short history (2 days): 7d/30d still use the only prior day.
    assert pick_prior_capture_date(latest, dates, 1) == date(2026, 8, 7)
    assert pick_prior_capture_date(latest, dates, 7) == date(2026, 8, 7)
    assert pick_prior_capture_date(latest, dates, 30) == date(2026, 8, 7)

    # Three days: 1d = yesterday; 7d/30d = oldest available (full span).
    three = [date(2026, 8, 8), date(2026, 8, 9), date(2026, 8, 10)]
    assert pick_prior_capture_date(date(2026, 8, 10), three, 1) == date(2026, 8, 9)
    assert pick_prior_capture_date(date(2026, 8, 10), three, 7) == date(2026, 8, 8)
    assert pick_prior_capture_date(date(2026, 8, 10), three, 30) == date(2026, 8, 8)

    longer = [date(2026, 7, 1), date(2026, 8, 1), date(2026, 8, 7), date(2026, 8, 8)]
    assert pick_prior_capture_date(latest, longer, 7) == date(2026, 8, 1)
    assert pick_prior_capture_date(latest, longer, 30) == date(2026, 7, 1)
    assert pick_prior_capture_date(latest, [latest], 7) is None


def test_as_bit_handles_pyodbc_bytes():
    assert as_bit(b"\x00") is False
    assert as_bit(b"\x01") is True
    assert as_bit(0) is False
    assert as_bit(1) is True
    assert as_bit(False) is False
    assert as_bit(True) is True


def test_rollup_databases_with_deltas():
    tables = [
        {
            "database_name": "A",
            "size_mb": 10,
            "row_count": 100,
            "is_heap": True,
            "delta_mb_7d": 2,
        },
        {
            "database_name": "A",
            "size_mb": 5,
            "row_count": 50,
            "is_heap": False,
            "delta_mb_7d": 1,
        },
        {
            "database_name": "B",
            "size_mb": 100,
            "row_count": 1,
            "is_heap": False,
            "delta_mb_7d": 40,
        },
    ]
    dbs = rollup_databases(tables)
    assert dbs[0]["database_name"] == "B"
    assert dbs[1]["total_size_mb"] == 15
    assert dbs[1]["heap_count"] == 1
    assert dbs[0]["delta_mb_7d"] == 40
    assert dbs[1]["delta_mb_7d"] == 3


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


def test_build_tables_payload_and_filter():
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
            },
            {
                "database_name": "db",
                "schema_name": "dbo",
                "table_name": "Small",
                "size_mb": 10,
                "row_count": 5,
                "is_heap": 1,
            },
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
    assert payload["growers_by_window"]["7"][0]["table_name"] == "Big"
    assert payload["growth_totals"]["7"] == 100
    assert pick_top_tables(payload["tables"], top=1)[0]["size_mb"] == 500

    filtered = filter_sort_tables(
        payload["tables"], search="big", sort="delta_mb", window_days=7
    )
    assert len(filtered) == 1
    assert filtered[0]["table_name"] == "Big"

    heaps = filter_sort_tables(payload["tables"], search="heap")
    assert len(heaps) == 1
    assert heaps[0]["table_name"] == "Small"

    clustered = filter_sort_tables(payload["tables"], search="clustered")
    assert len(clustered) == 1
    assert clustered[0]["table_name"] == "Big"

    by_type_heap = filter_sort_tables(payload["tables"], type_status="heap")
    assert len(by_type_heap) == 1
    assert by_type_heap[0]["table_name"] == "Small"

    by_type_ci = filter_sort_tables(payload["tables"], type_status="clustered")
    assert len(by_type_ci) == 1
    assert by_type_ci[0]["table_name"] == "Big"


def test_compose_deleted_and_search_keyword():
    history = [
        {
            "database_name": "db",
            "schema_name": "dbo",
            "table_name": "Gone",
            "captured_date": "2026-08-07",
            "size_mb": 80,
            "row_count": 100,
            "is_heap": 0,
        },
        {
            "database_name": "db",
            "schema_name": "dbo",
            "table_name": "Gone",
            "captured_date": "2026-08-08",
            "size_mb": 100,
            "row_count": 120,
            "is_heap": 0,
        },
        {
            "database_name": "db",
            "schema_name": "dbo",
            "table_name": "StillHere",
            "captured_date": "2026-08-08",
            "size_mb": 10,
            "row_count": 1,
            "is_heap": 0,
        },
    ]
    deleted = compose_deleted_tables(history, {("db", "dbo", "StillHere")})
    assert len(deleted) == 1
    assert deleted[0]["table_name"] == "Gone"
    assert deleted[0]["is_deleted"] is True
    assert deleted[0]["last_seen"] == "2026-08-08"
    assert deleted[0]["size_mb"] == 100
    assert deleted[0]["delta_mb_1d"] == 20

    raw = {
        "source": "catalog",
        "history_available": True,
        "tables": [
            {
                "database_name": "db",
                "schema_name": "dbo",
                "table_name": "StillHere",
                "size_mb": 10,
                "row_count": 1,
                "is_heap": 0,
            }
        ],
        "history_by_window": {},
        "deleted_history_rows": history,
        "errors": {},
    }
    payload = build_tables_payload(raw)
    assert payload["table_count"] == 1
    assert payload["deleted_table_count"] == 1
    only_del = filter_sort_tables(payload["tables"], search="deleted")
    assert len(only_del) == 1
    assert only_del[0]["table_name"] == "Gone"
    assert only_del[0]["last_seen"] == "2026-08-08"
    by_picker = filter_sort_tables(payload["tables"], type_status="deleted")
    assert len(by_picker) == 1
    assert by_picker[0]["table_name"] == "Gone"
    # heap/clustered must not include deleted
    assert filter_sort_tables(payload["tables"], search="clustered")[0]["table_name"] == "StillHere"
    assert filter_sort_tables(payload["tables"], type_status="clustered")[0]["table_name"] == "StillHere"
