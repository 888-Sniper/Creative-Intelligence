"""Standalone pure-helper regressions; no application/package startup required."""

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = (Path(__file__).resolve().parents[1]
               / "Backend" / "creative_intel" / "currency_scope.py")
SPEC = importlib.util.spec_from_file_location("currency_scope_quality", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
currency_scope = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(currency_scope)


class CurrencyScopeQualityTests(unittest.TestCase):
    def test_known_and_unknown_amounts_are_not_all_labeled_gbp(self):
        scope = currency_scope.money_scope([
            {"currency": "GBP", "spend": 100},
            {"currency": "", "spend": 100},
        ])
        self.assertIsNone(scope["currency"])
        self.assertEqual(scope["currencies"], ["GBP"])
        self.assertTrue(scope["mixed_currency"])
        self.assertFalse(scope["currency_known"])
        self.assertTrue(scope["unknown_currency_contribution"])

    def test_unknown_revenue_also_prevents_a_known_currency_label(self):
        scope = currency_scope.money_scope([
            {"currency": "GBP", "spend": 100, "revenue": 200},
            {"currency": None, "spend": 0, "revenue": 50},
        ])
        self.assertTrue(scope["mixed_currency"])
        self.assertIsNone(scope["currency"])

    def test_unknown_zero_amounts_do_not_change_known_money_units(self):
        scope = currency_scope.money_scope([
            {"currency": "GBP", "spend": 100},
            {"currency": " ", "spend": 0, "revenue": 0, "clicks": 5},
        ])
        self.assertEqual(scope["currency"], "GBP")
        self.assertTrue(scope["currency_known"])
        self.assertFalse(scope["mixed_currency"])
        self.assertFalse(scope["unknown_currency_contribution"])

    def test_offsetting_unknown_amounts_remain_unknown_contributions(self):
        scope = currency_scope.money_scope([
            {"currency": "GBP", "spend": 100},
            {"currency": "", "spend": 10},
            {"currency": "", "spend": -10},
        ])
        self.assertTrue(scope["mixed_currency"])
        self.assertTrue(scope["unknown_currency_contribution"])

    def test_known_native_currency_is_normalized_without_mutating_rows(self):
        rows = [{"currency": " gbp ", "spend": 100},
                {"currency": "GBP", "spend": 50}]
        scope = currency_scope.money_scope(rows)
        self.assertEqual(scope["currency"], "GBP")
        self.assertEqual(scope["currencies"], ["GBP"])
        self.assertTrue(scope["currency_known"])
        self.assertFalse(scope["mixed_currency"])
        self.assertEqual(rows[0]["currency"], " gbp ")

    def test_different_known_currencies_are_still_mixed(self):
        scope = currency_scope.money_scope([
            {"currency": "GBP", "spend": 100},
            {"currency": "EUR", "spend": 100},
        ])
        self.assertIsNone(scope["currency"])
        self.assertEqual(scope["currencies"], ["EUR", "GBP"])
        self.assertTrue(scope["mixed_currency"])
        self.assertFalse(scope["currency_known"])

    def test_all_unspecified_preserves_the_documented_legacy_calculation_policy(self):
        scope = currency_scope.money_scope([
            {"currency": "", "spend": 100},
            {"spend": 50},
        ])
        self.assertIsNone(scope["currency"])
        self.assertFalse(scope["currency_known"])
        self.assertEqual(scope["currencies"], [])
        self.assertFalse(scope["mixed_currency"])
        self.assertTrue(scope["unknown_currency_contribution"])

    def test_no_rows_never_claim_a_known_currency(self):
        for rows in (None, []):
            with self.subTest(rows=rows):
                scope = currency_scope.money_scope(rows)
                self.assertIsNone(scope["currency"])
                self.assertFalse(scope["currency_known"])
                self.assertFalse(scope["mixed_currency"])

    def test_row_order_does_not_change_classification(self):
        rows = [{"currency": "GBP", "spend": 100},
                {"currency": "", "revenue": 50}]
        self.assertEqual(currency_scope.money_scope(rows),
                         currency_scope.money_scope(list(reversed(rows))))


if __name__ == "__main__":
    unittest.main(verbosity=2)
