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
        elif self.path.startswith("/drive.xlsx"):
            from creative_intel import ooxml
            blob = ooxml.build_xlsx([{
                "name": "Export",
                "header": ["Campaign", "Spend", "Impressions", "Clicks",
                           "Conversions", "Ad Name"],
                "rows": [["DriveCamp", 9, 900, 9, 1, "d1"]]}])
            self._send(200, blob, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        elif self.path.startswith("/login"):
            self._send(200, "<!DOCTYPE html><html>login</html>", "text/html")
        elif "/insights" in self.path:
            query = parse_qs(urlparse(self.path).query)
            tok = query.get("access_token", [""])[0]
            if tok:
                StubHandler.seen["token"] = tok
            if "after=" in self.path:
                self._send(200, {"data": [{
                    "campaign_name": "MetaCamp2", "adset_name": "Set",
                    "ad_name": "meta-ad-2", "spend": "10.0",
                    "impressions": "1000", "clicks": "10",
                    "actions": [{"action_type": "purchase", "value": 1}],
                    "date_start": "2026-08-02",
                    "video_play_actions": [{"value": 100}]}]})
            else:
                host = self.headers.get("Host", "127.0.0.1")
                tok = query.get("access_token", [""])[0]
                # Like real Graph paging cursors, the next URL carries
                # the token so follow-up pages stay authenticated.
                self._send(200, {"data": [{
                    "campaign_name": "MetaCamp", "adset_name": "Set",
                    "ad_name": "meta-ad", "spend": "42.5",
                    "impressions": "4200", "clicks": "84",
                    "actions": [{"action_type": "purchase", "value": 7}],
                    "action_values": [{"action_type": "purchase",
                                       "value": 120.0}],
                    "date_start": "2026-08-01",
                    "video_play_actions": [{"value": 900}]}],
                    "paging": {"next": "http://%s/act/insights?after=page2"
                               "&access_token=%s" % (host, tok)}})
        elif "/report/integrated/get/" in self.path:
            # Synchronous-report contract (A09): GET with query
            # parameters — a JSON POST body must never arrive here.
            query = parse_qs(urlparse(self.path).query)
            StubHandler.seen["access_token"] = self.headers.get(
                "Access-Token")
            StubHandler.seen["report_type"] = (
                query.get("report_type") or [""])[0]
            StubHandler.seen["dimensions"] = json.loads(
                (query.get("dimensions") or ["[]"])[0])
            StubHandler.seen["metrics"] = json.loads(
                (query.get("metrics") or ["[]"])[0])
            StubHandler.seen["start_date"] = (
                query.get("start_date") or [""])[0]
            page = int((query.get("page") or ["1"])[0])
            StubHandler.seen["page"] = page
            if page >= 2:
                rows = [{
                    "dimensions": {"campaign_id": "TikCamp2",
                                   "adgroup_id": "g",
                                   "ad_id": "tt-ad-2",
                                   "stat_time_day": "2026-08-02"},
                    "metrics": {"spend": 25.0, "impressions": 2500,
                                "clicks": 50, "conversion": 5,
                                "video_views": 600,
                                "purchase_value": 40.0}}]
            else:
                rows = [{
                    "dimensions": {"campaign_id": "TikCamp",
                                   "adgroup_id": "g", "ad_id": "tt-ad",
                                   "stat_time_day": "2026-08-01"},
                    "metrics": {"spend": 15.0, "impressions": 1500,
                                "clicks": 30, "conversion": 3,
                                "video_views": 400, "roas": 2.0}}]
            self._send(200, {"code": 0, "data": {
                "list": rows,
                "page_info": {"page": page, "page_size": 1,
                              "total_number": 2}}})
        else:
            self._send(404, {"error": "no stub"})

    def do_POST(self):
        # A09: the synchronous TikTok report is GET-only. Any POST
        # here means the client regressed to a JSON body — fail the
        # request so the test errors instead of certifying it.
        StubHandler.seen["unexpected_post"] = self.path
        self._send(405, {"code": 405,
                         "message": "report reads must use GET"})


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
        cls._srv.server_close()

    def setUp(self):
        self._saved = dict(os.environ)
        # Loopback stub fetches stay allowed here; production never
        # sets this flag (see connectors.ALLOW_LOOPBACK_FETCH_ENV).
        os.environ[connectors.ALLOW_LOOPBACK_FETCH_ENV] = "1"
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

    def test_bearer_headers_https_only(self):
        self.assertIsNone(
            connectors.bearer_headers("https://example.com/x.csv", None))
        headers = connectors.bearer_headers(
            "https://docs.google.com/spreadsheets/d/X/export", "tok")
        self.assertEqual(headers, {"Authorization": "Bearer tok"})
        # Plaintext http must never carry the Google OAuth token.
        with self.assertRaises(connectors.ConnectorUnavailable):
            connectors.bearer_headers("http://example.com/x.csv", "tok")

    def test_nonpublic_fetch_targets_refused(self):
        for url in ("http://169.254.169.254/latest/meta-data/",
                    "http://10.0.0.1/x.csv",
                    "http://192.168.1.1/x.csv",
                    "http://[::1]/x.csv"):
            with self.assertRaises(connectors.ConnectorUnavailable,
                                   msg=url):
                connectors.fetch_bytes(url)

    def test_loopback_refused_without_test_flag(self):
        saved = os.environ.pop(connectors.ALLOW_LOOPBACK_FETCH_ENV,
                               None)
        try:
            with self.assertRaises(connectors.ConnectorUnavailable):
                connectors.fetch_bytes(self.base + "/sheet.csv")
        finally:
            if saved is not None:
                os.environ[connectors.ALLOW_LOOPBACK_FETCH_ENV] = saved

    def test_meta_insights_end_to_end(self):
        os.environ["CREATIVE_INTEL_KEY_META"] = "dummy-meta-token"
        os.environ["CREATIVE_INTEL_API_META"] = self.base
        text = connectors.meta_insights_csv("123", "2026-08-01", "2026-08-31")
        self.assertEqual(StubHandler.seen.get("token"), "dummy-meta-token")
        rows, quar = ingest.parse_csv_report(text, "meta", "meta-api")
        # Pagination followed: both stub pages land in one CSV.
        self.assertEqual([r["campaign"] for r in rows],
                         ["MetaCamp", "MetaCamp2"])
        self.assertEqual(rows[0]["spend"], 42.5)
        self.assertEqual(rows[0]["conversions"], 7.0)
        self.assertEqual(rows[0]["video_views"], 900)
        self.assertEqual(rows[0]["date"], "2026-08-01")
        self.assertEqual(rows[0]["revenue"], 120.0)
        self.assertEqual(rows[1]["spend"], 10.0)
        self.assertEqual(rows[1]["date"], "2026-08-02")
        self.assertEqual(rows[1]["revenue"], 0.0)
        self.assertFalse(rows[1]["revenue_reported"])
        self.assertTrue(rows[0]["revenue_reported"])
        self.assertEqual(quar, [])

    def test_tiktok_report_end_to_end(self):
        os.environ["CREATIVE_INTEL_KEY_TIKTOK"] = "dummy-tt-token"
        os.environ["CREATIVE_INTEL_API_TIKTOK"] = self.base
        text = connectors.tiktok_report_csv("456", "2026-08-01", "2026-08-31")
        self.assertEqual(StubHandler.seen.get("access_token"),
                         "dummy-tt-token")
        rows, _quar = ingest.parse_csv_report(text, "tiktok", "tiktok-api")
        # Page 2 requested and merged via page_info total_number.
        self.assertEqual(StubHandler.seen.get("page"), 2)
        self.assertEqual([r["campaign"] for r in rows],
                         ["TikCamp", "TikCamp2"])
        self.assertEqual(rows[0]["conversions"], 3.0)
        self.assertEqual(rows[1]["conversions"], 5.0)
        self.assertEqual(rows[0]["date"], "2026-08-01")
        self.assertEqual(rows[0]["revenue"], 30.0)
        self.assertTrue(rows[0]["revenue_reported"])
        self.assertEqual(rows[1]["date"], "2026-08-02")
        self.assertEqual(rows[1]["revenue"], 40.0)

    def test_tiktok_report_uses_get_with_query_params(self):
        # A09: synchronous reporting is GET with query parameters
        # (report_type BASIC, JSON-array dimensions/metrics, dates,
        # paging) — never a JSON POST body.
        os.environ["CREATIVE_INTEL_KEY_TIKTOK"] = "dummy-tt-token"
        os.environ["CREATIVE_INTEL_API_TIKTOK"] = self.base
        connectors.tiktok_report_csv("456", "2026-08-01",
                                            "2026-08-31")
        self.assertNotIn("unexpected_post", StubHandler.seen)
        self.assertEqual(StubHandler.seen["report_type"], "BASIC")
        self.assertIn("roas", StubHandler.seen["metrics"])
        self.assertIn("stat_time_day", StubHandler.seen["dimensions"])
        self.assertEqual(StubHandler.seen["start_date"], "2026-08-01")

    def test_tiktok_roas_metric_requested_with_fallback(self):
        os.environ["CREATIVE_INTEL_KEY_TIKTOK"] = "dummy-tt-token"
        os.environ["CREATIVE_INTEL_API_TIKTOK"] = self.base
        connectors.tiktok_report_csv("456", "2026-08-01",
                                            "2026-08-31")
        self.assertIn("roas", StubHandler.seen["metrics"])
        self.assertIn("stat_time_day", StubHandler.seen["dimensions"])

    def test_tiktok_bad_params_rejected_before_http(self):
        os.environ["CREATIVE_INTEL_KEY_TIKTOK"] = "dummy-tt-token"
        os.environ["CREATIVE_INTEL_API_TIKTOK"] = self.base
        with self.assertRaises(connectors.ConnectorUnavailable):
            connectors._tiktok_pages(
                self.base + "/open_api/v1.3/report/integrated/get/",
                "tok", "456", "2026-08-01", "2026-08-31",
                ["campaign_id"], ["spend", "no_such_metric"])
        with self.assertRaises(connectors.ConnectorUnavailable):
            connectors._tiktok_pages(
                self.base + "/open_api/v1.3/report/integrated/get/",
                "tok", "456", "08/01/2026", "2026-08-31",
                ["campaign_id"], ["spend"])

    def test_tiktok_exhausted_pages_fail_explicitly(self):
        import creative_intel.connectors as conn_mod
        orig = conn_mod._api_json

        def fake(url, token=None, headers=None):
            # Full pages forever, never a completion signal.
            return {"code": 0, "data": {
                "list": [{"dimensions": {}, "metrics": {}}] * 500,
                "page_info": {}}}

        conn_mod._api_json = fake
        try:
            with self.assertRaises(connectors.ConnectorUnavailable):
                connectors._tiktok_pages(
                    "https://business-api.tiktok.com"
                    "/open_api/v1.3/report/integrated/get/",
                    "tok", "456", "2026-08-01", "2026-08-31",
                    ["campaign_id"], ["spend"])
        finally:
            conn_mod._api_json = orig

    def test_tiktok_metric_rejection_falls_back(self):
        from urllib.parse import parse_qs, urlparse

        import creative_intel.connectors as conn_mod
        calls = []
        orig = conn_mod._api_json

        def fake(url, token=None, headers=None):
            query = parse_qs(urlparse(url).query)
            metrics = json.loads((query.get("metrics") or ["[]"])[0])
            calls.append(metrics)
            if "roas" in calls[-1]:
                return {"code": 40001, "message": "invalid metric: roas"}
            return {"code": 0, "data": {"list": [], "page_info": {}}}

        conn_mod._api_json = fake
        try:
            os.environ["CREATIVE_INTEL_KEY_TIKTOK"] = "dummy-tt-token"
            text = connectors.tiktok_report_csv("456", "2026-08-01",
                                                "2026-08-31")
        finally:
            conn_mod._api_json = orig
        self.assertEqual(len(calls), 2)
        self.assertNotIn("roas", calls[1])
        rows, _q = ingest.parse_csv_report(text, "tiktok", "tiktok-api")
        self.assertEqual(rows, [])

    def test_roas_revenue_unit(self):
        self.assertEqual(
            connectors._roas_revenue({"roas": 2.0, "spend": 15.0}), "30.0")
        self.assertEqual(connectors._roas_revenue({"spend": 15.0}), "")
        self.assertEqual(
            connectors._roas_revenue({"roas": "x", "spend": 15.0}), "")
        self.assertEqual(
            connectors._roas_revenue({"roas": 2.0, "spend": 0}), "")

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

    def test_drive_csv_and_xlsx(self):
        from ci_backend import actions as server
        conn = sqlite3.connect(":memory:")
        try:
            schema.init_db(conn)
            out = server.apply_action(
                conn, "connect-drive",
                {"url": self.base + "/sheet.csv", "platform": "meta"}, None)
            self.assertEqual(out["inserted"], 1)
            out = server.apply_action(
                conn, "connect-drive",
                {"url": self.base + "/drive.xlsx", "platform": "meta"}, None)
            self.assertEqual(out["inserted"], 1)
            names = sorted(r[0] for r in conn.execute(
                "SELECT DISTINCT campaign FROM ads").fetchall())
            self.assertEqual(names, ["DriveCamp", "StubCamp"])
        finally:
            conn.close()

    def test_drive_login_page_refused(self):
        from ci_backend import actions as server
        conn = sqlite3.connect(":memory:")
        try:
            schema.init_db(conn)
            with self.assertRaises(ValueError) as ctx:
                server.apply_action(
                    conn, "connect-drive",
                    {"url": self.base + "/login", "platform": "meta"}, None)
            self.assertIn("Connect Google Drive in Settings",
                              str(ctx.exception))
        finally:
            conn.close()

    def test_server_connect_actions(self):
        from ci_backend import actions as server
        os.environ["CREATIVE_INTEL_KEY_META"] = "dummy-meta-token"
        os.environ["CREATIVE_INTEL_API_META"] = self.base
        conn = sqlite3.connect(":memory:")
        try:
            schema.init_db(conn)
            out = server.apply_action(
                conn, "connect-meta",
                {"ad_account_id": "123", "since": "2026-08-01",
                 "until": "2026-08-31"}, None)
            self.assertEqual(out["inserted"], 2)
            n = conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0]
            self.assertEqual(n, 2)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
