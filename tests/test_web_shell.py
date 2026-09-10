"""Foap application-shell regression tests (stdlib unittest).

Static assertions over Web/Index.html plus live checks against a real
server instance: branding slots, navigation integrity, filter wiring,
asset sandbox, and escaping discipline.
"""

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

ROOT = os.path.join(os.path.dirname(__file__), "..")
HTML = open(os.path.join(ROOT, "Web", "Index.html")).read()


class ShellStaticTest(unittest.TestCase):
    def test_brand_slot_and_product_name(self):
        self.assertIn("assets/foap-logo.png", HTML)
        self.assertIn("Creative Intelligence", HTML)
        self.assertIn('rel="icon"', HTML)

    def test_nav_renamed_ids_intact(self):
        for view, label in (("main", "Overview"), ("campaign", "Campaigns"),
                            ("creative", "Creatives"), ("compare", "Compare"),
                            ("benchmark", "Benchmarks"),
                            ("report", "Reports")):
            self.assertIn('data-view="%s"' % view, HTML)
            self.assertIn(">%s<" % label, HTML)
        for section in ("v-main", "v-campaign", "v-creative", "v-compare",
                        "v-benchmark", "v-report"):
            self.assertIn('id="%s"' % section, HTML)

    def test_filter_ids_all_present(self):
        for fid in ("flt-client", "flt-project", "flt-campaign",
                    "flt-platform", "flt-vertical", "flt-market",
                    "flt-funnel", "flt-objective", "flt-kpi", "flt-date",
                    "flt-clear", "filter-summary"):
            self.assertIn('id="%s"' % fid, HTML)

    def test_ask_bar_present(self):
        self.assertIn('id="ask-q"', HTML)
        self.assertIn('id="ask-go"', HTML)
        self.assertIn("Ask Foap Creative Intelligence", HTML)

    def test_no_remote_resources(self):
        self.assertNotIn("http://", HTML.replace("http://127.0.0.1", "")
                         .replace("http://localhost", ""))
        self.assertNotIn("https://", HTML)
        self.assertNotIn("cdn", HTML.lower())

    def test_foap_tokens_anchor(self):
        self.assertIn("--foap-primary:#00C7B2", HTML.replace(" ", ""))
        self.assertIn('[data-theme="dark"]', HTML)

    def test_esc_discipline_intact(self):
        self.assertGreater(HTML.count("esc("), 40)
        self.assertIn("textContent", HTML)


class ShellLiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls._db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        server.Handler.db_path = cls._db
        cls._srv = HTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls._srv.server_address[1]
        cls._thread = threading.Thread(target=cls._srv.serve_forever,
                                       daemon=True)
        cls._thread.start()

    @classmethod
    def tearDownClass(cls):
        cls._srv.shutdown()
        cls._thread.join(timeout=10)
        os.unlink(cls._db)

    def _get(self, path):
        with urllib.request.urlopen(
                "http://127.0.0.1:%d%s" % (self.port, path),
                timeout=5) as resp:
            return resp.status, resp.headers.get("Content-Type"), \
                resp.read()

    def test_index_serves(self):
        status, ctype, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", ctype)
        self.assertIn(b"Foap Creative Intelligence", body)

    def test_favicon_asset_serves(self):
        status, ctype, body = self._get("/assets/favicon.png")
        self.assertEqual(status, 200)
        self.assertIn("image/png", ctype)
        self.assertTrue(body.startswith(b"\x89PNG"))

    def test_logo_and_mark_assets_serve(self):
        for path, minimum in (("/assets/foap-logo.png", 10000),
                              ("/assets/foap-mark.png", 5000)):
            status, ctype, body = self._get(path)
            self.assertEqual(status, 200, path)
            self.assertIn("image/png", ctype, path)
            self.assertTrue(body.startswith(b"\x89PNG"), path)
            self.assertGreater(len(body), minimum, path)

    def test_overview_kpi_set_present(self):
        for label in ("Spend", "Impressions", "CPM", "VTR", "CTR",
                      "CPA", "ROAS", "Best CPA"):
            self.assertIn(label, HTML)

    def test_logo_fallback_uses_official_mark(self):
        # No redrawn "foap." wordmark: fallback is the official mark,
        # degrading to plain text only if both assets fail.
        self.assertIn('id="brand-fallback"', HTML)
        self.assertIn("assets/foap-mark.png", HTML)
        self.assertNotIn("brand-fallback\"", HTML.replace(
            'id="brand-fallback"', ""))
        self.assertNotIn("foap<em>", HTML)
        self.assertIn("outerHTML='Foap'", HTML)

    def test_no_nested_container(self):
        self.assertNotIn('<main class="container">', HTML)
        self.assertIn("<main>", HTML)

    def test_creative_grid_media_first(self):
        # Grid cards render a real muted preview when an annotated
        # source URL exists, else keep the text placeholder.
        self.assertIn("playsinline", HTML)
        self.assertIn(".creative-card .media video", HTML)
        self.assertIn("pick_source(a)", HTML)

    def test_new_flow_controls_present(self):
        for cid in ("xlsx-file", "sheets-url", "sheets-go", "drive-url",
                    "drive-go", "meta-acct",
                    "meta-since", "meta-until", "tt-adv", "tt-start",
                    "tt-end", "meta-go", "tt-go", "conn-status",
                    "media-file", "media-go", "media-status", "prov-status",
                    "rep-pptx", "rep-xlsx", "rep-strict"):
            self.assertIn('id="%s"' % cid, HTML)

    def test_kpi_ranking_complete_and_directed(self):
        for kpi in ("cpm", "vtr", "roas"):
            self.assertIn('value="%s"' % kpi, HTML)
        self.assertIn('KPI_LOWER_BETTER=["cpa","cpc","cpm"]', HTML)
        self.assertIn("sort_creatives", HTML)
        self.assertIn("/api/creatives", HTML)

    def test_report_rank_control_and_deck_honesty(self):
        self.assertIn('id="rep-rank"', HTML)
        for value, label in (("cpa", "CPA"), ("cpm", "CPM"),
                             ("ctr", "CTR"), ("vtr", "VTR"),
                             ("roas", "ROAS")):
            self.assertIn('<option value="%s">%s</option>' % (value, label),
                          HTML)
        self.assertIn('rank_by:$("rep-rank").value', HTML)
        # The downloadable HTML deck names the report's rank metric;
        # Best/Watch must never fall back to hard-coded CPA text.
        self.assertIn("d.rank_by", HTML)
        self.assertIn("cw.best[rk]", HTML)
        self.assertIn("cw.worst[rk]", HTML)
        self.assertNotIn("(CPA ${esc(kpi(cw.best.cpa,1))})", HTML)
        self.assertNotIn("(CPA ${esc(kpi(cw.worst.cpa,1))})", HTML)

    def test_saved_views_carry_report_rank(self):
        self.assertIn('rank_by:$("rep-rank").value', HTML)
        self.assertIn('$("rep-rank").value=st.rank_by', HTML)

    def test_campaign_detail_rich(self):
        for needle in ("Campaign totals (scoped)", "Creatives ranked by",
                       "Recommendations", "Review or replace",
                       "Hook concentration"):
            self.assertIn(needle, HTML)

    def test_supers_falls_back_to_structure(self):
        self.assertIn("supers_txt", HTML)
        self.assertIn("from structure", HTML)

    def test_date_ranges_and_periods(self):
        for cid in ("flt-date-from", "flt-date-to", "per-a-from",
                    "per-a-to", "per-b-from", "per-b-to", "per-go",
                    "per-out"):
            self.assertIn('id="%s"' % cid, HTML)
        self.assertIn("/api/compare/periods", HTML)
        self.assertIn("data-range", HTML)

    def test_modality_displayed(self):
        self.assertIn("hook_modality", HTML)
        self.assertIn("brand_audio_mention_s", HTML)
        self.assertIn('id="brand-terms"', HTML)

    def test_office_labels_honest(self):
        self.assertIn("presentation (HTML deck)", HTML)
        self.assertIn("Generate PowerPoint (.pptx)", HTML)
        self.assertIn("Generate Excel (.xlsx)", HTML)
        self.assertIn("/api/connect/sheets", HTML)
        self.assertIn("/api/connect/drive", HTML)
        self.assertIn("/api/connect/meta", HTML)
        self.assertIn("/api/connect/tiktok", HTML)
        self.assertIn("/api/media/upload", HTML)

    def test_report_office_formats_end_to_end(self):
        import base64
        import urllib.request
        csv_payload = ("Campaign,Spend,Impressions,Clicks,Conversions\n"
                       "LiveCamp,50,5000,100,5\n").encode()
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/ingest" % self.port, data=json.dumps(
                {"platform": "meta",
                 "csv": csv_payload.decode()}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5):
            pass
        for fmt, key in (("pptx", "pptx_b64"), ("xlsx", "xlsx_b64")):
            req = urllib.request.Request(
                "http://127.0.0.1:%d/api/report" % self.port,
                data=json.dumps({"format": fmt,
                                 "kpis": ["cpa", "ctr"]}).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                rep = json.loads(resp.read())
            self.assertEqual(rep["format"], fmt)
            self.assertTrue(base64.b64decode(rep[key]).startswith(b"PK"))

    def test_asset_sandbox(self):
        import urllib.error
        for bad in ("/assets/../Index.html", "/assets/.hidden",
                    "/assets/x.py", "/assets/nope.png",
                    "/assets/favicon.svg"):
            try:
                self._get(bad)
                self.fail("served %s" % bad)
            except urllib.error.HTTPError as exc:
                self.assertEqual(exc.code, 404)


if __name__ == "__main__":
    unittest.main()
