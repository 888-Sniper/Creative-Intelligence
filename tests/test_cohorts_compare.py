"""EXPERT 2 (COHORTS+COMPARE) tests: cohorts, compare, report (stdlib unittest)."""

import json
import os
import sqlite3
import sys
import tempfile
import threading
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
           "Link Clicks,Conversions,Vertical,Market,Funnel Stage,Date\n"
           "C1,A1,hook-a,100,10000,200,10,Beauty,Spain,lower,2026-08-01\n"
           "C2,A2,hook-b,300,30000,300,15,Food,France,top,2026-08-02\n")


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

    def test_project_filter_uses_campaign_fallback(self):
        # Fixture rows carry no project column: identity falls back to
        # campaign, matched case-insensitively like the UI sends it.
        got = benchmarks.benchmark(self.conn, "campaign",
                                   {"include_projects": ["c1"]})
        self.assertEqual(sorted(got), ["C1"])

    def test_exclude_projects_case_insensitive(self):
        got = benchmarks.benchmark(self.conn, "campaign",
                                   {"exclude_projects": ["C1"]})
        self.assertEqual(sorted(got), ["C2"])

    def test_date_filter_exact_day(self):
        rows = benchmarks.all_rows(self.conn)
        dates = sorted({r.get("date") for r in rows if r.get("date")})
        self.assertTrue(dates)
        got = benchmarks.benchmark(self.conn, "campaign",
                                   {"date": [dates[0]]})
        self.assertEqual(len(got), 1)

    def test_project_query_param_maps_to_include(self):
        import server
        self.assertEqual(server._filters_from_query({"project": ["c1"]}),
                         {"include_projects": ["c1"]})


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
            benchmarks.build_report(conn, ["Alpha"], ["cpa"], None,
                                    fmt="keynote")
        conn.close()

    def test_totals_and_cpc_retained_not_dropped(self):
        conn = seeded_db()
        rep = benchmarks.build_report(conn, ["Alpha", "Beta"],
                                      ["spend", "impressions", "cpc", "cpa"],
                                      None, fmt="csv")
        header = rep["csv"].split("\n")[0]
        self.assertEqual(header, "campaign,spend,impressions,cpc,cpa")
        self.assertIn("Alpha,200.0,20000,", rep["csv"])
        conn.close()

    def test_total_first_kpi_falls_back_to_cpa_rank(self):
        conn = seeded_db()
        rep = benchmarks.build_report(conn, None, ["spend", "cpa"],
                                      None, fmt="deck")
        self.assertEqual(rep["deck"]["rank_by"], "cpa")
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


class CreativeCompareParityTest(unittest.TestCase):
    """GET /api/compare matches campaign-compare depth: full KPI set
    plus a data-grounded why-analysis."""

    def test_full_kpis_and_why(self):
        import server
        from http.server import HTTPServer
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        try:
            conn = sqlite3.connect(db)
            schema.init_db(conn)
            ingest.insert_rows(conn, ingest.parse_csv(
                "Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
                "Link Clicks,Conversions,Video Views,Revenue\n"
                "C,ca,cka,100,10000,200,10,3000,250\n"
                "C,cb,ckb,300,30000,300,15,3000,300\n", "meta"))
            for key, hook, mode in (("cka", "question", "creator"),
                                    ("ckb", "demo_open", "branded")):
                ann = creative.blank_annotation()
                ann["hook_type"] = hook
                ann["creator_vs_branded"] = mode
                creative.save_annotation(conn, key, ann)
            conn.close()
            server.Handler.db_path = db
            httpd = HTTPServer(("127.0.0.1", 0), server.Handler)
            port = httpd.server_address[1]
            thread = threading.Thread(target=httpd.serve_forever,
                                      daemon=True)
            thread.start()
            try:
                import urllib.request
                base = "http://127.0.0.1:%d" % port
                with urllib.request.urlopen(
                        base + "/api/compare?a=cka&b=ckb") as resp:
                    got = json.loads(resp.read())
                for key in ("cka", "ckb"):
                    for kpi in ("spend", "impressions", "clicks",
                                "conversions", "cpm", "vtr", "ctr", "cpc",
                                "cpa", "roas"):
                        self.assertIn(kpi, got[key])
                self.assertEqual(got["cka"]["cpa"], 10.0)
                self.assertEqual(got["ckb"]["cpa"], 20.0)
                self.assertEqual(got["why"]["top"], "cka")
                text = " ".join(got["why"]["differences"])
                self.assertIn("CPA", text)
                self.assertIn("question", text)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=10)
        finally:
            os.unlink(db)

    def test_why_empty_selection(self):
        import server
        why = server._creative_why("", "", {}, {})
        self.assertIsNone(why["top"])

    def test_why_contrasts_all_dimensions(self):
        import server
        aa = {"hook_type": "question", "creator_vs_branded": "creator",
              "duration_s": 30.0,
              "brand_seconds": [{"start_s": 1.0, "end_s": 2.0}],
              "product_seconds": [{"start_s": 5.0, "end_s": 8.0}],
              "cta": "shop now",
              "supers": ["-20% today"],
              "structure": {
                  "hook": {"start_s": 0.0, "end_s": 3.0, "confidence": 0.9},
                  "voiceover": {"start_s": 0.0, "end_s": 30.0,
                                "confidence": 0.8}}}
        ab = {"hook_type": "demo_open", "creator_vs_branded": "branded",
              "duration_s": 15.0,
              "brand_seconds": [{"start_s": 4.0, "end_s": 6.0}],
              "product_seconds": [],
              "structure": {
                  "hook": {"start_s": 0.0, "end_s": 3.0, "confidence": 0.9}}}
        da = {"spend": 100.0, "impressions": 10000, "clicks": 200,
              "conversions": 10, "cpa": 10.0, "ctr": 0.02, "vtr": 0.3,
              "cpc": 0.5, "cpm": 10.0, "roas": 2.0, "annotation": aa}
        db = {"spend": 100.0, "impressions": 10000, "clicks": 100,
              "conversions": 5, "cpa": 20.0, "ctr": 0.01, "vtr": 0.2,
              "cpc": 1.0, "cpm": 10.0, "roas": 1.0, "annotation": ab}
        why = server._creative_why("cka", "ckb", da, db)
        text = " ".join(why["differences"])
        self.assertEqual(why["top"], "cka")
        for needle in ("Length:", "Brand appears at", "Product appears in",
                       "CTA is annotated", "supers are annotated",
                       "Voiceover is annotated", "Structure:"):
            self.assertIn(needle, text)


class CreativesFilterTest(unittest.TestCase):
    """GET /api/creatives honours canonical axes server-side, so the
    Creative Library can never be wrongly emptied by client text blobs."""

    def _serve(self, db):
        import server
        from http.server import HTTPServer
        server.Handler.db_path = db
        httpd = HTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        return httpd, thread, "http://127.0.0.1:%d" % httpd.server_address[1]

    def test_vertical_filter_reaches_creatives(self):
        import urllib.request
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        try:
            conn = sqlite3.connect(db)
            schema.init_db(conn)
            ingest.insert_rows(conn, ingest.parse_csv(DIM_CSV, "meta"))
            conn.close()
            httpd, thread, base = self._serve(db)
            try:
                with urllib.request.urlopen(base + "/api/creatives") as resp:
                    all_keys = sorted(r["creative_key"]
                                      for r in json.loads(resp.read()))
                self.assertEqual(all_keys, ["hook-a", "hook-b"])
                with urllib.request.urlopen(
                        base + "/api/creatives?vertical=Beauty") as resp:
                    got = sorted(r["creative_key"]
                                 for r in json.loads(resp.read()))
                self.assertEqual(got, ["hook-a"])
                with urllib.request.urlopen(
                        base + "/api/creatives?vertical=Food") as resp:
                    got = sorted(r["creative_key"]
                                 for r in json.loads(resp.read()))
                self.assertEqual(got, ["hook-b"])
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=10)
        finally:
            os.unlink(db)


class ReportGateTest(unittest.TestCase):
    def test_report_blocked_while_reviews_pending(self):
        import server
        from creative_intel import qa
        conn = seeded_db()
        try:
            qa.answer(conn, "what is spend?")
            self.assertGreater(qa.pending_count(conn), 0)
            with self.assertRaises(ValueError) as ctx:
                server.expert2_report_route(
                    conn, {"format": "csv", "kpis": ["cpa"]})
            self.assertIn("review-to-zero", str(ctx.exception))
            rep = server.expert2_report_route(
                conn, {"format": "csv", "kpis": ["cpa"], "override": True})
            self.assertEqual(rep["format"], "csv")
        finally:
            conn.close()

    def test_report_open_with_no_pending_reviews(self):
        import server
        conn = seeded_db()
        try:
            rep = server.expert2_report_route(
                conn, {"format": "one-pager", "kpis": ["cpa"]})
            self.assertIn("Alpha", rep["markdown"])
        finally:
            conn.close()


class ReportExtrasTest(unittest.TestCase):
    def test_deck_markdown_carry_full_content(self):
        conn = seeded_db()
        try:
            rep = benchmarks.build_report(conn, ["Alpha", "Beta"],
                                          ["cpa", "ctr"], "campaign")
            deck = rep["deck"]
            for key in ("creatives", "learnings", "recommendations"):
                self.assertIn(key, deck)
            self.assertEqual(deck["creatives"]["Alpha"]["best"]
                             ["creative_key"], "a1")
            self.assertIn("Best / watch creatives", rep["markdown"])
            self.assertIn("Creative learnings", rep["markdown"])
            self.assertIn("heuristic", rep["markdown"])
            self.assertEqual(len(deck["slides"]), 2)  # campaign slides only
        finally:
            conn.close()

    def test_strict_human_drops_unverified_insights(self):
        conn = seeded_db()
        try:
            loose = benchmarks.build_report(conn, ["Alpha", "Beta"],
                                            ["cpa", "ctr"], "campaign")
            self.assertFalse(loose["deck"]["strict_human"])
            # Seeded annotations are never verified: flags say so.
            self.assertIn(False, loose["deck"]["learnings_verified"])
            self.assertIn(False, loose["deck"]["recommendations_verified"])
            strict = benchmarks.build_report(conn, ["Alpha", "Beta"],
                                             ["cpa", "ctr"], "campaign",
                                             strict_human=True)
            self.assertTrue(strict["deck"]["strict_human"])
            self.assertGreater(strict["deck"]["unverified_excluded"], 0)
            self.assertIn("No HUMAN-VERIFIED learnings yet.",
                          strict["deck"]["learnings"])
        finally:
            conn.close()

    def test_office_files_carry_all_sections(self):
        import base64
        import zipfile
        from io import BytesIO
        conn = seeded_db()
        try:
            rep = benchmarks.build_report(conn, ["Alpha", "Beta"],
                                          ["cpa", "ctr"], "campaign", "pptx")
            zf = zipfile.ZipFile(BytesIO(base64.b64decode(rep["pptx_b64"])))
            try:
                names = zf.namelist()
                slides = sorted(n for n in names
                                if n.startswith("ppt/slides/slide"))
                self.assertGreaterEqual(len(slides), 6)
                titles = [n for n in names if "/slides/" in n
                          and n.endswith(".xml")]
                blob = b" ".join(zf.read(n) for n in titles)
                for needle in (b"Benchmarks", b"Creative learnings",
                               b"Recommendations", b"a1"):
                    self.assertIn(needle, blob)
            finally:
                zf.close()
            rep = benchmarks.build_report(conn, ["Alpha", "Beta"],
                                          ["cpa", "ctr"], "campaign", "xlsx")
            zf = zipfile.ZipFile(BytesIO(base64.b64decode(rep["xlsx_b64"])))
            try:
                sheets = sorted(n for n in zf.namelist()
                                if n.startswith("xl/worksheets/"))
                self.assertGreaterEqual(len(sheets), 6)
                wb = zf.read("xl/workbook.xml").decode()
                for needle in ("Creatives", "All Creatives", "Benchmarks",
                               "Learnings", "Next steps"):
                    self.assertIn(needle, wb)
            finally:
                zf.close()
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
