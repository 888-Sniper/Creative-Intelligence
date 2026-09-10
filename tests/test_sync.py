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
            self.assertEqual(len(first), 1)
            res = next(iter(first.values()))
            self.assertEqual(res["source"], "meta")
            self.assertTrue(res["ok"])
            self.assertEqual(res["inserted"], 2)
            second = sync.tick(conn)
            res2 = next(iter(second.values()))
            self.assertEqual(res2["updated"], 2)
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
                by_source = {r["source"]: r for r in out.values()}
                self.assertFalse(by_source["meta"]["ok"])
                self.assertIn("bad token", by_source["meta"]["error"])
                self.assertTrue(by_source["tiktok"]["ok"])
                st = sync.status(conn)
                self.assertEqual(st["sources"]["meta"]["last_status"],
                                 "error")
                self.assertEqual(st["sources"]["tiktok"]["last_status"],
                                 "ok")
            finally:
                sync_mod.fetch_job = orig
        finally:
            conn.close()

    def test_multiple_jobs_per_source_run_independently(self):
        conn = _conn()
        import creative_intel.sync as sync_mod
        orig = sync_mod.fetch_job
        try:
            a = sync.create_job(conn, "meta", "Meta Account A",
                                {"ad_account_id": "1"}, owner="emp-1")
            b = sync.create_job(conn, "meta", "Meta Account B",
                                {"ad_account_id": "2"}, owner="emp-2")
            self.assertNotEqual(a["id"], b["id"])
            self.assertEqual(
                sorted(j["name"] for j in sync.list_jobs(conn)),
                ["Meta Account A", "Meta Account B"])
            sync_mod.fetch_job = lambda source, params: (
                ingest.parse_csv(CSV, "meta"), [])
            out = sync.tick(conn)
            self.assertEqual(len(out), 2)
            self.assertTrue(all(r["ok"] for r in out.values()))
            st = sync.status(conn)
            self.assertEqual(len(st["job_list"]), 2)
            for info in st["job_list"]:
                self.assertEqual(info["last_run"]["last_status"], "ok")
                self.assertIn(info["owner_employee_id"], ("emp-1", "emp-2"))
            # Disabling one job removes it from tick but keeps the row.
            sync.set_job_enabled(conn, a["id"], False)
            out = sync.tick(conn)
            self.assertEqual(list(out), [b["id"]])
            self.assertEqual(len(sync.list_jobs(conn)), 2)
            self.assertEqual(len(
                sync.list_jobs(conn, include_disabled=False)), 1)
            # Edit + delete round-trip.
            sync.update_job(conn, b["id"], name="Renamed B")
            self.assertEqual(sync.get_job(conn, b["id"])["name"],
                             "Renamed B")
            sync.delete_job(conn, a["id"])
            sync.delete_job(conn, b["id"])
            self.assertEqual(sync.list_jobs(conn), [])
            for bad in (lambda: sync.create_job(conn, "nope", "x", {}),
                        lambda: sync.create_job(conn, "meta", "", {}),
                        lambda: sync.create_job(conn, "meta", "x", []),
                        lambda: sync.update_job(conn, "missing", name="y"),
                        lambda: sync.set_job_enabled(conn, "missing", True),
                        lambda: sync.delete_job(conn, "missing")):
                with self.assertRaises(ValueError):
                    bad()
        finally:
            sync_mod.fetch_job = orig
            conn.close()

    def test_save_job_records_owner_and_status_reports_it(self):
        conn = _conn()
        try:
            sync.save_job(conn, "meta", {"ad_account_id": "1"},
                          owner="emp-123")
            self.assertEqual(sync.job_owners(conn), {"meta": "emp-123"})
            st = sync.status(conn)
            self.assertEqual(st["owners"], {"meta": "emp-123"})
            self.assertEqual(st["jobs"], ["meta"])
        finally:
            conn.close()

    def test_save_job_owner_defaults_empty_and_survives_migrate(self):
        conn = _conn()
        try:
            sync.save_job(conn, "tiktok", {})
            self.assertEqual(sync.job_owners(conn), {"tiktok": ""})
            schema.migrate(conn)
            self.assertEqual(sync.job_owners(conn), {"tiktok": ""})
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
        from ci_backend import actions as server
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
                self.assertEqual(sync.job_owners(conn), {"meta": ""})
                server.apply_action(
                    conn, "connect-meta",
                    {"ad_account_id": "1", "since": "2026-08-01",
                     "until": "2026-08-31"}, None, actor="emp-9")
                self.assertEqual(sync.job_owners(conn), {"meta": "emp-9"})
            finally:
                sync_mod.fetch_job = orig
        finally:
            conn.close()

    def test_sync_now_needs_saved_job(self):
        from ci_backend import actions as server
        conn = _conn()
        try:
            with self.assertRaises(ValueError):
                server.apply_action(conn, "sync-now",
                                    {"source": "meta"}, None)
        finally:
            conn.close()

    def test_http_status_and_run(self):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from conftest import make_client, mint_admin
        db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        try:
            client = make_client(db)
            client.headers.update(mint_admin(db))
            st = client.get("/api/sync/status")
            self.assertEqual(st.status_code, 200)
            self.assertEqual(st.json()["sources"], {})
            self.assertEqual(st.json()["recent"], [])
            self.assertEqual(st.json()["jobs"], [])
            r = client.post("/api/sync/run", json={"source": "meta"})
            self.assertEqual(r.status_code, 409)
            self.assertIn("no saved sync job", r.json()["error"])
        finally:
            os.unlink(db)



if __name__ == "__main__":
    unittest.main()
