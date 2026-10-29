"""Isolated native-cost and explanation regressions using synthetic aggregates."""

import copy
import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = (Path(__file__).resolve().parents[1]
               / "Backend" / "creative_intel" / "creative_comparison.py")
SPEC = importlib.util.spec_from_file_location("creative_comparison_quality", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
comparison = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(comparison)


def aggregate(currency="GBP", **values):
    return {"currency": currency, "currencies": [currency] if currency else [],
            "mixed_currency": False, **values}


class NativeCostComparisonTests(unittest.TestCase):
    def test_cross_currency_costs_have_no_ranking_or_winner(self):
        for metric in ("cpa", "cpc", "cpm"):
            with self.subTest(metric=metric):
                per = {"A": aggregate("GBP", **{metric: 10}),
                       "B": aggregate("EUR", **{metric: 8})}
                self.assertEqual(comparison.rank_creatives(["A", "B"], per, metric, higher=False),
                                 (["A", "B"], None))
                self.assertIn(metric.upper(), comparison.cost_comparison_reason(per.values(), metric))

    def test_same_currency_costs_keep_the_lower_value_winner(self):
        per = {"A": aggregate(cpa=10), "B": aggregate(cpa=8)}
        self.assertEqual(comparison.rank_creatives(["A", "B"], per, "cpa", higher=False),
                         (["B", "A"], "B"))

    def test_currency_case_and_whitespace_do_not_split_a_denomination(self):
        per = {"A": aggregate(" gbp ", cpa=10), "B": aggregate("GBP", cpa=8)}
        self.assertIsNone(comparison.cost_comparison_reason(per.values(), "cpa"))
        self.assertEqual(comparison.rank_creatives(["A", "B"], per, "cpa", higher=False)[1], "B")

    def test_unknown_denominations_cannot_produce_a_cost_winner(self):
        per = {"A": aggregate(None, cpa=10), "B": aggregate(None, cpa=8)}
        self.assertEqual(comparison.rank_creatives(["A", "B"], per, "cpa", higher=False)[1], None)

    def test_legacy_producer_without_currency_known_can_supply_explicit_currency(self):
        self.assertIsNone(comparison.cost_comparison_reason([aggregate(cpa=10), aggregate(cpa=8)], "cpa"))

    def test_explicit_unknown_or_mixed_metadata_is_not_overridden_by_a_label(self):
        for flag in ("mixed_currency", "unknown_currency_contribution", "currency_known"):
            with self.subTest(flag=flag):
                invalid = aggregate(cpa=8, **{flag: flag != "currency_known"})
                self.assertIsNotNone(comparison.cost_comparison_reason([aggregate(cpa=10), invalid], "cpa"))

    def test_inconsistent_declared_currencies_are_not_treated_as_known(self):
        for declared in (["EUR"], ["GBP", "EUR"], [None], "GBP"):
            with self.subTest(declared=declared):
                self.assertIsNotNone(comparison.cost_comparison_reason(
                    [aggregate(cpa=8, currencies=declared)], "cpa"))

    def test_unavailable_metric_does_not_add_another_currency_to_the_comparison(self):
        per = {"A": aggregate(cpa=10), "B": aggregate(None, cpa=None, mixed_currency=True)}
        self.assertEqual(comparison.rank_creatives(["B", "A"], per, "cpa", higher=False),
                         (["A", "B"], "A"))

    def test_measured_zero_cost_is_not_converted_to_missing(self):
        per = {"A": aggregate(cpa=10), "B": aggregate(cpa=0)}
        self.assertEqual(comparison.rank_creatives(["A", "B"], per, "cpa", higher=False),
                         (["B", "A"], "B"))

    def test_zero_or_equal_cost_does_not_establish_currency_comparability(self):
        for value in (0, 10):
            with self.subTest(value=value):
                per = {"A": aggregate("GBP", cpa=value), "B": aggregate("EUR", cpa=value)}
                self.assertEqual(comparison.rank_creatives(["A", "B"], per, "cpa", higher=False)[1], None)

    def test_same_currency_ties_preserve_selection_order(self):
        per = {"A": aggregate(cpa=10), "B": aggregate(cpa=10)}
        self.assertEqual(comparison.rank_creatives(["B", "A"], per, "cpa", higher=False),
                         (["B", "A"], "B"))

    def test_empty_and_all_missing_rankings_have_no_winner(self):
        self.assertEqual(comparison.rank_creatives([], {}, "cpa", higher=False), ([], None))
        self.assertEqual(comparison.rank_creatives(["A", "B"], {}, "cpa", higher=False),
                         (["A", "B"], None))

    def test_dimensionless_metrics_keep_their_existing_comparison_policy(self):
        for metric in ("ctr", "vtr", "roas"):
            with self.subTest(metric=metric):
                per = {"A": aggregate("GBP", **{metric: 1}), "B": aggregate("EUR", **{metric: 2})}
                self.assertIsNone(comparison.cost_comparison_reason(per.values(), metric))
                self.assertEqual(comparison.rank_creatives(["A", "B"], per, metric, higher=True),
                                 (["B", "A"], "B"))

    def test_comparison_does_not_mutate_native_values_or_metadata(self):
        per = {"A": aggregate("GBP", cpa=10), "B": aggregate("EUR", cpa=8)}
        original = copy.deepcopy(per)
        keys = ["B", "A"]
        comparison.rank_creatives(keys, per, "cpa", higher=False)
        comparison.multi_metric_notes(keys, per)
        comparison.pairwise_metric_notes("A", "B", per["A"], per["B"])
        self.assertEqual(per, original)
        self.assertEqual(keys, ["B", "A"])


class MetricExplanationTests(unittest.TestCase):
    def test_pairwise_cross_currency_cost_notes_withhold_each_cost_leader(self):
        a = aggregate("GBP", cpa=10, cpc=5, cpm=20, ctr=1)
        b = aggregate("EUR", cpa=8, cpc=4, cpm=15, ctr=2)
        notes = comparison.pairwise_metric_notes("A", "B", a, b)
        for metric in ("CPA", "CPC", "CPM"):
            self.assertTrue(any(note.startswith(f"{metric} comparison unavailable:") for note in notes))
            self.assertFalse(any(f"on {metric} (" in note for note in notes))
        self.assertIn("B leads A on CTR (2 vs 1)", notes)

    def test_pairwise_values_follow_the_named_leader_in_both_selection_orders(self):
        for metric, higher in (("cpa", False), ("cpc", False), ("cpm", False),
                               ("ctr", True), ("vtr", True), ("roas", True)):
            for winner in ("A", "B"):
                with self.subTest(metric=metric, winner=winner):
                    best, other = (20, 10) if higher else (10, 20)
                    values = {winner: best, "B" if winner == "A" else "A": other}
                    a, b = aggregate(**{metric: values["A"]}), aggregate(**{metric: values["B"]})
                    loser = "B" if winner == "A" else "A"
                    expected = f"{winner} leads {loser} on {metric.upper()} ({best} vs {other})"
                    self.assertEqual(comparison.pairwise_metric_notes("A", "B", a, b), [expected])
                    self.assertEqual(comparison.pairwise_metric_notes("B", "A", b, a), [expected])

    def test_missing_pair_value_keeps_its_insufficient_data_explanation(self):
        notes = comparison.pairwise_metric_notes("A", "B", aggregate(cpa=None), aggregate(cpa=10))
        self.assertEqual(notes, ["CPA is not measurable for A (insufficient data)"])

    def test_equal_pair_values_do_not_invent_a_leader(self):
        self.assertEqual(comparison.pairwise_metric_notes("A", "B", aggregate(cpa=10), aggregate(cpa=10)), [])

    def test_equal_pair_values_in_different_currencies_are_still_explained_as_unavailable(self):
        notes = comparison.pairwise_metric_notes("A", "B", aggregate("GBP", cpa=10), aggregate("EUR", cpa=10))
        self.assertEqual(len(notes), 1)
        self.assertTrue(notes[0].startswith("CPA comparison unavailable:"))

    def test_nway_cost_notes_do_not_declare_a_cross_currency_leader(self):
        per = {"A": aggregate("GBP", cpa=10), "B": aggregate("EUR", cpa=8), "C": aggregate("GBP", cpa=12)}
        notes = comparison.multi_metric_notes(["A", "B", "C"], per)
        self.assertEqual(notes, [comparison.cost_comparison_reason(per.values(), "cpa")])

    def test_nway_notes_preserve_exact_creative_value_associations(self):
        per = {"shared-creative": aggregate(cpa=20), "spain-only": aggregate(cpa=6.25),
               "null-cpa": aggregate(None, cpa=None)}
        notes = comparison.multi_metric_notes(list(per), per)
        self.assertEqual(notes, ["spain-only leads on CPA (6.25 vs shared-creative 20)"])
        self.assertNotIn("null-cpa", " ".join(notes))

    def test_nway_notes_keep_dimensionless_leaders_across_native_currencies(self):
        per = {"A": aggregate("GBP", ctr=1, roas=1), "B": aggregate("EUR", ctr=2, roas=2)}
        notes = comparison.multi_metric_notes(["A", "B"], per)
        self.assertIn("B leads on CTR (2 vs A 1)", notes)
        self.assertIn("B leads on ROAS (2 vs A 1)", notes)

    def test_single_unknown_cost_value_gets_an_unavailability_explanation(self):
        notes = comparison.multi_metric_notes(["A", "B"], {"A": aggregate(None, cpa=8), "B": {}})
        self.assertEqual(notes, [comparison.cost_comparison_reason([aggregate(None, cpa=8)], "cpa")])


class PrimaryWinnerTests(unittest.TestCase):
    def test_pairwise_primary_winner_does_not_compare_native_cpas(self):
        a, b = aggregate("GBP", cpa=10, conversions=2), aggregate("EUR", cpa=8, conversions=2)
        winner, reason = comparison.pairwise_primary_winner("A", "B", a, b)
        self.assertIsNone(winner)
        self.assertTrue(reason.startswith("CPA comparison unavailable:"))
        self.assertNotEqual(reason, comparison.NO_DELIVERY)

    def test_pairwise_primary_winner_keeps_same_currency_cpa_and_ties(self):
        a, b = aggregate(cpa=10, conversions=2), aggregate(cpa=8, conversions=2)
        self.assertEqual(comparison.pairwise_primary_winner("A", "B", a, b), ("B", None))
        self.assertEqual(comparison.pairwise_primary_winner("A", "B", b, b), ("A", None))

    def test_pairwise_primary_fallback_preserves_dimensionless_ctr(self):
        a, b = aggregate("GBP", ctr=1, impressions=100), aggregate("EUR", ctr=2, impressions=100)
        self.assertEqual(comparison.pairwise_primary_winner("A", "B", a, b), ("B", None))

    def test_pairwise_missing_cost_with_delivery_is_not_labelled_no_delivery(self):
        a, b = aggregate(cpa=None, conversions=2), aggregate(cpa=None, conversions=2)
        self.assertEqual(comparison.pairwise_primary_winner("A", "B", a, b),
                         (None, comparison.NO_COMPARABLE_METRIC))

    def test_pairwise_no_delivery_keeps_the_existing_message(self):
        self.assertEqual(comparison.pairwise_primary_winner("A", "B", {}, {}),
                         (None, comparison.NO_DELIVERY))

    def test_nway_primary_winner_does_not_compare_native_cpas(self):
        per = {"A": aggregate("GBP", cpa=10, conversions=2),
               "B": aggregate("EUR", cpa=8, conversions=2), "C": aggregate("GBP", cpa=12, conversions=2)}
        winner, reason = comparison.multi_primary_winner(list(per), per)
        self.assertIsNone(winner)
        self.assertTrue(reason.startswith("CPA comparison unavailable:"))

    def test_nway_primary_winner_keeps_comparable_costs_and_ignores_missing_values(self):
        per = {"A": aggregate(cpa=10, conversions=2), "B": aggregate(cpa=8, conversions=2),
               "C": aggregate(None, cpa=None, conversions=2)}
        self.assertEqual(comparison.multi_primary_winner(list(per), per), ("B", None))

    def test_nway_primary_fallback_preserves_dimensionless_ctr(self):
        per = {"A": aggregate("GBP", ctr=1), "B": aggregate("EUR", ctr=2)}
        self.assertEqual(comparison.multi_primary_winner(list(per), per), ("B", None))

    def test_nway_missing_cost_with_delivery_is_not_labelled_no_delivery(self):
        self.assertEqual(comparison.multi_primary_winner(["A"], {"A": aggregate(cpa=None, conversions=2)}),
                         (None, comparison.NO_COMPARABLE_METRIC))

    def test_nway_no_delivery_keeps_the_existing_message(self):
        self.assertEqual(comparison.multi_primary_winner(["A", "B"], {}), (None, comparison.NO_DELIVERY))


class CampaignComparisonAvailabilityTests(unittest.TestCase):
    def test_cross_currency_campaigns_keep_kpis_without_a_cost_winner(self):
        per = {"UK": aggregate("GBP", cpa=10), "Spain": aggregate("EUR", cpa=8)}
        result = comparison.unavailable_campaign_cost_comparison(per, "cpa")
        self.assertEqual(result["ranking"], ["UK", "Spain"])
        self.assertIsNone(result["winner"])
        self.assertEqual(result["rank_by"], "cpa")
        self.assertEqual(result["kpis"], per)
        self.assertEqual(result["why"], {
            "metric": "cpa", "top": None, "bottom": None,
            "differences": [comparison.cost_comparison_reason(per.values(), "cpa")], "details": {},
        })

    def test_all_native_cost_metrics_use_the_same_campaign_policy(self):
        for metric in ("cpa", "cpc", "cpm"):
            with self.subTest(metric=metric):
                per = {"UK": aggregate("GBP", **{metric: 10}), "Spain": aggregate("EUR", **{metric: 8})}
                self.assertIsNotNone(comparison.unavailable_campaign_cost_comparison(per, metric))

    def test_same_currency_campaigns_continue_the_existing_comparison(self):
        per = {"UK 1": aggregate(cpa=10), "UK 2": aggregate(cpa=8)}
        self.assertIsNone(comparison.unavailable_campaign_cost_comparison(per, "cpa"))

    def test_campaign_unknown_currency_cannot_acquire_a_default_denomination(self):
        per = {"A": aggregate(None, cpa=10), "B": aggregate(None, cpa=8)}
        result = comparison.unavailable_campaign_cost_comparison(per, "cpa")
        self.assertIsNone(result["winner"])
        self.assertIn("unknown", result["why"]["differences"][0])

    def test_campaign_display_order_keeps_unavailable_entries(self):
        per = {"Missing": aggregate(None, cpa=None), "Spain": aggregate("EUR", cpa=8),
               "UK": aggregate("GBP", cpa=10)}
        self.assertEqual(comparison.unavailable_campaign_cost_comparison(per, "cpa")["ranking"], list(per))

    def test_empty_and_single_campaign_cases_keep_the_callers_existing_contract(self):
        self.assertIsNone(comparison.unavailable_campaign_cost_comparison({}, "cpa"))
        self.assertIsNone(comparison.unavailable_campaign_cost_comparison(
            {"A": aggregate(None, cpa=10)}, "cpa"))

    def test_all_missing_campaign_metrics_keep_the_existing_uncomputable_reason(self):
        self.assertIsNone(comparison.unavailable_campaign_cost_comparison({"A": {}, "B": {}}, "cpa"))

    def test_missing_campaign_metric_does_not_block_a_known_comparable_value(self):
        per = {"A": aggregate(cpa=10), "B": aggregate(None, cpa=None)}
        self.assertIsNone(comparison.unavailable_campaign_cost_comparison(per, "cpa"))

    def test_dimensionless_campaign_metrics_do_not_inherit_a_cost_restriction(self):
        for metric in ("ctr", "vtr", "roas"):
            with self.subTest(metric=metric):
                per = {"A": aggregate("GBP", **{metric: 1}), "B": aggregate("EUR", **{metric: 2})}
                self.assertIsNone(comparison.unavailable_campaign_cost_comparison(per, metric))

    def test_campaign_native_values_are_not_converted_or_mutated(self):
        per = {"UK": aggregate("GBP", cpa=10), "Spain": aggregate("EUR", cpa=8)}
        original = copy.deepcopy(per)
        comparison.unavailable_campaign_cost_comparison(per, "cpa")
        self.assertEqual(per, original)


if __name__ == "__main__":
    unittest.main()
