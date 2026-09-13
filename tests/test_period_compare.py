"""Previous-equivalent-period KPI comparisons (stdlib unittest).

Covers date-boundary arithmetic, real-data aggregation, ratio
semantics, zero/missing handling, direction/sentiment, and filter
propagation — all against real helpers, never stubbed arithmetic.
"""

import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))
from creative_intel import ingest, period_compare, schema  # noqa: E402

HDR = (
    "Campaign,Ad Name,Creative Name,Amount Spent,Impressions,Link Clicks,Conversions,Revenue,Platform,Date\n"
)


def _db(csv_text, platform="meta"):
    # parse_csv pins every row to its source platform, so each
    # platform's rows are ingested with their own source.
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    ingest.insert_rows(conn, ingest.parse_csv(csv_text, platform, "upload"))
    return conn


def _db_multi(parts):
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    for csv_text, platform in parts:
        ingest.insert_rows(conn, ingest.parse_csv(csv_text, platform, "upload"))
    return conn


def _row(camp, ad, spend, impr, clicks, conv, rev, plat, day):
    return "%s,%s,c-%s,%s,%s,%s,%s,%s,%s,%s\n" % (camp, ad, ad, spend, impr, clicks, conv, rev, plat, day)


# Previous window 2023-12-25..2023-12-31, current 2024-01-01..2024-01-07.
# Split by platform because parse_csv pins rows to one source.
PREV_META = "".join(
    [
        _row("Seeded", "p1", 100, 10000, 200, 10, 200, "meta", "2023-12-25"),
    ]
)
PREV_TIKTOK = "".join(
    [
        _row("Seeded", "p2", 100, 10000, 200, 10, 200, "tiktok", "2023-12-28"),
    ]
)
CUR_META = "".join(
    [
        _row("Seeded", "c1", 150, 12500, 300, 12, 300, "meta", "2024-01-02"),
    ]
)
CUR_TIKTOK = "".join(
    [
        _row("Seeded", "c2", 150, 12500, 300, 12, 300, "tiktok", "2024-01-05"),
    ]
)
PREV = PREV_META + PREV_TIKTOK
CUR = CUR_META + CUR_TIKTOK


def _db_seeded():
    return _db_multi([(HDR + PREV_META + CUR_META, "meta"), (HDR + PREV_TIKTOK + CUR_TIKTOK, "tiktok")])


class PreviousPeriodTest(unittest.TestCase):
    def test_task_example(self):
        self.assertEqual(
            period_compare.previous_period("2024-01-01", "2024-03-31"), ("2023-10-02", "2023-12-31")
        )

    def test_single_day_leap(self):
        # Mar 1 2024 minus one day is Feb 29 (leap year).
        self.assertEqual(
            period_compare.previous_period("2024-03-01", "2024-03-01"), ("2024-02-29", "2024-02-29")
        )

    def test_single_day_non_leap(self):
        self.assertEqual(
            period_compare.previous_period("2023-03-01", "2023-03-01"), ("2023-02-28", "2023-02-28")
        )

    def test_seven_days(self):
        self.assertEqual(
            period_compare.previous_period("2024-01-01", "2024-01-07"), ("2023-12-25", "2023-12-31")
        )

    def test_thirty_day_range(self):
        self.assertEqual(
            period_compare.previous_period("2024-01-01", "2024-01-30"), ("2023-12-02", "2023-12-31")
        )

    def test_thirty_one_day_range(self):
        self.assertEqual(
            period_compare.previous_period("2024-01-01", "2024-01-31"), ("2023-12-01", "2023-12-31")
        )

    def test_february_leap_span(self):
        # Feb 2024 has 29 days; equal-length window ends Jan 31.
        self.assertEqual(
            period_compare.previous_period("2024-02-01", "2024-02-29"), ("2024-01-03", "2024-01-31")
        )

    def test_identical_duration(self):
        import datetime

        for lo, hi in (
            ("2024-01-01", "2024-01-01"),
            ("2024-01-01", "2024-01-07"),
            ("2024-01-01", "2024-03-31"),
            ("2023-12-25", "2024-01-07"),
            ("2024-02-01", "2024-02-29"),
        ):
            plo, phi = period_compare.previous_period(lo, hi)
            want = (datetime.date.fromisoformat(hi) - datetime.date.fromisoformat(lo)).days + 1
            got = (datetime.date.fromisoformat(phi) - datetime.date.fromisoformat(plo)).days + 1
            self.assertEqual(got, want, (lo, hi))
            # Adjacent: previous ends the day the current starts.
            self.assertEqual(
                datetime.date.fromisoformat(phi) + datetime.timedelta(days=1), datetime.date.fromisoformat(lo)
            )

    def test_inverted_range_raises(self):
        with self.assertRaises(ValueError):
            period_compare.previous_period("2024-02-01", "2024-01-01")

    def test_bad_shape_raises(self):
        with self.assertRaises(ValueError):
            period_compare.previous_period("2024-13-01", "2024-01-07")


class CompareKpisTest(unittest.TestCase):
    def _got(self, csv_text, scope, platform="meta"):
        conn = _db(csv_text, platform)
        try:
            return period_compare.compare_kpis(conn, scope)
        finally:
            conn.close()

    def _got_seeded(self, scope):
        conn = _db_seeded()
        try:
            return period_compare.compare_kpis(conn, scope)
        finally:
            conn.close()

    def test_periods_and_additive_metrics(self):
        got = self._got_seeded({"date_from": "2024-01-01", "date_to": "2024-01-07"})
        self.assertEqual(got["current_period"], {"start": "2024-01-01", "end": "2024-01-07"})
        self.assertEqual(got["previous_period"], {"start": "2023-12-25", "end": "2023-12-31"})
        impr = got["metrics"]["impressions"]
        self.assertEqual(impr["current"], 25000)
        self.assertEqual(impr["previous"], 20000)
        self.assertEqual(impr["percent_change"], 25.0)
        self.assertEqual(impr["direction"], "up")
        self.assertEqual(impr["sentiment"], "good")
        self.assertEqual(impr["state"], "compared")
        spend = got["metrics"]["spend"]
        self.assertEqual(spend["percent_change"], 50.0)
        self.assertEqual(spend["sentiment"], "neutral")

    def test_explicit_range_selects_windows(self):
        got = self._got_seeded({"date_from": "2024-01-01", "date_to": "2024-01-07"})
        self.assertEqual(got["metrics"]["clicks"]["current"], 600)
        self.assertEqual(got["metrics"]["clicks"]["previous"], 400)

    def test_ratio_metrics_recomputed_per_period(self):
        # CTR current = 600/25000 = 2.4%; previous = 400/20000 = 2.0%.
        got = self._got_seeded({"date_from": "2024-01-01", "date_to": "2024-01-07"})
        ctr = got["metrics"]["ctr"]
        self.assertAlmostEqual(ctr["current"], 0.024)
        self.assertAlmostEqual(ctr["previous"], 0.02)
        self.assertEqual(ctr["percent_change"], 20.0)
        self.assertEqual(ctr["sentiment"], "good")
        # CPA current = 300/24 = 12.5; previous = 200/20 = 10.0.
        cpa = got["metrics"]["cpa"]
        self.assertAlmostEqual(cpa["current"], 12.5)
        self.assertAlmostEqual(cpa["previous"], 10.0)
        self.assertEqual(cpa["percent_change"], 25.0)
        self.assertEqual(cpa["direction"], "up")
        self.assertEqual(cpa["sentiment"], "bad")

    def test_roas_comparison(self):
        got = self._got_seeded({"date_from": "2024-01-01", "date_to": "2024-01-07"})
        roas = got["metrics"]["roas"]
        self.assertAlmostEqual(roas["current"], 2.0)
        self.assertAlmostEqual(roas["previous"], 2.0)
        self.assertEqual(roas["percent_change"], 0.0)
        self.assertEqual(roas["direction"], "flat")
        self.assertEqual(roas["sentiment"], "neutral")

    def test_filter_propagation_apples_to_apples(self):
        # Platform=tiktok must apply to BOTH windows, not just current.
        got = self._got_seeded({"platform": ["tiktok"], "date_from": "2024-01-01", "date_to": "2024-01-07"})
        impr = got["metrics"]["impressions"]
        self.assertEqual(impr["current"], 12500)
        self.assertEqual(impr["previous"], 10000)
        self.assertEqual(impr["percent_change"], 25.0)

    def test_new_state_when_previous_window_has_zero(self):
        csv = HDR + _row("S", "a", 50, 5000, 50, 0, 100, "meta", "2023-12-26")
        csv += _row("S", "b", 50, 5000, 50, 5, 100, "meta", "2024-01-03")
        got = self._got(csv, {"date_from": "2024-01-01", "date_to": "2024-01-07"})
        conv = got["metrics"]["conversions"]
        self.assertEqual(conv["previous"], 0)
        self.assertEqual(conv["current"], 5)
        self.assertEqual(conv["state"], "new")
        self.assertIsNone(conv["percent_change"])
        # CPA previous is unmeasurable (no conversions) while current
        # is: also "new", never infinite.
        self.assertEqual(got["metrics"]["cpa"]["state"], "new")

    def test_both_zero_is_no_comparison(self):
        csv = HDR + _row("S", "a", 0, 0, 0, 0, 0, "meta", "2023-12-26")
        csv += _row("S", "b", 0, 0, 0, 0, 0, "meta", "2024-01-03")
        got = self._got(csv, {"date_from": "2024-01-01", "date_to": "2024-01-07"})
        self.assertEqual(got["metrics"]["impressions"]["state"], "none")

    def test_missing_previous_window_is_no_comparison(self):
        # No rows at all before the current window: honest "none",
        # never a fabricated percentage.
        csv = HDR + _row("S", "b", 50, 5000, 50, 5, 100, "meta", "2024-01-03")
        got = self._got(csv, {"date_from": "2024-01-01", "date_to": "2024-01-07"})
        for metric, comp in got["metrics"].items():
            self.assertEqual(comp["state"], "none", metric)
            self.assertIsNone(comp["percent_change"], metric)

    def test_full_decrease_to_zero(self):
        csv = HDR + _row("S", "a", 50, 5000, 50, 5, 100, "meta", "2023-12-26")
        csv += _row("S", "b", 0, 0, 0, 0, 0, "meta", "2024-01-03")
        got = self._got(csv, {"date_from": "2024-01-01", "date_to": "2024-01-07"})
        impr = got["metrics"]["impressions"]
        self.assertEqual(impr["state"], "compared")
        self.assertEqual(impr["percent_change"], -100.0)
        self.assertEqual(impr["direction"], "down")

    def test_no_rows_anywhere(self):
        conn = _db(HDR)
        try:
            got = period_compare.compare_kpis(conn, {})
        finally:
            conn.close()
        self.assertIsNone(got["comparison"])
        self.assertEqual(got["metrics"], {})

    def test_record_counts_distinguish_empty_from_uncomputable(self):
        # Empty scope reports zero current rows (zero placeholders);
        # a populated scope reports its row counts (missing measures
        # there mean Unavailable, never a placeholder zero).
        conn = _db(HDR)
        try:
            got = period_compare.compare_kpis(conn, {})
        finally:
            conn.close()
        self.assertEqual(got["current_n_ads"], 0)
        self.assertEqual(got["previous_n_ads"], 0)
        got = self._got_seeded({"date_from": "2024-01-01",
                                "date_to": "2024-01-07"})
        self.assertGreater(got["current_n_ads"], 0)
        self.assertGreater(got["previous_n_ads"], 0)

    def test_no_dates_uses_dataset_extent_as_current(self):
        got = self._got_seeded({})
        self.assertEqual(got["current_period"], {"start": "2023-12-25", "end": "2024-01-05"})
        self.assertEqual(got["previous_period"], {"start": "2023-12-13", "end": "2023-12-24"})

    def test_exact_date_is_a_one_day_period(self):
        csv = (
            HDR
            + _row("S", "a", 80, 8000, 80, 8, 160, "meta", "2024-01-06")
            + _row("S", "b", 100, 10000, 100, 10, 200, "meta", "2024-01-07")
        )
        got = self._got(csv, {"date": "2024-01-07"})
        self.assertEqual(got["current_period"], {"start": "2024-01-07", "end": "2024-01-07"})
        self.assertEqual(got["previous_period"], {"start": "2024-01-06", "end": "2024-01-06"})
        impr = got["metrics"]["impressions"]
        self.assertEqual(impr["current"], 10000)
        self.assertEqual(impr["previous"], 8000)
        self.assertEqual(impr["percent_change"], 25.0)

    def test_exact_date_does_not_leak_into_previous_window(self):
        # Only Jan 7 rows exist: an exact-date scope must still find
        # the empty Jan 6 window, not constrain it to Jan 7 as well.
        csv = HDR + _row("S", "b", 100, 10000, 100, 10, 200, "meta", "2024-01-07")
        got = self._got(csv, {"date": "2024-01-07"})
        self.assertEqual(got["metrics"]["impressions"]["current"], 10000)
        self.assertEqual(got["metrics"]["impressions"]["state"], "none")

    def test_single_bound_is_no_comparison(self):
        got = self._got(HDR + PREV + CUR, {"date_from": "2024-01-01"})
        self.assertIsNone(got["comparison"])

    def test_mixed_currency_nulls_money_comparison(self):
        csv = (
            HDR
            + _row("S", "a", 50, 5000, 50, 5, 100, "meta", "2023-12-26")
            + _row("S", "b", 50, 5000, 50, 5, 100, "meta", "2024-01-03")
        )
        conn = _db(csv)
        try:
            conn.execute("UPDATE ads SET currency='GBP' WHERE date='2023-12-26'")
            conn.execute("UPDATE ads SET currency='USD' WHERE date='2024-01-03'")
            conn.commit()
            got = period_compare.compare_kpis(conn, {"date_from": "2024-01-01", "date_to": "2024-01-07"})
        finally:
            conn.close()
        self.assertTrue(got["metrics"]["cpa"]["current"] is None or got["metrics"]["cpa"]["previous"] is None)
        self.assertEqual(got["metrics"]["cpa"]["state"], "none")
        # Non-money metrics still compare.
        self.assertEqual(got["metrics"]["impressions"]["state"], "compared")

    def test_empty_previous_keeps_single_currency_money_current(self):
        # Fresh import: the previous window is empty, so no
        # cross-currency comparison exists. Single-currency money
        # facts stay visible with no percentage (not coerced to
        # zero downstream); a mixed current side stays unmeasurable.
        csv = HDR + _row("S", "c1", 150, 12500, 300, 12, 300, "meta", "2024-01-02")
        conn = _db(csv)
        try:
            got = period_compare.compare_kpis(conn, {})
        finally:
            conn.close()
        spend = got["metrics"]["spend"]
        self.assertEqual(spend["current"], 150)
        self.assertIsNone(spend["previous"])
        self.assertIsNone(spend["percent_change"])
        self.assertEqual(spend["state"], "none")
        roas = got["metrics"]["roas"]
        self.assertEqual(roas["current"], 2.0)
        self.assertIsNone(roas["previous"])
        self.assertEqual(roas["state"], "none")

    def test_no_infinity_or_nan_anywhere(self):
        import math

        got = self._got_seeded({"date_from": "2024-01-01", "date_to": "2024-01-07"})
        for metric, comp in got["metrics"].items():
            for key in ("current", "previous", "percent_change", "abs_change"):
                val = comp[key]
                if isinstance(val, float):
                    self.assertFalse(math.isinf(val) or math.isnan(val), (metric, key, val))


if __name__ == "__main__":
    unittest.main()
