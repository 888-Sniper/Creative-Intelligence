"""EXPERT 2 (COHORTS+COMPARE) tests: cohorts, compare, report (stdlib unittest)."""

import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import benchmarks, cohorts, creative, ingest, schema  # noqa: E402

META = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
        "Link Clicks,Conversions\n"
        "Alpha,A1,a1,100,10000,200,10\n"
        "Alpha,A2,a2,100,10000,200,10\n"
        "Beta,B1,b1,300,10000,100,5\n"
        "Beta,B2,b2,300,10000,100,5\n"
        "Gamma,G1,g1,100,10000,150,8\n")
TIKTOK = ("Campaign,Ad,Video Name,Spend,Impressions,Clicks,Results\n"
          "Gamma,G2,g2,100,10000,150,8\n")


DIM_CSV = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
           "Link Clicks,Conversions,Vertical,Market,Funnel Stage\n"
           "C1,A1,hook-a,100,10000,200,10,Beauty,Spain,lower\n"
           "C2,A2,hook-b,300,30000,300,15,Food,France,top\n")


def fresh_db():
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    return conn


class FilterParamsTest(unittest.TestCase):
    def setUp(self):
        self.conn = fresh_db()
        ingest.insert_rows(self.conn, ingest.parse_csv(DIM_CSV, "meta"))

    def tearDown(self):
        self.conn.close()

    def test_vertical_filter_queries_store(self):
        got = benchmarks.benchmark(self.conn, "campaign",
                                   {"vertical": ["beauty"]})
        self.assertEqual(sorted(got), ["C1"])

    def test_funnel_alias_and_case_insensitive(self):
        got = benchmarks.benchmark(self.conn, "campaign",
                                   {"funnel": ["LOWER"]})
        self.assertEqual(sorted(got), ["C1"])
        got = benchmarks.benchmark(self.conn, "campaign",
                                   {"funnel": ["top"]})
        self.assertEqual(sorted(got), ["C2"])

    def test_multi_axis_market(self):
        got = benchmarks.benchmark(self.conn, "platform",
                                   {"market": ["spain"],
                                    "vertical": ["BEAUTY"]})
        self.assertEqual(sorted(got), ["meta"])

    def test_no_filters_returns_all(self):
        got = benchmarks.benchmark(self.conn, "campaign", {})
        self.assertEqual(sorted(got), ["C1", "C2"])

    def test_query_parser_ignores_all_and_unknown(self):
        import server
        self.assertEqual(server._filters_from_query(
            {"vertical": ["Beauty"], "platform": ["all", ""],
             "hack": ["x"]}), {"vertical": ["Beauty"]})
        self.assertEqual(server._filters_from_query({}), {})


def seeded_db():
    conn = fresh_db()
    ingest.insert_rows(conn, ingest.parse_csv(META, "meta"))
    ingest.insert_rows(conn, ingest.parse_csv(TIKTOK, "tiktok"))
    for key, hook, mode in (("a1", "question", "creator"),
                            ("a2", "question", "creator"),
                            ("b1", "demo_open", "branded"),
                            ("b2", "demo_open", "branded"),
                            ("g1", "question", "creator"),
                            ("g2", "demo_open", "branded")):
        ann = creative.blank_annotation()
        ann["hook_type"] = hook
        ann["creator_vs_branded"] = mode
        creative.save_annotation(conn, key, ann)
    return conn


class FilterBuilderTest(unittest.TestCase):
    def test_platform_filter(self):
        conn = seeded_db()
        meta = benchmarks.benchmark_filtered(conn, {"platform": "meta"})
        self.assertEqual(meta["n_ads"], 5)
        tik = benchmarks.benchmark_filtered(conn, {"platform": ["tiktok"]})
        self.assertEqual(tik["n_ads"], 1)
        conn.close()

    def test_include_exclude_projects(self):
        conn = seeded_db()
        inc = benchmarks.benchmark_filtered(conn, {"include_projects": ["Alpha"]})
        self.assertEqual(inc["n_ads"], 2)
        exc = benchmarks.benchmark_filtered(conn, {"exclude_projects": ["Alpha"]})
        self.assertEqual(exc["n_ads"], 4)
        self.assertNotIn("Alpha", exc["project_list"])
        conn.close()

    def test_unknown_filter_key_rejected(self):
        conn = seeded_db()
        with self.assertRaises(ValueError):
            benchmarks.benchmark_filtered(conn, {"hack": "x"})
        with self.assertRaises(ValueError):
            cohorts.save_cohort(conn, "bad", {"hack": "x"})
        conn.close()

    def test_bands_spend_weighted(self):
        got = benchmarks.describe_bands([1.0, 3.0], [100, 300])
        self.assertAlmostEqual(got["mean_weighted"], 2.5)
        self.assertEqual(got["n"], 2)
        self.assertLessEqual(got["p25"], got["median"])
        self.assertLessEqual(got["median"], got["p75"])

    def test_min_n_guard(self):
        conn = fresh_db()
        ingest.insert_rows(conn, ingest.parse_csv(
            "Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
            "Link Clicks,Conversions\nSolo,S1,s1,100,10000,200,10\n", "meta"))
        tiny = benchmarks.benchmark_filtered(conn, {})
        self.assertEqual(tiny["status"], "insufficient")
        conn.close()
        conn = seeded_db()
        full = benchmarks.benchmark_filtered(conn, {})
        self.assertEqual(full["status"], "ok")
        self.assertEqual(full["stats"]["projects"], 3)
        conn.close()


class CohortPersistenceTest(unittest.TestCase):
    def test_save_list_get_build_delete(self):
        conn = seeded_db()
        saved = cohorts.save_cohort(conn, "meta-only", {"platform": "meta"})
        self.assertEqual(saved["filters"], {"platform": ["meta"]})
        names = [c["name"] for c in cohorts.list_cohorts(conn)]
        self.assertIn("meta-only", names)
        got = cohorts.get_cohort(conn, name="meta-only")
        self.assertEqual(got["id"], saved["id"])
        built = cohorts.build_cohort(conn, name="meta-only")
        self.assertEqual(built["n_ads"], 5)
        self.assertEqual(built["cohort"]["name"], "meta-only")
        with self.assertRaises(ValueError):
            cohorts.save_cohort(conn, "meta-only", {})
        with self.assertRaises(ValueError):
            cohorts.get_cohort(conn, name="nope")
        out = cohorts.delete_cohort(conn, name="meta-only")
        self.assertTrue(out["ok"])
        self.assertEqual(cohorts.list_cohorts(conn), [])
        conn.close()

    def test_adhoc_build(self):
        conn = seeded_db()
        built = cohorts.build_cohort(conn, filters={"platform": "tiktok"})
        self.assertEqual(built["n_ads"], 1)
        self.assertEqual(built["status"], "insufficient")
        conn.close()


class CompareTest(unittest.TestCase):
    def test_per_campaign_kpis(self):
        conn = seeded_db()
        comp = benchmarks.compare_campaigns(conn, ["Alpha", "Beta"], rank_by="cpa")
        for name in ("Alpha", "Beta"):
            for kpi in ("cpm", "vtr", "ctr", "cpa", "roas"):
                self.assertIn(kpi, comp["kpis"][name])
        self.assertEqual(comp["kpis"]["Alpha"]["cpa"], 10.0)
        self.assertEqual(comp["kpis"]["Beta"]["cpa"], 60.0)
        self.assertEqual(comp["ranking"][0], "Alpha")
        conn.close()

    def test_rank_direction(self):
        conn = seeded_db()
        by_ctr = benchmarks.compare_campaigns(conn, ["Alpha", "Beta"], rank_by="ctr")
        self.assertEqual(by_ctr["ranking"][0], "Alpha")  # 0.02 > 0.01
        with self.assertRaises(ValueError):
            benchmarks.compare_campaigns(conn, ["Alpha"], rank_by="nope")
        with self.assertRaises(ValueError):
            benchmarks.compare_campaigns(conn, ["Missing"])
        conn.close()

    def test_why_analysis_names_differences(self):
        conn = seeded_db()
        comp = benchmarks.compare_campaigns(conn, ["Alpha", "Beta"], rank_by="cpa")
        text = " ".join(comp["why"]["differences"])
        self.assertIn("hook_type", text)
        self.assertIn("creator mode", text)
        self.assertEqual(comp["why"]["top"], "Alpha")
        self.assertEqual(comp["why"]["bottom"], "Beta")
        conn.close()


class ReportTest(unittest.TestCase):
    def test_one_pager_csv_deck(self):
        conn = seeded_db()
        rep = benchmarks.build_report(conn, ["Alpha", "Beta"], ["cpa", "ctr"],
                                      "campaign", fmt="one-pager")
        self.assertIn("Alpha", rep["markdown"])
        self.assertIn("Beta", rep["markdown"])
        csv_rep = benchmarks.build_report(conn, ["Alpha", "Beta"], ["cpa"],
                                          None, fmt="csv")
        self.assertTrue(csv_rep["csv"].startswith("campaign,cpa\n"))
        self.assertIn("Alpha,10.0", csv_rep["csv"])
        deck_rep = benchmarks.build_report(conn, ["Alpha", "Beta"], ["cpa", "ctr"],
                                           None, fmt="deck")
        self.assertEqual(len(deck_rep["deck"]["slides"]), 2)
        self.assertTrue(deck_rep["deck"]["why"])
        with self.assertRaises(ValueError):
            benchmarks.build_report(conn, ["Alpha"], [], None)
        with self.assertRaises(ValueError):
            benchmarks.build_report(conn, ["Alpha"], ["cpa"], None, fmt="pptx")
        conn.close()


class ServerRoutesTest(unittest.TestCase):
    def _serve(self, db_path):
        import threading
        from http.server import HTTPServer
        import server as srv
        srv.Handler.db_path = db_path
        httpd = HTTPServer(("127.0.0.1", 0), srv.Handler)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        return httpd, port

    def test_http_compare_cohorts_report(self):
        import urllib.request
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        try:
            conn = sqlite3.connect(db)
            schema.init_db(conn)
            conn.close()
            conn = sqlite3.connect(db)
            ingest.insert_rows(conn, ingest.parse_csv(META, "meta"))
            ingest.insert_rows(conn, ingest.parse_csv(TIKTOK, "tiktok"))
            conn.close()
            httpd, port = self._serve(db)
            try:
                base = "http://127.0.0.1:%d" % port
                with urllib.request.urlopen(
                        base + "/api/compare/campaigns?campaigns=Alpha,Beta"
                        "&rank_by=cpa") as resp:
                    comp = json.loads(resp.read())
                self.assertEqual(comp["ranking"][0], "Alpha")
                self.assertTrue(comp["why"]["differences"])
                payload = json.dumps({"name": "meta-only",
                                      "filters": {"platform": "meta"}}).encode()
                req = urllib.request.Request(base + "/api/cohorts", data=payload,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req) as resp:
                    saved = json.loads(resp.read())
                self.assertEqual(saved["name"], "meta-only")
                with urllib.request.urlopen(base + "/api/cohorts/build?name=meta-only") as resp:
                    built = json.loads(resp.read())
                self.assertEqual(built["n_ads"], 5)
                payload = json.dumps({"campaigns": ["Alpha", "Beta"],
                                      "kpis": ["cpa", "ctr"],
                                      "format": "csv"}).encode()
                req = urllib.request.Request(base + "/api/report", data=payload,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req) as resp:
                    rep = json.loads(resp.read())
                self.assertIn("Alpha,10.0", rep["csv"])
                # Legacy routes still serve.
                with urllib.request.urlopen(base + "/api/benchmarks?group_by=campaign") as resp:
                    legacy = json.loads(resp.read())
                self.assertIn("Alpha", legacy)
            finally:
                httpd.shutdown()
                httpd.server_close()
        finally:
            os.unlink(db)


if __name__ == "__main__":
    unittest.main()
