"""Synthetic watch-time pooling checks without application initialization."""

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "Backend" / "creative_intel"
NAMESPACE = "quality_watch_time"
package = types.ModuleType(NAMESPACE)
package.__path__ = []
sys.modules[NAMESPACE] = package
for name in ("currency_scope", "metric_availability", "analyst_metrics"):
    spec = importlib.util.spec_from_file_location(f"{NAMESPACE}.{name}", ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
metrics = sys.modules[f"{NAMESPACE}.analyst_metrics"]


def observation(*, missing=(), **values):
    return {
        "creative_key": "creative",
        "watch_time_basis": "views",
        "watch_time_total_s": 0,
        "video_views": 100,
        "video_starts": 100,
        "avg_watch_per_view_s": 8,
        "missing_json": json.dumps(list(missing)),
        **values,
    }


class WatchTimePopulationQualityTests(unittest.TestCase):
    def test_zero_watch_total_contributes_its_matching_views(self):
        result, _ = metrics.awt_per_view([
            observation(watch_time_total_s=0),
            observation(watch_time_total_s=1000),
        ])
        self.assertEqual(result["value"], 5)
        self.assertEqual(result["numerator"], 1000)
        self.assertEqual(result["denominator"], 200)
        self.assertEqual(result["state"], metrics.MEASURED)

    def test_all_measured_zero_totals_remain_zero_not_reported_average(self):
        result, _ = metrics.awt_per_view([observation(), observation(video_views=50)])
        self.assertEqual(result["value"], 0)
        self.assertEqual(result["denominator"], 150)
        self.assertEqual(result["basis"], "total_over_video_views")
        self.assertEqual(result["state"], metrics.MEASURED)

    def test_measured_zero_has_a_zero_percentage_of_known_duration(self):
        result, pct = metrics.awt_per_view([observation()], {"creative": 20})
        self.assertEqual(result["value"], 0)
        self.assertEqual(pct["value"], 0)
        self.assertEqual(pct["state"], metrics.MEASURED)

    def test_missing_total_does_not_contribute_a_stored_zero_or_weight(self):
        result, _ = metrics.awt_per_view([
            observation(missing=["watch_time_total_s"], video_views=900),
            observation(watch_time_total_s=1000),
        ])
        self.assertEqual(result["value"], 10)
        self.assertEqual(result["denominator"], 100)
        self.assertIn("1 of 2 rows", " ".join(result["reasons"]))

    def test_missing_matching_count_excludes_both_sides(self):
        result, _ = metrics.awt_per_view([
            observation(watch_time_total_s=1000, missing=["video_views"]),
            observation(watch_time_total_s=0),
        ])
        self.assertEqual(result["value"], 0)
        self.assertEqual(result["numerator"], 0)
        self.assertEqual(result["denominator"], 100)
        self.assertIn("1 of 2 rows", " ".join(result["reasons"]))

    def test_zero_matching_count_cannot_add_unmatched_watch_seconds(self):
        result, _ = metrics.awt_per_view([
            observation(watch_time_total_s=900, video_views=0),
            observation(watch_time_total_s=100),
        ])
        self.assertEqual(result["value"], 1)
        self.assertEqual(result["numerator"], 100)
        self.assertEqual(result["denominator"], 100)

    def test_no_positive_matching_count_stays_unavailable(self):
        result, pct = metrics.awt_per_view([observation(video_views=0)], {"creative": 20})
        self.assertIsNone(result["value"])
        self.assertIsNone(pct["value"])
        self.assertEqual(result["state"], metrics.NA)

    def test_start_based_zero_total_uses_starts_not_views(self):
        result, _ = metrics.awt_per_view([
            observation(watch_time_basis="starts", video_starts=50, video_views=900),
            observation(watch_time_basis="starts", watch_time_total_s=500,
                        video_starts=50, video_views=1),
        ])
        self.assertEqual(result["value"], 5)
        self.assertEqual(result["denominator"], 100)
        self.assertEqual(result["basis"], "total_over_video_starts")

    def test_zero_totals_do_not_hide_mixed_watch_bases(self):
        result, pct = metrics.awt_per_view([
            observation(watch_time_basis="starts"),
            observation(watch_time_basis="views", watch_time_total_s=1000),
        ])
        self.assertIsNone(result["value"])
        self.assertIsNone(pct["value"])
        self.assertEqual(result["state"], metrics.NA)
        self.assertIn("mixed watch-time bases", " ".join(result["reasons"]))

    def test_unusable_count_does_not_introduce_a_different_basis(self):
        result, _ = metrics.awt_per_view([
            observation(watch_time_basis="starts", watch_time_total_s=900,
                        missing=["video_starts"]),
            observation(watch_time_basis="views", watch_time_total_s=1000),
        ])
        self.assertEqual(result["value"], 10)
        self.assertEqual(result["denominator"], 100)

    def test_stored_missing_total_does_not_introduce_a_different_basis(self):
        result, _ = metrics.awt_per_view([
            observation(watch_time_basis="starts", watch_time_total_s=900,
                        missing=["watch_time_total_s"]),
            observation(watch_time_basis="views", watch_time_total_s=1000),
        ])
        self.assertEqual(result["value"], 10)
        self.assertEqual(result["basis"], "total_over_video_views")

    def test_positive_totals_keep_existing_pooled_result_and_metadata(self):
        result, pct = metrics.awt_per_view([
            observation(watch_time_total_s=100, video_views=50),
            observation(watch_time_total_s=900, video_views=150),
        ], {"creative": 20})
        self.assertEqual(result["value"], 5)
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["unit"], "seconds")
        self.assertEqual(pct["value"], 25)

    def test_identical_zero_rows_each_contribute_once(self):
        zero = observation()
        result, _ = metrics.awt_per_view([zero, zero.copy(), observation(watch_time_total_s=900)])
        self.assertEqual(result["value"], 3)
        self.assertEqual(result["denominator"], 300)

    def test_legacy_unmarked_zero_retains_documented_measured_semantics(self):
        row = observation()
        del row["missing_json"]
        result, _ = metrics.awt_per_view([row])
        self.assertEqual(result["value"], 0)
        self.assertEqual(result["state"], metrics.MEASURED)


def average_observation(average, views, *, missing=(), **values):
    return observation(
        missing=["watch_time_total_s", *missing],
        avg_watch_per_view_s=average,
        video_views=views,
        **values,
    )


class WatchTimeAverageFallbackQualityTests(unittest.TestCase):
    def test_missing_totals_use_the_view_weighted_reported_average(self):
        result, _ = metrics.awt_per_view([
            average_observation(1, 100), average_observation(3, 900),
        ])
        self.assertAlmostEqual(result["value"], 2.8)
        self.assertEqual(result["state"], metrics.ESTIMATED)
        self.assertEqual(result["numerator"], 2800)
        self.assertEqual(result["denominator"], 1000)
        self.assertEqual(result["basis"], "weighted_mean_of_reported_avgs")
        self.assertIn("approximation from rounded source averages", result["reasons"])

    def test_reported_zero_average_keeps_its_weight(self):
        result, _ = metrics.awt_per_view([
            average_observation(0, 100), average_observation(3, 900),
        ])
        self.assertAlmostEqual(result["value"], 2.7)
        self.assertEqual(result["denominator"], 1000)

    def test_all_zero_averages_and_duration_percentage_remain_estimated_zero(self):
        result, pct = metrics.awt_per_view([
            average_observation(0, 100), average_observation(0, 50),
        ], {"creative": 20})
        self.assertEqual(result["value"], 0)
        self.assertEqual(result["state"], metrics.ESTIMATED)
        self.assertEqual(pct["value"], 0)
        self.assertEqual(pct["state"], metrics.ESTIMATED)

    def test_missing_average_excludes_its_stored_value_and_weight(self):
        result, _ = metrics.awt_per_view([
            average_observation(1, 100),
            average_observation(9, 900, missing=["avg_watch_per_view_s"]),
        ])
        self.assertEqual(result["value"], 1)
        self.assertEqual(result["denominator"], 100)
        self.assertIn("1 of 2 rows", " ".join(result["reasons"]))

    def test_missing_views_exclude_both_weighted_numerator_and_denominator(self):
        result, _ = metrics.awt_per_view([
            average_observation(1, 100),
            average_observation(9, 900, missing=["video_views"]),
        ])
        self.assertEqual(result["value"], 1)
        self.assertEqual(result["numerator"], 100)
        self.assertEqual(result["denominator"], 100)

    def test_nonpositive_view_counts_cannot_weight_reported_averages(self):
        for count in [0, -5]:
            with self.subTest(count=count):
                result, _ = metrics.awt_per_view([
                    average_observation(1, 100), average_observation(9, count),
                ])
                self.assertEqual(result["value"], 1)
                self.assertEqual(result["denominator"], 100)

    def test_per_user_average_is_not_a_substitute_for_missing_per_view_average(self):
        result, pct = metrics.awt_per_view([
            average_observation(0, 100, missing=["avg_watch_per_view_s"],
                                avg_watch_per_user_s=20),
        ])
        self.assertIsNone(result["value"])
        self.assertIsNone(pct["value"])
        self.assertEqual(result["state"], metrics.UNSUPPORTED)

    def test_supplied_averages_without_usable_weights_remain_unavailable(self):
        for row in [average_observation(2, 0),
                    average_observation(2, 100, missing=["video_views"])]:
            with self.subTest(row=row):
                result, pct = metrics.awt_per_view([row])
                self.assertIsNone(result["value"])
                self.assertIsNone(pct["value"])
                self.assertEqual(result["state"], metrics.NA)

    def test_empty_scope_remains_unsupported(self):
        result, _ = metrics.awt_per_view([])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.UNSUPPORTED)

    def test_supplied_totals_keep_priority_over_other_rows_reported_averages(self):
        result, _ = metrics.awt_per_view([
            observation(watch_time_total_s=1000), average_observation(1, 900),
        ])
        self.assertEqual(result["value"], 10)
        self.assertEqual(result["state"], metrics.MEASURED)
        self.assertEqual(result["basis"], "total_over_video_views")

    def test_invalid_supplied_totals_do_not_silently_switch_to_an_average(self):
        result, _ = metrics.awt_per_view([observation(watch_time_total_s=-1)])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.NA)

    def test_reported_per_view_fallback_uses_views_not_start_counts(self):
        result, _ = metrics.awt_per_view([
            average_observation(1, 100, watch_time_basis="starts", video_starts=900),
            average_observation(3, 900, watch_time_basis="starts", video_starts=100),
        ])
        # The total is absent: this route retains the explicit per-view
        # average/video_views contract rather than reinterpreting that field.
        self.assertAlmostEqual(result["value"], 2.8)
        self.assertEqual(result["denominator"], 1000)

    def test_duration_percentage_preserves_estimate_provenance(self):
        result, pct = metrics.awt_per_view([
            average_observation(1, 100), average_observation(3, 900),
        ], {"creative": 20})
        self.assertAlmostEqual(pct["value"], 14)
        self.assertEqual(pct["state"], metrics.ESTIMATED)
        self.assertEqual(pct["reasons"], result["reasons"])

    def test_multi_creative_average_does_not_invent_a_shared_duration(self):
        result, pct = metrics.awt_per_view([
            average_observation(1, 100, creative_key="A"),
            average_observation(3, 900, creative_key="B"),
        ], {"A": 10, "B": 20})
        self.assertAlmostEqual(result["value"], 2.8)
        self.assertIsNone(pct["value"])
        self.assertEqual(pct["state"], metrics.NA)


if __name__ == "__main__":
    unittest.main()
