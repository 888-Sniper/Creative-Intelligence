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
        status, ctype, body = self._get("/assets/favicon.svg")
        self.assertEqual(status, 200)
        self.assertIn("svg", ctype)
        self.assertIn(b"#00C7B2", body)

    def test_asset_sandbox(self):
        import urllib.error
        for bad in ("/assets/../Index.html", "/assets/.hidden",
                    "/assets/x.py", "/assets/nope.png"):
            try:
                self._get(bad)
                self.fail("served %s" % bad)
            except urllib.error.HTTPError as exc:
                self.assertEqual(exc.code, 404)


if __name__ == "__main__":
    unittest.main()
