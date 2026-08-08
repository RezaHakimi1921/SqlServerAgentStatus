"""Insight metric scheduler — one base tick; each metric has its own interval."""
from __future__ import annotations

import os
import time
from typing import Callable, Dict, List, Optional

from config import is_configured
from core.insight.collectors import collect_blocking_metrics, collect_job_failed_metrics
from core.insight.registry import DEFAULT_METRICS, MetricSpec, min_tick_seconds
from core.insight.rules import evaluate_rules
from core.insight.store import MetricSample, insert_samples
from core.logging_setup import get_logger

log = get_logger("sqlmonitor.insight.scheduler")

CollectorFn = Callable[[], List[MetricSample]]

# Which collector produces which metric names
_COLLECTOR_GROUPS: Dict[str, tuple] = {
    "blocking": (
        ("blocking_session_count", "blocking_wait_ms", "head_blocker_count"),
        collect_blocking_metrics,
    ),
    "job_failed": (
        ("job_failed",),
        collect_job_failed_metrics,
    ),
}

_last_run_monotonic: Dict[str, float] = {}
_lock_busy = False


def _env_interval_override(name: str, default: int) -> int:
    key = f"INSIGHT_INTERVAL_{name.upper()}"
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        v = int(raw)
        return max(10, v)
    except ValueError:
        return default


def resolved_metrics() -> List[MetricSpec]:
    """Priority: DB schedule → env override → code defaults."""
    from core.insight.schedule import schedule_as_specs

    try:
        specs = schedule_as_specs()
    except Exception:
        log.exception("schedule_as_specs failed")
        specs = [m for m in DEFAULT_METRICS if m.enabled]

    out: List[MetricSpec] = []
    for m in specs:
        interval = _env_interval_override(m.name, m.interval_sec)
        if interval != m.interval_sec:
            out.append(MetricSpec(
                name=m.name,
                interval_sec=interval,
                scope=m.scope,
                description=m.description,
                enabled=True,
            ))
        else:
            out.append(m)
    return out


def collector_enabled() -> bool:
    flag = os.getenv("INSIGHT_COLLECTOR_ENABLED", "1").strip().lower()
    return flag not in ("0", "false", "no", "off")


def tick_interval_ms() -> int:
    return min_tick_seconds(resolved_metrics()) * 1000


def _due(metric_name: str, interval_sec: int, now: float) -> bool:
    last = _last_run_monotonic.get(metric_name)
    if last is None:
        return True
    return (now - last) >= interval_sec


def run_due_collectors() -> Dict[str, int]:
    """Run only collectors whose metrics are due. Safe to call every base tick."""
    global _lock_busy
    if not collector_enabled() or not is_configured():
        return {"skipped": 1}
    if _lock_busy:
        return {"busy": 1}

    _lock_busy = True
    wrote = 0
    groups_run = 0
    try:
        specs = {m.name: m for m in resolved_metrics()}
        now = time.monotonic()

        for group_key, (metric_names, fn) in _COLLECTOR_GROUPS.items():
            # Group is due if ANY of its metrics is due (they share one query)
            due_names = [
                n for n in metric_names
                if n in specs and _due(n, specs[n].interval_sec, now)
            ]
            if not due_names:
                continue
            try:
                samples = fn()
                # Keep only metrics that belong to this group (and are registered)
                allowed = set(metric_names) & set(specs.keys())
                samples = [s for s in samples if s.metric_name in allowed]
                n = insert_samples(samples)
                wrote += n
                groups_run += 1
                for nme in metric_names:
                    if nme in specs:
                        _last_run_monotonic[nme] = now
                if n:
                    log.info("insight collect %s wrote %s row(s)", group_key, n)
            except Exception:
                log.exception("insight collect failed group=%s", group_key)

        # Rules over Metric Store (cheap reads of what we already stored)
        try:
            evaluate_rules()
        except Exception:
            log.exception("insight rules failed")

        return {"groups": groups_run, "rows": wrote}
    finally:
        _lock_busy = False
