"""Honest pooled metrics: A14 (matched ROAS + currency gating),
A15 (vtr/view_rate split from one registry), A16 (null bands).

Each test replays the audit's isolated reproduction against the real
helpers — not stubbed arithmetic — so the buggy numbers (ROAS 0.2,
plays-labelled VTR, zero bands) cannot return silently.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import analyst, analyst_metrics, benchmarks, ingest


def _row(spend, impressions, video_views=0, views_100=0, revenue=0.0,
         reported=False, currency="", missing=()):
    row = {"spend": spend, "impressions": impressions,
           "clicks": 0, "conversions": 0, "video_views": video_views,
           "views_100": views_100, "revenue": revenue,
           "revenue_reported": reported, "currency": currency,
           "conv_rate": 0.0, "creative_key": "k"}
    import json
    row["missing_json"] = json.dumps(sorted(missing))
    return row


class MatchedRoasTest(unittest.TestCase):
    def test_audit_repro_partial_revenue(self):
        # A14 audit repro: GBP 100 spend / 200 reported revenue plus
        # GBP 900 spend with revenue unavailable. The old code gated
        # on any() and returned 200/1000 = 0.2; the honest answer is
        # ROAS 2.0 over the reporting tenth of spend.
        rows = [_row(100.0, 1000, revenue=200.0, reported=True,
                     currency="GBP"),
                _row(900.0, 9000, currency="GBP",
                     missing=("revenue",))]
        value, coverage = benchmarks.matched_roas(rows)
        self.assertEqual(value, 2.0)
        self.assertAlmostEqual(coverage, 0.1)
        got = benchmarks.kpis_for_rows(rows)
        self.assertEqual(got["roas"], 2.0)
        self.assertAlmostEqual(got["roas_coverage"], 0.1)

    def test_no_reported_rows_yields_null_not_zero(self):
        rows = [_row(100.0, 1000, currency="GBP", missing=("revenue",))]
        value, coverage = benchmarks.matched_roas(rows)
        self.assertIsNone(value)
        self.assertEqual(coverage, 0.0)
        self.assertIsNone(benchmarks.kpis_for_rows(rows)["roas"])

    def test_mixed_currency_nulls_money_ratios(self):
        rows = [_row(100.0, 10000, video_views=3000, views_100=1000,
                     revenue=200.0, reported=True, currency="GBP"),
                _row(100.0, 10000, video_views=3000, views_100=1000,
                     revenue=200.0, reported=True, currency="EUR")]
        got = benchmarks.kpis_for_rows(rows)
        self.assertTrue(got["mixed_currency"])
        self.assertEqual(got["currencies"], ["EUR", "GBP"])
        self.assertIsNone(got["currency"])
        for key in ("cpm", "cpc", "cpa", "roas"):
            self.assertIsNone(got[key])
        # Unit-free rates still pool; the split stays separable.
        self.assertEqual(got["view_rate"], 0.3)
        self.assertEqual(got["vtr"], 0.1)
        self.assertEqual(got["by_currency"]["GBP"]["spend"], 100.0)
        self.assertEqual(got["by_currency"]["EUR"]["revenue"], 200.0)

    def test_single_currency_scope_unaffected(self):
        rows = [_row(100.0, 10000, revenue=150.0, reported=True,
                     currency="usd")]
        got = benchmarks.kpis_for_rows(rows)
        self.assertFalse(got["mixed_currency"])
        self.assertEqual(got["currency"], "USD")
        self.assertEqual(got["roas"], 1.5)

    def test_engine_money_gated_on_mixed_currency(self):
        # A14 applies to the Analyst engine too: cpa/roas/cpcv go NA
        # on mixed scopes while unit-free rates still compute.
        rows = [_row(100.0, 10000, video_views=3000, views_100=1000,
                     currency="GBP"),
                _row(100.0, 10000, video_views=3000, views_100=1000,
                     currency="EUR")]
        out = analyst.creative_metrics(rows)
        self.assertEqual(out["cpa"]["state"], analyst_metrics.NA)
        self.assertEqual(out["roas"]["state"], analyst_metrics.NA)
        self.assertEqual(analyst_metrics.cpcv(rows)["state"],
                         analyst_metrics.NA)
        self.assertIsNotNone(out["vtr"]["value"])


class RateIdentityTest(unittest.TestCase):
    def test_audit_repro_split_rates(self):
        # A15 audit repro: 1,000 impressions, 600 plays, 100
        # completions. One id per definition, both from the registry.
        rows = [_row(50.0, 1000, video_views=600, views_100=100)]
        got = benchmarks.kpis_for_rows(rows)
        self.assertEqual(got["vtr"], 0.1)
        self.assertEqual(got["view_rate"], 0.6)

    def test_unmeasured_completions_are_null_not_zero(self):
        # Completions never supplied (ingest-realistic missing_json):
        # VTR is unknown, while the measured play rate still pools.
        rows = [_row(50.0, 1000, video_views=600,
                     missing=("views_100",))]
        got = benchmarks.kpis_for_rows(rows)
        self.assertIsNone(got["vtr"])
        self.assertEqual(got["view_rate"], 0.6)

    def test_registry_defines_both_ids_distinctly(self):
        vtr = analyst_metrics.METRICS["vtr"]
        play = analyst_metrics.METRICS["view_rate"]
        self.assertEqual(vtr["numerator"], "views_100")
        self.assertEqual(play["numerator"], "video_views")
        self.assertNotEqual(vtr["numerator"], play["numerator"])
        for spec in (vtr, play):
            label = spec["display"]["en"]
            self.assertIn("impressions", label)

    def test_ingest_marks_absent_completions_missing(self):
        # End to end through the real CSV pipeline: a report without
        # a completions column records views_100 missing, so pooled
        # VTR is None instead of a false 0.0.
        rows, _quarantined, _meta = ingest.parse_csv_report_ex(
            "Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
            "Link Clicks,Conversions,Video Views\n"
            "C,A,a,50,1000,10,2,600\n", "meta")
        self.assertIn("views_100", rows[0]["missing_json"])
        got = benchmarks.kpis_for_rows(rows)
        self.assertIsNone(got["vtr"])
        self.assertEqual(got["view_rate"], 0.6)


class NullBandsTest(unittest.TestCase):
    def test_empty_population_has_null_bands(self):
        # A16 audit repro: n = 0, n_missing = 2, and no numeric zero
        # posing as a measured benchmark.
        got = benchmarks.describe_bands([None, None], [5, 6])
        self.assertEqual((got["n"], got["n_missing"]), (0, 2))
        for key in ("mean_weighted", "p25", "median", "p75"):
            self.assertIsNone(got[key])

    def test_empty_inputs_have_null_bands(self):
        got = benchmarks.describe_bands([], [])
        self.assertEqual(got["n"], 0)
        for key in ("mean_weighted", "p25", "median", "p75"):
            self.assertIsNone(got[key])

    def test_measured_values_still_band(self):
        got = benchmarks.describe_bands([2.0, 4.0], [1, 1])
        self.assertEqual(got["n"], 2)
        self.assertIsNotNone(got["median"])


if __name__ == "__main__":
    unittest.main()
