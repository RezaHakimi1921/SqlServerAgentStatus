import unittest
from datetime import datetime, timedelta, timezone

from analytics.growth_forecast import (
    GrowthForecastConfig,
    GrowthPoint,
    forecast_growth,
)


class GrowthForecastTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.config = GrowthForecastConfig(
            min_daily_samples=14,
            min_span_days=14,
            min_coverage=0.8,
            horizon_days=180,
        )

    def points(self, count=20, step=10_000_000):
        return [
            GrowthPoint(self.start + timedelta(days=i), 1_000_000_000 + i * step)
            for i in range(count)
        ]

    def test_linear_growth_produces_explainable_scenarios(self):
        result = forecast_growth(self.points(), 2_000_000_000, self.config)
        self.assertEqual(result.status, "forecast_available")
        self.assertEqual(result.method, "theil_sen_daily_median")
        self.assertAlmostEqual(result.slope_p50_bytes_per_day, 10_000_000)
        self.assertGreater(result.days_to_target_p50_slope, 0)
        self.assertEqual(result.valid_daily_samples, 20)
        self.assertEqual(result.coverage, 1.0)

    def test_insufficient_history_fails_closed(self):
        result = forecast_growth(self.points(count=5), 2_000_000_000, self.config)
        self.assertEqual(result.status, "insufficient_history")
        self.assertIsNone(result.slope_p50_bytes_per_day)

    def test_structural_jump_is_not_projected_as_linear_growth(self):
        points = self.points()
        points[10] = GrowthPoint(points[10].observed_at, points[10].value_bytes + 2_000_000_000)
        result = forecast_growth(points, 4_000_000_000, self.config)
        self.assertEqual(result.status, "structural_change")
        self.assertIsNone(result.days_to_target_p50_slope)

    def test_exceeded_threshold_is_not_reported_as_future_forecast(self):
        result = forecast_growth(self.points(), 1_000_000_000, self.config)
        self.assertEqual(result.status, "threshold_exceeded")
        self.assertIsNone(result.days_to_target_p50_slope)

    def test_duplicate_same_day_samples_are_aggregated_by_median(self):
        points = self.points()
        points.extend([
            GrowthPoint(self.start + timedelta(hours=1), 1_000_000_000),
            GrowthPoint(self.start + timedelta(hours=2), 1_000_000_010),
        ])
        result = forecast_growth(points, None, self.config)
        self.assertEqual(result.status, "trend_available")
        self.assertEqual(result.valid_daily_samples, 20)

    def test_naive_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            forecast_growth([GrowthPoint(datetime(2026, 1, 1), 100)], None, self.config)


if __name__ == "__main__":
    unittest.main()
