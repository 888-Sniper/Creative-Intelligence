"""Pure diagnostic producer/summary checks; no application imports or APIs.

The explicitly named functions and literal policy data are compiled unchanged
from permitted source. The real metric helpers load in a private namespace.
"""

import ast
import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "Backend" / "creative_intel"
NAMESPACE = "quality_diagnostic_polarity"
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

FUNCTIONS = {
    "_measured", "classify", "_finding", "confidence_for", "_ctx_value", "_band",
    "_base", "_observed", "_benchmarks", "_spec_applies", "evaluate_spec",
    "rule_hook_hold_combo", "rule_quartile_completion_combo", "rule_cost_combo",
    "_series_points", "rule_fatigue", "rule_scale_deterioration", "rule_brand_recall_gap",
    "_first_span", "_slot_boundaries", "rule_drop_near_product", "rule_drop_near_transition",
    "rule_remix_hook_hold", "_group_pooled", "rule_format_comparison", "rule_duration_roles",
    "five_layer_summary",
}
CONSTANTS = {"MIN_COHORT_N", "PREFERRED_COHORT_N", "MARGIN", "MIN_IMPRESSIONS", "RULE_SPECS", "LAYERS"}
source_path = ROOT / "analyst_diagnostics.py"
selected = []
for node in ast.parse(source_path.read_text()).body:
    if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS:
        assert not node.decorator_list
        for default in [*node.args.defaults, *node.args.kw_defaults]:
            if default is not None:
                if isinstance(default, ast.Name):
                    assert default.id in CONSTANTS
                else:
                    ast.literal_eval(default)
        selected.append(node)
    elif isinstance(node, ast.Assign) and len(node.targets) == 1:
        if isinstance(node.targets[0], ast.Name) and node.targets[0].id in CONSTANTS:
            ast.literal_eval(node.value)
            selected.append(node)
assert len(selected) == len(FUNCTIONS) + len(CONSTANTS)
policy = {"metrics": metrics}
exec(compile(ast.Module(body=selected, type_ignores=[]), str(source_path), "exec"), policy)


def context(values=None, **kwargs):
    values = values or {}
    ctx = {"creative_key": "synthetic", "annotation_status": "human_verified",
           "cohort_n": 6, "exposure": 10_000, "scope": {"campaign": "synthetic"},
           "dataset_version": "synthetic-version", "objective": "reach",
           "metrics": {key: {"value": value, "state": "measured", "basis": "synthetic"}
                       for key, value in values.items()},
           "cohort": {key: [10] * 6 for key in values}}
    ctx.update(kwargs)
    return ctx


def series(first_vtr=30, last_vtr=30):
    return [{"date": f"2026-01-0{index + 1}", "frequency": {"value": frequency},
             "vtr": {"value": vtr}, "spend": spend,
             "spend_state": "measured", "currency": "USD", "currencies": ["USD"],
             "currency_known": True, "mixed_currency": False, "unknown_currency_contribution": False,
             "cpa": {"value": cpa, "state": "measured"}}
            for index, (frequency, vtr, spend, cpa) in enumerate([
                (1, first_vtr, 10, 10), (1.5, 30, 20, 15), (2, last_vtr, 30, 20)])]


def summary(ctx, findings, layer):
    return next(item for item in policy["five_layer_summary"](ctx, findings) if item["layer"] == layer)


class DiagnosticPolarityQualityTests(unittest.TestCase):
    def assert_positive(self, function, ctx, expected_id, layer):
        finding = policy[function](ctx)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["finding_id"], expected_id)
        self.assertIn(finding["confidence_level"], ("high", "medium"))
        self.assertEqual(finding.get("polarity"), "strength")
        self.assertEqual(summary(ctx, [finding], layer)["status"], "strength")

    def test_positive_hook_and_hold_is_a_strength(self):
        self.assert_positive("rule_hook_hold_combo", context({"hook_rate_2s_impr": 30, "hold_rate": 30}),
                             "hook_hold_high_high", "hold")

    def test_positive_quartiles_are_a_strength(self):
        self.assert_positive("rule_quartile_completion_combo",
                             context({"quartile_25_impr": 30, "completion_impr": 30}),
                             "q25_completion_high_high", "depth")

    def test_low_costs_are_a_strength(self):
        self.assert_positive("rule_cost_combo", context({"cpm": 2, "cpcv": 2}), "cost_low_low", "efficiency")

    def test_resilience_is_a_strength_without_a_key_metric_band(self):
        self.assert_positive("rule_fatigue", context({"frequency": 2, "vtr": 30}, series=series()),
                             "fatigue_resilient", "efficiency")

    def test_medium_confidence_positive_finding_does_not_become_concern(self):
        self.assert_positive("rule_hook_hold_combo",
                             context({"hook_rate_2s_impr": 30, "hold_rate": 30}, annotation_status="auto"),
                             "hook_hold_high_high", "hold")

    def test_adverse_findings_still_create_concern(self):
        ctx = context({"cpm": 30, "cpcv": 30})
        finding = policy["rule_cost_combo"](ctx)
        self.assertEqual(finding.get("polarity"), "concern")
        self.assertEqual(summary(ctx, [finding], "efficiency")["status"], "concern")

    def test_supported_positive_and_adverse_evidence_is_mixed(self):
        ctx = context({"cpm": 30, "cpcv": 30, "frequency": 2, "vtr": 30}, series=series())
        findings = [policy["rule_cost_combo"](ctx), policy["rule_fatigue"](ctx)]
        self.assertEqual(summary(ctx, findings, "efficiency")["status"], "mixed")

    def test_adverse_finding_and_favourable_key_metric_is_mixed(self):
        ctx = context({"cpm": 2, "cpcv": 30})
        self.assertEqual(summary(ctx, [policy["rule_cost_combo"](ctx)], "efficiency")["status"], "mixed")

    def test_priority_does_not_supply_polarity(self):
        ctx = context({"hook_rate_2s_impr": 30, "hold_rate": 30})
        positive = policy["rule_hook_hold_combo"](ctx)
        positive["priority"] = "high"
        self.assertEqual(summary({}, [positive], "hold")["status"], "strength")
        negative = {**positive, "polarity": "concern", "priority": "low"}
        self.assertEqual(summary({}, [negative], "hold")["status"], "concern")

    def test_low_confidence_and_exploratory_findings_do_not_force_a_verdict(self):
        for confidence in ("low", "exploratory"):
            for polarity in ("strength", "concern"):
                finding = {"finding_id": "synthetic", "layer": "hold", "confidence_level": confidence,
                           "polarity": polarity}
                self.assertEqual(summary({}, [finding], "hold")["status"], "mixed")

    def test_unknown_or_missing_polarity_does_not_become_adversity(self):
        for polarity in (None, "future-kind", "context"):
            finding = {"finding_id": "synthetic", "layer": "hold", "confidence_level": "high"}
            if polarity is not None:
                finding["polarity"] = polarity
            self.assertEqual(summary({}, [finding], "hold")["status"], "mixed")

    def test_metric_strength_without_findings_is_preserved(self):
        self.assertEqual(summary(context({"hold_rate": 30}), [], "hold")["status"], "strength")

    def test_no_data_is_still_unknown(self):
        self.assertTrue(all(item["status"] == "unknown" for item in policy["five_layer_summary"]({}, [])))

    def test_cost_direction_and_neutral_frequency_are_preserved(self):
        ctx = {"metrics": {key: {"value": value, "state": "measured"}
                           for key, value in {"cpm": 99, "cpcv": 9, "frequency": 8}.items()},
               "cohort": {"cpm": [1, 2, 3], "cpcv": [0.1, 0.2, 0.3], "frequency": [1, 1.5, 2]}}
        self.assertNotEqual(summary(ctx, [], "efficiency")["status"], "strength")

    def test_layer_shape_finding_order_and_scope_are_unchanged(self):
        findings = [{"finding_id": "a", "layer": "hold", "confidence_level": "high", "polarity": "strength"},
                    {"finding_id": "b", "layer": "hold", "confidence_level": "high", "polarity": "concern"}]
        layers = policy["five_layer_summary"]({}, findings)
        self.assertEqual([item["layer"] for item in layers], ["stop", "hold", "depth", "brand", "efficiency"])
        hold = next(item for item in layers if item["layer"] == "hold")
        self.assertEqual(set(hold), {"layer", "question", "status", "metric_bands", "finding_ids"})
        self.assertEqual(hold["finding_ids"], ["a", "b"])
        self.assertEqual(summary({}, findings, "stop")["status"], "unknown")

    def test_every_catalogue_spec_has_a_supported_explicit_polarity(self):
        contextual = {"narrow_appeal", "length_completion", "short_completion", "broad_unproven",
                      "watched_not_felt", "promising_undertested"}
        for spec in policy["RULE_SPECS"]:
            expected = "context" if spec["id"] in contextual else "concern"
            values = {}
            for metric, bands in spec["bands"].items():
                higher = spec.get("higher", {}).get(metric, True)
                values[metric] = 10 if bands[0] == "average" else 30 if (bands[0] == "high") == higher else 2
            ctx = context(values, objective=spec["objectives"][0], spend=10, cohort_spend=[100] * 6)
            finding = policy["evaluate_spec"](ctx, spec)
            self.assertIsNotNone(finding, spec["id"])
            self.assertEqual(spec.get("polarity"), expected, spec["id"])
            self.assertEqual(finding.get("polarity"), expected, spec["id"])

    def test_contextual_duration_tradeoff_does_not_force_concern(self):
        spec = next(item for item in policy["RULE_SPECS"] if item["id"] == "length_completion")
        ctx = context({"completion_impr": 2, "awt_per_view": 30})
        finding = policy["evaluate_spec"](ctx, spec)
        self.assertEqual(finding.get("polarity"), "context")
        self.assertNotEqual(summary(ctx, [finding], "depth")["status"], "concern")

    def test_all_four_way_producers_label_adverse_and_positive_branches(self):
        combinations = [
            ("rule_hook_hold_combo", ["hook_rate_2s_impr", "hold_rate"], False),
            ("rule_quartile_completion_combo", ["quartile_25_impr", "completion_impr"], False),
            ("rule_cost_combo", ["cpm", "cpcv"], True),
        ]
        for name, keys, cost in combinations:
            for left in (2, 30):
                for right in (2, 30):
                    good = left == right == (2 if cost else 30)
                    finding = policy[name](context(dict(zip(keys, [left, right]))))
                    self.assertEqual(finding.get("polarity"), "strength" if good else "concern", name)

    def test_remaining_adverse_producers_label_their_findings(self):
        cases = [
            ("rule_fatigue", context({"frequency": 2, "vtr": 10}, series=series(last_vtr=10))),
            ("rule_scale_deterioration", context({"cpa": 20}, series=series())),
            ("rule_brand_recall_gap", context(
                {"quartile_50_impr": 30, "hook_rate_2s_impr": 30},
                annotation={"measured_recall": {"assessment": "weak", "study": "synthetic"}},
            )),
            ("rule_drop_near_product", context(annotation={"product_seconds": [{"start_s": 5}]},
                                               retention_drops=[{"start_s": 4, "end_s": 6, "drop_pts": 5}])),
            ("rule_drop_near_transition", context(
                annotation={"structure": {"body": {"start_s": 5, "end_s": 8}}},
                retention_drops=[{"start_s": 4, "end_s": 6, "drop_pts": 5}],
            )),
            ("rule_remix_hook_hold", context({"hook_rate_2s_impr": 30, "hold_rate": 2},
                                             annotation={"format_kind": "graphics_remix"})),
        ]
        for name, ctx in cases:
            finding = policy[name](ctx)
            self.assertIsNotNone(finding, name)
            self.assertEqual(finding.get("polarity"), "concern", name)

    def test_relative_format_and_duration_comparisons_are_context(self):
        formats = [{"creative_key": "a", "format_kind": "creator_led"},
                   {"creative_key": "b", "format_kind": "graphics_remix"}]
        rows = {"a": [{"views_2s": 10, "impressions": 100}], "b": [{"views_2s": 30, "impressions": 100}]}
        finding = policy["rule_format_comparison"](formats, rows, {}, "synthetic")[0]
        self.assertEqual(finding.get("polarity"), "context")
        timed = [
            {"creative_key": "long", "duration_s": 30,
             "metrics": {"awt_per_view": {"value": 20}, "completion_impr": {"value": 10}}},
            {"creative_key": "short", "duration_s": 10,
             "metrics": {"awt_per_view": {"value": 8}, "completion_impr": {"value": 30}}},
        ]
        self.assertEqual(policy["rule_duration_roles"](timed, {}, "synthetic").get("polarity"), "context")

    def test_unspecified_constructor_polarity_is_context(self):
        finding = policy["_finding"](
            rule_id="synthetic", layer="hold", creative_ids=["synthetic"], signal="signal",
            diagnosis="diagnosis", hypothesis="hypothesis", iteration="iteration", priority="high",
            confidence={"level": "high", "reasons": []}, observed={}, benchmarks={}, preserve="keep",
            change="test", alternatives=[], limits=[], metric_ids=[], scope={}, dataset_version="synthetic",
        )
        self.assertEqual(finding.get("polarity"), "context")


if __name__ == "__main__":
    unittest.main()
