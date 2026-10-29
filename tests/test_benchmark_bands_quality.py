"""Pure benchmark statistics without importing the mixed reporting module."""

import ast
import json
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "Backend" / "creative_intel" / "benchmarks.py"
tree = ast.parse(SOURCE.read_text())
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name in {"_percentile", "describe_bands"}]
assert {node.name for node in functions} == {"_percentile", "describe_bands"}
namespace = {}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"), namespace)
describe_bands = namespace["describe_bands"]


class BenchmarkBandsQualityTests(unittest.TestCase):
    def test_zero_weights_have_no_weighted_mean_but_keep_bands(self):
        result = describe_bands([2, 4], [0, 0])
        self.assertIsNone(result["mean_weighted"])
        self.assertEqual(result["mean_weighted_reason"], "zero_total_weight")
        self.assertEqual((result["p25"], result["median"], result["p75"]), (2.5, 3, 3.5))
        self.assertEqual((result["n"], result["n_missing"]), (2, 0))

    def test_one_zero_weight_observation_keeps_its_percentiles(self):
        result = describe_bands([4], [0])
        self.assertIsNone(result["mean_weighted"])
        self.assertEqual((result["p25"], result["median"], result["p75"]), (4, 4, 4))

    def test_zero_metric_with_positive_weight_is_a_real_zero_mean(self):
        result = describe_bands([0, 0], [10, 20])
        self.assertEqual(result["mean_weighted"], 0)
        self.assertIsNone(result["mean_weighted_reason"])

    def test_zero_weight_does_not_affect_mean_but_remains_in_unweighted_bands(self):
        result = describe_bands([2, 4], [0, 10])
        self.assertEqual(result["mean_weighted"], 4)
        self.assertEqual(result["median"], 3)

    def test_positive_weight_pooling_and_rounding_are_preserved(self):
        result = describe_bands([1, 3], [100, 300])
        self.assertEqual(result["mean_weighted"], 2.5)
        self.assertIsNone(result["mean_weighted_reason"])
        self.assertEqual(describe_bands([0, 1], [2, 1])["mean_weighted"], 0.3333)

    def test_missing_values_exclude_their_weights_from_the_mean(self):
        result = describe_bands([None, 2, None, 4], [10, 20, 30, 40])
        self.assertEqual(result["mean_weighted"], 3.3333)
        self.assertEqual((result["n"], result["n_missing"]), (2, 2))
        self.assertEqual(result["median"], 3)

    def test_missing_weights_preserve_the_existing_pair_exclusion(self):
        result = describe_bands([2, 4], [None, 10])
        self.assertEqual(result["mean_weighted"], 4)
        self.assertEqual(result["median"], 4)
        self.assertEqual(result["n_missing"], 1)

    def test_empty_and_all_missing_populations_keep_null_bands(self):
        for values, weights in [([], []), ([None, None], [5, 6]), ([2, 4], [None, None]), (None, None)]:
            with self.subTest(values=values, weights=weights):
                result = describe_bands(values, weights)
                for key in ["mean_weighted", "p25", "median", "p75"]:
                    self.assertIsNone(result[key])
                self.assertEqual(result["n"], 0)
                self.assertEqual(result["mean_weighted_reason"], "no_usable_pairs")

    def test_zero_unweighted_percentiles_are_not_erased_with_zero_weights(self):
        result = describe_bands([0, 0], [0, 0])
        self.assertIsNone(result["mean_weighted"])
        self.assertEqual((result["p25"], result["median"], result["p75"]), (0, 0, 0))

    def test_nonpositive_total_weight_never_manufactures_a_zero_mean(self):
        result = describe_bands([2, 4], [-1, 0])
        self.assertIsNone(result["mean_weighted"])
        self.assertEqual(result["mean_weighted_reason"], "non_positive_total_weight")
        self.assertEqual(result["median"], 3)

    def test_duplicate_values_still_count_as_separate_observations(self):
        result = describe_bands([2, 2, 4], [0, 0, 0])
        self.assertEqual(result["n"], 3)
        self.assertEqual(result["median"], 2)
        self.assertIsNone(result["mean_weighted"])

    def test_unavailable_mean_serializes_as_json_null_with_its_reason(self):
        decoded = json.loads(json.dumps(describe_bands([2, 4], [0, 0])))
        self.assertIsNone(decoded["mean_weighted"])
        self.assertEqual(decoded["mean_weighted_reason"], "zero_total_weight")
        self.assertEqual(decoded["median"], 3)


if __name__ == "__main__":
    unittest.main()
