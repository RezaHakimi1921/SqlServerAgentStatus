"""Explainable baseline forecasting for SQL Server object size history.

This is a read-only analytics primitive. It does not query SQL Server or perform
any action. Forecasts are scenarios, not calibrated statistical guarantees.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class GrowthPoint:
    observed_at: datetime
    value_bytes: int


@dataclass(frozen=True)
class GrowthForecastConfig:
    min_daily_samples: int = 14
    min_span_days: int = 14
    min_coverage: float = 0.80
    horizon_days: int = 180
    jump_mad_factor: float = 8.0
    min_jump_bytes: int = 64 * 1024 * 1024


@dataclass(frozen=True)
class GrowthForecast:
    status: str
    method: str
    method_version: str
    current_value_bytes: Optional[int]
    target_value_bytes: Optional[int]
    slope_p10_bytes_per_day: Optional[float]
    slope_p50_bytes_per_day: Optional[float]
    slope_p90_bytes_per_day: Optional[float]
    days_to_target_p10_slope: Optional[float]
    days_to_target_p50_slope: Optional[float]
    days_to_target_p90_slope: Optional[float]
    forecast_value_at_horizon_p10_slope: Optional[float]
    forecast_value_at_horizon_p50_slope: Optional[float]
    forecast_value_at_horizon_p90_slope: Optional[float]
    valid_daily_samples: int
    span_days: int
    coverage: float
    residual_mad_bytes: Optional[float]
    confidence: str
    generated_at_utc: str
    limitations: Tuple[str, ...]

    def as_dict(self) -> Dict[str, object]:
        result = dict(self.__dict__)
        result["limitations"] = list(self.limitations)
        return result


def _require_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    return value.astimezone(timezone.utc)


def _daily_medians(points: Iterable[GrowthPoint]) -> List[Tuple[date, float]]:
    buckets: Dict[date, List[int]] = {}
    for point in points:
        if point.value_bytes < 0:
            raise ValueError("value_bytes must be non-negative")
        observed = _require_utc_aware(point.observed_at)
        buckets.setdefault(observed.date(), []).append(int(point.value_bytes))
    return [(day, float(median(values))) for day, values in sorted(buckets.items())]


def _quantile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = pos - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _theil_sen(days_and_values: Sequence[Tuple[int, float]]) -> Tuple[float, float, List[float]]:
    slopes: List[float] = []
    for i, (t1, y1) in enumerate(days_and_values):
        for t2, y2 in days_and_values[i + 1:]:
            if t2 > t1:
                slopes.append((y2 - y1) / (t2 - t1))
    if not slopes:
        raise ValueError("at least two different observation days are required")
    slope = float(median(slopes))
    intercept = float(median([y - slope * t for t, y in days_and_values]))
    return slope, intercept, slopes


def _mad(values: Sequence[float]) -> float:
    center = float(median(values))
    return float(median([abs(value - center) for value in values]))


def _base_result(
    *, status: str, points_count: int, span_days: int, coverage: float,
    current: Optional[int], target: Optional[int], config: GrowthForecastConfig,
    limitations: Sequence[str], confidence: str = "none",
) -> GrowthForecast:
    return GrowthForecast(
        status=status,
        method="theil_sen_daily_median",
        method_version="0.1.0",
        current_value_bytes=current,
        target_value_bytes=target,
        slope_p10_bytes_per_day=None,
        slope_p50_bytes_per_day=None,
        slope_p90_bytes_per_day=None,
        days_to_target_p10_slope=None,
        days_to_target_p50_slope=None,
        days_to_target_p90_slope=None,
        forecast_value_at_horizon_p10_slope=None,
        forecast_value_at_horizon_p50_slope=None,
        forecast_value_at_horizon_p90_slope=None,
        valid_daily_samples=points_count,
        span_days=span_days,
        coverage=coverage,
        residual_mad_bytes=None,
        confidence=confidence,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        limitations=tuple(limitations),
    )


def forecast_growth(
    points: Iterable[GrowthPoint],
    target_value_bytes: Optional[int],
    config: GrowthForecastConfig = GrowthForecastConfig(),
) -> GrowthForecast:
    """Forecast size scenarios from timestamped samples.

    Daily medians reduce duplicate-poll noise. Theil–Sen slopes are calculated
    over all daily pairs. The p10/p50/p90 slopes are empirical scenarios, not
    calibrated confidence intervals. The caller owns persistence and API output.
    """
    if config.min_daily_samples < 2 or config.min_span_days < 1:
        raise ValueError("minimum history configuration is invalid")
    if not 0 < config.min_coverage <= 1:
        raise ValueError("min_coverage must be in (0, 1]")
    if config.horizon_days < 1:
        raise ValueError("horizon_days must be positive")
    if target_value_bytes is not None and target_value_bytes < 0:
        raise ValueError("target_value_bytes must be non-negative or None")

    daily = _daily_medians(points)
    if not daily:
        return _base_result(
            status="insufficient_history", points_count=0, span_days=0, coverage=0.0,
            current=None, target=target_value_bytes, config=config,
            limitations=["No valid size observations were provided."],
        )

    first_day, last_day = daily[0][0], daily[-1][0]
    span_days = (last_day - first_day).days
    expected_days = span_days + 1
    coverage = len(daily) / expected_days
    current = int(round(daily[-1][1]))

    if len(daily) < config.min_daily_samples or span_days < config.min_span_days:
        return _base_result(
            status="insufficient_history", points_count=len(daily), span_days=span_days,
            coverage=coverage, current=current, target=target_value_bytes, config=config,
            limitations=["Not enough daily observations or elapsed history for the configured minimum."],
        )
    if coverage < config.min_coverage:
        return _base_result(
            status="low_coverage", points_count=len(daily), span_days=span_days,
            coverage=coverage, current=current, target=target_value_bytes, config=config,
            limitations=["Observation gaps exceed the configured coverage limit."],
        )

    origin = first_day
    normalized = [((day - origin).days, value) for day, value in daily]
    deltas = [normalized[i][1] - normalized[i - 1][1] for i in range(1, len(normalized))]
    if len(deltas) >= 5:
        delta_center = float(median(deltas))
        delta_mad = _mad(deltas)
        jump_threshold = max(config.min_jump_bytes, config.jump_mad_factor * delta_mad)
        large_jumps = [delta for delta in deltas if abs(delta - delta_center) > jump_threshold]
        if large_jumps:
            return _base_result(
                status="structural_change", points_count=len(daily), span_days=span_days,
                coverage=coverage, current=current, target=target_value_bytes, config=config,
                limitations=[
                    "A large step change was detected in size deltas; review rebuild, purge, restore, compression, or partition operations before forecasting."
                ],
            )

    slope, intercept, slopes = _theil_sen(normalized)
    fitted = [intercept + slope * day for day, _ in normalized]
    residuals = [value - estimate for (_, value), estimate in zip(normalized, fitted)]
    residual_mad = _mad(residuals)
    slope_low = _quantile(slopes, 0.10)
    slope_mid = _quantile(slopes, 0.50)
    slope_high = _quantile(slopes, 0.90)

    relative_error = residual_mad / max(float(current), 1.0)
    if coverage >= 0.95 and relative_error <= 0.02:
        confidence = "high"
    elif coverage >= 0.85 and relative_error <= 0.10:
        confidence = "medium"
    else:
        confidence = "low"

    limitations = [
        "Slope percentiles are empirical scenarios, not statistically calibrated confidence intervals.",
        "A linear trend assumes the recent growth regime continues through the forecast horizon.",
    ]
    if target_value_bytes is None:
        status = "trend_available"
    elif current >= target_value_bytes:
        status = "threshold_exceeded"
    elif slope_mid <= 0:
        status = "no_positive_growth_trend"
    else:
        median_days = (target_value_bytes - current) / slope_mid
        status = "beyond_horizon" if median_days > config.horizon_days else "forecast_available"

    def days_to_target(slope_value: float) -> Optional[float]:
        if target_value_bytes is None or current >= target_value_bytes or slope_value <= 0:
            return None
        return (target_value_bytes - current) / slope_value

    def value_at_horizon(slope_value: float) -> float:
        return max(0.0, current + slope_value * config.horizon_days)

    if status == "beyond_horizon":
        limitations.append("Median-slope threshold crossing is beyond the configured forecast horizon.")

    return GrowthForecast(
        status=status,
        method="theil_sen_daily_median",
        method_version="0.1.0",
        current_value_bytes=current,
        target_value_bytes=target_value_bytes,
        slope_p10_bytes_per_day=slope_low,
        slope_p50_bytes_per_day=slope_mid,
        slope_p90_bytes_per_day=slope_high,
        days_to_target_p10_slope=days_to_target(slope_low),
        days_to_target_p50_slope=days_to_target(slope_mid),
        days_to_target_p90_slope=days_to_target(slope_high),
        forecast_value_at_horizon_p10_slope=value_at_horizon(slope_low),
        forecast_value_at_horizon_p50_slope=value_at_horizon(slope_mid),
        forecast_value_at_horizon_p90_slope=value_at_horizon(slope_high),
        valid_daily_samples=len(daily),
        span_days=span_days,
        coverage=coverage,
        residual_mad_bytes=residual_mad,
        confidence=confidence,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        limitations=tuple(limitations),
    )
