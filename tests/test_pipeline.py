"""MVP test suite (stdlib unittest)."""

import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Source"))

from creative_intel import (benchmarks, creative, export_gate, ingest,
                            providers, retention, schema)

META_CSV = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,Link Clicks,"
            "Conversions\nC1,A1,hook-a,100,10000,200,10\nC1,A2,hook-b,300,30000,300,15\n")
TIKTOK_CSV = ("Campaign,Ad,Video Name,Spend,Impressions,Clicks,Results\n"
              "S1,B1,hook-a,200,20000,400,20\n")


def fresh_db():
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    return conn


class IngestTest(unittest.TestCase):
    def test_meta_aliases(self):
        rows = ingest.parse_csv(META_CSV, "meta")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["spend"], 100.0)
        self.assertEqual(rows[0]["creative_key"], "hook-a")
        self.assertEqual(rows[1]["impressions"], 30000)

    def test_tiktok_aliases(self):
        rows = ingest.parse_csv(TIKTOK_CSV, "tiktok")
        self.assertEqual(rows[0]["clicks"], 400)
        self.assertEqual(rows[0]["conversions"], 20.0)

    def test_empty_csv_rejected(self):
        with self.assertRaises(ValueError):
            ingest.parse_csv("   \n", "meta")

    def test_excel_without_openpyxl_errors_clearly(self):
        try:
            import openpyxl  # noqa
            self.skipTest("openpyxl installed")
        except ImportError:
            with self.assertRaises(ValueError):
                ingest.parse_workbook("x.xlsx", "meta")

    def test_insert_creates_creatives(self):
        conn = fresh_db()
        n = ingest.insert_rows(conn, ingest.parse_csv(META_CSV, "meta"))
        self.assertEqual(n, 2)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM creatives").fetchone()[0], 2)
        conn.close()

    def test_garbage_and_nonfinite_quarantined(self):
        dirty = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
                 "Link Clicks,Conversions\n"
                 "C1,A1,good,100,10000,200,10\n"
                 "C1,A2,bad-spend,abc,10000,200,10\n"
                 "C1,A3,inf-spend,inf,10000,200,10\n"
                 "C1,A4,nan-clicks,100,10000,nan,10\n")
        rows, quarantined = ingest.parse_csv_report(dirty, "meta")
        self.assertEqual([r["creative_key"] for r in rows], ["good"])
        self.assertEqual([q["source_row"] for q in quarantined], [3, 4, 5])
        self.assertTrue(all(q["reason"] for q in quarantined))
        # Lenient wrapper keeps its contract: clean rows only.
        self.assertEqual(len(ingest.parse_csv(dirty, "meta")), 1)

    def test_ingest_rejects_bad_payload(self):
        import server
        conn = fresh_db()
        with self.assertRaises(ValueError):
            server.apply_action(conn, "ingest", {}, providers.Providers())
        with self.assertRaises(ValueError):
            server.apply_action(conn, "ingest", {"csv": META_CSV},
                                providers.Providers())
        conn.close()

    def test_load_fixtures_into_temp_db(self):
        import server
        import tempfile
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        try:
            total = server.load_fixtures(db)
            self.assertGreater(total, 0)
        finally:
            os.unlink(db)


class BenchmarkTest(unittest.TestCase):
    def test_spend_weighted_cpa(self):
        conn = fresh_db()
        ingest.insert_rows(conn, ingest.parse_csv(META_CSV, "meta"))
        got = benchmarks.benchmark(conn, "campaign")
        self.assertEqual(got["C1"]["spend"], 400.0)
        self.assertEqual(got["C1"]["cpa"], 16.0)  # 400/25
        self.assertAlmostEqual(got["C1"]["ctr"], 500 / 40000, places=4)
        conn.close()

    def test_bad_group_rejected(self):
        conn = fresh_db()
        with self.assertRaises(ValueError):
            benchmarks.benchmark(conn, "hack")
        conn.close()


class CreativeTest(unittest.TestCase):
    def test_blank_validates(self):
        self.assertEqual(creative.validate(creative.blank_annotation()), [])

    def test_bad_hook_rejected(self):
        ann = creative.blank_annotation()
        ann["hook_type"] = "mind_control"
        self.assertTrue(creative.validate(ann))

    def test_pipeline_then_gate(self):
        conn = fresh_db()
        prov = providers.Providers()
        ingest.insert_rows(conn, ingest.parse_csv(META_CSV, "meta"))
        report = creative.run_pipeline(conn, "hook-a", prov)
        self.assertEqual(len(report["stages"]), 5)
        self.assertEqual(report["annotation"]["status"], "auto")
        with self.assertRaises(export_gate.ExportBlocked):
            export_gate.build_one_pager(conn, ["hook-a"], {})
        creative.mark_verified(conn, "hook-a")
        out = export_gate.build_one_pager(conn, ["hook-a"], {})
        self.assertIn("hook-a", out["markdown"])
        conn.close()

    def test_verify_without_annotation_fails(self):
        conn = fresh_db()
        conn.execute("INSERT INTO creatives (creative_key) VALUES ('x')")
        with self.assertRaises(ValueError):
            creative.mark_verified(conn, "x")
        conn.close()


class RetentionTest(unittest.TestCase):
    def test_join_segments(self):
        conn = fresh_db()
        prov = providers.Providers()
        ingest.insert_rows(conn, ingest.parse_csv(META_CSV, "meta"))
        creative.run_pipeline(conn, "hook-a", prov)
        conn.executemany(
            "INSERT INTO retention VALUES (?, ?, ?)",
            [("hook-a", 0.0, 100.0), ("hook-a", 3.0, 80.0),
             ("hook-a", 27.0, 40.0)])
        segs = {s["segment"]: s for s in retention.join_segments(conn, "hook-a")}
        self.assertEqual(segs["hook"]["drop_pts"], 20.0)
        self.assertEqual(segs["cta"]["drop_pts"], 0.0)
        conn.close()


class CrossEngineTest(unittest.TestCase):
    def test_source_backend_agree_on_ratios(self):
        from benchmarks import derived as source_derived
        conn = fresh_db()
        ingest.insert_rows(conn, ingest.parse_csv(META_CSV, "meta"))
        got = benchmarks.benchmark(conn, "campaign")["C1"]
        total = {"spend": 400.0, "impr": 40000, "clicks": 500,
                 "video_views": 0, "conversions": 25.0, "revenue": 0.0}
        mine = source_derived(dict(total))
        self.assertAlmostEqual(got["cpa"], mine["cpa"], places=2)
        self.assertAlmostEqual(got["ctr"], mine["ctr"], places=4)
        conn.close()


class ReplayTest(unittest.TestCase):
    def test_log_round_trip(self):
        import server
        conn = fresh_db()
        prov = providers.Providers()
        payload = {"platform": "meta", "source": "upload", "csv": META_CSV}
        server.apply_action(conn, "ingest", payload, prov)
        from creative_intel import replay
        replay.log(conn, "ingest", payload)
        hist = replay.history(conn)
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["action"], "ingest")
        self.assertEqual(hist[0]["payload"], payload)
        mem = sqlite3.connect(":memory:")
        schema.init_db(mem)
        server.apply_action(mem, hist[0]["action"], hist[0]["payload"], prov)
        self.assertEqual(mem.execute("SELECT COUNT(*) FROM ads").fetchone()[0], 2)
        conn.close()
        mem.close()


if __name__ == "__main__":
    unittest.main()
