"""Regressions for the QI150 and QI176 fact-pack remainder.

Mixed native money is not added or ranked. A wholly unspecified
currency still produces numeric spend and CPA. ROAS winners stay on
revenue-reporting rows. These cases do not snapshot annotations.
"""

import json
import os
import sqlite3
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "Backend"))

from creative_intel import qa, schema  # noqa: E402


def fresh_db():
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    return conn


def insert_ads(conn, rows):
    conn.executemany(
        "INSERT INTO ads (platform, campaign, ad_name, creative_key,"
        " spend, impressions, clicks, conversions, revenue,"
        " revenue_reported, currency, date, market, funnel_stage,"
        " vertical)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows)


def row(campaign, key, spend, conversions, currency, market, stage,
        vertical, platform="meta", revenue=0, reported=0, clicks=10):
    return (platform, campaign, key, key, spend, 1000, clicks, conversions,
            revenue, reported, currency, "2026-08-01", market, stage,
            vertical)


def test_mixed_fact_pack_does_not_add_or_rank_native_money():
    conn = fresh_db()
    try:
        insert_ads(conn, [
            row("Alpha", "a-gbp", 10, 1, "GBP", "Aland", "alpha", "apple"),
            row("Zulu", "z-eur", 500, 100, "EUR", "Zedland", "zeta", "zebra"),
        ])
        pack = qa._fact_pack(conn)
    finally:
        conn.close()
    assert pack["totals"]["spend"] is None
    assert pack["totals"]["cpa"] is None
    assert pack["totals"]["mixed_currency"] is True
    assert pack["totals"]["spend_ranking"] == "unavailable"
    assert pack["totals"]["ctr"] == 0.01
    assert "roas" not in pack["totals"]
    assert [item["campaign"] for item in pack["campaigns"]] == ["Alpha", "Zulu"]
    assert pack["campaigns"][0]["spend"] == 10
    assert pack["campaigns"][0]["currency"] == "GBP"
    assert pack["campaigns"][0]["cpa"] == 10
    assert pack["campaigns"][1]["spend"] == 500
    assert pack["campaigns"][1]["currency"] == "EUR"
    assert pack["markets"][0]["market"] == "Aland"
    assert pack["markets"][0]["spend"] == 10
    assert pack["funnel"][0]["stage"] == "alpha"
    assert pack["verticals"][0]["vertical"] == "apple"
    assert pack["verticals"][0]["spend"] == 10
    assert pack["quintiles"]["top_20_pct"] == []
    assert pack["quintiles"]["bottom_20_pct"] == []
    assert pack["quintiles"]["ranking"] == "unavailable"
    assert "$" not in json.dumps(pack)


def test_blank_currency_fact_pack_still_ranks():
    conn = fresh_db()
    try:
        insert_ads(conn, [
            row("Zulu", "z-hi", 100, 10, "", "Zedland", "zeta", "zebra"),
            row("Alpha", "a-lo", 50, 10, "", "Aland", "alpha", "apple"),
        ])
        pack = qa._fact_pack(conn)
    finally:
        conn.close()
    assert pack["totals"]["spend"] == 150
    assert pack["totals"]["cpa"] == 7.5
    assert pack["totals"]["mixed_currency"] is False
    assert pack["totals"]["currency_known"] is False
    assert pack["totals"]["currency"] is None
    assert pack["totals"]["spend_ranking"] == "available"
    assert pack["campaigns"][0]["campaign"] == "Zulu"
    assert pack["campaigns"][0]["spend"] == 100
    assert pack["quintiles"]["top_20_pct"] == ["a-lo"]
    assert "ranking" not in pack["quintiles"]
    assert "$" not in json.dumps(pack)


def test_one_currency_fact_pack_keeps_its_code_and_cost_rank():
    conn = fresh_db()
    try:
        insert_ads(conn, [
            row("Zulu", "z-hi", 100, 10, "GBP", "Zedland", "zeta", "zebra"),
            row("Alpha", "a-lo", 50, 10, "GBP", "Aland", "alpha", "apple"),
        ])
        pack = qa._fact_pack(conn)
    finally:
        conn.close()
    assert pack["totals"]["spend"] == 150
    assert pack["totals"]["currency"] == "GBP"
    assert pack["totals"]["currency_known"] is True
    assert pack["totals"]["mixed_currency"] is False
    assert pack["campaigns"][0]["campaign"] == "Zulu"
    assert pack["quintiles"]["top_20_pct"] == ["a-lo"]
    assert "$" not in json.dumps(pack)


def test_known_plus_unknown_fact_pack_is_unavailable():
    conn = fresh_db()
    try:
        insert_ads(conn, [
            row("Alpha", "a-blank", 10, 1, "", "Aland", "alpha", "apple"),
            row("Zulu", "z-gbp", 500, 10, "GBP", "Zedland", "zeta", "zebra"),
        ])
        pack = qa._fact_pack(conn)
    finally:
        conn.close()
    assert pack["totals"]["spend"] is None
    assert pack["totals"]["cpa"] is None
    assert pack["totals"]["mixed_currency"] is True
    assert pack["campaigns"][0]["campaign"] == "Alpha"
    assert pack["campaigns"][0]["spend"] == 10
    assert pack["campaigns"][1]["spend"] == 500
    assert pack["campaigns"][1]["currency"] == "GBP"
    assert pack["quintiles"]["top_20_pct"] == []


def test_gbp_cpa_does_not_rank_ahead_of_or_behind_eur_cpa():
    rows = [
        {"creative_key": "gbp", "spend": 10, "conversions": 1,
         "impressions": 100, "clicks": 1, "currency": "GBP", "revenue": 0},
        {"creative_key": "eur", "spend": 8, "conversions": 1,
         "impressions": 100, "clicks": 1, "currency": "EUR", "revenue": 0},
    ]
    top, bottom, count = qa._quintile_split(rows, "cpa")
    assert (top, bottom, count) == ([], [], 2)
    assert qa._group_score([rows[0]], "cpa") == 10
    assert qa._group_score([rows[1]], "cpa") == 8
    same = [
        {"creative_key": "dear", "spend": 20, "conversions": 1,
         "impressions": 100, "clicks": 1, "currency": "GBP", "revenue": 0},
        {"creative_key": "cheap", "spend": 10, "conversions": 1,
         "impressions": 100, "clicks": 1, "currency": "GBP", "revenue": 0},
    ]
    top, bottom, count = qa._quintile_split(same, "cpa")
    assert top == ["cheap"]
    assert bottom == ["dear"]
    assert count == 2


def test_mixed_spend_question_names_no_top_row():
    conn = fresh_db()
    try:
        insert_ads(conn, [
            row("Alpha", "small-gbp", 10, 1, "GBP", "Aland", "alpha", "apple"),
            row("Zulu", "large-eur", 500, 1, "EUR", "Zedland", "zeta", "zebra"),
        ])
        text = qa.answer(conn, "what is total spend?")["answer"]
    finally:
        conn.close()
    assert "unavailable" in text
    assert "No spend ranking is available across currencies." in text
    assert "Top spend row" not in text
    assert "large-eur" not in text
    assert "$" not in text


def test_blank_spend_question_still_names_the_larger_row():
    conn = fresh_db()
    try:
        insert_ads(conn, [
            row("Alpha", "small", 10, 1, "", "Aland", "alpha", "apple"),
            row("Zulu", "large", 500, 1, "", "Zedland", "zeta", "zebra"),
        ])
        text = qa.answer(conn, "what is total spend?")["answer"]
    finally:
        conn.close()
    assert "Top spend row is 'large'" in text
    assert "currency unknown" in text
    assert "$" not in text


def test_cross_currency_roas_has_no_winner():
    conn = fresh_db()
    try:
        insert_ads(conn, [
            row("A", "gbp", 100, 1, "GBP", "UK", "low", "ads",
                revenue=400, reported=1),
            row("B", "eur", 100, 1, "EUR", "DE", "low", "ads",
                platform="tiktok", revenue=150, reported=1),
        ])
        text = qa.answer(conn, "Which platform has the best ROAS?")["answer"]
    finally:
        conn.close()
    assert "no ROAS winner" in text
    assert "Top platform by ROAS is" not in text


def test_reported_roas_keeps_matched_value_and_coverage():
    conn = fresh_db()
    try:
        insert_ads(conn, [
            row("A", "reported", 100, 1, "GBP", "UK", "low", "ads",
                revenue=200, reported=1),
            row("A", "unreported", 100, 1, "GBP", "UK", "low", "ads",
                revenue=0, reported=0),
            row("B", "other", 100, 1, "GBP", "UK", "low", "ads",
                platform="tiktok", revenue=150, reported=1),
        ])
        text = qa.answer(conn, "Which platform has the best ROAS?")["answer"]
    finally:
        conn.close()
    assert "Top platform by ROAS is Meta at 2.0x" in text
    assert "coverage 50%" in text
    assert "1.0x" not in text


def test_cross_currency_cpa_split_names_no_cost_winner():
    conn = fresh_db()
    try:
        insert_ads(conn, [
            row("Alpha", "gbp-dear", 10, 1, "GBP", "Aland", "alpha", "apple"),
            row("Zulu", "eur-cheap", 8, 1, "EUR", "Zedland", "zeta", "zebra"),
        ])
        text = qa.answer(conn, "Compare top vs bottom cpa")["answer"]
    finally:
        conn.close()
    assert "no CPA winner" in text
    assert "Not enough ranked creatives" in text
    assert "Top 20%" not in text
    assert "$" not in text


def test_ctr_split_still_ranks_across_currencies():
    conn = fresh_db()
    try:
        insert_ads(conn, [
            row("Alpha", "high-eur", 10, 1, "EUR", "Aland", "alpha", "apple",
                clicks=200),
            row("Zulu", "low-gbp", 500, 1, "GBP", "Zedland", "zeta", "zebra",
                clicks=10),
        ])
        text = qa.answer(conn, "Compare top vs bottom ctr")["answer"]
    finally:
        conn.close()
    top, bottom = text.split("Bottom 20%", 1)
    assert "high-eur" in top
    assert "low-gbp" in bottom


def test_unreported_revenue_does_not_win_a_roas_split():
    conn = fresh_db()
    try:
        insert_ads(conn, [
            row("A", "reported-high", 100, 1, "GBP", "UK", "low", "ads",
                revenue=200, reported=1),
            row("A", "reported-low", 100, 1, "GBP", "UK", "low", "ads",
                revenue=50, reported=1),
            row("A", "unreported-huge", 100, 1, "GBP", "UK", "low", "ads",
                revenue=900, reported=0),
        ])
        text = qa.answer(conn, "Compare top vs bottom roas")["answer"]
    finally:
        conn.close()
    top, bottom = text.split("Bottom 20%", 1)
    assert "reported-high" in top
    assert "unreported-huge" not in top
    assert "unreported-huge" not in bottom
