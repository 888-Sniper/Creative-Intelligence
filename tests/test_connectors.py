"""Connector tests: Sheets/Drive URL handling, Meta/TikTok API ingestion.

Platform APIs run against loopback stubs via CREATIVE_INTEL_API_*
overrides with dummy env tokens: the real HTTP request/response code
paths execute, no Keychain and no internet needed.
"""

import json
import os
import sqlite3
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import connectors, ingest, schema

SHEET_CSV = ("Campaign,Spend,Impressions,Clicks,Conversions,Video Views,Ad Name\n"
             "StubCamp,10,1000,20,2,300,stub-ad\n")


class StubHandler(BaseHTTPRequestHandler):
    seen = {}

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            raw = body.encode()
        elif isinstance(body, bytes):
            raw = body
        else:
            raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        StubHandler.seen["auth"] = self.headers.get("Authorization")
        StubHandler.seen["path"] = self.path
        if self.path.startswith("/sheet"):
            self._send(200, SHEET_CSV, "text/csv")
        elif self.path.startswith("/login"):
            self._send(200, "<!DOCTYPE html><html>login</html>", "text/html")
        elif "/insights" in self.path:
            query = parse_qs(urlparse(self.path).query)
            StubHandler.seen["token"] = query.get("access_token", [""])[0]
            self._send(200, {"data": [{
                "campaign_name": "MetaCamp", "adset_name": "Set",
                "ad_name": "meta-ad", "spend": "42.5", "impressions": "4200",
                "clicks": "84",
                "actions": [{"action_type": "purchase", "value": 7}],
                "video_play_actions": [{"value": 900}]}]})
        else:
            self._send(404, {"error": "no stub"})

    def do_POST(self):
        StubHandler.seen["access_token"] = self.headers.get("Access-Token")
        length = int(self.headers.get("Content-Length", 0))
        StubHandler.seen["body"] = self.rfile.read(length)
        self._send(200, {"code": 0, "data": {"list": [{
            "dimensions": {"campaign_id": "TikCamp", "adgroup_id": "g",
                           "ad_id": "tt-ad"},
            "metrics": {"spend": 15.0, "impressions": 1500, "clicks": 30,
                        "conversion": 3, "video_views": 400}}]}})


class ConnectorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._srv = HTTPServer(("127.0.0.1", 0), StubHandler)
        cls.base = "http://127.0.0.1:%d" % cls._srv.server_address[1]
        cls._thread = threading.Thread(target=cls._srv.serve_forever,
                                       daemon=True)
        cls._thread.start()

    @classmethod
    def tearDownClass(cls):
        cls._srv.shutdown()
        cls._thread.join(timeout=10)

    def setUp(self):
        self._saved = dict(os.environ)
        StubHandler.seen = {}

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved)

    def test_sheets_url_normalisation(self):
        url = connectors.sheets_csv_url(
            "https://docs.google.com/spreadsheets/d/ABC123/edit#gid=7")
        self.assertEqual(
            url, "https://docs.google.com/spreadsheets/d/ABC123/export"
                 "?format=csv&gid=7")
        plain = "https://example.com/export?output=csv"
        self.assertEqual(connectors.sheets_csv_url(plain), plain)
        with self.assertRaises(connectors.ConnectorUnavailable):
            connectors.sheets_csv_url("ftp://example.com/x.csv")

    def test_drive_url_normalisation(self):
        url = connectors.drive_file_url(
            "https://drive.google.com/file/d/XYZ789/view?usp=sharing")
        self.assertEqual(
            url, "https://drive.google.com/uc?export=download&id=XYZ789")

    def test_fetch_sheet_csv_roundtrip(self):
        text = connectors.fetch_sheet_csv(self.base + "/sheet.csv")
        rows, quar = ingest.parse_csv_report(text, "meta", "sheets")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["campaign"], "StubCamp")
        self.assertEqual(rows[0]["spend"], 10.0)
        self.assertEqual(quar, [])

    def test_login_page_refused(self):
        with self.assertRaises(connectors.ConnectorUnavailable):
            connectors.fetch_sheet_csv(self.base + "/login")

    def test_meta_insights_end_to_end(self):
        os.environ["CREATIVE_INTEL_KEY_META"] = "dummy-meta-token"
        os.environ["CREATIVE_INTEL_API_META"] = self.base
        text = connectors.meta_insights_csv("123", "2026-08-01", "2026-08-31")
        self.assertEqual(StubHandler.seen.get("token"), "dummy-meta-token")
        rows, quar = ingest.parse_csv_report(text, "meta", "meta-api")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["campaign"], "MetaCamp")
        self.assertEqual(rows[0]["spend"], 42.5)
        self.assertEqual(rows[0]["conversions"], 7.0)
        self.assertEqual(rows[0]["video_views"], 900)
        self.assertEqual(quar, [])

    def test_tiktok_report_end_to_end(self):
        os.environ["CREATIVE_INTEL_KEY_TIKTOK"] = "dummy-tt-token"
        os.environ["CREATIVE_INTEL_API_TIKTOK"] = self.base
        text = connectors.tiktok_report_csv("456", "2026-08-01", "2026-08-31")
        self.assertEqual(StubHandler.seen.get("access_token"),
                         "dummy-tt-token")
        rows, _quar = ingest.parse_csv_report(text, "tiktok", "tiktok-api")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["campaign"], "TikCamp")
        self.assertEqual(rows[0]["conversions"], 3.0)

    def test_platform_needs_token(self):
        for fn, args in (
                (connectors.meta_insights_csv, ("123", "a", "b")),
                (connectors.tiktok_report_csv, ("456", "a", "b"))):
            with self.assertRaises(connectors.ConnectorUnavailable):
                fn(*args)

    def test_tokens_never_surface(self):
        os.environ["CREATIVE_INTEL_KEY_META"] = "super-secret-meta"
        try:
            connectors.meta_insights_csv("", "a", "b")
        except connectors.ConnectorUnavailable as e:
            self.assertNotIn("super-secret-meta", str(e))
        else:
            self.fail("expected failure without account id")

    def test_server_connect_actions(self):
        import server
        os.environ["CREATIVE_INTEL_KEY_META"] = "dummy-meta-token"
        os.environ["CREATIVE_INTEL_API_META"] = self.base
        conn = sqlite3.connect(":memory:")
        try:
            schema.init_db(conn)
            out = server.apply_action(
                conn, "connect-meta",
                {"ad_account_id": "123", "since": "2026-08-01",
                 "until": "2026-08-31"}, None)
            self.assertEqual(out["inserted"], 1)
            n = conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0]
            self.assertEqual(n, 1)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
