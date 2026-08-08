"""Progress bar logic for Session Lookup — never claim 100% while still running."""
from modules.activity.layout import compute_progress_bar_state


def test_suspended_rows_over_estimate_not_complete():
    state = compute_progress_bar_state(
        rows_done=1_220_997,
        rows_est=867_314,
        status="suspended",
        has_active_request=True,
    )
    assert state["mode"] == "exceeded"
    assert state["exceeded"] is True
    assert state["fill_pct"] is not None
    assert state["fill_pct"] < 100.0
    assert "100%" not in (state["label"] or "")
    assert state["note"] and "still running" in state["note"].lower()


def test_running_under_estimate_caps_below_100():
    state = compute_progress_bar_state(
        rows_done=900,
        rows_est=1000,
        status="running",
        has_active_request=True,
    )
    assert state["mode"] == "running"
    assert state["fill_pct"] == 90.0
    assert state["fill_pct"] < 100.0


def test_sleeping_without_active_request_is_ended_not_success():
    """Cancel and finish both look sleeping — do not claim 100% success."""
    state = compute_progress_bar_state(
        rows_done=1000,
        rows_est=1000,
        status="sleeping",
        has_active_request=False,
    )
    assert state["mode"] == "ended"
    assert "ended" in (state["label"] or "").lower()
    assert "100%" not in (state["label"] or "")


def test_dmv_percent_while_running_never_hits_100_visually():
    state = compute_progress_bar_state(
        rows_done=0,
        rows_est=0,
        percent_complete=100,
        status="suspended",
        has_active_request=True,
    )
    # no rows; dmv says 100 but still running → clamp
    assert state["fill_pct"] is not None
    assert state["fill_pct"] < 100.0


def test_chart_hot_not_triggered_by_near_peak_window():
    """last≈peak of a short window must NOT paint the card red."""
    from modules.activity.layout import _panel_is_hot

    # Rising series ending at its own max — old bug returned 100% relative
    cpu_ok = [18, 20, 22, 25, 29]
    assert _panel_is_hot("cpu", cpu_ok, [100, 200, 300]) is False
    assert _panel_is_hot("cpu", [70, 75, 85], []) is True

    reads = [500, 1000, 2054]
    sess_reads = [100, 150, 250]
    assert _panel_is_hot("reads", reads, sess_reads) is False

    # High PLE is healthy
    assert _panel_is_hot("ple", [9730, 9732, 9734], [1e9, 1.1e9]) is False
    # Low PLE is hot
    assert _panel_is_hot("ple", [900, 400, 120], []) is True
