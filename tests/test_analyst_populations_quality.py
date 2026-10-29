"""Pure metric-engine regressions, without application bootstrap or fixtures.

Only the metric engine and its two explicit pure helper dependencies are loaded
under a private test namespace. No creative_intel package initializer is run.
"""

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "Backend" / "creative_intel"
NAMESPACE = "quality_analyst_populations"
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
    return {"impressions": 0, "reach": 0, "frequency": 0,
            "likes": 0, "comments": 0, "shares": 0, "saves": 0,
            "missing_json": json.dumps(list(missing)), **values}


class FrequencyPopulationQualityTests(unittest.TestCase):
    def test_partial_reach_does_not_describe_the_entire_scope(self):
        result = metrics.frequency([
            observation(impressions=200, reach=100, missing=["frequency"]),
            observation(impressions=800, missing=["frequency", "reach"]),
        ])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.NA)

    def test_single_fully_reported_row_retains_measured_frequency(self):
        result = metrics.frequency([
            observation(impressions=200, reach=100, missing=["frequency"]),
        ])
        self.assertEqual(result["value"], 2)
        self.assertEqual(result["state"], metrics.MEASURED)
        self.assertEqual(result["numerator"], 200)
        self.assertEqual(result["denominator"], 100)
        self.assertEqual(result["basis"], "impressions_over_scope_reach")
        self.assertEqual(result["unit"], "ratio")
        self.assertEqual(result["direction"], "neutral")

    def test_missing_impressions_cannot_become_measured_zero(self):
        result = metrics.frequency([
            observation(reach=100, missing=["frequency", "impressions"]),
        ])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.NA)

    def test_stored_impressions_marked_missing_are_not_reported(self):
        result = metrics.frequency([
            observation(impressions=200, reach=100, missing=["frequency", "impressions"]),
        ])
        self.assertIsNone(result["value"])

    def test_stored_reach_marked_missing_is_not_reported(self):
        result = metrics.frequency([
            observation(impressions=200, reach=100, missing=["frequency", "reach"]),
        ])
        self.assertIsNone(result["value"])

    def test_multiple_reach_rows_do_not_imply_deduplicated_scope_reach(self):
        result = metrics.frequency([
            observation(impressions=200, reach=100, missing=["frequency"]),
            observation(impressions=300, reach=100, missing=["frequency"]),
        ])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.NA)

    def test_reported_zero_impressions_remain_measured_zero(self):
        result = metrics.frequency([
            observation(impressions=0, reach=100, missing=["frequency"]),
        ])
        self.assertEqual(result["value"], 0)
        self.assertEqual(result["state"], metrics.MEASURED)

    def test_zero_reach_is_not_a_usable_divisor(self):
        result = metrics.frequency([observation(impressions=200, reach=0)])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.NA)

    def test_reported_frequency_keeps_reach_weighting(self):
        result = metrics.frequency([
            observation(frequency=1, impressions=1000, reach=1000),
            observation(frequency=4, impressions=2000, reach=500),
        ])
        self.assertEqual(result["value"], 2)
        self.assertEqual(result["state"], metrics.ESTIMATED)
        self.assertEqual(result["basis"], "reach_weighted_reported")

    def test_reported_frequency_discloses_excluded_missing_reach(self):
        result = metrics.frequency([
            observation(frequency=2, reach=100),
            observation(frequency=8, missing=["reach"]),
        ])
        self.assertEqual(result["value"], 2)
        self.assertEqual(result["state"], metrics.ESTIMATED)
        self.assertIn("1 of 2 rows lack reach and are excluded", result["reasons"])

    def test_reported_frequency_without_reach_retains_labelled_mean(self):
        result = metrics.frequency([
            observation(frequency=2, missing=["reach"]),
            observation(frequency=4, missing=["reach"]),
        ])
        self.assertEqual(result["value"], 3)
        self.assertEqual(result["state"], metrics.ESTIMATED)
        self.assertEqual(result["basis"], "mean_reported")

    def test_empty_frequency_scope_remains_unavailable(self):
        result = metrics.frequency([])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.NA)


class EngagementPopulationQualityTests(unittest.TestCase):
    def test_disjoint_populations_cannot_form_a_measured_rate(self):
        result = metrics.engagement_rate([
            observation(likes=20, missing=["impressions"]),
            observation(impressions=100, missing=["likes", "comments", "shares", "saves"]),
        ])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.UNSUPPORTED)

    def test_unmatched_interactions_do_not_inflate_a_matched_zero(self):
        result = metrics.engagement_rate([
            observation(likes=20, missing=["impressions"]),
            observation(impressions=100),
        ])
        self.assertEqual(result["value"], 0)
        self.assertEqual(result["numerator"], 0)
        self.assertEqual(result["denominator"], 100)
        self.assertEqual(result["state"], metrics.ESTIMATED)
        self.assertIn("1 of 2 rows", " ".join(result["reasons"]))

    def test_unmatched_impressions_do_not_dilute_a_reported_rate(self):
        result = metrics.engagement_rate([
            observation(likes=10, impressions=100),
            observation(impressions=900, missing=["likes", "comments", "shares", "saves"]),
        ])
        self.assertEqual(result["value"], 10)
        self.assertEqual(result["numerator"], 10)
        self.assertEqual(result["denominator"], 100)
        self.assertEqual(result["state"], metrics.ESTIMATED)
        self.assertIn("1 of 2 rows", " ".join(result["reasons"]))

    def test_partial_interaction_family_keeps_its_reported_impressions(self):
        result = metrics.engagement_rate([
            observation(likes=18, impressions=1000),
            observation(impressions=1000, missing=["saves"]),
        ])
        self.assertAlmostEqual(result["value"], 0.9)
        self.assertEqual(result["numerator"], 18)
        self.assertEqual(result["denominator"], 2000)
        self.assertEqual(result["state"], metrics.ESTIMATED)
        self.assertIn("1 of 2 matched rows", " ".join(result["reasons"]))

    def test_partial_interaction_family_ignores_stored_missing_values(self):
        result = metrics.engagement_rate([
            observation(likes=10, saves=90, impressions=100, missing=["saves"]),
        ])
        self.assertEqual(result["value"], 10)
        self.assertEqual(result["state"], metrics.ESTIMATED)

    def test_all_missing_interactions_remain_unsupported(self):
        result = metrics.engagement_rate([
            observation(impressions=100, missing=["likes", "comments", "shares", "saves"]),
        ])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.UNSUPPORTED)

    def test_all_missing_impressions_are_unsupported_not_a_zero_divisor(self):
        result = metrics.engagement_rate([
            observation(likes=10, missing=["impressions"]),
        ])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.UNSUPPORTED)

    def test_reported_zero_impressions_remain_na(self):
        result = metrics.engagement_rate([observation(likes=10, impressions=0)])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.NA)
        self.assertEqual(result["numerator"], 10)
        self.assertEqual(result["denominator"], 0)

    def test_reported_zero_interactions_remain_measured(self):
        result = metrics.engagement_rate([observation(impressions=100)])
        self.assertEqual(result["value"], 0)
        self.assertEqual(result["state"], metrics.MEASURED)
        self.assertEqual(result["reasons"], [])

    def test_fully_reported_populations_pool_before_division(self):
        result = metrics.engagement_rate([
            observation(likes=5, comments=3, shares=1, saves=1, impressions=100),
            observation(likes=10, comments=5, shares=3, saves=2, impressions=400),
        ])
        self.assertEqual(result["value"], 6)
        self.assertEqual(result["state"], metrics.MEASURED)
        self.assertEqual(result["numerator"], 30)
        self.assertEqual(result["denominator"], 500)
        self.assertEqual(result["basis"], "pooled_interactions")
        self.assertEqual(result["unit"], "percent")
        self.assertEqual(result["direction"], "higher_is_better")

    def test_empty_engagement_scope_remains_unsupported(self):
        result = metrics.engagement_rate([])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.UNSUPPORTED)

    def test_legacy_missing_markers_keep_the_existing_zero_policy(self):
        result = metrics.engagement_rate([{"likes": 10, "impressions": 100}])
        self.assertEqual(result["value"], 10)
        self.assertEqual(result["state"], metrics.MEASURED)


class CostPerReachAvailabilityQualityTests(unittest.TestCase):
    def test_missing_spend_is_not_free_reach(self):
        result = metrics.cost_per_1000_reached([
            observation(spend=0, reach=100, missing=["spend"], currency="GBP"),
        ])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.UNSUPPORTED)
        self.assertIn("spend", " ".join(result["reasons"]))

    def test_stored_spend_marked_missing_is_not_reported(self):
        result = metrics.cost_per_1000_reached([
            observation(spend=50, reach=100, missing=["spend"], currency="GBP"),
        ])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.UNSUPPORTED)

    def test_separate_rows_cannot_supply_matching_spend_and_reach(self):
        result = metrics.cost_per_1000_reached([
            observation(spend=0, reach=100, missing=["spend"], currency="GBP"),
            observation(spend=50, missing=["reach"], currency="GBP"),
        ])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.UNSUPPORTED)

    def test_explicit_zero_spend_remains_measured_zero(self):
        result = metrics.cost_per_1000_reached([
            observation(spend=0, reach=100, currency="GBP"),
        ])
        self.assertEqual(result["value"], 0)
        self.assertEqual(result["state"], metrics.MEASURED)
        self.assertEqual(result["numerator"], 0)
        self.assertEqual(result["denominator"], 100)
        self.assertEqual(result["basis"], "single_scope_reach")

    def test_positive_spend_uses_the_reported_reach(self):
        result = metrics.cost_per_1000_reached([
            observation(spend=50, reach=200, currency="EUR"),
        ])
        self.assertEqual(result["value"], 250)
        self.assertEqual(result["state"], metrics.MEASURED)
        self.assertEqual(result["numerator"], 50)
        self.assertEqual(result["denominator"], 200)
        self.assertEqual(result["metric_id"], "cost_per_1000_reached")

    def test_missing_reach_remains_unsupported(self):
        result = metrics.cost_per_1000_reached([
            observation(spend=50, reach=100, missing=["reach"], currency="GBP"),
        ])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.UNSUPPORTED)

    def test_zero_reach_remains_unavailable(self):
        result = metrics.cost_per_1000_reached([observation(spend=50, reach=0, currency="GBP")])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.NA)

    def test_negative_reach_remains_unavailable(self):
        result = metrics.cost_per_1000_reached([observation(spend=50, reach=-100, currency="GBP")])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.NA)

    def test_mixed_currencies_remain_unavailable(self):
        result = metrics.cost_per_1000_reached([
            observation(spend=50, reach=200, currency="GBP"),
            observation(spend=50, missing=["reach"], currency="EUR"),
        ])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.NA)
        self.assertIn("mixed currencies", " ".join(result["reasons"]))

    def test_known_and_unknown_spend_does_not_override_currency_policy(self):
        result = metrics.cost_per_1000_reached([
            observation(spend=50, reach=200, currency="GBP"),
            observation(spend=50, missing=["reach"]),
        ])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.NA)

    def test_legacy_row_without_missing_markers_keeps_explicit_spend(self):
        result = metrics.cost_per_1000_reached([{"spend": 50, "reach": 200}])
        self.assertEqual(result["value"], 250)
        self.assertEqual(result["state"], metrics.MEASURED)

    def test_legacy_unspecified_spend_keeps_the_existing_zero_policy(self):
        result = metrics.cost_per_1000_reached([{"reach": 100}])
        self.assertEqual(result["value"], 0)
        self.assertEqual(result["state"], metrics.MEASURED)

    def test_multiple_reach_rows_are_not_added(self):
        result = metrics.cost_per_1000_reached([
            observation(spend=50, reach=100, currency="GBP"),
            observation(spend=50, reach=100, currency="GBP"),
        ])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.NA)

    def test_one_reach_row_cannot_price_a_multi_row_scope(self):
        result = metrics.cost_per_1000_reached([
            observation(spend=50, reach=200, currency="GBP"),
            observation(spend=50, missing=["reach"], currency="GBP"),
        ])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.NA)
        self.assertIn("row", " ".join(result["reasons"]))

    def test_empty_scope_remains_unsupported(self):
        result = metrics.cost_per_1000_reached([])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.UNSUPPORTED)

    def test_unrelated_missing_fields_do_not_hide_reported_spend(self):
        result = metrics.cost_per_1000_reached([
            observation(spend=50, reach=200, missing=["likes", "impressions"], currency="GBP"),
        ])
        self.assertEqual(result["value"], 250)
        self.assertEqual(result["state"], metrics.MEASURED)


if __name__ == "__main__":
    unittest.main()
