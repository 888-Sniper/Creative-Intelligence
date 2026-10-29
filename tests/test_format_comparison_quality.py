"""Synthetic format-policy tests with the real pure metric implementation.

Only four explicitly selected diagnostic functions and a literal constant are
compiled. The application package initializer and diagnostic module imports are
not executed. These tests do not establish full Analyst workflow integration.
"""

import ast
import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "Backend" / "creative_intel"
NAMESPACE = "quality_format_comparison"
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

policy_path = ROOT / "analyst_diagnostics.py"
policy_tree = ast.parse(policy_path.read_text())
names = {"_measured", "_finding", "_group_pooled", "rule_format_comparison"}
selected = []
for node in policy_tree.body:
    if isinstance(node, ast.FunctionDef) and node.name in names:
        assert not node.decorator_list
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                ast.literal_eval(default)
        selected.append(node)
    elif isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == "MIN_COHORT_N" for target in node.targets
    ):
        ast.literal_eval(node.value)
        selected.append(node)
assert len(selected) == 5
policy = {"metrics": metrics}
exec(compile(ast.Module(body=selected, type_ignores=[]), str(policy_path), "exec"), policy)
compare = policy["rule_format_comparison"]


def fixture(left_format, right_format, left_rate, right_rate, count=1):
    summaries = []
    rows = {}
    for side, format_kind, rate in [("left", left_format, left_rate), ("right", right_format, right_rate)]:
        for index in range(count):
            key = f"{side}-{index}"
            summaries.append({"creative_key": key, "format_kind": format_kind})
            rows[key] = [{"impressions": 10_000, "views_2s": rate * 100,
                          "missing_json": "[]"}]
    return summaries, rows


class FormatComparisonDirectionQualityTests(unittest.TestCase):
    def check_direction(self, left_format, right_format, left_rate, right_rate,
                        expected_hypothesis, expected_iteration, count=1):
        summaries, rows = fixture(left_format, right_format, left_rate, right_rate, count)
        findings = compare(summaries, rows, "synthetic-scope", "synthetic-version")
        self.assertEqual(len(findings), 1)
        result = findings[0]
        winner, loser = ("left", "right") if left_rate > right_rate else ("right", "left")
        self.assertEqual(result["creative_ids"],
                         [f"{side}-{index}" for side in [winner, loser] for index in range(count)])
        self.assertEqual(result["creative_hypothesis"], expected_hypothesis)
        self.assertEqual(result["recommended_iteration"], expected_iteration)
        self.assertEqual(result["diagnosis"], "plausible association only: " + expected_hypothesis)
        self.assertEqual(result["element_to_preserve"], f"{winner}-0-side execution")
        self.assertEqual(result["element_to_change"], f"{loser}-0-side rework")
        self.assertIn(f"{left_rate:.1f}%", result["primary_signal"])
        self.assertIn(f"{right_rate:.1f}%", result["primary_signal"])
        self.assertIn(f"{left_rate - right_rate:+.1f} pp", result["primary_signal"])
        self.assertEqual(result["observed_values"]["diff_pp"], left_rate - right_rate)
        self.assertEqual(result["scope"], "synthetic-scope")
        self.assertEqual(result["dataset_version"], "synthetic-version")
        self.assertTrue(result["alternative_explanations"])
        self.assertTrue(result["limitations"])
        return result

    def test_b_roll_winner_keeps_demonstration_recommendation(self):
        result = self.check_direction("b_roll", "solo_creator", 30, 10,
                                     "Product demonstration may be effective in this cohort.",
                                     "Test result/demo-first openings.")
        self.assertEqual(result["confidence_level"], "exploratory")

    def test_face_to_camera_winner_gets_matching_recommendation(self):
        self.check_direction("b_roll", "solo_creator", 10, 30,
                             "Direct-to-camera execution may be effective in this cohort.",
                             "Test face-to-camera openings.")

    def test_human_led_winner_keeps_creator_recommendation(self):
        self.check_direction("creator_led", "graphics_remix", 30, 10,
                             "Human-led execution may fit this cohort better.",
                             "Develop creator-led variants.")

    def test_graphics_winner_gets_matching_recommendation(self):
        self.check_direction("creator_led", "graphics_remix", 10, 30,
                             "Graphics-led execution may fit this cohort better.",
                             "Develop graphics-led variants.")

    def test_small_gaps_in_either_direction_still_emit_no_finding(self):
        for left, right in [(20, 20.9), (20.9, 20), (20, 20)]:
            with self.subTest(left=left, right=right):
                summaries, rows = fixture("creator_led", "graphics_remix", left, right)
                self.assertEqual(compare(summaries, rows, "scope", "version"), [])

    def test_exact_one_percentage_point_gap_retains_direction(self):
        self.check_direction("creator_led", "graphics_remix", 20, 21,
                             "Graphics-led execution may fit this cohort better.",
                             "Develop graphics-led variants.")

    def test_missing_left_hook_metric_emits_no_finding(self):
        summaries, rows = fixture("creator_led", "graphics_remix", 10, 30)
        rows["left-0"][0]["missing_json"] = '["views_2s"]'
        self.assertEqual(compare(summaries, rows, "scope", "version"), [])

    def test_missing_right_hook_metric_emits_no_finding(self):
        summaries, rows = fixture("creator_led", "graphics_remix", 30, 10)
        rows["right-0"][0]["missing_json"] = '["views_2s"]'
        self.assertEqual(compare(summaries, rows, "scope", "version"), [])

    def test_missing_comparison_group_emits_no_finding(self):
        summaries, rows = fixture("b_roll", "unclassified", 30, 10)
        self.assertEqual(compare(summaries, rows, "scope", "version"), [])

    def test_larger_groups_keep_observational_confidence_and_matching_advice(self):
        result = self.check_direction("creator_led", "graphics_remix", 10, 30,
                                     "Graphics-led execution may fit this cohort better.",
                                     "Develop graphics-led variants.", count=3)
        self.assertEqual(result["confidence_level"], "medium")
        self.assertIn("observational", " ".join(result["limitations"]))

    def test_pooled_exposure_not_mean_of_individual_rates_selects_winner(self):
        summaries, rows = fixture("creator_led", "graphics_remix", 80, 20)
        rows["left-0"] = [{"impressions": 100, "views_2s": 80},
                          {"impressions": 900, "views_2s": 0}]
        result = compare(summaries, rows, "scope", "version")[0]
        self.assertEqual(result["observed_values"]["left_hook"], 8)
        self.assertEqual(result["creative_ids"][0], "right-0")
        self.assertEqual(result["recommended_iteration"], "Develop graphics-led variants.")

    def test_empty_input_emits_no_finding(self):
        self.assertEqual(compare([], {}, "scope", "version"), [])


if __name__ == "__main__":
    unittest.main()
