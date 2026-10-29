"""Synthetic native-money labels and campaign spend explanations, isolated from the app."""

import copy
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "Backend" / "creative_intel"


def load_pure_module(name):
    spec = importlib.util.spec_from_file_location(f"quality_money_{name}", ROOT / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


money = load_pure_module("native_money")
comparison = load_pure_module("creative_comparison")


def aggregate(spend, currency="GBP", **metadata):
    return {"spend": spend, "currency": currency,
            "currencies": [currency] if currency else [], "mixed_currency": False, **metadata}


class NativeMoneyFormattingTests(unittest.TestCase):
    def test_known_denominations_preserve_the_native_number(self):
        for currency in ("GBP", "EUR", "USD"):
            with self.subTest(currency=currency):
                self.assertEqual(money.compact_money(25.5, currency), f"{currency} 25.50")

    def test_compact_amounts_use_the_same_explicit_currency_contract(self):
        for value, expected in ((1000, "1K"), (53_364.56, "53.4K"), (1_000_000, "1M"), (1_250_000, "1.2M")):
            with self.subTest(value=value):
                self.assertEqual(money.compact_money(value, "GBP"), f"GBP {expected}")

    def test_negative_native_amounts_keep_their_sign(self):
        self.assertEqual(money.compact_money(-1234, "EUR"), "EUR -1.2K")
        self.assertEqual(money.compact_money(-12.5, "EUR"), "EUR -12.50")

    def test_measured_zero_is_not_missing_money(self):
        self.assertEqual(money.compact_money(0, "USD"), "USD 0.00")

    def test_currency_case_and_whitespace_are_normalized(self):
        self.assertEqual(money.compact_money(100, " gbp "), "GBP 100.00")

    def test_unknown_currency_is_explicit_and_never_acquires_a_dollar_sign(self):
        for currency in (None, "", "   "):
            with self.subTest(currency=currency):
                text = money.compact_money(1234, currency)
                self.assertEqual(text, "1.2K (currency unknown)")
                self.assertNotIn("$", text)
                self.assertNotIn("USD", text)

    def test_missing_invalid_and_nonfinite_values_are_unavailable(self):
        for value in (None, "not a number", float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                self.assertEqual(money.compact_money(value, "GBP"), "unavailable")

    def test_numeric_string_formatting_keeps_the_native_amount(self):
        self.assertEqual(money.compact_money("12.25", "EUR"), "EUR 12.25")


class CampaignSpendExplanationTests(unittest.TestCase):
    def test_comparable_spend_uses_explicit_units_and_original_value_owners(self):
        top, bottom = aggregate(1000), aggregate(500)
        original = copy.deepcopy((top, bottom))
        note, details = comparison.campaign_spend_note("A", "B", top, bottom, money.compact_money)
        self.assertEqual(note, "Scale differs: A spent GBP 1K vs B GBP 500.00 (A has higher native spend)")
        self.assertEqual(details, {"top": 1000, "bottom": 500})
        self.assertEqual((top, bottom), original)
        self.assertNotIn("weight", note)

    def test_bottom_with_more_spend_keeps_its_name_and_value(self):
        note, details = comparison.campaign_spend_note(
            "Winner", "Other", aggregate(500, "EUR"), aggregate(1000, "EUR"), money.compact_money)
        self.assertEqual(note,
                         "Scale differs: Winner spent EUR 500.00 vs Other EUR 1K"
                         " (Other has higher native spend)")
        self.assertEqual(details, {"top": 500, "bottom": 1000})

    def test_cross_currency_spend_has_no_larger_amount_claim_or_numeric_details(self):
        note, details = comparison.campaign_spend_note(
            "UK", "Spain", aggregate(1000, "GBP"), aggregate(500, "EUR"), money.compact_money)
        self.assertIn("SPEND comparison unavailable", note)
        self.assertIsNone(details)
        self.assertNotIn("higher", note)
        self.assertNotIn("weight", note)

    def test_unknown_or_mixed_spend_does_not_use_a_known_label(self):
        cases = [aggregate(500, None), aggregate(500, mixed_currency=True),
                 aggregate(500, currency_known=False), aggregate(500, unknown_currency_contribution=True)]
        for bottom in cases:
            with self.subTest(bottom=bottom):
                note, details = comparison.campaign_spend_note(
                    "A", "B", aggregate(1000), bottom, money.compact_money)
                self.assertIn("SPEND comparison unavailable", note)
                self.assertIsNone(details)

    def test_measured_zero_is_included_in_a_comparable_spend_description(self):
        note, details = comparison.campaign_spend_note(
            "A", "B", aggregate(0), aggregate(100), money.compact_money)
        self.assertIn("A spent GBP 0.00", note)
        self.assertIn("B has higher native spend", note)
        self.assertEqual(details, {"top": 0, "bottom": 100})

    def test_equal_comparable_spend_keeps_the_existing_no_difference_behavior(self):
        self.assertEqual(comparison.campaign_spend_note(
            "A", "B", aggregate(100), aggregate(100), money.compact_money), (None, None))

    def test_equal_numbers_do_not_establish_equal_cross_currency_spend(self):
        note, details = comparison.campaign_spend_note(
            "A", "B", aggregate(100, "GBP"), aggregate(100, "EUR"), money.compact_money)
        self.assertIn("SPEND comparison unavailable", note)
        self.assertIsNone(details)

    def test_missing_spend_is_not_formatted_or_compared_as_zero(self):
        def unexpected_formatter(value, currency):
            self.fail("Unreported spend must not reach the formatter")

        note, details = comparison.campaign_spend_note(
            "A", "B", aggregate(None), aggregate(100), unexpected_formatter)
        self.assertIn("reported spend is missing or invalid", note)
        self.assertIsNone(details)

    def test_nonfinite_spend_does_not_create_a_scale_claim(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                note, details = comparison.campaign_spend_note(
                    "A", "B", aggregate(value), aggregate(100), money.compact_money)
                self.assertIn("Spend comparison unavailable", note)
                self.assertIsNone(details)

    def test_formatter_receives_each_amounts_explicit_source_currency(self):
        calls = []

        def capture(value, currency):
            calls.append((value, currency))
            return money.compact_money(value, currency)

        note, _ = comparison.campaign_spend_note("A", "B", aggregate(100, " gbp "), aggregate(200), capture)
        self.assertEqual(calls, [(100, " gbp "), (200, "GBP")])
        self.assertIn("GBP 100.00", note)
        self.assertIn("GBP 200.00", note)

    def test_dimensionless_campaign_comparison_does_not_enable_cross_unit_spend_claims(self):
        per = {"UK": aggregate(1000, "GBP", ctr=0.1), "Spain": aggregate(500, "EUR", ctr=0.2)}
        self.assertIsNone(comparison.unavailable_campaign_cost_comparison(per, "ctr"))
        note, details = comparison.campaign_spend_note(
            "Spain", "UK", per["Spain"], per["UK"], money.compact_money)
        self.assertIn("SPEND comparison unavailable", note)
        self.assertIsNone(details)


if __name__ == "__main__":
    unittest.main()
