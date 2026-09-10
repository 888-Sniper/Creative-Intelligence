"""Q&A metric-correctness regressions (stdlib unittest).

Proves each Q&A branch answers the metric actually asked for — not just
that the answer is flagged grounded:
- Source ask: a VTR question compares VTR (early vs late product
  appearance over video_views/impr), never CPA; a TikTok-format question
  filters TikTok rows and compares creator vs branded formats.
- Backend qa: same two branches over the SQLite ads + annotations store.
- Both engines refuse unknown topics instead of inventing advice.
"""

import csv
import datetime
import json
import os
import sqlite3
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "Backend"))
sys.path.insert(0, os.path.join(ROOT, "Source"))

from ask import answer  # noqa: E402
from benchmarks import derived  # noqa: E402
from creative import join_metrics, load_annotations, verified  # noqa: E402
from creative_intel import ingest, qa, schema  # noqa: E402

FIXTURES = os.path.join(ROOT, "fixtures")
TIKTOK_IDS = {"GL-002-A", "GL-002-B", "HY-002-A"}


def fixture_joined():
    rows = []
    with open(os.path.join(FIXTURES, "Sample Dataset.csv")) as fh:
        for raw in csv.DictReader(fh):
            row = {k: (float(v) if k in ("spend", "impr", "clicks",
                                         "video_views", "conversions",
                                         "revenue") else v)
                   for k, v in raw.items()}
            rows.append(derived(row))
    anns = load_annotations(os.path.join(FIXTURES, "Sample Annotations.csv"))
    return rows, join_metrics(verified(anns), rows)


META_CSV = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
            "Link Clicks,Conversions,Video Views\n"
            "C1,A1,hook-a,100,10000,200,10,3000\n"
            "C1,A2,hook-b,300,30000,300,15,6000\n")
TIKTOK_CSV = ("Campaign,Ad,Video Name,Spend,Impressions,Clicks,Results,"
              "Video Views\n"
              "S1,B1,tt-creator,200,20000,400,20,8000\n"
              "S1,B2,tt-branded,100,10000,100,5,2000\n")


def fresh_db():
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    return conn


def annotate(conn, key, product_start=None, mode=None):
    ann = {}
    if product_start is not None:
        ann["product_seconds"] = [{"start_s": product_start,
                                   "end_s": product_start + 1.0}]
    if mode is not None:
        ann["creator_vs_branded"] = mode
    conn.execute(
        "INSERT INTO annotations (creative_key, schema_version,"
        " annotation_json, updated_at) VALUES (?, ?, ?, ?)",
        (key, "v0", json.dumps(ann),
         datetime.datetime.now(datetime.timezone.utc).isoformat()))
    conn.commit()


class SourceVtrTest(unittest.TestCase):
    def test_vtr_question_compares_vtr_not_cpa(self):
        rows, joined = fixture_joined()
        out = answer("Does showing the product earlier improve VTR?",
                     rows, joined)
        self.assertTrue(out["grounded"])
        self.assertIn("VTR", out["answer"])
        # Pooled VTR from the fixture: early 72500/200000, late 43500/150000.
        self.assertIn("36.2", out["answer"])
        self.assertIn("29.0", out["answer"])
        self.assertNotIn("CPA", out["answer"])
        self.assertTrue({"GL-001-A", "GL-002-B"} <= set(out["citations"]))

    def test_product_timing_phrasing_hits_vtr_branch(self):
        rows, joined = fixture_joined()
        out = answer("Should the product appear earlier in the video?",
                     rows, joined)
        self.assertTrue(out["grounded"])
        self.assertIn("VTR", out["answer"])
        self.assertNotIn("CPA", out["answer"])

    def test_vtr_needs_both_sides(self):
        rows, joined = fixture_joined()
        early_only = [r for r in joined
                      if float(r["product_first_visible_s"]) <= 3.0]
        out = answer("Does showing the product earlier improve VTR?",
                     rows, early_only)
        self.assertFalse(out["grounded"])
        self.assertEqual(out["citations"], [])


class SourceTiktokTest(unittest.TestCase):
    def test_tiktok_question_compares_formats_on_tiktok_rows(self):
        rows, joined = fixture_joined()
        out = answer("Which formats perform best on TikTok?", rows, joined)
        self.assertTrue(out["grounded"])
        self.assertIn("creator", out["answer"].lower())
        self.assertIn("2.77", out["answer"])
        # Every citation must come from TikTok-filtered rows.
        self.assertTrue(set(out["citations"]) <= TIKTOK_IDS)
        self.assertTrue(len(out["citations"]) > 0)

    def test_tiktok_question_never_reports_platform_cpa_leader(self):
        rows, joined = fixture_joined()
        out = answer("Which formats perform best on TikTok?", rows, joined)
        self.assertNotIn("leads on weighted CPA", out["answer"])

    def test_no_tiktok_rows_refuses(self):
        rows, joined = fixture_joined()
        meta_only = [r for r in joined if r["platform"] == "meta"]
        out = answer("Which formats perform best on TikTok?",
                     rows, meta_only)
        self.assertFalse(out["grounded"])
        self.assertEqual(out["citations"], [])


class SourceUnknownTest(unittest.TestCase):
    def test_unknown_topic_refuses(self):
        rows, joined = fixture_joined()
        out = answer("Should we buy radio spots?", rows, joined)
        self.assertFalse(out["grounded"])
        self.assertEqual(out["citations"], [])
        self.assertIn("Insufficient data", out["answer"])


class BackendVtrTest(unittest.TestCase):
    def _seeded(self):
        conn = fresh_db()
        ingest.insert_rows(conn, ingest.parse_csv(META_CSV, "meta"))
        ingest.insert_rows(conn, ingest.parse_csv(TIKTOK_CSV, "tiktok"))
        annotate(conn, "hook-a", product_start=1.0, mode="creator")
        annotate(conn, "hook-b", product_start=8.0, mode="branded")
        annotate(conn, "tt-creator", product_start=2.0, mode="creator")
        annotate(conn, "tt-branded", product_start=9.0, mode="branded")
        return conn

    def test_vtr_compares_early_vs_late(self):
        conn = self._seeded()
        out = qa.answer(conn, "Does early product appearance improve VTR?")
        # Early: (3000+8000)/(10000+20000)=36.7%; late: 8000/40000=20.0%.
        self.assertIn("VTR", out["answer"])
        self.assertIn("36.7%", out["answer"])
        self.assertIn("20.0%", out["answer"])
        self.assertIn("hook-a", out["answer"])
        self.assertIn("hook-b", out["answer"])
        self.assertNotIn("CPA", out["answer"])
        self.assertIn("Annotation", out["sources"])
        conn.close()

    def test_vtr_without_timing_falls_back_to_blended(self):
        conn = fresh_db()
        ingest.insert_rows(conn, ingest.parse_csv(META_CSV, "meta"))
        out = qa.answer(conn, "What is the VTR?")
        # Blended: 9000/40000 = 22.5%, top views from hook-b.
        self.assertIn("22.5%", out["answer"])
        self.assertIn("hook-b", out["answer"])
        conn.close()


class BackendTiktokTest(unittest.TestCase):
    def _seeded(self):
        conn = fresh_db()
        ingest.insert_rows(conn, ingest.parse_csv(META_CSV, "meta"))
        ingest.insert_rows(conn, ingest.parse_csv(TIKTOK_CSV, "tiktok"))
        annotate(conn, "tt-creator", mode="creator")
        annotate(conn, "tt-branded", mode="branded")
        return conn

    def test_tiktok_filters_platform_and_compares_formats(self):
        conn = self._seeded()
        out = qa.answer(conn, "Which TikTok format wins, creator or branded?")
        self.assertIn("tt-creator", out["answer"])
        self.assertIn("tt-branded", out["answer"])
        self.assertNotIn("hook-a", out["answer"])
        self.assertNotIn("hook-b", out["answer"])
        self.assertIn("creator", out["answer"])
        self.assertIn("branded", out["answer"])
        self.assertIn("CPA $10.00", out["answer"])
        self.assertIn("CPA $20.00", out["answer"])
        conn.close()

    def test_no_tiktok_rows_says_so(self):
        conn = fresh_db()
        ingest.insert_rows(conn, ingest.parse_csv(META_CSV, "meta"))
        out = qa.answer(conn, "Which TikTok format wins?")
        self.assertIn("No TikTok rows", out["answer"])
        conn.close()


class BackendUnknownTest(unittest.TestCase):
    def test_unknown_topic_refuses(self):
        conn = fresh_db()
        ingest.insert_rows(conn, ingest.parse_csv(META_CSV, "meta"))
        out = qa.answer(conn, "Should we buy radio spots?")
        self.assertIn("Insufficient data", out["answer"])
        conn.close()


if __name__ == "__main__":
    unittest.main()
