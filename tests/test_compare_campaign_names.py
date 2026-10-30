"""QI-004: campaign names that contain commas stay one selection."""

import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))
from creative_intel import ingest, schema  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import make_client, mint_admin, temp_db_path  # noqa: E402

CSV = (
    "Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
    "Link Clicks,Conversions\n"
    "\"US, CA\",A1,a1,100,10000,200,10\n"
    "Other,B1,b1,50,5000,100,5\n"
    "Alpha,C1,c1,80,8000,80,8\n"
    "Beta,D1,d1,40,4000,40,4\n"
    "\"A&B\",E1,e1,10,1000,10,1\n"
    "100%,F1,f1,10,1000,10,1\n"
    "Łódź,G1,g1,10,1000,10,1\n"
)


def _db():
    db = temp_db_path()
    conn = sqlite3.connect(db)
    schema.init_db(conn)
    conn.close()
    conn = sqlite3.connect(db)
    ingest.insert_rows(conn, ingest.parse_csv(CSV, "meta"))
    conn.close()
    return db


class CompareCampaignNamesTest(unittest.TestCase):
    def test_repeated_query_values_stay_exact_names(self):
        from ci_backend import actions as server
        db = _db()
        conn = sqlite3.connect(db)
        try:
            got = server.expert2_compare_route(conn, {
                "campaigns": ["US, CA", "Other"],
                "rank_by": ["cpa"],
            })
            self.assertEqual(sorted(got["kpis"]), ["Other", "US, CA"])
        finally:
            conn.close()
            os.unlink(db)

    def test_json_body_reaches_aggregation_without_splitting(self):
        db = _db()
        try:
            client = make_client(db)
            client.headers.update(mint_admin(db))
            resp = client.post("/api/compare/campaigns", json={
                "campaigns": ["US, CA", "Other"],
                "rank_by": "cpa",
            })
            self.assertEqual(resp.status_code, 200, resp.text)
            self.assertEqual(sorted(resp.json()["kpis"]), ["Other", "US, CA"])
        finally:
            os.unlink(db)

    def test_http_repeated_parameters_stay_exact_names(self):
        db = _db()
        try:
            client = make_client(db)
            client.headers.update(mint_admin(db))
            resp = client.get("/api/compare/campaigns", params=[
                ("campaigns", "US, CA"),
                ("campaigns", "A&B"),
                ("campaigns", "100%"),
                ("campaigns", "Łódź"),
                ("rank_by", "cpa"),
            ])
            self.assertEqual(resp.status_code, 200, resp.text)
            self.assertEqual(
                sorted(resp.json()["kpis"]),
                ["100%", "A&B", "US, CA", "Łódź"],
            )
        finally:
            os.unlink(db)

    def test_legacy_single_value_still_splits_on_commas(self):
        from ci_backend import actions as server
        db = _db()
        conn = sqlite3.connect(db)
        try:
            got = server.expert2_compare_route(conn, {
                "campaigns": ["Alpha,Beta"],
                "rank_by": ["cpa"],
            })
            self.assertEqual(sorted(got["kpis"]), ["Alpha", "Beta"])
            # A single already-decoded value cannot tell an encoded
            # comma from a separator. That raw query belongs to the
            # deferred GET handler, so this stays the legacy split.
            legacy = server.expert2_compare_route(conn, {
                "campaigns": ["US, CA,Other"],
                "rank_by": ["cpa"],
            })
            self.assertEqual(sorted(legacy["kpis"]), ["Other"])
        finally:
            conn.close()
            os.unlink(db)
