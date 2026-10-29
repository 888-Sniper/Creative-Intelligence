"""Isolated canonical-row ratio tests; no mixed application fixture imports."""

import importlib.util
import json
import unittest
from pathlib import Path

MODULE_PATH = (Path(__file__).resolve().parents[1]
               / "Backend" / "creative_intel" / "metric_availability.py")
SPEC = importlib.util.spec_from_file_location("metric_availability_quality", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
availability = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(availability)


class MetricAvailabilityQualityTests(unittest.TestCase):
    def test_common_components_preserve_the_unrounded_matched_population(self):
        rows = [{"spend": 10.125, "clicks": 3, "impressions": 120, "conversions": 1},
                {"spend": 900, "clicks": 0, "impressions": 9000, "conversions": 0,
                 "missing_json": '["clicks", "conversions"]'}]
        ratios, coverage, components = availability.reported_common_kpi_details(rows)
        self.assertEqual(ratios["cpc"], 3.38)
        self.assertEqual(components["cpc"], {
            "numerator": 10.125, "denominator": 3, "reporting_rows": 1, "total_rows": 2,
        })
        self.assertEqual(components["ctr"]["denominator"], 120)
        self.assertEqual(coverage["ctr"], {"reporting_rows": 1, "total_rows": 2})
        self.assertEqual(availability.reported_common_kpis(rows), (ratios, coverage))

    def test_empty_components_retain_zero_row_counts_without_inventing_values(self):
        ratios, coverage, components = availability.reported_common_kpi_details([])
        self.assertTrue(all(value is None for value in ratios.values()))
        self.assertEqual(components["cpa"], {
            "numerator": 0, "denominator": 0, "reporting_rows": 0, "total_rows": 0,
        })
        self.assertEqual(coverage["cpa"], {"reporting_rows": 0, "total_rows": 0})

    def test_roas_components_exclude_nonreporting_spend(self):
        value, coverage, component = availability.reported_roas_details([
            {"spend": 100, "revenue": 200, "revenue_reported": True},
            {"spend": 900, "revenue": 0, "revenue_reported": False},
        ])
        self.assertEqual(value, 2)
        self.assertEqual(coverage, 0.1)
        self.assertEqual(component, {
            "numerator": 200, "denominator": 100, "reporting_rows": 1,
            "total_rows": 2, "total_spend": 1000,
        })

    def test_roas_components_preserve_the_revenue_reported_flag_contract(self):
        value, coverage, component = availability.reported_roas_details([
            {"spend": 100, "revenue": 200, "missing_json": "[]"},
        ])
        self.assertIsNone(value)
        self.assertEqual(coverage, 0)
        self.assertEqual(component["reporting_rows"], 0)
        self.assertEqual(component["numerator"], 0)

    def test_roas_reported_zero_is_measured(self):
        value, coverage, component = availability.reported_roas_details([
            {"spend": 100, "revenue": 0, "revenue_reported": True},
        ])
        self.assertEqual(value, 0)
        self.assertEqual(coverage, 1)
        self.assertEqual(component["denominator"], 100)
        self.assertEqual(component["reporting_rows"], 1)

    def test_roas_zero_or_negative_reporting_spend_stays_unavailable(self):
        for spend in (0, -100):
            with self.subTest(spend=spend):
                value, coverage, component = availability.reported_roas_details([
                    {"spend": spend, "revenue": 200, "revenue_reported": True},
                ])
                self.assertIsNone(value)
                self.assertIsNone(coverage)
                self.assertEqual(component["denominator"], spend)

    def test_roas_empty_scope_retains_undefined_spend_coverage(self):
        value, coverage, component = availability.reported_roas_details([])
        self.assertIsNone(value)
        self.assertIsNone(coverage)
        self.assertEqual(component, {
            "numerator": 0, "denominator": 0, "reporting_rows": 0,
            "total_rows": 0, "total_spend": 0,
        })

    def test_roas_components_do_not_reconstruct_rounded_revenue(self):
        rows = [{"spend": 3, "revenue": 1, "revenue_reported": True}]
        before = json.dumps(rows, sort_keys=True)
        value, coverage, component = availability.reported_roas_details(rows)
        self.assertEqual(value, 0.3333)
        self.assertEqual(coverage, 1)
        self.assertEqual(component["numerator"], 1)
        self.assertEqual(component["denominator"], 3)
        self.assertEqual(json.dumps(rows, sort_keys=True), before)

    def test_raw_totals_keep_all_unreported_fields_unavailable(self):
        fields = ("spend", "impressions", "clicks", "conversions", "video_views", "revenue")
        row = {field: 0 for field in fields}
        row["missing_json"] = json.dumps(fields)
        self.assertEqual(availability.reported_raw_totals([row]),
                         {"n_ads": 1, **{field: None for field in fields}})

    def test_raw_totals_preserve_supplied_zero_for_every_field(self):
        fields = ("spend", "impressions", "clicks", "conversions", "video_views", "revenue")
        row = {field: 0 for field in fields}
        row["missing_json"] = "[]"
        self.assertEqual(availability.reported_raw_totals([row]),
                         {"n_ads": 1, **{field: 0 for field in fields}})

    def test_partial_raw_totals_sum_only_reporting_rows(self):
        got = availability.reported_raw_totals([
            {"spend": 12.5, "revenue": 0, "missing_json": '["revenue"]'},
            {"spend": 50, "revenue": 20, "missing_json": '["spend"]'},
        ])
        self.assertEqual(got["spend"], 12.5)
        self.assertEqual(got["revenue"], 20)
        self.assertEqual(got["n_ads"], 2)

    def test_empty_raw_totals_are_unavailable_with_zero_rows(self):
        got = availability.reported_raw_totals([])
        self.assertEqual(got["n_ads"], 0)
        self.assertTrue(all(value is None for field, value in got.items() if field != "n_ads"))

    def test_legacy_raw_totals_keep_missing_keys_as_measured_zero(self):
        got = availability.reported_raw_totals([{"spend": 3}])
        self.assertEqual(got["spend"], 3)
        self.assertEqual(got["revenue"], 0)
        self.assertEqual(got["video_views"], 0)

    def test_raw_totals_accept_iterators_without_mutating_rows(self):
        rows = [{"spend": 12, "missing_json": '["revenue"]'}, {"spend": 5}]
        original = json.dumps(rows, sort_keys=True)
        got = availability.reported_raw_totals(iter(rows))
        self.assertEqual(got["spend"], 17)
        self.assertEqual(got["revenue"], 0)
        self.assertEqual(got["n_ads"], 2)
        self.assertEqual(json.dumps(rows, sort_keys=True), original)

    def test_unsupplied_clicks_are_unavailable_not_measured_zero(self):
        value, coverage = availability.pooled_reported_ratio([
            {"clicks": 0, "impressions": 100, "missing_json": '["clicks"]'},
        ], "clicks", "impressions")
        self.assertIsNone(value)
        self.assertEqual(coverage, {"reporting_rows": 0, "total_rows": 1})

    def test_reported_zero_clicks_remain_measured(self):
        value, coverage = availability.pooled_reported_ratio([
            {"clicks": 0, "impressions": 100, "missing_json": "[]"},
        ], "clicks", "impressions")
        self.assertEqual(value, 0)
        self.assertEqual(coverage, {"reporting_rows": 1, "total_rows": 1})

    def test_unsupplied_spend_does_not_become_zero_cost(self):
        for denominator in ("clicks", "impressions", "conversions"):
            with self.subTest(denominator=denominator):
                value, coverage = availability.pooled_reported_ratio([
                    {"spend": 0, denominator: 100, "missing_json": '["spend"]'},
                ], "spend", denominator)
                self.assertIsNone(value)
                self.assertEqual(coverage["reporting_rows"], 0)

    def test_partial_clicks_use_only_the_matched_impression_population(self):
        value, coverage = availability.pooled_reported_ratio([
            {"clicks": 10, "impressions": 100, "missing_json": "[]"},
            {"clicks": 0, "impressions": 900, "missing_json": '["clicks"]'},
        ], "clicks", "impressions")
        self.assertEqual(value, 0.1)
        self.assertEqual(coverage, {"reporting_rows": 1, "total_rows": 2})

    def test_missing_denominator_also_excludes_the_rows_numerator(self):
        value, coverage = availability.pooled_reported_ratio([
            {"spend": 10, "clicks": 5, "missing_json": "[]"},
            {"spend": 100, "clicks": 0, "missing_json": '["clicks"]'},
        ], "spend", "clicks")
        self.assertEqual(value, 2)
        self.assertEqual(coverage, {"reporting_rows": 1, "total_rows": 2})

    def test_disjoint_reporting_populations_do_not_form_a_ratio(self):
        value, coverage = availability.pooled_reported_ratio([
            {"clicks": 10, "impressions": 0, "missing_json": '["impressions"]'},
            {"clicks": 0, "impressions": 100, "missing_json": '["clicks"]'},
        ], "clicks", "impressions")
        self.assertIsNone(value)
        self.assertEqual(coverage, {"reporting_rows": 0, "total_rows": 2})

    def test_measured_zero_denominator_is_unavailable_with_reported_coverage(self):
        value, coverage = availability.pooled_reported_ratio([
            {"spend": 10, "clicks": 0, "missing_json": "[]"},
        ], "spend", "clicks")
        self.assertIsNone(value)
        self.assertEqual(coverage, {"reporting_rows": 1, "total_rows": 1})

    def test_legacy_rows_retain_their_documented_zero_interpretation(self):
        for marker in (None, ""):
            with self.subTest(marker=marker):
                value, coverage = availability.pooled_reported_ratio([
                    {"impressions": 100, "missing_json": marker},
                ], "clicks", "impressions")
                self.assertEqual(value, 0)
                self.assertEqual(coverage["reporting_rows"], 1)

    def test_scaling_and_duplicate_rows_preserve_population_weight(self):
        row = {"spend": 2, "impressions": 500, "missing_json": "[]"}
        value, coverage = availability.pooled_reported_ratio([row, dict(row)], "spend", "impressions", 1000)
        self.assertEqual(value, 4)
        self.assertEqual(coverage, {"reporting_rows": 2, "total_rows": 2})

    def test_inputs_are_unchanged_and_row_order_does_not_affect_the_result(self):
        rows = [{"spend": 4, "clicks": 2, "missing_json": "[]"},
                {"spend": 3, "clicks": 1, "missing_json": '["spend"]'}]
        original = json.dumps(rows, sort_keys=True)
        expected = availability.pooled_reported_ratio(rows, "spend", "clicks")
        self.assertEqual(
            availability.pooled_reported_ratio(list(reversed(rows)), "spend", "clicks"), expected,
        )
        self.assertEqual(json.dumps(rows, sort_keys=True), original)

    def test_no_rows_have_no_ratio_and_zero_coverage(self):
        self.assertEqual(availability.pooled_reported_ratio([], "clicks", "impressions"),
                         (None, {"reporting_rows": 0, "total_rows": 0}))

    def test_common_kpis_keep_the_existing_fraction_units_and_rounding(self):
        ratios, coverage = availability.reported_common_kpis([
            {"spend": 10, "clicks": 3, "impressions": 120, "conversions": 1},
        ])
        self.assertEqual(ratios, {"ctr": 0.025, "cpc": 3.33, "cpm": 83.33, "cpa": 10})
        self.assertEqual(coverage, {key: {"reporting_rows": 1, "total_rows": 1} for key in ratios})

    def test_common_cost_ratios_are_unavailable_when_spend_was_not_supplied(self):
        ratios, coverage = availability.reported_common_kpis([
            {"spend": 0, "clicks": 10, "impressions": 100, "conversions": 2,
             "missing_json": '["spend"]'},
        ])
        self.assertEqual(ratios, {"ctr": 0.1, "cpc": None, "cpm": None, "cpa": None})
        self.assertEqual(coverage["ctr"], {"reporting_rows": 1, "total_rows": 1})
        for key in ("cpc", "cpm", "cpa"):
            self.assertEqual(coverage[key], {"reporting_rows": 0, "total_rows": 1})

    def test_common_ratios_on_an_empty_scope_are_unavailable(self):
        ratios, coverage = availability.reported_common_kpis([])
        self.assertEqual(ratios, {"ctr": None, "cpc": None, "cpm": None, "cpa": None})
        self.assertEqual(coverage, {key: {"reporting_rows": 0, "total_rows": 0} for key in ratios})


if __name__ == "__main__":
    unittest.main(verbosity=2)
