"""Manual comparison arithmetic on synthetic aggregates, with no application I/O."""

import copy
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "Backend" / "creative_intel"


def load(name):
    spec = importlib.util.spec_from_file_location(f"manual_period_{name}", ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


period = load("period_metrics")
currency = load("currency_scope")
MONEY = ("spend", "cpc", "cpm", "cpa")


def kpis(code="GBP", value=10):
    return {**{metric: value for metric in period.MANUAL_PERIOD_METRICS},
            **currency.money_scope([{"currency": code, "spend": value}])}


class ManualPeriodQualityTests(unittest.TestCase):
    def assert_money_unavailable(self, a, b):
        delta, reasons = period.manual_period_deltas(a, b)
        self.assertEqual({metric: delta[metric] for metric in MONEY}, dict.fromkeys(MONEY))
        self.assertEqual(reasons, dict.fromkeys(MONEY, "incomparable_currency"))
        return delta

    def test_different_known_units_do_not_produce_money_deltas(self):
        delta = self.assert_money_unavailable(kpis("GBP", 100), kpis("EUR", 200))
        for metric in ("impressions", "clicks", "conversions", "vtr", "view_rate", "ctr", "roas"):
            self.assertEqual(delta[metric], 100)

    def test_same_known_currency_preserves_b_minus_a(self):
        delta, reasons = period.manual_period_deltas(kpis(value=10), kpis(value=12))
        self.assertEqual(delta, dict.fromkeys(period.MANUAL_PERIOD_METRICS, 2))
        self.assertEqual(reasons, {})

    def test_case_and_whitespace_are_normalized(self):
        a = {**kpis(), "currency": " gbp ", "currencies": ["gBp"]}
        self.assertEqual(period.manual_period_deltas(a, kpis(value=20))[0]["spend"], 10)

    def test_two_wholly_unspecified_units_keep_legacy_deltas(self):
        delta, reasons = period.manual_period_deltas(kpis(None), kpis(None, 20))
        self.assertEqual(delta["spend"], 10)
        self.assertEqual(reasons, {})

    def test_known_and_unknown_units_are_not_comparable_in_either_order(self):
        for a, b in [(kpis(), kpis(None)), (kpis(None), kpis())]:
            with self.subTest(a=a["currency"]):
                self.assert_money_unavailable(a, b)

    def test_mixed_side_remains_unavailable_even_if_a_numeric_spend_exists(self):
        mixed = {**kpis(), **currency.money_scope([
            {"currency": "GBP", "spend": 10}, {"currency": "EUR", "spend": 20}])}
        self.assert_money_unavailable(mixed, kpis())
        self.assert_money_unavailable(kpis(), mixed)

    def test_unknown_contribution_is_not_hidden_by_known_rows(self):
        unknown = {**kpis(), **currency.money_scope([
            {"currency": "GBP", "spend": 10}, {"currency": None, "spend": 20}])}
        self.assert_money_unavailable(unknown, kpis())

    def test_empty_side_keeps_existing_count_arithmetic_but_no_money_change(self):
        empty = {**kpis(value=0), **currency.money_scope([])}
        delta = self.assert_money_unavailable(empty, kpis(value=10))
        self.assertEqual(delta["impressions"], 10)

    def test_missing_metadata_never_invents_a_currency(self):
        self.assert_money_unavailable({"spend": 10}, {"spend": 20})

    def test_inconsistent_metadata_never_establishes_matching_units(self):
        for change in ({"currency_known": False}, {"mixed_currency": True},
                       {"unknown_currency_contribution": True}, {"currencies": ["EUR"]},
                       {"currencies": []}, {"currencies": None}):
            with self.subTest(change=change):
                self.assert_money_unavailable({**kpis(), **change}, kpis())

    def test_missing_values_remain_unavailable_without_a_currency_mismatch_reason(self):
        for a, b in [({**kpis(), "cpa": None}, kpis()), (kpis(), {**kpis(), "cpa": None})]:
            delta, reasons = period.manual_period_deltas(a, b)
            self.assertIsNone(delta["cpa"])
            self.assertEqual(reasons, {})

    def test_reported_zero_is_preserved_with_matching_units(self):
        delta, reasons = period.manual_period_deltas(kpis(value=0), kpis(value=0))
        self.assertEqual(delta["spend"], 0)
        self.assertEqual(reasons, {})

    def test_negative_change_and_rounding_are_preserved(self):
        delta, _ = period.manual_period_deltas(kpis(value=10.123456), kpis(value=1.234567))
        self.assertEqual(delta["spend"], -8.8889)

    def test_native_sides_are_not_rewritten_or_converted(self):
        a, b = kpis("GBP", 100), kpis("EUR", 200)
        before = copy.deepcopy((a, b))
        period.manual_period_deltas(a, b)
        self.assertEqual((a, b), before)

    def test_dimensionless_roas_keeps_its_existing_policy(self):
        a, b = kpis("GBP"), kpis("EUR")
        a["roas"], b["roas"] = 1.25, 2.5
        delta, reasons = period.manual_period_deltas(a, b)
        self.assertEqual(delta["roas"], 1.25)
        self.assertNotIn("roas", reasons)

    def test_legacy_unknown_unit_policy_is_shared_by_automatic_and_manual(self):
        self.assertTrue(period._money_comparable(kpis(None), kpis(None)))
        delta, reasons = period.manual_period_deltas(kpis(None), kpis(None, 20))
        self.assertEqual(delta["spend"], 10)
        self.assertEqual(reasons, {})
