"""Metric definitions — each metric has its own capture interval."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class MetricSpec:
    """One capturable metric.

    interval_sec: how often this metric is sampled (independent per metric).
    The scheduler ticks at the GCD of intervals (default 10s) and only runs
    collectors that are due.
    """

    name: str
    interval_sec: int
    scope: str  # server | job | session | database
    description: str
    enabled: bool = True


# Default schedule — override later via env INSIGHT_INTERVAL_<NAME>=seconds if needed
DEFAULT_METRICS: List[MetricSpec] = [
    MetricSpec(
        name="blocking_session_count",
        interval_sec=10,
        scope="server",
        description="Count of sessions currently blocked (DMV snapshot)",
    ),
    MetricSpec(
        name="blocking_wait_ms",
        interval_sec=10,
        scope="server",
        description="Max wait_time_ms among blocked requests (DMV snapshot)",
    ),
    MetricSpec(
        name="head_blocker_count",
        interval_sec=10,
        scope="server",
        description="Distinct head blockers (DMV snapshot)",
    ),
    MetricSpec(
        name="job_failed",
        interval_sec=60,
        scope="job",
        description="New Agent job step failure since last poll (msdb history)",
    ),
]


def metrics_by_name() -> Dict[str, MetricSpec]:
    return {m.name: m for m in DEFAULT_METRICS if m.enabled}


def min_tick_seconds(metrics: List[MetricSpec] | None = None) -> int:
    """Scheduler base tick = min interval among enabled metrics (floor 10s)."""
    ms = [m for m in (metrics or DEFAULT_METRICS) if m.enabled]
    if not ms:
        return 10
    return max(10, min(m.interval_sec for m in ms))
