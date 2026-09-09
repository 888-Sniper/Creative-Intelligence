"""Extended benchmark totals: summarize() exposes the full Overview KPI set.

Additive keys only (cpm / vtr / roas / revenue / clicks / conversions /
video_views); pre-existing keys keep their exact meaning.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import benchmarks


class SummarizeTotalsTest(unittest.TestCase):
    def test_extended_kpis_match_hand_computation(self):
        rows = [
            {"spend": 100.0, "impressions": 10000, "clicks": 200,
             "conversions": 10, "video_views": 3000, "revenue": 250.0,
             "conv_rate": 0.001, "creative_key": "a"},
            {"spend": 300.0, "impressions": 30000, "clicks": 300,
             "conversions": 30, "video_views": 6000, "revenue": 750.0,
             "conv_rate": 0.001, "creative_key": "b"},
        ]
        got = benchmarks.summarize(rows)
        # Pre-existing keys unchanged.
        self.assertEqual(got["spend"], 400.0)
        self.assertEqual(got["impressions"], 40000)
        self.assertEqual(got["ctr"], 0.0125)
        self.assertEqual(got["cpc"], 0.8)
        self.assertEqual(got["cpa"], 10.0)
        # Extended keys.
        self.assertEqual(got["clicks"], 500)
        self.assertEqual(got["conversions"], 40)
        self.assertEqual(got["video_views"], 9000)
        self.assertEqual(got["revenue"], 1000.0)
        self.assertEqual(got["cpm"], 10.0)
        self.assertEqual(got["vtr"], 0.225)
        self.assertEqual(got["roas"], 2.5)

    def test_extended_kpis_zero_safe(self):
        rows = [{"spend": 0.0, "impressions": 0, "clicks": 0,
                 "conversions": 0, "conv_rate": 0.0,
                 "creative_key": "z"}]
        got = benchmarks.summarize(rows)
        self.assertEqual(got["cpm"], 0.0)
        self.assertEqual(got["vtr"], 0.0)
        self.assertEqual(got["roas"], 0.0)
        self.assertEqual(got["revenue"], 0.0)


if __name__ == "__main__":
    unittest.main()
