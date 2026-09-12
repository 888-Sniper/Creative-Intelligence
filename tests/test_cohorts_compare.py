"""EXPERT 2 (COHORTS+COMPARE) tests: cohorts, compare, report (stdlib unittest)."""

import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))
from conftest import temp_db_path  # noqa: E402
from creative_intel import benchmarks, cohorts, creative, ingest, schema  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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


class CohortScopeTest(unittest.TestCase):
    SCOPE_CSV = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
                 "Link Clicks,Conversions,Vertical,Market,Funnel Stage,Date\n"
                 "C1,A1,hook-a,100,10000,200,10,Beauty,Spain,lower,2026-08-01\n"
                 "C1,A2,hook-b,100,10000,200,10,Beauty,Spain,lower,2026-08-02\n"
                 "C2,A3,hook-c,100,10000,200,10,Beauty,Spain,lower,2026-08-03\n")

    def _db(self):
        conn = fresh_db()
        ingest.insert_rows(
            conn, ingest.parse_csv(self.SCOPE_CSV, "meta", "upload"))
        return conn

    def test_build_copies_campaign_and_dates(self):
        from ci_backend import actions as server
        conn = self._db()
        try:
            got = server.expert2_cohort_build_route(conn, {
                "metric": ["cpa"], "campaign": ["C1"],
                "date_from": ["2026-08-02"], "date_to": ["2026-08-02"]})
            self.assertEqual(got["filters"]["campaign"], ["C1"])
            self.assertEqual(got["filters"]["date_from"], "2026-08-02")
            self.assertEqual(got["filters"]["date_to"], "2026-08-02")
            self.assertEqual(got["n_ads"], 1)
            all_rows = server.expert2_cohort_build_route(
                conn, {"metric": ["cpa"]})
            self.assertEqual(all_rows["n_ads"], 3)
        finally:
            conn.close()


class RevenueProvenanceTest(unittest.TestCase):
    REV = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
           "Link Clicks,Conversions,Revenue\n"
           "C1,A1,a1,100,10000,200,10,250\n"
           "C1,A2,a2,100,10000,200,10,0\n")
    NOREV = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
             "Link Clicks,Conversions\n"
             "C1,A1,a1,100,10000,200,10\n")

    def test_reported_flag_at_parse(self):
        rows, _q = ingest.parse_csv_report(self.REV, "meta", "upload")
        self.assertEqual(
            [r["revenue_reported"] for r in rows], [True, True])
        self.assertEqual([r["revenue"] for r in rows], [250.0, 0.0])
        rows, _q = ingest.parse_csv_report(self.NOREV, "meta", "upload")
        self.assertEqual([r["revenue_reported"] for r in rows], [False])

    def test_roas_none_when_unavailable_zero_when_reported(self):
        conn = fresh_db()
        try:
            ingest.insert_rows(
                conn, ingest.parse_csv(self.NOREV, "meta", "upload"))
            kpis = benchmarks.kpis_for_rows(
                benchmarks.all_rows(conn))
            self.assertIsNone(kpis["roas"])
            conn2 = fresh_db()
            ingest.insert_rows(
                conn2, ingest.parse_csv(self.REV, "meta", "upload"))
            kpis2 = benchmarks.kpis_for_rows(
                benchmarks.all_rows(conn2))
            # (250 + 0) / (100 + 100) = 1.25, reported zero counts.
            self.assertEqual(kpis2["roas"], 1.25)
            conn2.close()
        finally:
            conn.close()

    def test_roas_of_unit(self):
        self.assertIsNone(benchmarks.roas_of(0.0, 100.0, False))
        self.assertEqual(benchmarks.roas_of(0.0, 100.0, True), 0.0)
        self.assertEqual(benchmarks.roas_of(50.0, 100.0, False), 0.5)
        self.assertIsNone(benchmarks.roas_of(50.0, 0.0, True))


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
        from ci_backend import actions as server
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
        from ci_backend import actions as server
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

    def test_bands_skip_none_never_zero(self):
        got = benchmarks.describe_bands([None, 2.0, None, 4.0], [10, 20, 30, 40])
        self.assertEqual(got["n"], 2)
        self.assertEqual(got["n_missing"], 2)
        self.assertAlmostEqual(got["mean_weighted"], (2.0 * 20 + 4.0 * 40) / 60,
                                   places=4)
        self.assertEqual(benchmarks.describe_bands([], [])["n"], 0)
        # A16: an empty valid population has no measured centre or
        # spread — every numeric band is None, never a 0.0 that reads
        # as a measured benchmark.
        empty = benchmarks.describe_bands([None, None], [5, 6])
        self.assertEqual((empty["n"], empty["n_missing"]), (0, 2))
        for key in ("mean_weighted", "p25", "median", "p75"):
            self.assertIsNone(empty[key])

    def test_zero_conversion_rows_do_not_crash_benchmark(self):
        conn = fresh_db()
        try:
            ingest.insert_rows(conn, ingest.parse_csv(
                "Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
                "Link Clicks,Conversions\n"
                "Solo,S1,s1,100,10000,200,0\n"
                "Solo,S2,s2,50,5000,100,0\n", "meta"))
            got = benchmarks.benchmark_filtered(conn, {})
            self.assertEqual(got["n_ads"], 2)
            self.assertEqual(got["stats"]["n"], 0)
            self.assertEqual(got["stats"]["n_missing"], 2)
            self.assertEqual(got["status"], "insufficient")
        finally:
            conn.close()

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
        # User-facing attribute names are human words, not column keys.
        self.assertIn("Hook type", text)
        self.assertIn("Creator mode", text)
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

    def test_csv_quotes_campaign_names_with_commas(self):
        import csv as csv_mod
        import io as io_mod
        conn = seeded_db()
        conn.execute("UPDATE ads SET campaign=? WHERE campaign=?",
                     ("Alpha, Q3", "Alpha"))
        conn.commit()
        try:
            rep = benchmarks.build_report(conn, ["Alpha, Q3"], ["cpa"],
                                          None, fmt="csv")
            parsed = list(csv_mod.reader(io_mod.StringIO(rep["csv"])))
            self.assertEqual(parsed[0], ["campaign", "cpa"])
            self.assertEqual(parsed[1][0], "Alpha, Q3")
            self.assertEqual(len(parsed[1]), 2)
        finally:
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
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from conftest import make_client, mint_admin
        client = make_client(db_path)
        client.headers.update(mint_admin(db_path))
        return client

    def test_http_compare_cohorts_report(self):
        db = temp_db_path()
        try:
            conn = sqlite3.connect(db)
            schema.init_db(conn)
            conn.close()
            conn = sqlite3.connect(db)
            ingest.insert_rows(conn, ingest.parse_csv(META, "meta"))
            ingest.insert_rows(conn, ingest.parse_csv(TIKTOK, "tiktok"))
            conn.close()
            client = self._serve(db)
            comp = client.get("/api/compare/campaigns?campaigns=Alpha,Beta"
                          "&rank_by=cpa").json()
            self.assertEqual(comp["ranking"][0], "Alpha")
            self.assertTrue(comp["why"]["differences"])
            saved = client.post("/api/cohorts",
                            json={"name": "meta-only",
                                  "filters": {"platform": "meta"}}).json()
            self.assertEqual(saved["name"], "meta-only")
            built = client.get("/api/cohorts/build?name=meta-only").json()
            self.assertEqual(built["n_ads"], 5)
            rep = client.post("/api/report",
                          json={"campaigns": ["Alpha", "Beta"],
                                "kpis": ["cpa", "ctr"],
                                "format": "csv"}).json()
            self.assertIn("Alpha,10.0", rep["csv"])
            # Legacy routes still serve.
            legacy = client.get("/api/benchmarks?group_by=campaign").json()
            self.assertIn("Alpha", legacy)
        finally:
            os.unlink(db)


class CreativeCompareParityTest(unittest.TestCase):
    """GET /api/compare matches campaign-compare depth: full KPI set
    plus a data-grounded why-analysis."""

    def test_full_kpis_and_why(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from conftest import make_client, mint_admin
        db = temp_db_path()
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
            _client = make_client(db)
            _client.headers.update(mint_admin(db))
            got = _client.get("/api/compare?a=cka&b=ckb").json()
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
            os.unlink(db)

    def test_rank_by_roas_crowns_single_roas_winner(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from conftest import make_client, mint_admin
        db = temp_db_path()
        try:
            conn = sqlite3.connect(db)
            schema.init_db(conn)
            ingest.insert_rows(conn, ingest.parse_csv(
                "Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
                "Link Clicks,Conversions,Video Views,Revenue\n"
                "C,ca,cka,100,10000,200,10,3000,150\n"
                "C,cb,ckb,300,30000,300,10,3000,900\n", "meta"))
            conn.close()
            _client = make_client(db)
            _client.headers.update(mint_admin(db))
            got = _client.get("/api/compare?a=cka&b=ckb&rank_by=roas").json()
            # CPA-top is cka (10 vs 30) but the ROAS winner is ckb
            # (3.0 vs 1.5): one winner, controlled by rank_by.
            self.assertEqual(got["cka"]["cpa"], 10.0)
            self.assertEqual(got["ckb"]["roas"], 3.0)
            self.assertEqual(got["rank_by"], "roas")
            self.assertEqual(got["ranking"], ["ckb", "cka"])
            self.assertEqual(got["winner"], "ckb")
            self.assertEqual(got["why"]["top"], "ckb")
        finally:
            os.unlink(db)

    def test_why_empty_selection(self):
        from ci_backend import actions as server
        why = server._creative_why("", "", {}, {})
        self.assertIsNone(why["top"])

    def test_why_contrasts_all_dimensions(self):
        from ci_backend import actions as server
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
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from conftest import make_client, mint_admin
        _client = make_client(db)
        _client.headers.update(mint_admin(db))
        return _client

    def test_vertical_filter_reaches_creatives(self):
        db = temp_db_path()
        try:
            conn = sqlite3.connect(db)
            schema.init_db(conn)
            ingest.insert_rows(conn, ingest.parse_csv(DIM_CSV, "meta"))
            conn.close()
            _client = self._serve(db)
            all_keys = sorted(r["creative_key"]
                              for r in _client.get("/api/creatives").json())
            self.assertEqual(all_keys, ["hook-a", "hook-b"])
            got = sorted(r["creative_key"] for r in _client.get(
                "/api/creatives?vertical=Beauty").json())
            self.assertEqual(got, ["hook-a"])
            got = sorted(r["creative_key"] for r in _client.get(
                "/api/creatives?vertical=Food").json())
            self.assertEqual(got, ["hook-b"])
        finally:
            os.unlink(db)


class ReportGateTest(unittest.TestCase):
    def test_report_blocked_while_reviews_pending(self):
        from ci_backend import actions as server
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
        from ci_backend import actions as server
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
            # No verified annotations: strict best/watch are empty.
            self.assertIsNone(strict["deck"]["creatives"]["Alpha"]["best"])
        finally:
            conn.close()

    def test_strict_prefers_verified_creatives(self):
        conn = seeded_db()
        try:
            creative.mark_verified(conn, "a2")
            strict = benchmarks.build_report(conn, ["Alpha"],
                                             ["cpa", "ctr"], None,
                                             strict_human=True)
            best = strict["deck"]["creatives"]["Alpha"]["best"]
            self.assertIsNotNone(best)
            self.assertEqual(best["creative_key"], "a2")
            self.assertTrue(best["verified"])
            loose = benchmarks.build_report(conn, ["Alpha"],
                                            ["cpa", "ctr"], None)
            self.assertEqual(
                loose["deck"]["creatives"]["Alpha"]["best"]["creative_key"],
                "a1")
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
                for needle in (b"Benchmarks", b"Creative Learnings",
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
                               "Learnings", "Next Steps"):
                    self.assertIn(needle, wb)
            finally:
                zf.close()
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
