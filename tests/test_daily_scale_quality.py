"""Synthetic daily producer/diagnostic checks without campaign/app execution."""

import ast
import copy
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "Backend" / "creative_intel"
NAMESPACE = "quality_daily_scale"
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

FUNCTIONS = {"_measured", "_finding", "confidence_for", "_base", "_series_points",
             "rule_fatigue", "rule_scale_deterioration"}
CONSTANTS = {"MIN_COHORT_N", "PREFERRED_COHORT_N", "MIN_IMPRESSIONS", "MARGIN"}
diagnostic_path = ROOT / "analyst_diagnostics.py"
selected = []
for node in ast.parse(diagnostic_path.read_text()).body:
    if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
        assert not node.decorator_list
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                ast.literal_eval(default)
        selected.append(node)
    elif isinstance(node, ast.Assign) and len(node.targets) == 1:
        if isinstance(node.targets[0], ast.Name) and node.targets[0].id in CONSTANTS:
            ast.literal_eval(node.value)
            selected.append(node)
assert len(selected) == len(FUNCTIONS | CONSTANTS)
policy = {"metrics": metrics}
exec(compile(ast.Module(body=selected, type_ignores=[]), str(diagnostic_path), "exec"), policy)

producer_path = ROOT / "analyst.py"
selected = [n for n in ast.parse(producer_path.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name == "_series_for"]
assert len(selected) == 1 and not selected[0].decorator_list and not selected[0].args.defaults
producer = {"metrics": metrics}
exec(compile(ast.Module(body=selected, type_ignores=[]), str(producer_path), "exec"), producer)


def rows(*, currency="USD", vtr_falls=False, conversions=1):
    return [{"date": f"2026-01-0{i + 1}", "currency": currency,
             "spend": spend, "revenue": 0, "conversions": conversions,
             "impressions": 1000, "views_100": (300, 200, 100)[i] if vtr_falls else 300,
             "frequency": 1 + i * 0.5, "reach": 1000, "missing_json": "[]"}
            for i, spend in enumerate((10, 20, 30))]


def context(series):
    return {"creative_key": "synthetic", "series": series, "metrics": {
        "cpa": {"value": 20, "state": "measured"},
        "vtr": {"value": 20, "state": "measured"},
        "frequency": {"value": 2, "state": "measured"}},
        "annotation_status": "human_verified", "cohort_n": 6, "exposure": 10000,
        "scope": {"campaign": "synthetic"}, "dataset_version": "synthetic"}


def series(observations):
    return producer["_series_for"](observations)


def scale(observations):
    return policy["rule_scale_deterioration"](context(series(observations)))


class DailyScaleQualityTests(unittest.TestCase):
    def test_same_currency_cpa_deterioration_still_fires_with_explicit_units(self):
        finding = scale(rows())
        self.assertIsNotNone(finding)
        self.assertEqual(finding["finding_id"], "scale_deterioration")
        self.assertEqual(finding["polarity"], "concern")
        self.assertEqual(finding["observed_values"]["currency"], "USD")
        self.assertIn("USD", finding["primary_signal"])
        self.assertIn("CPA", finding["primary_signal"])

    def test_same_currency_vtr_branch_still_works_without_measured_cpa(self):
        finding = scale(rows(vtr_falls=True, conversions=0))
        self.assertIsNotNone(finding)
        self.assertIn("VTR", finding["primary_signal"])
        self.assertEqual(finding["observed_values"]["currency"], "USD")

    def test_different_endpoint_currencies_do_not_invent_scale_deterioration(self):
        for vtr_branch in (False, True):
            data = rows(vtr_falls=vtr_branch, conversions=0 if vtr_branch else 1)
            data[-1]["currency"] = "EUR"
            with self.subTest(vtr_branch=vtr_branch):
                self.assertIsNone(scale(data))

    def test_mixed_last_day_has_no_comparable_spend(self):
        data = rows(vtr_falls=True, conversions=0)
        data.append({**data[-1], "currency": "EUR", "spend": 50})
        last = series(data)[-1]
        self.assertIsNone(last["spend"])
        self.assertTrue(last["mixed_currency"])
        self.assertFalse(last["currency_known"])
        self.assertIsNone(scale(data))

    def test_mixed_first_day_cannot_be_a_monetary_baseline(self):
        data = rows(vtr_falls=True, conversions=0)
        data.append({**data[0], "currency": "EUR", "spend": 1})
        self.assertIsNone(series(data)[0]["spend"])
        self.assertIsNone(scale(data))

    def test_unknown_endpoint_amount_does_not_acquire_the_other_day_currency(self):
        data = rows()
        data[-1]["currency"] = ""
        self.assertIsNone(series(data)[-1]["spend"])
        self.assertIsNone(scale(data))

    def test_all_unspecified_currencies_do_not_establish_comparable_units(self):
        data = rows(currency="")
        self.assertTrue(all(point["spend"] is None for point in series(data)))
        self.assertIsNone(scale(data))

    def test_partial_daily_spend_is_not_treated_as_complete_daily_spend(self):
        data = rows(vtr_falls=True, conversions=0)
        data.append({**data[0], "spend": 0, "missing_json": json.dumps(["spend"])})
        first = series(data)[0]
        self.assertIsNone(first["spend"])
        self.assertEqual(first["spend_state"], metrics.MISSING)
        self.assertIsNone(scale(data))

    def test_all_missing_spend_is_not_a_measured_zero_baseline(self):
        data = rows(vtr_falls=True, conversions=0)
        data[0].update(spend=0, missing_json=json.dumps(["spend"]))
        first = series(data)[0]
        self.assertIsNone(first["spend"])
        self.assertEqual(first["spend_state"], metrics.UNSUPPORTED)
        self.assertIsNone(scale(data))

    def test_measured_zero_spend_is_preserved(self):
        data = rows()
        data[0]["spend"] = 0
        first = series(data)[0]
        self.assertEqual(first["spend"], 0)
        self.assertEqual(first["spend_state"], metrics.MEASURED)
        self.assertTrue(first["currency_known"])

    def test_zero_unknown_contribution_retains_known_scope_policy(self):
        data = rows()
        data.append({**data[0], "currency": "", "spend": 0, "revenue": 0})
        first = series(data)[0]
        self.assertEqual(first["spend"], 10)
        self.assertEqual(first["currency"], "USD")
        self.assertTrue(first["currency_known"])

    def test_currency_codes_use_existing_case_and_space_normalization(self):
        data = rows(currency=" usd ")
        data[-1]["currency"] = "USD"
        self.assertTrue(all(point["currency"] == "USD" for point in series(data)))
        self.assertIsNotNone(scale(data))

    def test_legacy_points_without_money_metadata_abstain_but_keep_fatigue(self):
        points = series(rows(vtr_falls=True))
        for point in points:
            for key in ("currency", "currencies", "currency_known", "mixed_currency",
                        "unknown_currency_contribution", "spend_state"):
                point.pop(key, None)
        ctx = context(points)
        self.assertIsNone(policy["rule_scale_deterioration"](ctx))
        self.assertEqual(policy["rule_fatigue"](ctx)["finding_id"], "fatigue")

    def test_mixed_money_does_not_hide_dimensionless_fatigue(self):
        data = rows(vtr_falls=True, conversions=0)
        data[-1]["currency"] = "EUR"
        ctx = context(series(data))
        self.assertIsNone(policy["rule_scale_deterioration"](ctx))
        self.assertEqual(policy["rule_fatigue"](ctx)["finding_id"], "fatigue")

    def test_missing_or_inconsistent_endpoint_metadata_never_authorizes_money(self):
        for field, value in (("currency_known", False), ("mixed_currency", True),
                             ("unknown_currency_contribution", True), ("currency", None),
                             ("spend_state", metrics.MISSING), ("spend", None)):
            points = series(rows())
            points[-1][field] = value
            with self.subTest(field=field):
                self.assertIsNone(policy["rule_scale_deterioration"](context(points)))

    def test_fewer_than_three_dates_do_not_create_a_scale_finding(self):
        self.assertIsNone(scale(rows()[:2]))

    def test_existing_spend_threshold_is_not_relaxed(self):
        data = rows(vtr_falls=True, conversions=0)
        data[-1]["spend"] = 10
        self.assertIsNone(scale(data))

    def test_date_order_undated_exclusion_and_input_preservation(self):
        data = list(reversed(rows()))
        data.append({**data[0], "date": "", "currency": "EUR", "spend": 500})
        original = copy.deepcopy(data)
        self.assertEqual([point["date"] for point in series(data)],
                         ["2026-01-01", "2026-01-02", "2026-01-03"])
        self.assertEqual(data, original)


if __name__ == "__main__":
    unittest.main()
