"""Synthetic formula checks without workbook/archive or application imports.

Use explicitly permitted formula builders and the existing test-only formula
subset evaluator. This is not a native Excel/LibreOffice calculation engine.
"""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Backend" / "creative_intel" / "analyst_workbook.py"
FUNCTIONS = {"_ratio_formula", "_input_ref", "metric_cell_formula", "_benchmark_formulas",
             "hypothesis_formula"}
LITERALS = {"FIRST_DATA_ROW", "N_ROWS", "INPUT_COLUMNS", "NA", "HOLD_DURATION_NA", "METRIC_COLUMNS",
            "WORKBOOK_RATIOS", "BENCHMARK_ROWS"}
DERIVED = {"LAST_DATA_ROW", "INPUT_FIELD_COL", "METRIC_COL", "BENCHMARK_ROW_BY_METRIC"}
selected = []
for node in ast.parse(SOURCE.read_text()).body:
    if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
        assert not node.decorator_list and not node.args.defaults
        selected.append(node)
    elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        name = node.targets[0].id
        if name in LITERALS:
            ast.literal_eval(node.value)
            selected.append(node)
        elif name in DERIVED:
            assert isinstance(node.value, (ast.DictComp, ast.BinOp))
            assert all(isinstance(call.func, ast.Name) and call.func.id == "enumerate"
                       for call in ast.walk(node.value) if isinstance(call, ast.Call))
            selected.append(node)
formula = {}
exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec"), formula)
assert all(name in formula for name in FUNCTIONS | LITERALS | (DERIVED - {"BENCHMARK_ROW_BY_METRIC"}))

EVALUATOR_SOURCE = ROOT / "tests" / "test_analyst_workbook.py"
EVALUATOR_NAMES = {"_colkey", "_Tok", "_strip_absolute", "_tokenize", "Evaluator", "_Range", "_Err"}
selected = [n for n in ast.parse(EVALUATOR_SOURCE.read_text()).body
            if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in EVALUATOR_NAMES]
assert len(selected) == len(EVALUATOR_NAMES)
evaluation = {"re": re}
exec(compile(ast.Module(body=selected, type_ignores=[]), str(EVALUATOR_SOURCE), "exec"), evaluation)
Evaluator, Error = evaluation["Evaluator"], evaluation["_Err"]


def cohort(two_second_views=400):
    return [{"impressions": 1000, "views_2s": two_second_views, "views_3s": 200,
             "views_25": hold_views, "duration_s": 20} for hold_views in (50, 150)]


def sheet_evaluator(rows):
    sheets = {name: {} for name in ("Input", "Metrics", "Benchmarks", "Hypotheses")}
    for row, data in enumerate(rows, formula["FIRST_DATA_ROW"]):
        for col, field, _ in formula["INPUT_COLUMNS"]:
            if field in data:
                value = data[field]
                sheets["Input"][f"{col}{row}"] = ("num" if isinstance(value, (int, float)) else "text", value)
        for col, metric, _ in formula["METRIC_COLUMNS"]:
            sheets["Metrics"][f"{col}{row}"] = ("formula", formula["metric_cell_formula"](metric, row))
    for row, (_, metric) in enumerate(formula["BENCHMARK_ROWS"], formula["FIRST_DATA_ROW"]):
        if metric:
            pooled, _, _, _ = formula["_benchmark_formulas"](metric, formula["METRIC_COL"][metric])
            sheets["Benchmarks"][f"B{row}"] = ("formula", pooled)
    return Evaluator(sheets)


def verdict(evaluator, rule="weak_hold", row=6):
    return evaluator.eval(formula["hypothesis_formula"](rule, row), "Hypotheses")


def direct(hook2=40, hook3=20, hold=25, bench2=40, bench3=20, bench_hold=50):
    def cell(value):
        return ("num" if isinstance(value, (int, float)) else "text", value)
    return Evaluator({"Metrics": {"B6": cell(hook2), "C6": cell(hook3), "D6": cell(hold)},
                      "Benchmarks": {"B6": cell(bench2), "B7": cell(bench3), "B8": cell(bench_hold)},
                      "Hypotheses": {}})


class WorkbookHypothesisQualityTests(unittest.TestCase):
    def test_three_second_hook_uses_its_own_pooled_benchmark(self):
        evaluator = sheet_evaluator(cohort())
        self.assertEqual(evaluator.cell("Benchmarks", "B6"), 40)
        self.assertEqual(evaluator.cell("Benchmarks", "B7"), 20)
        self.assertEqual(evaluator.cell("Benchmarks", "B8"), 50)
        self.assertIn("high hook / weak hold", verdict(evaluator))
        self.assertEqual(verdict(evaluator, row=7), "hold OK or hook first")

    def test_changing_only_two_second_views_cannot_change_weak_hold(self):
        for value in (100, 400, 900):
            with self.subTest(two_second_views=value):
                self.assertIn("high hook / weak hold", verdict(sheet_evaluator(cohort(value))))

    def test_hook_equality_at_eighty_percent_is_included(self):
        self.assertIn("high hook / weak hold", verdict(direct(hook3=16)))

    def test_hook_below_eighty_percent_keeps_hook_first(self):
        self.assertEqual(verdict(direct(hook3=15.999)), "hold OK or hook first")

    def test_hold_equality_at_eighty_percent_is_not_weak(self):
        self.assertEqual(verdict(direct(hold=40)), "hold OK or hook first")

    def test_hold_just_below_eighty_percent_is_weak(self):
        self.assertIn("high hook / weak hold", verdict(direct(hold=39.999)))

    def test_missing_three_second_benchmark_cannot_be_replaced_with_two_second_data(self):
        for missing in ("", "n/a", "invalid", Error()):
            with self.subTest(missing=type(missing).__name__):
                self.assertEqual(verdict(direct(bench2=10, bench3=missing)), "insufficient data")

    def test_all_four_weak_hold_inputs_require_actual_numbers(self):
        for field in ("hook3", "hold", "bench3", "bench_hold"):
            for value in ("", "20", "n/a (25% before 3s)", True, Error()):
                with self.subTest(field=field, value=type(value).__name__):
                    self.assertEqual(verdict(direct(**{field: value})), "insufficient data")

    def test_short_duration_hold_is_insufficient_not_healthy(self):
        rows = cohort()
        rows[0]["duration_s"] = 6
        self.assertEqual(verdict(sheet_evaluator(rows)), "insufficient data")

    def test_missing_counts_remain_insufficient(self):
        rows = cohort()
        del rows[0]["views_3s"]
        self.assertEqual(verdict(sheet_evaluator(rows)), "insufficient data")

    def test_low_hook_still_uses_two_second_benchmark(self):
        self.assertIn("LOW 2s retention", verdict(direct(hook2=10, bench2=40, bench3=1), "low_hook"))
        self.assertEqual(verdict(direct(hook2=32, bench2=40, bench3=100), "low_hook"), "hook OK")

    def test_measured_zero_is_numeric_and_not_missing(self):
        self.assertIn("LOW 2s retention", verdict(direct(hook2=0), "low_hook"))
        self.assertEqual(verdict(direct(hook2=0, bench2=0), "low_hook"), "hook OK")

    def test_low_hook_non_numeric_input_or_benchmark_is_insufficient(self):
        for field in ("hook2", "bench2"):
            for value in ("", "40", "n/a", Error(), False):
                with self.subTest(field=field, value=type(value).__name__):
                    self.assertEqual(verdict(direct(**{field: value}), "low_hook"), "insufficient data")

    def test_shared_layout_mapping_drives_formula_references(self):
        text = formula["hypothesis_formula"]("weak_hold", 23)
        for metric in ("hook_rate_3s_impr", "hold_25_over_3s"):
            benchmark_row = formula["FIRST_DATA_ROW"] + next(
                i for i, (_, mid) in enumerate(formula["BENCHMARK_ROWS"]) if mid == metric)
            self.assertIn(f"Benchmarks!B${benchmark_row}", text)
            self.assertIn(f'Metrics!{formula["METRIC_COL"][metric]}23', text)
        self.assertNotIn("Benchmarks!B$6", text)

    def test_unknown_rule_still_raises(self):
        with self.assertRaisesRegex(ValueError, "unknown rule"):
            formula["hypothesis_formula"]("missing-rule", 6)

    def test_evaluator_number_predicate_excludes_text_booleans_and_errors(self):
        evaluator = direct()
        cases = ((0, True), (1.5, True), ("1", False), ("", False), (True, False), (Error(), False))
        for value, expected in cases:
            self.assertEqual(evaluator._call("ISNUMBER", [value]), expected)


class WorkbookHoldPopulationQualityTests(unittest.TestCase):
    @staticmethod
    def row(duration=20, numerator=50, denominator=100):
        return {"duration_s": duration, "views_25": numerator, "views_3s": denominator}

    def summaries(self, rows):
        evaluator = sheet_evaluator(rows)
        formulas = formula["_benchmark_formulas"]("hold_25_over_3s", "D")
        return tuple(evaluator.eval(item, "Benchmarks") for item in formulas)

    def test_known_short_video_is_excluded_from_both_pooled_sums(self):
        rows = [self.row(), self.row(duration=6, numerator=90)]
        evaluator = sheet_evaluator(rows)
        self.assertEqual(evaluator.cell("Metrics", "D6"), 50)
        self.assertEqual(evaluator.cell("Metrics", "D7"), "n/a (25% before 3s)")
        self.assertEqual(self.summaries(rows), (50, 50, 50, 1))

    def test_large_short_population_does_not_dilute_a_compatible_row(self):
        self.assertEqual(self.summaries([self.row(), self.row(6, 900, 1000)]), (50, 50, 50, 1))

    def test_all_short_rows_have_no_pooled_hold_or_numeric_population(self):
        evaluator = sheet_evaluator([self.row(6), self.row(11.999)])
        pooled, _, _, count = formula["_benchmark_formulas"]("hold_25_over_3s", "D")
        self.assertEqual(evaluator.eval(pooled, "Benchmarks"), "n/a")
        self.assertEqual(evaluator.eval(count, "Benchmarks"), 0)

    def test_twelve_second_boundary_is_included_but_lower_duration_is_not(self):
        self.assertEqual(self.summaries([self.row(12), self.row(11.999, 90)]), (50, 50, 50, 1))

    def test_blank_duration_preserves_current_individual_eligibility(self):
        for blank_row in ({"views_25": 90, "views_3s": 100}, self.row("", 90)):
            with self.subTest(explicit_blank="duration_s" in blank_row):
                summaries = self.summaries([self.row(), blank_row, self.row(6, 10)])
                self.assertEqual(summaries, (70, 70, 70, 2))

    def test_zero_duration_remains_known_short_not_unknown(self):
        self.assertEqual(self.summaries([self.row(), self.row(0, 90)]), (50, 50, 50, 1))

    def test_reported_zero_numerator_remains_a_real_observation(self):
        rows = [self.row(numerator=0), self.row(), self.row(6, 90)]
        self.assertEqual(self.summaries(rows), (25, 25, 25, 2))

    def test_missing_numerator_or_denominator_is_excluded_in_both_sums(self):
        for missing in ("views_25", "views_3s"):
            row = self.row(numerator=90)
            del row[missing]
            with self.subTest(missing=missing):
                self.assertEqual(self.summaries([self.row(), row]), (50, 50, 50, 1))

    def test_zero_denominator_does_not_add_unavailable_numerator_to_the_pool(self):
        self.assertEqual(self.summaries([self.row(), self.row(numerator=90, denominator=0)]), (50, 50, 50, 1))

    def test_pool_remains_exposure_weighted_not_mean_of_individual_rates(self):
        pooled, mean, median, count = self.summaries([
            self.row(numerator=50, denominator=100), self.row(numerator=150, denominator=1000),
            self.row(6, 900, 1000),
        ])
        self.assertAlmostEqual(pooled, 200 / 1100 * 100)
        self.assertEqual((mean, median, count), (32.5, 32.5, 2))

    def test_no_rows_remains_unavailable_with_zero_count(self):
        evaluator = sheet_evaluator([])
        pooled, _, _, count = formula["_benchmark_formulas"]("hold_25_over_3s", "D")
        self.assertEqual(evaluator.eval(pooled, "Benchmarks"), "n/a")
        self.assertEqual(evaluator.eval(count, "Benchmarks"), 0)

    def test_literal_exclusion_criteria_preserve_zeroes_and_ignore_case(self):
        self.assertFalse(Evaluator._match_crit("<>n/a", "N/A"))
        self.assertFalse(Evaluator._match_crit("<>n/a (25% before 3s)", "n/a (25% before 3s)"))
        self.assertTrue(Evaluator._match_crit("<>n/a", 0))
        self.assertTrue(Evaluator._match_crit("<>", 0))
