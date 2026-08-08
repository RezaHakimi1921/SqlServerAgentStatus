"""Estimated finish time for Session Lookup Identity card."""
from datetime import datetime

from modules.activity.layout import compute_finish_eta


def test_eta_from_row_rate():
    # 50% done in 100s → ~100s remaining
    now = datetime(2026, 8, 1, 20, 0, 0)
    eta = compute_finish_eta(
        rows_done=500,
        rows_est=1000,
        elapsed_ms=100_000,
        has_active_request=True,
        status="running",
        now=now,
    )
    assert eta is not None
    assert eta["mode"] == "eta"
    assert eta["remaining_ms"] == 100_000
    assert eta["finish_clock"] == "20:01:40"
    assert eta["confidence"] in ("low", "medium")


def test_eta_from_percent_when_no_rows_est():
    now = datetime(2026, 8, 1, 12, 0, 0)
    eta = compute_finish_eta(
        rows_done=0,
        rows_est=0,
        elapsed_ms=60_000,
        percent_complete=25,
        has_active_request=True,
        status="running",
        now=now,
    )
    assert eta is not None
    assert eta["mode"] == "eta"
    # 25% in 60s → 180s remaining → 12:03:00
    assert eta["remaining_ms"] == 180_000
    assert eta["finish_clock"] == "12:03:00"


def test_no_eta_when_idle():
    assert compute_finish_eta(
        rows_done=900,
        rows_est=1000,
        elapsed_ms=10_000,
        has_active_request=False,
        status="sleeping",
    ) is None


def test_exceeded_estimate_has_distinct_mode():
    eta = compute_finish_eta(
        rows_done=2000,
        rows_est=1000,
        elapsed_ms=120_000,
        has_active_request=True,
        status="suspended",
        now=datetime(2026, 8, 1, 10, 0, 0),
    )
    assert eta is not None
    assert eta["mode"] == "exceeded"
    assert eta["finish_clock"] is None


def test_too_early_no_eta():
    assert compute_finish_eta(
        rows_done=1,
        rows_est=1_000_000,
        elapsed_ms=500,
        has_active_request=True,
        status="running",
    ) is None
