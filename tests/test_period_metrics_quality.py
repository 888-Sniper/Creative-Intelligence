"""Synthetic period arithmetic without application, fixtures, storage or I/O."""

import importlib.util
import json
import unittest
from pathlib import Path

HELPERS = Path(__file__).resolve().parents[1] / "Backend" / "creative_intel"


def _load(name):
    spec = importlib.util.spec_from_file_location(f"period_quality_{name}", HELPERS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


availability = _load("metric_availability")
period = _load("period_metrics")
currency = _load("currency_scope")
RAW_FIELDS = ("spend", "impressions", "clicks", "conversions", "video_views", "revenue")


def _row(**overrides):
    return {
        "spend": 100, "impressions": 1000, "clicks": 100, "conversions": 10,
        "video_views": 200, "revenue": 300, "currency": "GBP", "missing_json": "[]",
        **overrides,
    }


def _pooled(rows):
    # Only the new pure aggregation helpers run here. ROAS/video aggregation,
    # storage selection and API integration are deliberately not simulated.
    ratios, coverage = availability.reported_common_kpis(rows)
    return {**ratios, **currency.money_scope(rows), "metric_coverage": coverage}


def _compare(current, previous):
    return period.compare_period_metrics(
        availability.reported_raw_totals(current), availability.reported_raw_totals(previous),
        _pooled(current), _pooled(previous),
    )


class PeriodCurrencyContextTests(unittest.TestCase):
    def test_matching_known_currency_is_exposed_for_both_periods(self):
        current, previous = _pooled([_row()]), _pooled([_row(spend=50)])
        context = period.period_currency_context(current, previous)
        self.assertEqual(context["current"], currency.money_scope([_row()]))
        self.assertEqual(context["previous"], currency.money_scope([_row(spend=50)]))
        self.assertTrue(context["same_known_currency"])

    def test_different_known_currencies_are_retained_without_conversion(self):
        context = period.period_currency_context(_pooled([_row(currency="GBP")]),
                                                 _pooled([_row(currency="EUR")]))
        self.assertEqual(context["current"]["currency"], "GBP")
        self.assertEqual(context["previous"]["currency"], "EUR")
        self.assertFalse(context["same_known_currency"])

    def test_two_unknown_periods_do_not_establish_a_known_currency(self):
        context = period.period_currency_context(
            _pooled([_row(currency=None)]), _pooled([_row(currency=None)]))
        self.assertIsNone(context["current"]["currency"])
        self.assertFalse(context["current"]["currency_known"])
        self.assertFalse(context["same_known_currency"])

    def test_mixed_period_metadata_stays_mixed(self):
        context = period.period_currency_context(_pooled([_row(currency="GBP"), _row(currency="EUR")]),
                                                 _pooled([_row(currency="GBP")]))
        self.assertIsNone(context["current"]["currency"])
        self.assertEqual(context["current"]["currencies"], ["EUR", "GBP"])
        self.assertTrue(context["current"]["mixed_currency"])
        self.assertFalse(context["same_known_currency"])

    def test_missing_metadata_is_not_filled_with_a_default_currency(self):
        context = period.period_currency_context({}, {})
        self.assertTrue(all(value is None for value in context["current"].values()))
        self.assertTrue(all(value is None for value in context["previous"].values()))
        self.assertFalse(context["same_known_currency"])

    def test_empty_side_does_not_hide_the_other_periods_known_currency(self):
        context = period.period_currency_context(_pooled([]), _pooled([_row(currency="EUR")]))
        self.assertFalse(context["current"]["currency_known"])
        self.assertEqual(context["current"]["currencies"], [])
        self.assertEqual(context["previous"]["currency"], "EUR")
        self.assertFalse(context["same_known_currency"])

    def test_currency_lists_are_copied_without_exporting_other_aggregate_data(self):
        pooled = _pooled([_row()])
        context = period.period_currency_context(pooled, pooled)
        self.assertNotIn("metric_coverage", context["current"])
        self.assertNotIn("cpa", context["current"])
        context["current"]["currencies"].append("EUR")
        self.assertEqual(pooled["currencies"], ["GBP"])
        self.assertEqual(context["previous"]["currencies"], ["GBP"])

    def test_inconsistent_metadata_does_not_establish_matching_known_units(self):
        pooled = _pooled([_row()])
        for change in ({"mixed_currency": True}, {"unknown_currency_contribution": True},
                       {"currency_known": None}, {"currencies": ["EUR"]}, {"currencies": []}):
            with self.subTest(change=change):
                context = period.period_currency_context({**pooled, **change}, pooled)
                self.assertFalse(context["same_known_currency"])

    def test_context_does_not_change_legacy_unknown_currency_arithmetic(self):
        current, previous = [_row(currency=None, spend=200)], [_row(currency=None, spend=100)]
        before = _compare(current, previous)
        context = period.period_currency_context(_pooled(current), _pooled(previous))
        self.assertFalse(context["same_known_currency"])
        self.assertEqual(_compare(current, previous), before)
        self.assertEqual(before["spend"]["state"], "compared")


class PeriodMetricsQualityTests(unittest.TestCase):
    def test_unreported_previous_raw_fields_never_become_new(self):
        for field in RAW_FIELDS:
            with self.subTest(field=field):
                got = _compare([_row()], [_row(**{field: 0, "missing_json": json.dumps([field])})])[field]
                self.assertEqual(got["current"], _row()[field])
                self.assertIsNone(got["previous"])
                self.assertEqual(got["state"], "none")
                self.assertEqual(got["direction"], "flat")
                self.assertIsNone(got["percent_change"])
                self.assertIsNone(got["abs_change"])

    def test_unreported_current_raw_fields_never_become_full_decreases(self):
        for field in RAW_FIELDS:
            with self.subTest(field=field):
                got = _compare([_row(**{field: 0, "missing_json": json.dumps([field])})], [_row()])[field]
                self.assertIsNone(got["current"])
                self.assertEqual(got["previous"], _row()[field])
                self.assertEqual(got["state"], "none")
                self.assertEqual(got["sentiment"], "neutral")
                self.assertIsNone(got["percent_change"])

    def test_measured_zero_previous_raw_fields_still_become_new(self):
        for field in RAW_FIELDS:
            with self.subTest(field=field):
                got = _compare([_row()], [_row(**{field: 0})])[field]
                self.assertEqual(got["previous"], 0)
                self.assertEqual(got["state"], "new")
                self.assertEqual(got["direction"], "up")
                self.assertIsNone(got["percent_change"])

    def test_measured_zero_current_raw_fields_retain_full_decreases(self):
        for field in RAW_FIELDS:
            with self.subTest(field=field):
                got = _compare([_row(**{field: 0})], [_row()])[field]
                self.assertEqual(got["current"], 0)
                self.assertEqual(got["state"], "compared")
                self.assertEqual(got["direction"], "down")
                self.assertEqual(got["percent_change"], -100.0)
                self.assertEqual(got["abs_change"], -_row()[field])

    def test_missing_previous_ratio_inputs_do_not_mean_new(self):
        for metric, field in (("ctr", "clicks"), ("cpc", "spend"),
                              ("cpm", "spend"), ("cpa", "conversions")):
            with self.subTest(metric=metric):
                got = _compare([_row()], [_row(**{field: 0, "missing_json": json.dumps([field])})])[metric]
                self.assertIsNotNone(got["current"])
                self.assertIsNone(got["previous"])
                self.assertEqual(got["state"], "none")

    def test_missing_current_ratio_inputs_do_not_mean_zero(self):
        for metric, field in (("ctr", "clicks"), ("cpc", "spend"),
                              ("cpm", "spend"), ("cpa", "conversions")):
            with self.subTest(metric=metric):
                got = _compare([_row(**{field: 0, "missing_json": json.dumps([field])})], [_row()])[metric]
                self.assertIsNone(got["current"])
                self.assertIsNotNone(got["previous"])
                self.assertEqual(got["state"], "none")

    def test_reported_zero_denominator_is_unavailable_not_a_measured_zero(self):
        for metric, field in (("ctr", "impressions"), ("cpc", "clicks"),
                              ("cpm", "impressions"), ("cpa", "conversions")):
            with self.subTest(metric=metric):
                got = _compare([_row()], [_row(**{field: 0})])[metric]
                self.assertIsNone(got["previous"])
                self.assertEqual(got["state"], "none")
                self.assertEqual(got["direction"], "flat")
                self.assertEqual(got["sentiment"], "neutral")
                self.assertIsNone(got["percent_change"])

    def test_reported_zero_ratio_numerator_is_a_real_full_decrease(self):
        got = _compare([_row(clicks=0)], [_row()])["ctr"]
        self.assertEqual(got["current"], 0)
        self.assertEqual(got["percent_change"], -100.0)
        self.assertEqual(got["sentiment"], "bad")

    def test_same_zero_raw_values_have_no_percentage(self):
        got = _compare([_row(conversions=0)], [_row(conversions=0)])["conversions"]
        self.assertEqual(got["state"], "none")
        self.assertEqual(got["abs_change"], 0)
        self.assertIsNone(got["percent_change"])

    def test_existing_ratio_units_rounding_and_sentiment_are_preserved(self):
        got = _compare([_row(spend=300, clicks=600, impressions=25000, conversions=24)],
                       [_row(spend=200, clicks=400, impressions=20000, conversions=20)])
        self.assertEqual(got["ctr"], {
            "current": 0.024, "previous": 0.02, "percent_change": 20.0,
            "direction": "up", "sentiment": "good", "state": "compared", "abs_change": 0.004,
        })
        self.assertEqual(got["cpa"]["current"], 12.5)
        self.assertEqual(got["cpa"]["previous"], 10)
        self.assertEqual(got["cpa"]["percent_change"], 25.0)
        self.assertEqual(got["cpa"]["sentiment"], "bad")
        self.assertEqual(got["spend"]["sentiment"], "neutral")

    def test_partial_reporting_compares_only_known_populations(self):
        current = [_row(clicks=10, impressions=100),
                   _row(clicks=0, impressions=900, missing_json='["clicks"]')]
        got = _compare(current, [_row(clicks=5, impressions=100)])["ctr"]
        self.assertEqual(got["current"], 0.1)
        self.assertEqual(got["previous"], 0.05)
        self.assertEqual(got["percent_change"], 100.0)
        self.assertEqual(_pooled(current)["metric_coverage"]["ctr"],
                         {"reporting_rows": 1, "total_rows": 2})

    def test_empty_previous_keeps_current_values_without_change(self):
        got = _compare([_row()], [])
        self.assertEqual(got["spend"]["current"], 100)
        self.assertEqual(got["cpa"]["current"], 10)
        for metric in got.values():
            self.assertIsNone(metric["previous"])
            self.assertEqual(metric["state"], "none")

    def test_empty_current_keeps_previous_values_without_full_decrease(self):
        got = _compare([], [_row()])
        self.assertEqual(got["spend"]["previous"], 100)
        for metric in got.values():
            self.assertIsNone(metric["current"])
            self.assertEqual(metric["state"], "none")

    def test_empty_periods_produce_only_unavailable_metric_values(self):
        got = _compare([], [])
        for metric in got.values():
            self.assertIsNone(metric["current"])
            self.assertIsNone(metric["previous"])
            self.assertIsNone(metric["abs_change"])
            self.assertEqual(metric["state"], "none")

    def test_distinct_currencies_do_not_compare_money(self):
        got = _compare([_row(currency="GBP")], [_row(currency="USD")])
        for key in ("spend", "revenue", "cpc", "cpm", "cpa"):
            self.assertIsNone(got[key]["current"])
            self.assertIsNone(got[key]["previous"])
            self.assertEqual(got[key]["state"], "none")
        self.assertEqual(got["impressions"]["state"], "compared")

    def test_mixed_current_keeps_money_unavailable_with_empty_previous(self):
        got = _compare([_row(currency="GBP"), _row(currency="USD")], [])
        self.assertIsNone(got["spend"]["current"])
        self.assertIsNone(got["cpa"]["current"])
        self.assertEqual(got["impressions"]["current"], 2000)

    def test_known_plus_unknown_currency_still_blocks_money_comparison(self):
        got = _compare([_row(currency="GBP"), _row(currency="")], [_row(currency="GBP")])
        self.assertIsNone(got["spend"]["current"])
        self.assertEqual(got["spend"]["state"], "none")
        self.assertEqual(got["clicks"]["percent_change"], 100.0)

    def test_legacy_unspecified_currency_retains_existing_calculation_policy(self):
        got = _compare([_row(spend=200, currency="")], [_row(currency="")])["spend"]
        self.assertEqual(got["current"], 200)
        self.assertEqual(got["previous"], 100)
        self.assertEqual(got["percent_change"], 100.0)

    def test_null_money_totals_are_not_rounded_or_coerced_to_zero(self):
        got = _compare([_row(missing_json='["spend", "revenue"]')], [_row()])
        self.assertIsNone(got["spend"]["current"])
        self.assertIsNone(got["revenue"]["current"])
        self.assertEqual(got["spend"]["state"], "none")

    def test_money_rounding_retains_two_decimal_contract(self):
        got = _compare([_row(spend=12.345, revenue=23.456)], [_row()])
        self.assertEqual(got["spend"]["current"], 12.35)
        self.assertEqual(got["revenue"]["current"], 23.46)

    def test_direct_callers_do_not_interpret_previous_none_as_zero(self):
        got = period.compare_metric(2, None, "roas", prev_has_rows=True)
        self.assertEqual(got["state"], "none")
        flagged = period.compare_metric(2, None, "roas", prev_has_rows=True, previous_reported=False)
        self.assertEqual(flagged["state"], "none")

    def test_legacy_pooled_payload_without_coverage_keeps_null_ratio_unavailable(self):
        raw = availability.reported_raw_totals([_row()])
        got = period.compare_period_metrics(raw, raw, {"ctr": 0.1}, {"ctr": None})
        self.assertEqual(got["ctr"]["state"], "none")

    def test_other_ratio_metadata_is_not_invented(self):
        raw = availability.reported_raw_totals([_row()])
        got = period.compare_period_metrics(raw, raw, {"roas": 2}, {"roas": None})
        self.assertEqual(got["roas"]["state"], "none")
        self.assertEqual(got["roas"]["current"], 2)

    def test_row_presence_cannot_establish_a_missing_previous_measurement(self):
        for current in (None, 0, 2):
            for has_rows in (False, True):
                with self.subTest(current=current, has_rows=has_rows):
                    self.assertEqual(period._compare_values(current, None, has_rows),
                                     ("none", None, "flat"))

    def test_measured_zero_ratios_keep_the_zero_baseline_state(self):
        for metric in ("ctr", "cpc", "cpm", "cpa", "vtr", "view_rate", "roas"):
            with self.subTest(metric=metric):
                got = period.compare_metric(2, 0, metric, prev_has_rows=True)
                self.assertEqual(got["previous"], 0)
                self.assertEqual(got["state"], "new")
                self.assertEqual(got["sentiment"], "neutral")
                self.assertIsNone(got["percent_change"])

    def test_known_current_zero_is_retained_when_previous_ratio_is_undefined(self):
        raw = availability.reported_raw_totals([_row()])
        got = period.compare_period_metrics(raw, raw, {"roas": 0}, {"roas": None})["roas"]
        self.assertEqual(got["current"], 0)
        self.assertIsNone(got["previous"])
        self.assertEqual(got["state"], "none")
        self.assertIsNone(got["percent_change"])
        self.assertIsNone(got["abs_change"])

    def test_rows_and_aggregate_payloads_are_not_mutated(self):
        rows = [_row(), _row(missing_json='["clicks"]')]
        raw, pooled = availability.reported_raw_totals(rows), _pooled(rows)
        before = json.dumps([rows, raw, pooled], sort_keys=True)
        period.compare_period_metrics(raw, raw, pooled, pooled)
        self.assertEqual(json.dumps([rows, raw, pooled], sort_keys=True), before)

    def test_synthetic_payload_is_json_serializable_without_nonfinite_numbers(self):
        got = _compare([_row(conversions=0, clicks=0)], [_row(conversions=0, impressions=0)])
        encoded = json.dumps(got, allow_nan=False)
        self.assertIsInstance(encoded, str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
