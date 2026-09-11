"""Seed an isolated E2E database (test infrastructure only, never production).

Creates an active admin, an active employee, and a pending employee, each
with a live session token, and writes the raw tokens to a JSON file for
Playwright to plant as session cookies. Usage:
    python3 e2e/seed.py <db_path> <seeds_json_path>
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "Backend"))

from ci_backend import employees as emp
from ci_backend.db import (ensure_migrated, make_engine,  # noqa: E402
                           make_session_factory)
from creative_intel import ingest  # noqa: E402  # isort: skip

ADS_HDR = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
           "Link Clicks,Conversions,Revenue,Date\n")


def _ads_row(camp, ad, spend, impr, clicks, conv, rev, day):
    return "%s,%s,c-%s,%s,%s,%s,%s,%s,%s\n" % (
        camp, ad, ad, spend, impr, clicks, conv, rev, day)


# Deterministic two-period performance data for KPI comparison tests.
# Current week 2024-01-01..2024-01-07 vs previous 2023-12-25..2023-12-31:
# impressions 25000 vs 20000 (+25%), clicks 600 vs 400 (+50%),
# spend 300 vs 200 (+50%), conversions 24 vs 20 (+20%),
# CTR 2.4% vs 2.0% (+20%), CPA 12.5 vs 10.0 (+25%, lower-better),
# ROAS 2.0 vs 2.0 (flat).
ADS_SEEDS = (
    (ADS_HDR
     + _ads_row("Seeded", "p1", 100, 10000, 200, 10, 200, "2023-12-25")
     + _ads_row("Seeded", "c1", 150, 12500, 300, 12, 300, "2024-01-02"),
     "meta"),
    (ADS_HDR
     + _ads_row("Seeded", "p2", 100, 10000, 200, 10, 200, "2023-12-28")
     + _ads_row("Seeded", "c2", 150, 12500, 300, 12, 300, "2024-01-05"),
     "tiktok"),
)


def seed_ads(db_path) -> None:
    import sqlite3

    from creative_intel import schema

    conn = sqlite3.connect(db_path)
    try:
        # Product tables are created lazily per request in production
        # (get_product_conn); the seed creates them up front instead.
        schema.init_db(conn)
        for csv_text, platform in ADS_SEEDS:
            ingest.insert_rows(
                conn, ingest.parse_csv(csv_text, platform, "upload"))
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    db_path, seeds_path = sys.argv[1], sys.argv[2]
    container = sys.argv[3] if len(sys.argv) > 3 else ""
    engine = make_engine(db_path)
    ensure_migrated(engine)
    factory = make_session_factory(engine)
    with factory() as sess:
        admin = emp.admin_create(sess, "root", "boss@foap.test",
                                 first_name="Boss", last_name="Admin",
                                 role="admin")
        employee = emp.admin_create(sess, admin.id, "ada@foap.test",
                                    first_name="Ada", last_name="L",
                                    role="employee")
        pending, _ = emp.ensure_identity(sess, {
            "email": "pip@foap.test", "verified": True,
            "workos_user_id": "w-pip", "first_name": "Pip",
            "last_name": "Pending", "avatar_url": ""})
        assert pending.status == "pending", pending.status
        # Dedicated KPI-comparison account: auth.spec logs the employee
        # out and revokes the admin sessions, so the comparison spec
        # must not depend on either of those tokens.
        kpi_user = emp.admin_create(sess, admin.id, "kpi@foap.test",
                                    first_name="Kay", last_name="Peye",
                                    role="employee")
        seeds = {
            "admin": emp.create_session(sess, admin.id, "", container),
            "employee": emp.create_session(sess, employee.id, "", container),
            "pending": emp.create_session(sess, pending.id, "w-pip",
                                           container),
            "kpi": emp.create_session(sess, kpi_user.id, "", container),
        }
    with open(seeds_path, "w") as fh:
        json.dump(seeds, fh)
    seed_ads(db_path)
    print("seeded %s" % db_path)


if __name__ == "__main__":
    main()
