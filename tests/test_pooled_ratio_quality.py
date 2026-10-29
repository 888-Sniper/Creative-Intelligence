"""Pure pooled-ratio parity and bounded operation-count regressions."""

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "Backend" / "creative_intel"
NAMESPACE = "quality_pooled_ratio"
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


def observation(clicks=0, impressions=0, missing=(), **extra):
    return {"clicks": clicks, "impressions": impressions,
            "missing_json": json.dumps(list(missing)), **extra}


def calculate(rows, scale=100):
    return metrics.pooled_ratio(rows, "ctr_all", "clicks", "impressions", scale)


class PooledRatioQualityTests(unittest.TestCase):
    def test_pooling_uses_sums_not_a_mean_of_row_rates(self):
        result = calculate([observation(1, 100), observation(9, 300)])
        self.assertEqual(result["value"], 2.5)
        self.assertEqual(result["numerator"], 10)
        self.assertEqual(result["denominator"], 400)
        self.assertEqual(result["state"], metrics.MEASURED)
        self.assertEqual(result["basis"], "pooled")
        self.assertEqual(result["reasons"], [])

    def test_partial_populations_keep_exact_state_and_provenance(self):
        result = calculate([
            observation(10, 100), observation(90, 900, ["clicks"]),
            observation(80, 800, ["impressions"]),
        ])
        self.assertEqual(result["value"], 10)
        self.assertEqual(result["state"], metrics.ESTIMATED)
        self.assertEqual(result["reasons"], [
            "2 of 3 rows lack clicks/impressions; pooled from 1 rows",
        ])

    def test_disjoint_supplied_fields_have_no_ratio(self):
        result = calculate([observation(10, 0, ["impressions"]),
                            observation(0, 100, ["clicks"])])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.NA)
        self.assertEqual(result["numerator"], 0)
        self.assertEqual(result["denominator"], 0)
        self.assertEqual(result["reasons"], [
            "2 of 2 rows lack clicks/impressions; pooled from 0 rows",
            "denominator is zero",
        ])

    def test_absent_field_or_empty_scope_remains_unsupported(self):
        for rows in [[], [observation(2, 10, ["clicks"])],
                     [observation(2, 10, ["impressions"])]]:
            with self.subTest(rows=rows):
                result = calculate(rows)
                self.assertIsNone(result["value"])
                self.assertEqual(result["state"], metrics.UNSUPPORTED)
                self.assertEqual(result["reasons"], ["clicks or impressions not supplied in scope"])

    def test_measured_zero_numerator_is_not_missing(self):
        result = calculate([observation(0, 100)])
        self.assertEqual(result["value"], 0)
        self.assertEqual(result["state"], metrics.MEASURED)

    def test_zero_denominator_retains_numerator_and_na_state(self):
        result = calculate([observation(5, 0)])
        self.assertIsNone(result["value"])
        self.assertEqual(result["state"], metrics.NA)
        self.assertEqual(result["numerator"], 5)
        self.assertEqual(result["reasons"], ["denominator is zero"])

    def test_equal_rows_and_repeated_objects_each_contribute(self):
        row = observation(1, 100)
        result = calculate([row, row.copy(), row, observation(9, 100)])
        self.assertEqual(result["numerator"], 12)
        self.assertEqual(result["denominator"], 400)
        self.assertEqual(result["value"], 3)

    def test_custom_scale_and_same_field_keep_existing_semantics(self):
        rows = [observation(2, 100)]
        self.assertEqual(calculate(rows, scale=1)["value"], 0.02)
        result = metrics.pooled_ratio(rows, "ctr_all", "clicks", "clicks", 1)
        self.assertEqual(result["value"], 1)

    def test_unknown_metric_is_rejected_before_rows_are_examined(self):
        with patch.object(metrics, "_missing_of", wraps=metrics._missing_of) as missing:
            with self.assertRaisesRegex(ValueError, "unknown metric"):
                metrics.pooled_ratio([observation(1, 2)], "not_registered", "clicks", "impressions")
            missing.assert_not_called()

    def test_builtin_float_sum_order_is_preserved(self):
        values = [1e16, 1.0, 1.0]
        result = calculate([observation(value, 1) for value in values], scale=1)
        self.assertEqual(result["numerator"], sum(values))
        self.assertEqual(result["value"], sum(values) / 3)

    def test_missing_markers_are_parsed_at_most_once_per_input_row(self):
        rows = [observation(i, 100, ["clicks"] if i % 2 else []) for i in range(20)]
        with patch.object(metrics, "_missing_of", wraps=metrics._missing_of) as missing:
            calculate(rows)
        self.assertLessEqual(missing.call_count, len(rows))

    def test_distinct_row_work_does_not_grow_quadratically(self):
        class CountedRow(dict):
            comparisons = 0

            def __eq__(self, other):
                type(self).comparisons += 1
                return super().__eq__(other)

        for size in [32, 64, 128]:
            with self.subTest(size=size):
                rows = [CountedRow(observation(i, 100, row_id=i)) for i in range(size)]
                CountedRow.comparisons = 0
                result = calculate(rows)
                self.assertEqual(result["denominator"], size * 100)
                self.assertLessEqual(CountedRow.comparisons, 4 * size)


if __name__ == "__main__":
    unittest.main()
