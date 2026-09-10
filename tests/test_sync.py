"""Scheduled sync tests: upsert dedup, run history, retries, HTTP surface."""

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

from creative_intel import ingest, schema, sync
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auth_help import authed, req as areq

CSV = ("campaign,ad set,ad name,spend,impressions,clicks,conversions,date\n"
       "CampA,Set1,ad-1,10,1000,20,2,2026-08-01\n"
       "CampA,Set1,ad-2,20,2000,30,3,2026-08-01\n")
CSV_CHANGED = ("campaign,ad set,ad name,spend,impressions,clicks,conversions,date\n"
               "CampA,Set1,ad-1,99,1000,20,2,2026-08-01\n"
               "CampA,Set1,ad-3,5,500,5,1,2026-08-01\n")


def _conn():
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    return conn


def _count(conn):
    return conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0]


class UpsertTest(unittest.TestCase):
    def test_insert_rows_appends_distinct_facts(self):
        other = ("campaign,ad set,ad name,spend,date\n"
                 "CampB,Set9,ad-9,7,2026-08-02\n"
                 "CampB,Set9,ad-10,8,2026-08-02\n")
        conn = _conn()
        try:
            self.assertEqual(
                ingest.insert_rows(conn, ingest.parse_csv(CSV, "meta")), 2)
            self.assertEqual(
                ingest.insert_rows(conn, ingest.parse_csv(other, "meta")),
                2)
            self.assertEqual(_count(conn), 4)
        finally:
            conn.close()

    def test_insert_rows_rejects_exact_duplicates(self):
        # The sync key is row identity at the DB level: the raw append
        # primitive refuses exact-duplicate facts instead of doubling
        # totals. Product surfaces use upsert_rows(), which merges.
        conn = _conn()
        try:
            ingest.insert_rows(conn, ingest.parse_csv(CSV, "meta"))
            with self.assertRaises(sqlite3.IntegrityError):
                ingest.insert_rows(conn, ingest.parse_csv(CSV, "meta"))
        finally:
            conn.close()

    def test_upsert_dedups_and_updates(self):
        conn = _conn()
        try:
            first = ingest.parse_csv(CSV, "meta")
            out1 = ingest.upsert_rows(conn, first)
            self.assertEqual(out1, {"inserted": 2, "updated": 0})
            second = ingest.parse_csv(CSV_CHANGED, "meta")
            out2 = ingest.upsert_rows(conn, second)
            self.assertEqual(out2, {"inserted": 1, "updated": 1})
            self.assertEqual(_count(conn), 3)
            spend = conn.execute(
                "SELECT spend FROM ads WHERE ad_name='ad-1'").fetchone()[0]
            self.assertEqual(spend, 99.0)
        finally:
            conn.close()

    def test_migrate_collapses_legacy_duplicates(self):
        # Simulate a pre-sync-key database: no uniqueness index, with
        # duplicate facts from repeated imports. migrate() collapses
        # them (last write wins) and installs the index.
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(schema.DDL.replace(
                "CREATE UNIQUE INDEX IF NOT EXISTS ads_sync_key ON ads\n"
                "    (source, platform, campaign, adset, ad_name, date);",
                ""))
            self.assertIsNone(conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND name='ads_sync_key'").fetchone())
            rows = ingest.parse_csv(CSV, "meta")
            ingest.insert_rows(conn, rows)
            # Bypass the (absent) index the way legacy code did: raw
            # appends of the same facts.
            ingest.insert_rows(conn, rows)
            self.assertEqual(_count(conn), 4)
            schema.migrate(conn)
            self.assertEqual(_count(conn), 2)
            idx = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
                " AND name='ads_sync_key'").fetchone()
            self.assertIsNotNone(idx)
            with self.assertRaises(sqlite3.IntegrityError):
                ingest.insert_rows(conn, rows)
        finally:
            conn.close()


class RunHistoryTest(unittest.TestCase):
    def test_import_once_records_ok_run(self):
        conn = _conn()
        try:
            out = sync.import_once(
                conn, "meta", lambda: (ingest.parse_csv(CSV, "meta"), []))
            self.assertEqual(out["inserted"], 2)
            self.assertEqual(out["updated"], 0)
            self.assertEqual(out["quarantined_count"], 0)
            st = sync.status(conn)
            self.assertEqual(st["sources"]["meta"]["last_status"], "ok")
            self.assertEqual(st["sources"]["meta"]["last_inserted"], 2)
            self.assertTrue(st["sources"]["meta"]["last_success_at"])
            self.assertEqual(len(st["recent"]), 1)
        finally:
            conn.close()

    def test_import_once_records_error_and_reraises(self):
        conn = _conn()
        try:
            def boom():
                raise ValueError("no token")
            with self.assertRaises(ValueError):
                sync.import_once(conn, "meta", boom)
            st = sync.status(conn)
            self.assertEqual(st["sources"]["meta"]["last_status"], "error")
            self.assertIn("no token", st["sources"]["meta"]["last_error"])
            self.assertEqual(st["sources"]["meta"]["last_success_at"], "")
        finally:
            conn.close()

    def test_run_once_retries_then_succeeds(self):
        conn = _conn()
        try:
            calls = []

            def flaky():
                calls.append(1)
                if len(calls) < 3:
                    raise ConnectionError("flap")
                return ingest.parse_csv(CSV, "meta"), []
            sleeps = []
            out = sync.run_once(conn, "meta", flaky,
                                sleep=sleeps.append)
            self.assertEqual(out["attempts"], 3)
            self.assertEqual(sleeps, [2.0, 8.0])
            st = sync.status(conn)
            self.assertEqual(st["sources"]["meta"]["last_status"], "ok")
            self.assertEqual(st["sources"]["meta"]["last_attempts"], 3)
        finally:
            conn.close()

    def test_run_once_gives_up_with_error_visible(self):
        conn = _conn()
        try:
            def dead():
                raise ConnectionError("down")
            with self.assertRaises(ConnectionError):
                sync.run_once(conn, "meta", dead, sleep=lambda s: None)
            st = sync.status(conn)
            src = st["sources"]["meta"]
            self.assertEqual(src["last_status"], "error")
            self.assertEqual(src["last_attempts"], 3)
            self.assertIn("down", src["last_error"])
        finally:
            conn.close()


class JobsTest(unittest.TestCase):
    def test_save_and_tick_jobs(self):
        conn = _conn()
        import creative_intel.sync as sync_mod
        orig = sync_mod.fetch_job
        try:
            sync.save_job(conn, "meta", {"ad_account_id": "1"})
            self.assertEqual(sync.jobs(conn),
                             {"meta": {"ad_account_id": "1"}})
            # tick() resolves fetch_job via the module attribute.
            sync_mod.fetch_job = lambda source, params: (
                ingest.parse_csv(CSV, "meta"), [])
            first = sync.tick(conn)
            self.assertTrue(first["meta"]["ok"])
            self.assertEqual(first["meta"]["inserted"], 2)
            second = sync.tick(conn)
            self.assertEqual(second["meta"]["updated"], 2)
            self.assertEqual(_count(conn), 2)
        finally:
            sync_mod.fetch_job = orig
            conn.close()

    def test_tick_isolates_job_failures(self):
        conn = _conn()
        try:
            import creative_intel.sync as sync_mod
            orig = sync_mod.fetch_job

            def fake(source, params):
                if source == "meta":
                    raise ValueError("bad token")
                return ingest.parse_csv(CSV, "tiktok"), []
            sync_mod.fetch_job = fake
            try:
                sync.save_job(conn, "meta", {})
                sync.save_job(conn, "tiktok", {})
                out = sync.tick(conn)
                self.assertFalse(out["meta"]["ok"])
                self.assertIn("bad token", out["meta"]["error"])
                self.assertTrue(out["tiktok"]["ok"])
                st = sync.status(conn)
                self.assertEqual(st["sources"]["meta"]["last_status"],
                                 "error")
                self.assertEqual(st["sources"]["tiktok"]["last_status"],
                                 "ok")
            finally:
                sync_mod.fetch_job = orig
        finally:
            conn.close()

    def test_save_job_rejects_unknown_source(self):
        conn = _conn()
        try:
            with self.assertRaises(ValueError):
                sync.save_job(conn, "nope", {})
        finally:
            conn.close()


class ServerSyncTest(unittest.TestCase):
    def test_connect_upserts_and_saves_job(self):
        import server
        conn = _conn()
        try:
            import creative_intel.sync as sync_mod
            orig = sync_mod.fetch_job
            sync_mod.fetch_job = lambda source, params: (
                ingest.parse_csv(CSV, "meta"), [])
            try:
                out1 = server.apply_action(
                    conn, "connect-meta",
                    {"ad_account_id": "1", "since": "2026-08-01",
                     "until": "2026-08-31"}, None)
                self.assertEqual(out1["inserted"], 2)
                self.assertEqual(out1["updated"], 0)
                out2 = server.apply_action(
                    conn, "connect-meta",
                    {"ad_account_id": "1", "since": "2026-08-01",
                     "until": "2026-08-31"}, None)
                self.assertEqual(out2["inserted"], 0)
                self.assertEqual(out2["updated"], 2)
                self.assertEqual(_count(conn), 2)
                self.assertEqual(
                    sync.jobs(conn)["meta"]["ad_account_id"], "1")
            finally:
                sync_mod.fetch_job = orig
        finally:
            conn.close()

    def test_sync_now_needs_saved_job(self):
        import server
        conn = _conn()
        try:
            with self.assertRaises(ValueError):
                server.apply_action(conn, "sync-now",
                                    {"source": "meta"}, None)
        finally:
            conn.close()

    def test_http_status_and_run(self):
        import server as srv
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        try:
            conn = sqlite3.connect(db)
            schema.init_db(conn)
            conn.close()
            srv.Handler.db_path = db
            httpd = HTTPServer(("127.0.0.1", 0), srv.Handler)
            port = httpd.server_address[1]
            thread = threading.Thread(target=httpd.serve_forever,
                                      daemon=True)
            thread.start()
            try:
                base = "http://127.0.0.1:%d" % port
                cookie = authed(db)
                with urllib.request.urlopen(
                        areq(base + "/api/sync/status", cookie)) as resp:
                    st = json.loads(resp.read())
                self.assertEqual(st["sources"], {})
                self.assertEqual(st["recent"], [])
                self.assertEqual(st["jobs"], [])
                req = urllib.request.Request(
                    base + "/api/sync/run",
                    data=json.dumps({"source": "meta"}).encode(),
                    headers={"Content-Type": "application/json",
                             "Cookie": cookie})
                try:
                    urllib.request.urlopen(req)
                    self.fail("expected 409")
                except urllib.error.HTTPError as exc:
                    self.assertEqual(exc.code, 409)
                    body = json.loads(exc.read())
                    self.assertIn("no saved sync job", body["error"])
            finally:
                httpd.shutdown()
                thread.join(timeout=10)
        finally:
            os.unlink(db)


if __name__ == "__main__":
    unittest.main()
