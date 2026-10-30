"""Regressions for checkpoint 036: the ten high groups.

QI-001, QI035, QI036, QI037, QI038, QI172, QI173 (QI259), QI178,
QI263, and QI315. These tests stay on the public helpers. They do
not call the review route, start a worker, or run a restore.
"""

import datetime
import inspect
import json
import os
import sqlite3
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "Backend"))

from ci_backend import worker  # noqa: E402
from creative_intel import (  # noqa: E402
    benchmarks,
    drafts,
    ingest,
    jobs,
    qa,
    review_bind,
    schema,
)
from creative_intel import video_analysis as va  # noqa: E402


def fresh_db():
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    return conn


def annotate(conn, key, product_start=None, mode=None):
    ann = {}
    if product_start is not None:
        ann["product_seconds"] = [{"start_s": product_start,
                                   "end_s": product_start + 1.0}]
    if mode is not None:
        ann["creator_vs_branded"] = mode
    conn.execute(
        "INSERT INTO annotations (creative_key, schema_version,"
        " annotation_json, updated_at) VALUES (?, ?, ?, ?)",
        (key, "v0", json.dumps(ann),
         datetime.datetime.now(datetime.timezone.utc).isoformat()))
    conn.commit()


def ads_rows(conn):
    cols = [c[0] for c in conn.execute("SELECT * FROM ads LIMIT 0").description]
    return [dict(zip(cols, row)) for row in conn.execute("SELECT * FROM ads")]


# --- QI035 header precedence ------------------------------------------

def test_alias_order_reserves_link_clicks():
    clicks = ingest._ALIASES["clicks"]
    assert clicks[0] == "clicks"
    assert clicks[-1] == "link clicks"
    assert ingest._ALIASES["link_clicks"][0] == "link clicks"


def test_both_click_columns_stay_on_their_fields():
    col_map, ambiguous = ingest._map_headers(
        ["Clicks", "Link Clicks", "Spend"])
    assert col_map["clicks"] == "Clicks"
    assert col_map["link_clicks"] == "Link Clicks"
    assert not any(item.get("field") == "clicks" for item in ambiguous)
    conn = fresh_db()
    out = ingest.import_report(
        conn,
        "Campaign,Ad,Creative,Impressions,Clicks,Link Clicks\n"
        "C,A,kboth,1000,10,40\n",
        "meta")
    row = conn.execute(
        "SELECT clicks, link_clicks FROM ads").fetchone()
    assert out["quarantined"] == 0
    assert row == (10, 40)
    conn.close()


def test_link_clicks_only_still_fills_clicks():
    col_map, _ambiguous = ingest._map_headers(["Link Clicks", "Impressions"])
    assert col_map["clicks"] == "Link Clicks"
    assert col_map["link_clicks"] == "Link Clicks"
    conn = fresh_db()
    out = ingest.import_report(
        conn,
        "Campaign,Ad,Creative,Impressions,Link Clicks\n"
        "C,A,klink,1000,50\n",
        "meta")
    row = conn.execute(
        "SELECT clicks, link_clicks FROM ads").fetchone()
    assert out["mapping"]["clicks"] == "Link Clicks"
    assert row == (50, 50)
    conn.close()


def test_disagreeing_spend_columns_are_quarantined():
    conn = fresh_db()
    out = ingest.import_report(
        conn,
        "Campaign,Ad,Creative,Spend,Cost,Impressions\n"
        "C,A,kbad,10,99,1000\n",
        "meta")
    assert out["inserted"] == 0
    assert out["quarantined"] == 1
    assert "ambiguous spend" in out["quarantine"][0]["reason"]
    assert conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0] == 0
    conn.close()


def test_agreeing_spend_columns_keep_the_first_and_record_ambiguity():
    conn = fresh_db()
    out = ingest.import_report(
        conn,
        "Campaign,Ad,Creative,Spend,Cost,Impressions\n"
        "C,A,kok,10,10,1000\n",
        "meta")
    assert out["inserted"] == 1
    assert out["quarantined"] == 0
    assert any(item.get("field") == "spend" for item in out["ambiguous"])
    assert conn.execute("SELECT spend FROM ads").fetchone()[0] == 10
    conn.close()


def test_duplicate_headers_are_recorded():
    _col_map, ambiguous = ingest._map_headers(["Spend", "Spend"])
    assert any(item.get("reason") == "duplicate headers" for item in ambiguous)


# --- QI036 missing revenue is not a reported zero ---------------------

def test_blank_revenue_markers_stay_unreported_and_zero_stays_reported():
    conn = fresh_db()
    ingest.import_report(
        conn,
        "Campaign,Ad,Creative,Spend,Revenue\n"
        "C,A1,kblank,10,\n"
        "C,A2,kdash,10,-\n"
        "C,A3,kna,10,n/a\n"
        "C,A4,kNA,10,N/A\n"
        "C,A5,kbrak,10,brak\n"
        "C,A6,kzero,10,0\n",
        "meta")
    flags = dict(conn.execute(
        "SELECT creative_key, revenue_reported FROM ads").fetchall())
    for key in ("kblank", "kdash", "kna", "kNA", "kbrak"):
        assert flags[key] in (0, False)
    assert flags["kzero"] in (1, True)
    conn.close()


def test_unmapped_revenue_is_unreported():
    conn = fresh_db()
    ingest.import_report(
        conn,
        "Campaign,Ad,Creative,Spend,Impressions\n"
        "C,A,knone,10,100\n",
        "meta")
    flag = conn.execute(
        "SELECT revenue_reported FROM ads").fetchone()[0]
    assert flag in (0, False)
    conn.close()


def test_matched_roas_uses_only_reported_revenue():
    conn = fresh_db()
    ingest.import_report(
        conn,
        "Campaign,Ad,Creative,Spend,Impressions,Revenue\n"
        "C,A,rep,100,1000,200\n"
        "C,B,miss,900,1000,brak\n",
        "meta")
    value, coverage = benchmarks.matched_roas(ads_rows(conn))
    assert value == 2.0
    assert coverage == 0.1
    conn.close()


# --- QI037 one transaction for facts and provenance -------------------

def test_commit_false_rolls_back_and_default_upsert_commits():
    conn = fresh_db()
    rows = ingest.parse_csv(
        "Campaign,Ad,Creative,Spend,Impressions\n"
        "C,A,ktx,10,100\n",
        "meta")
    ingest.upsert_rows(conn, rows, commit=False)
    assert conn.in_transaction
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0] == 0
    ingest.upsert_rows(conn, rows)
    assert not conn.in_transaction
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0] == 1
    conn.close()


def test_import_count_failure_rolls_back_facts_and_provenance():
    class Boom(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if isinstance(sql, str) and "UPDATE analyst_imports" in sql:
                raise sqlite3.OperationalError(
                    "forced import count failure")
            return super().execute(sql, parameters)

    conn = sqlite3.connect(":memory:", factory=Boom)
    schema.init_db(conn)
    with pytest.raises(sqlite3.OperationalError):
        ingest.import_report(
            conn,
            "Campaign,Ad,Creative,Spend,Impressions\n"
            "C,A,kroll,10,100\n",
            "meta")
    assert conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM analyst_imports").fetchone()[0] == 0
    conn.close()


# --- QI038 quartile denominator is the reporting exposure -------------

def _curve(conn, key):
    return conn.execute(
        "SELECT t_sec, retention_pct, coverage FROM retention"
        " WHERE creative_key=? ORDER BY t_sec",
        (key,)).fetchall()


def test_partial_quartile_uses_reporting_impressions_only():
    conn = fresh_db()
    ingest.insert_rows(conn, ingest.parse_csv(
        "Campaign,Ad,Creative,Impressions,100% Views\n"
        "C,A1,pkey,1000,100\n"
        "C,A2,pkey,9000,\n",
        "meta"))
    assert _curve(conn, "pkey") == [(0.0, 100.0, 1.0), (30.0, 10.0, 0.1)]
    conn.close()


def test_measured_zero_quartile_stays_zero():
    conn = fresh_db()
    ingest.insert_rows(conn, ingest.parse_csv(
        "Campaign,Ad,Creative,Impressions,100% Views\n"
        "C,A,zkey,1000,0\n",
        "meta"))
    assert _curve(conn, "zkey") == [(0.0, 100.0, 1.0), (30.0, 0.0, 1.0)]
    conn.close()


def test_wholly_missing_quartile_adds_no_point():
    conn = fresh_db()
    ingest.insert_rows(conn, ingest.parse_csv(
        "Campaign,Ad,Creative,Impressions,100% Views\n"
        "C,A,mkey,1000,\n",
        "meta"))
    assert _curve(conn, "mkey") == []
    conn.close()


def test_migrate_adds_coverage_and_keeps_the_old_point():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE ads (id INTEGER PRIMARY KEY, platform TEXT,"
        " source TEXT, campaign TEXT, adset TEXT, ad_name TEXT,"
        " creative_key TEXT, spend REAL, impressions INTEGER,"
        " clicks INTEGER, conversions REAL, video_views INTEGER,"
        " views_25 INTEGER, views_50 INTEGER, views_75 INTEGER,"
        " views_100 INTEGER, client TEXT, project TEXT,"
        " vertical TEXT, market TEXT, objective TEXT,"
        " funnel_stage TEXT, date TEXT, revenue REAL)")
    conn.execute(
        "CREATE TABLE retention (creative_key TEXT NOT NULL,"
        " t_sec REAL NOT NULL, retention_pct REAL NOT NULL,"
        " PRIMARY KEY (creative_key, t_sec))")
    conn.execute("INSERT INTO retention VALUES ('k', 0, 99)")
    schema.migrate(conn)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(retention)")]
    assert "coverage" in cols
    got = conn.execute(
        "SELECT retention_pct, coverage FROM retention").fetchone()
    assert got[0] == 99
    assert got[1] is None
    conn.close()


# --- QI172 incomparable view rates ------------------------------------

def _seed_rates(early_completions, late_completions):
    early_cell = "100" if early_completions else ""
    late_cell = "200" if late_completions else ""
    conn = fresh_db()
    csv_text = (
        "Campaign,Ad,Creative,Spend,Impressions,Clicks,Conversions,"
        "Video Views,100% Views\n"
        "C,A1,early-c,100,1000,10,1,500,{early}\n"
        "C,A2,late-p,100,1000,10,1,400,{late}\n"
    ).format(early=early_cell, late=late_cell)
    ingest.insert_rows(conn, ingest.parse_csv(csv_text, "meta"))
    annotate(conn, "early-c", product_start=1.0)
    annotate(conn, "late-p", product_start=8.0)
    return conn


def test_early_completions_and_late_plays_are_not_ranked():
    conn = _seed_rates(True, False)
    text = qa.answer(
        conn, "Does early product appearance improve VTR?")["answer"]
    assert "Unclear:" in text
    assert "not comparable" in text
    assert "VTR" in text and "play rate" in text
    assert "Yes:" not in text and "No:" not in text
    assert "10.0%" not in text and "40.0%" not in text
    conn.close()


def test_early_plays_and_late_completions_are_not_ranked():
    conn = _seed_rates(False, True)
    text = qa.answer(
        conn, "Does early product appearance improve VTR?")["answer"]
    assert "Unclear:" in text
    assert "not comparable" in text
    assert "play rate" in text and "VTR" in text
    assert "Yes:" not in text and "No:" not in text
    assert "50.0%" not in text and "20.0%" not in text
    conn.close()


# --- QI173 / QI259 unavailable rates are not measured zeroes ----------

def test_zero_conversion_format_cpa_is_unavailable():
    conn = fresh_db()
    ingest.insert_rows(conn, ingest.parse_csv(
        "Campaign,Ad,Video Name,Spend,Impressions,Clicks,Results,"
        "Video Views\n"
        "S1,B1,tt-zero,200,20000,400,0,8000\n",
        "tiktok"))
    annotate(conn, "tt-zero", mode="creator")
    text = qa.answer(conn, "Which TikTok format wins?")["answer"]
    assert "CPA unavailable" in text
    assert "CPA $0.00" not in text
    conn.close()


def test_zero_impression_ctr_is_unavailable_and_zero_clicks_stay_zero():
    empty = fresh_db()
    ingest.insert_rows(empty, ingest.parse_csv(
        "Campaign,Ad,Creative,Spend,Impressions,Clicks\n"
        "C,A,zimp,10,0,3\n",
        "meta"))
    missing = qa.answer(empty, "What is the CTR?")["answer"]
    assert "unavailable" in missing
    assert "0.00%" not in missing
    assert "300.00%" not in missing
    empty.close()

    measured = fresh_db()
    ingest.insert_rows(measured, ingest.parse_csv(
        "Campaign,Ad,Creative,Spend,Impressions,Clicks\n"
        "C,A,zclk,10,1000,0\n",
        "meta"))
    present = qa.answer(measured, "What is the CTR?")["answer"]
    assert "0.00%" in present
    assert "unavailable" not in present
    measured.close()


# --- QI178 ranking follows the asked metric ---------------------------

def test_top_and_bottom_follow_ctr_when_cpa_ranks_the_other_way():
    lines = ["Campaign,Ad,Creative,Spend,Impressions,Clicks,Conversions"]
    for i in range(1, 11):
        lines.append("C,Ad%02d,c%02d,100,1000,%d,%d" % (i, i, i * 10, 11 - i))
    conn = fresh_db()
    ingest.insert_rows(conn, ingest.parse_csv("\n".join(lines) + "\n", "meta"))
    text = qa.answer(
        conn, "Compare the top versus bottom creatives by CTR")["answer"]
    assert "Top creative by CTR is c10 at 10.00%." in text
    assert "Top 20% by CTR" in text
    assert "Bottom 20% by CTR" in text
    assert "by CPA" not in text
    top, bottom = text.split("Bottom 20% by CTR", 1)
    assert "c10" in top and "c09" in top
    assert "c01" in bottom and "c02" in bottom
    assert "c10" not in bottom
    conn.close()


def test_unnamed_top_versus_bottom_ranks_by_spend():
    conn = fresh_db()
    ingest.insert_rows(conn, ingest.parse_csv(
        "Campaign,Ad,Creative,Spend,Impressions\n"
        "C,A,c-hi,500,1000\n"
        "C,B,c-lo,10,1000\n",
        "meta"))
    text = qa.answer(conn, "Compare top vs bottom creatives")["answer"]
    assert "Top 20%" in text and "Bottom 20%" in text
    assert "by SPEND" in text
    top, bottom = text.split("Bottom 20%", 1)
    assert "c-hi" in top
    assert "c-lo" in bottom
    conn.close()


def test_one_creative_is_not_enough_for_a_split():
    conn = fresh_db()
    ingest.insert_rows(conn, ingest.parse_csv(
        "Campaign,Ad,Creative,Spend,Impressions\n"
        "C,A,only,10,100\n",
        "meta"))
    text = qa.answer(conn, "Compare top vs bottom creatives")["answer"]
    assert "Not enough ranked creatives" in text
    conn.close()


def test_mixed_currency_has_no_spend_or_cpa_score():
    mixed = [
        {"spend": 10, "revenue": 0, "impressions": 100, "clicks": 10,
         "conversions": 1, "currency": "USD", "creative_key": "a"},
        {"spend": 10, "revenue": 0, "impressions": 100, "clicks": 10,
         "conversions": 1, "currency": "EUR", "creative_key": "b"},
    ]
    assert qa._group_score(mixed, "cpa") is None
    assert qa._group_score(mixed, None) is None
    assert qa._group_score(mixed, "ctr") == 0.1


# --- QI263 lease scan without starting the worker ---------------------

def test_recovery_due_uses_the_monotonic_deadline():
    assert worker.recovery_due(None, 10.0, 5.0) == (True, 15.0)
    assert worker.recovery_due(20.0, 10.0, 5.0) == (False, 20.0)
    assert worker.recovery_due(10.0, 10.0, 5.0) == (True, 15.0)


def test_expired_lease_requeues_once_and_a_fresh_lease_stays(tmp_path):
    db = str(tmp_path / "jobs.db")
    conn = worker._connect(db)
    job = jobs.enqueue(conn, "ask", {})
    jobs.claim(conn, job["id"])
    conn.close()

    assert worker.recover_expired_leases(db) == 0
    conn = sqlite3.connect(db)
    assert jobs.get(conn, job["id"])["status"] == "running"
    conn.execute(
        "UPDATE worker_jobs SET lease_expires_at='2000-01-01T00:00:00+00:00'"
        " WHERE id=?",
        (job["id"],))
    conn.commit()
    conn.close()

    due, _deadline = worker.recovery_due(100.0, 50.0, 5.0)
    assert due is False
    conn = sqlite3.connect(db)
    assert jobs.get(conn, job["id"])["status"] == "running"
    conn.close()

    due, deadline = worker.recovery_due(50.0, 50.0, 5.0)
    assert due is True
    assert deadline == 55.0
    assert worker.recover_expired_leases(db) == 1
    conn = sqlite3.connect(db)
    assert jobs.get(conn, job["id"])["status"] == "queued"
    conn.close()
    assert worker.recover_expired_leases(db) == 0


def test_both_loops_recheck_recovery_due():
    assert "recovery_due" in inspect.getsource(worker.daemon)
    assert "recover_expired_leases" in inspect.getsource(worker.daemon)
    assert "recovery_due" in inspect.getsource(worker.main)
    assert "recover_expired_leases" in inspect.getsource(worker.main)


# --- QI315 documentation only -----------------------------------------

def test_restore_doc_stages_and_keeps_a_rollback_copy():
    path = os.path.join(ROOT, "docs", "BACKUP.md")
    text = open(path, encoding="utf-8").read()
    section = text[text.index("## Restore"):text.index("## Before migrations")]
    assert ".restore-staging" in section
    assert ".restore-rollback" in section
    assert "test -s" in section
    assert 'cp "$BACKUP/creative_intel.db" "<data>/creative_intel.db"' not in section
    assert 'cp -r "$BACKUP/media" "<data>/media"' not in section
    assert section.index('"<data>/.restore-rollback/media"') < section.index(
        'rm -rf "<data>/media"')
    assert "Do not run it against a live host" in section


# --- QI-001 video-only rebind boundary --------------------------------

def test_video_only_flag_compares_without_treating_legacy_as_a_change():
    assert review_bind.stored_video_only({"video_only": True}) is True
    assert review_bind.stored_video_only({"video_only": False}) is False
    assert review_bind.stored_video_only({}) is False
    assert review_bind.stored_video_only(None) is False
    assert review_bind.inputs_unchanged(
        {"video_id": "v", "video_only": False},
        {"video_id": "v"}) is True
    assert review_bind.inputs_unchanged(
        {"video_id": "v", "video_only": True},
        {"video_id": "v", "video_only": False}) is False
    assert review_bind.inputs_unchanged(
        {"video_id": "v", "video_only": True},
        {"video_id": "v"}) is False
    assert "video_only" in review_bind.SNAPSHOT_KEYS


def test_video_only_bind_needs_no_destination():
    conn = fresh_db()
    did = drafts.create_draft(conn, "emp-1")
    drafts.add_video(conn, did, "ck-1", media_id=0, duration_s=15.8,
                     width=1080, height=1920, sha256="abc",
                     validation={"status": "valid"})
    snap = va.bind_snapshot(conn, did, video_only=True)
    assert snap["video_only"] is True
    assert snap["records"] == []
    with pytest.raises(va.AnalysisUnavailable):
        va.bind_snapshot(conn, did)
    conn.close()


def test_review_rebind_passes_the_stored_video_only_flag():
    path = os.path.join(ROOT, "Backend", "ci_backend", "routers", "product.py")
    text = open(path, encoding="utf-8").read()
    assert "video_only=review_bind.stored_video_only(stored_snap)" in text
    assert "for snap_key in review_bind.SNAPSHOT_KEYS:" in text
