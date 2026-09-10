"""Campaign Detail recommendations: grounded, KPI-aware, report-parity."""

import json
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import benchmarks, creative, ingest, schema

CSV = ("campaign,ad set,ad name,spend,impressions,clicks,conversions,"
       "revenue,market,date\n"
       # CPA winner (2.0), ROAS loser (1.0x): creator demo, early product.
       "Alpha,Set1,win-cpa,10,1000,20,5,10,Spain,2026-08-01\n"
       # CPA loser (50.0), ROAS loser (0.5x): branded offer, late product.
       "Alpha,Set1,lose-cpa,100,2000,30,2,50,France,2026-08-01\n"
       # CPA mid (10.0), ROAS winner (8.0x): creator demo, early product.
       "Alpha,Set1,mid-roas,100,4000,80,10,800,Spain,2026-08-02\n"
       # Peer campaign for the benchmark gap (CPA 20.0, ROAS 1.0x).
       "Beta,Set9,beta-1,60,3000,60,3,60,Spain,2026-08-01\n")


def _ann(**over):
    ann = creative.blank_annotation()
    ann.update(over)
    return ann


def _conn():
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    # Fresh distinct facts: plain append stores the identical rows that
    # upsert_rows would (keeps this suite independent of the sync layer).
    ingest.insert_rows(conn, ingest.parse_csv(CSV, "meta"))
    creative.save_annotation(conn, "win-cpa", _ann(
        hook_type="demo_open", creator_vs_branded="creator",
        duration_s=12.0, product_seconds=[{"start_s": 1, "end_s": 3}],
        brand_seconds=[{"start_s": 0, "end_s": 1}],
        cta={"start_s": 8, "end_s": 10}, status="human_verified"))
    creative.save_annotation(conn, "lose-cpa", _ann(
        hook_type="offer", creator_vs_branded="branded",
        duration_s=30.0, product_seconds=[{"start_s": 8, "end_s": 12}],
        cta={"start_s": 20, "end_s": 25}, status="auto"))
    creative.save_annotation(conn, "mid-roas", _ann(
        hook_type="demo_open", creator_vs_branded="creator",
        duration_s=14.0, product_seconds=[{"start_s": 2, "end_s": 4}],
        status="auto"))
    return conn


def _sections(result):
    return {s["key"]: s for s in result["sections"]}


class CampaignRecoTest(unittest.TestCase):
    def test_six_sections_grounded_in_cpa(self):
        conn = _conn()
        try:
            out = benchmarks.campaign_recommendations(
                conn, "Alpha", rank_by="cpa")
            self.assertEqual(out["campaign"], "Alpha")
            self.assertEqual(out["rank_by"], "cpa")
            self.assertEqual(out["n_creatives"], 3)
            secs = _sections(out)
            self.assertEqual(
                sorted(secs),
                ["benchmark_gap", "scale", "stop_watch", "test_next",
                 "to_improve", "what_worked"])
            for sec in secs.values():
                self.assertTrue(sec["title"])
                self.assertTrue(sec["bullets"])
                for bullet in sec["bullets"]:
                    self.assertIn("text", bullet)
                    self.assertIn("verified", bullet)
            scale = secs["scale"]["bullets"][0]
            self.assertIn("win-cpa", scale["text"])
            self.assertIn("$2.0", scale["text"])
            self.assertTrue(scale["verified"])
            stop = secs["stop_watch"]["bullets"][0]
            self.assertIn("lose-cpa", stop["text"])
            self.assertIn("$50.0", stop["text"])
            worked = " ".join(b["text"]
                              for b in secs["what_worked"]["bullets"])
            self.assertIn("demo_open", worked)
            self.assertIn("creator", worked)
            gaps = " ".join(b["text"]
                            for b in secs["to_improve"]["bullets"])
            self.assertIn("8", gaps)
            self.assertIn("1", gaps)
            nxt = secs["test_next"]["bullets"][0]["text"]
            self.assertIn("win-cpa", nxt)
            self.assertIn("CTA around 8", nxt)
            gap = secs["benchmark_gap"]["bullets"][0]["text"]
            self.assertIn("peer median", gap)
            self.assertIn("$20.0", gap)
        finally:
            conn.close()

    def test_kpi_aware_roas_picks_roas_winner(self):
        conn = _conn()
        try:
            out = benchmarks.campaign_recommendations(
                conn, "Alpha", rank_by="roas")
            secs = _sections(out)
            scale = secs["scale"]["bullets"][0]["text"]
            self.assertIn("mid-roas", scale)
            self.assertIn("8.0x", scale)
            stop = secs["stop_watch"]["bullets"][0]["text"]
            self.assertIn("lose-cpa", stop)
        finally:
            conn.close()

    def test_matches_report_engine(self):
        # Dashboard and reports share _report_extras: the SCALE bullet
        # names the report's SCALE creative, and the stop/watch bullet
        # names the engine's worst row. (Single-campaign reports emit
        # no STOP line — the within-campaign hold is the Detail
        # value-add, drawn from the same best/worst rows.)
        conn = _conn()
        try:
            for rank_by in ("cpa", "roas"):
                extras = benchmarks._report_extras(
                    conn, ["Alpha"], rank_by=rank_by)
                reco = " ".join(extras["recommendations"])
                rows = extras["per_campaign"]["Alpha"]
                out = benchmarks.campaign_recommendations(
                    conn, "Alpha", rank_by=rank_by)
                secs = _sections(out)
                scale_key = secs["scale"]["bullets"][0]["text"].split()[1]
                self.assertIn(scale_key, reco)
                self.assertEqual(scale_key,
                                 rows["best"]["creative_key"])
                stop_text = secs["stop_watch"]["bullets"][0]["text"]
                self.assertTrue(stop_text.startswith("Avoid scaling"))
                self.assertEqual(stop_text.split()[2],
                                 rows["worst"]["creative_key"])
        finally:
            conn.close()

    def test_scope_filters_population(self):
        conn = _conn()
        try:
            out = benchmarks.campaign_recommendations(
                conn, "Alpha", scope={"market": ["Spain"]}, rank_by="cpa")
            self.assertEqual(out["n_creatives"], 2)
            out = benchmarks.campaign_recommendations(
                conn, "Alpha", scope={"market": ["France"]}, rank_by="cpa")
            self.assertEqual(out["n_creatives"], 1)
            secs = _sections(out)
            self.assertIn("Only one",
                          secs["to_improve"]["bullets"][0]["text"])
        finally:
            conn.close()

    def test_insufficient_data_is_explicit(self):
        conn = _conn()
        try:
            out = benchmarks.campaign_recommendations(
                conn, "Nope", rank_by="cpa")
            self.assertEqual(out["n_creatives"], 0)
            secs = _sections(out)
            self.assertIn("No creatives",
                          secs["what_worked"]["bullets"][0]["text"])
            self.assertIn("Not enough data",
                          secs["scale"]["bullets"][0]["text"])
            self.assertIn("Not enough data",
                          secs["test_next"]["bullets"][0]["text"])
        finally:
            conn.close()

    def test_invalid_rank_by_rejected(self):
        conn = _conn()
        try:
            with self.assertRaises(ValueError):
                benchmarks.campaign_recommendations(
                    conn, "Alpha", rank_by="clicks")
        finally:
            conn.close()

    def test_cpc_ranks_lowest_click_cost(self):
        csv = ("campaign,ad set,ad name,spend,impressions,clicks,"
               "conversions,date\n"
               "Gamma,Set1,cpc-a,100,1000,100,1,2026-08-01\n"
               "Gamma,Set1,cpc-b,50,1000,10,10,2026-08-01\n")
        conn = _conn()
        try:
            ingest.upsert_rows(conn, ingest.parse_csv(csv, "meta"))
            out = benchmarks.campaign_recommendations(
                conn, "Gamma", rank_by="cpc")
            secs = _sections(out)
            # CPC winner (cpc-a at $1.00) differs from the CPA winner
            # (cpc-b at $5.00): the ranking is CPC-led, not CPA-led.
            scale = secs["scale"]["bullets"][0]["text"]
            self.assertIn("cpc-a", scale)
            self.assertIn("$1.0", scale)
        finally:
            conn.close()

    def test_spend_falls_back_to_cpa_with_notice(self):
        conn = _conn()
        try:
            out = benchmarks.campaign_recommendations(
                conn, "Alpha", rank_by="spend")
            self.assertEqual(out["rank_by"], "cpa")
            self.assertEqual(out["rank_by_requested"], "spend")
            self.assertIn("CPA", out["notice"])
            cpa = benchmarks.campaign_recommendations(
                conn, "Alpha", rank_by="cpa")
            self.assertEqual(
                _sections(out)["scale"], _sections(cpa)["scale"])
        finally:
            conn.close()

    def test_verified_flags_follow_annotations(self):
        conn = _conn()
        try:
            out = benchmarks.campaign_recommendations(
                conn, "Alpha", rank_by="cpa")
            secs = _sections(out)
            # Winner is human_verified; loser is auto.
            self.assertTrue(secs["scale"]["bullets"][0]["verified"])
            stop = secs["stop_watch"]["bullets"][0]
            self.assertTrue(stop["text"].startswith("Avoid scaling"))
            self.assertFalse(stop["verified"])
        finally:
            conn.close()


class CampaignRecoHttpTest(unittest.TestCase):
    def test_http_shape_and_errors(self):
        import server as srv
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        try:
            live = _conn()
            disk = sqlite3.connect(db)
            schema.init_db(disk)
            for sql in live.iterdump():
                if sql.startswith("INSERT"):
                    disk.execute(sql)
            disk.commit()
            live.close()
            disk.close()
            srv.Handler.db_path = db
            httpd = HTTPServer(("127.0.0.1", 0), srv.Handler)
            port = httpd.server_address[1]
            thread = threading.Thread(target=httpd.serve_forever,
                                      daemon=True)
            thread.start()
            try:
                base = "http://127.0.0.1:%d" % port
                with urllib.request.urlopen(
                        base + "/api/campaigns/recommendations"
                        "?name=Alpha&rank_by=roas") as resp:
                    out = json.loads(resp.read())
                self.assertEqual(out["rank_by"], "roas")
                self.assertEqual(len(out["sections"]), 6)
                scale = [s for s in out["sections"]
                         if s["key"] == "scale"][0]["bullets"][0]
                self.assertIn("mid-roas", scale["text"])

                def _get(path):
                    try:
                        urllib.request.urlopen(base + path)
                        self.fail("expected 409 for %s" % path)
                    except urllib.error.HTTPError as exc:
                        self.assertEqual(exc.code, 409)
                        return json.loads(exc.read())

                body = _get("/api/campaigns/recommendations")
                self.assertIn("campaign name", body["error"])
                body = _get("/api/campaigns/recommendations"
                            "?name=Alpha&rank_by=clicks")
                self.assertIn("rank_by", body["error"])
                with urllib.request.urlopen(
                        base + "/api/campaigns/recommendations"
                        "?name=Alpha&rank_by=cpc") as resp:
                    cpc = json.loads(resp.read())
                self.assertEqual(cpc["rank_by"], "cpc")
                with urllib.request.urlopen(
                        base + "/api/campaigns/recommendations"
                        "?name=Alpha&rank_by=spend") as resp:
                    spend = json.loads(resp.read())
                self.assertEqual(spend["rank_by"], "cpa")
                self.assertEqual(spend["rank_by_requested"], "spend")
                self.assertIn("CPA", spend["notice"])
            finally:
                httpd.shutdown()
                thread.join(timeout=10)
        finally:
            os.unlink(db)


    def test_http_project_filter_isolates(self):
        # Two projects share campaign Alpha with DIFFERENT winners: a
        # dropped project axis would analyse both and crown the wrong
        # creative (this caught Scope-normalized() losing the axis).
        import server as srv
        csv = ("campaign,ad set,ad name,spend,impressions,clicks,"
               "conversions,project,date\n"
               "Alpha,Set1,win-p1,10,1000,20,5,Proj1,2026-08-01\n"
               "Alpha,Set1,lose-p1,100,2000,30,2,Proj1,2026-08-01\n"
               "Alpha,Set2,win-p2,15,1000,20,5,Proj2,2026-08-01\n"
               "Alpha,Set2,lose-p2,200,2000,30,2,Proj2,2026-08-01\n")
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        try:
            conn = sqlite3.connect(db)
            schema.init_db(conn)
            ingest.upsert_rows(conn, ingest.parse_csv(csv, "meta"))
            conn.close()
            srv.Handler.db_path = db
            httpd = HTTPServer(("127.0.0.1", 0), srv.Handler)
            port = httpd.server_address[1]
            thread = threading.Thread(target=httpd.serve_forever,
                                      daemon=True)
            thread.start()
            try:
                base = "http://127.0.0.1:%d" % port

                def _get_json(path):
                    with urllib.request.urlopen(base + path) as resp:
                        return json.loads(resp.read())

                p1 = _get_json("/api/campaigns/recommendations"
                               "?name=Alpha&rank_by=cpa&project=Proj1")
                self.assertEqual(p1["n_creatives"], 2)
                scale1 = [s for s in p1["sections"]
                          if s["key"] == "scale"][0]["bullets"][0]
                self.assertIn("win-p1", scale1["text"])
                p2 = _get_json("/api/campaigns/recommendations"
                               "?name=Alpha&rank_by=cpa&project=Proj2")
                self.assertEqual(p2["n_creatives"], 2)
                scale2 = [s for s in p2["sections"]
                          if s["key"] == "scale"][0]["bullets"][0]
                self.assertIn("win-p2", scale2["text"])
                unscoped = _get_json("/api/campaigns/recommendations"
                                     "?name=Alpha&rank_by=cpa")
                self.assertEqual(unscoped["n_creatives"], 4)
            finally:
                httpd.shutdown()
                thread.join(timeout=10)
        finally:
            os.unlink(db)


if __name__ == "__main__":
    unittest.main()
