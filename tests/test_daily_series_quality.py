"""QI016/QI150 daily + filtered-benchmark currency/population contracts.

Synthetic in-memory rows only. Daily money ratios must come from the
canonical matched populations, never unconditional revenue/spend sums,
and filtered benchmark bands must not pool unlike native units.
"""

import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import benchmarks, schema


def _conn(rows):
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    conn.executemany(
        "INSERT INTO ads (platform, campaign, ad_name, creative_key,"
        " spend, impressions, clicks, conversions, revenue,"
        " revenue_reported, currency, missing_json, date)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [("meta", "A", key, key, spend, 10000, 200, conv, revenue,
          reported, currency, "[]", date)
         for key, spend, conv, revenue, reported, currency, date in rows])
    return conn


class DailySeriesQualityTests(unittest.TestCase):
    def test_daily_roas_uses_reporting_population(self):
        conn = _conn([
            ("k1", 100, 10, 200, 1, "GBP", "2026-08-01"),
            ("k2", 100, 10, 0, 0, "GBP", "2026-08-01"),
        ])
        try:
            day = benchmarks.daily_series(conn)["days"][0]
            self.assertEqual(day["spend"], 200.0)
            self.assertEqual(day.get("roas"), 2.0)
            self.assertEqual(day.get("currency"), "GBP")
            self.assertFalse(day.get("mixed_currency"))
        finally:
            conn.close()

    def test_daily_mixed_currency_money_ratios_unavailable(self):
        conn = _conn([
            ("k1", 100, 10, 200, 1, "GBP", "2026-08-01"),
            ("k2", 100, 10, 300, 1, "EUR", "2026-08-01"),
        ])
        try:
            day = benchmarks.daily_series(conn)["days"][0]
            self.assertIsNone(day.get("roas"))
            self.assertIsNone(day.get("cpa"))
            self.assertIsNone(day.get("cpm"))
            self.assertTrue(day.get("mixed_currency"))
        finally:
            conn.close()


class BenchmarkFilteredQualityTests(unittest.TestCase):
    def test_mixed_currency_money_bands_unavailable(self):
        conn = _conn([
            ("k1", 100, 10, 200, 1, "GBP", "2026-08-01"),
            ("k2", 100, 5, 300, 1, "EUR", "2026-08-01"),
        ])
        try:
            got = benchmarks.benchmark_filtered(conn, metric="cpa")
            self.assertEqual(got["stats"]["n"], 0)
            self.assertIsNone(got["stats"]["median"])
            self.assertEqual(got["status"], "insufficient")
        finally:
            conn.close()

    def test_mixed_currency_dimensionless_bands_keep_percentiles(self):
        conn = _conn([
            ("k1", 100, 10, 200, 1, "GBP", "2026-08-01"),
            ("k2", 100, 5, 300, 1, "EUR", "2026-08-01"),
        ])
        try:
            got = benchmarks.benchmark_filtered(conn, metric="ctr")
            self.assertEqual(got["stats"]["n"], 2)
            self.assertIsNotNone(got["stats"]["median"])
            self.assertIsNone(got["stats"]["mean_weighted"])
        finally:
            conn.close()

    def test_mixed_currency_money_bands_name_the_reason(self):
        conn = _conn([
            ("k1", 100, 10, 200, 1, "GBP", "2026-08-01"),
            ("k2", 100, 5, 300, 1, "EUR", "2026-08-01"),
        ])
        try:
            got = benchmarks.benchmark_filtered(conn, metric="cpa")
            self.assertIn("mixed currencies", " ".join(got["stats"]["reasons"]))
            self.assertEqual(got["stats"]["n_missing"], 2)
        finally:
            conn.close()

    def test_single_currency_cpc_bands_are_canonical(self):
        conn = _conn([
            ("k1", 100, 10, 200, 1, "GBP", "2026-08-01"),
            ("k2", 300, 15, 300, 1, "GBP", "2026-08-01"),
        ])
        try:
            got = benchmarks.benchmark_filtered(conn, metric="cpc")
            self.assertEqual(got["stats"]["n"], 2)
            self.assertIsNotNone(got["stats"]["median"])
        finally:
            conn.close()

    def test_single_currency_money_bands_unchanged(self):
        conn = _conn([
            ("k1", 100, 10, 200, 1, "GBP", "2026-08-01"),
            ("k2", 300, 15, 300, 1, "GBP", "2026-08-01"),
        ])
        try:
            got = benchmarks.benchmark_filtered(conn, metric="cpa")
            self.assertEqual(got["stats"]["n"], 2)
            self.assertIsNotNone(got["stats"]["median"])
            self.assertIsNotNone(got["stats"]["mean_weighted"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
