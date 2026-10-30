"""Regressions for checkpoint 037: the six partial groups.

QI016 reconstruction is covered in the UI pooling tests. These cases
cover QI057 raw totals, QI150 currency gates, QI176 tied coverage,
QI017 native labels, and QI028 null weighted means. They do not edit
or snapshot the deferred fact pack, start a worker, or run a restore.
"""

import importlib
import os
import sqlite3
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "Backend"))
sys.path.insert(0, os.path.join(ROOT, "Source"))

from creative_intel import benchmarks, ingest, qa, schema  # noqa: E402


def fresh_db():
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    return conn


def test_unreported_raw_totals_stay_null():
    missing = [{"spend": None, "revenue": None, "impressions": 10,
                "clicks": 1, "conversions": 0, "video_views": 0,
                "missing_json": '["spend", "revenue"]'}]
    summary = benchmarks.summarize(missing)
    kpis = benchmarks.kpis_for_rows(missing)
    assert summary["spend"] is None
    assert summary["revenue"] is None
    assert kpis["spend"] is None
    assert summary["impressions"] == 10


def test_supplied_zero_stays_zero_and_legacy_rows_stay_measured():
    zero = benchmarks.summarize([{"spend": 0, "revenue": 0, "missing_json": "[]"}])
    assert zero["spend"] == 0
    assert zero["revenue"] == 0
    legacy = benchmarks.kpis_for_rows([{"spend": None, "impressions": 5}])
    assert legacy["spend"] == 0
    assert legacy["impressions"] == 5


def test_partial_raw_total_sums_only_reporting_rows():
    rows = [
        {"spend": 40, "revenue": 10, "missing_json": "[]"},
        {"spend": None, "revenue": None, "missing_json": '["spend", "revenue"]'},
    ]
    summary = benchmarks.summarize(rows)
    assert summary["spend"] == 40
    assert summary["revenue"] == 10


def test_missing_clicks_make_ctr_unavailable_and_zero_clicks_stay_zero():
    missing = benchmarks.kpis_for_rows([{
        "impressions": 100, "clicks": None, "spend": 10, "conversions": 1,
        "missing_json": '["clicks"]',
    }])
    assert missing["ctr"] is None
    assert missing["clicks"] is None
    assert missing["impressions"] == 100
    zero = benchmarks.kpis_for_rows([{
        "impressions": 100, "clicks": 0, "spend": 10, "conversions": 1,
        "missing_json": "[]",
    }])
    assert zero["ctr"] == 0


def test_mixed_currency_ranking_is_unavailable_and_legacy_still_ranks():
    mixed = ("campaign,ad name,spend,impressions,clicks,conversions,"
             "revenue,currency,date\n"
             "Mix,a,10,1000,20,5,20,USD,2026-08-01\n"
             "Mix,b,100,2000,30,2,50,EUR,2026-08-01\n")
    conn = fresh_db()
    try:
        ingest.insert_rows(conn, ingest.parse_csv(mixed, "meta"))
        out = benchmarks.campaign_recommendations(conn, "Mix", rank_by="cpa")
        text = " ".join(bullet["text"] for sec in out["sections"]
                        for bullet in sec["bullets"])
        assert "comparison unavailable" in text
        assert "$" not in text
        extras = benchmarks._report_extras(conn, ["Mix"], rank_by="cpa")
        assert extras["currency_blocked"] is True
        assert extras["per_campaign"]["Mix"]["best"] is None
    finally:
        conn.close()

    peers = ("campaign,ad name,spend,impressions,clicks,conversions,"
             "revenue,currency,date\n"
             "Alpha,a,10,1000,20,5,20,USD,2026-08-01\n"
             "Beta,b,60,3000,60,3,60,EUR,2026-08-01\n")
    conn = fresh_db()
    try:
        ingest.insert_rows(conn, ingest.parse_csv(peers, "meta"))
        out = benchmarks.campaign_recommendations(conn, "Alpha", rank_by="cpa")
        gap = " ".join(bullet["text"] for bullet in
                       next(sec["bullets"] for sec in out["sections"]
                            if sec["key"] == "benchmark_gap"))
        assert "comparison unavailable" in gap
        assert "$" not in gap
    finally:
        conn.close()


def test_legacy_blank_currency_rank_names_unknown_unit():
    csv = ("campaign,ad name,spend,impressions,clicks,conversions,"
           "revenue,date\n"
           "Alpha,win,10,1000,20,5,10,2026-08-01\n"
           "Alpha,lose,100,2000,30,2,50,2026-08-01\n"
           "Beta,peer,60,3000,60,3,60,2026-08-01\n")
    conn = fresh_db()
    try:
        ingest.insert_rows(conn, ingest.parse_csv(csv, "meta"))
        out = benchmarks.campaign_recommendations(conn, "Alpha", rank_by="cpa")
        text = " ".join(bullet["text"] for sec in out["sections"]
                        for bullet in sec["bullets"])
        assert "peer median" in text
        assert "currency unknown" in text
        assert "2.00 (currency unknown)" in text
        assert "$" not in text
    finally:
        conn.close()


def test_tied_roas_winner_labels_partial_coverage_only():
    conn = fresh_db()
    try:
        conn.executemany(
            "INSERT INTO ads (platform, campaign, ad_name, creative_key,"
            " spend, impressions, clicks, conversions, revenue,"
            " revenue_reported, currency, date)"
            " VALUES (?,?,?,?,?,10000,200,10,?,?,?,?)",
            [
                ("meta", "A", "k1", "k1", 100, 200, 1, "", "2026-08-01"),
                ("meta", "A", "k2", "k2", 900, 0, 0, "", "2026-08-01"),
                ("tiktok", "B", "k3", "k3", 100, 200, 1, "", "2026-08-01"),
            ])
        got = qa.answer(conn, "Which platform has the best ROAS?")
        assert "tied" in got["answer"]
        assert "revenue-reporting spend coverage" in got["answer"]
        assert "coverage 100%" not in got["answer"]
    finally:
        conn.close()

    conn = fresh_db()
    try:
        conn.executemany(
            "INSERT INTO ads (platform, campaign, ad_name, creative_key,"
            " spend, impressions, clicks, conversions, revenue,"
            " revenue_reported, currency, date)"
            " VALUES (?,?,?,?,?,10000,200,10,?,?,?,?)",
            [
                ("meta", "A", "k1", "k1", 100, 200, 1, "GBP", "2026-08-01"),
                ("tiktok", "B", "k2", "k2", 100, 200, 1, "GBP", "2026-08-01"),
            ])
        got = qa.answer(conn, "Which platform has the best ROAS?")
        assert "tied" in got["answer"]
        assert "coverage" not in got["answer"]
        spend = qa.answer(conn, "What is total spend?")
        assert "GBP" in spend["answer"]
        assert "$" not in spend["answer"]
    finally:
        conn.close()


def test_zero_weight_mean_stays_unavailable_in_source_exports():
    source_benchmarks = importlib.import_module("benchmarks")
    reports = importlib.import_module("reports")
    dashboard = importlib.import_module("dashboard")
    deck = importlib.import_module("deck")
    assert source_benchmarks.spend_weighted_mean([12.0], [0]) is None
    assert source_benchmarks.spend_weighted_mean([0.0], [10]) == 0
    assert source_benchmarks.spend_weighted_mean([None, 8.0], [10, 0]) is None

    rows = []
    for index in range(5):
        rows.append({
            "campaign_id": "c%s" % index,
            "creative_id": "cr%s" % index,
            "project": "p%s" % (index % 3),
            "platform": "meta",
            "date": "2026-08-01",
            "spend": 0,
            "impr": 100,
            "clicks": 1,
            "video_views": 10,
            "conversions": 0,
            "revenue": 0,
            "cpa": 5.0,
            "roas": 0.0,
        })
    text = reports.one_pager(rows, [], {}, "Cohort")
    assert "CPA benchmark (cpa): unavailable" in text
    assert "weighted mean unavailable" in text
    html = dashboard.render(rows, rows, "Cohort")
    assert "Benchmark CPA unavailable" in html
    deck_html = deck.render_deck(rows, [], "Cohort")
    assert "Cohort CPA mean unavailable" in deck_html
    assert "weighted mean unavailable" in deck_html
    empty = dashboard.render([], [], "Empty")
    assert "Benchmark CPA" in empty
    empty_deck = deck.render_deck([], [], "Empty")
    assert "<!DOCTYPE html>" in empty_deck
    assert "Creative learnings" in empty_deck


def test_null_cpa_does_not_crash_source_ask():
    ask = importlib.import_module("ask")
    joined = [{
        "creative_id": "cr%s" % index,
        "project": "p%s" % (index % 3),
        "platform": "meta",
        "hook_type": "demo",
        "cpa": None,
        "spend": 0,
        "duration_s": 10,
        "funnel_stage": "lower",
    } for index in range(5)]
    hook = ask.answer("Which hook wins?", joined, joined)
    assert "unavailable" in hook["answer"]
    assert hook["grounded"] is True
    funnel = ask.answer("How does the lower funnel perform?", joined, joined)
    assert "unavailable" in funnel["answer"]
