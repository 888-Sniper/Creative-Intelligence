"""Campaign metadata endpoint: real per-campaign attributes for filters/table.

Pins the /api/campaigns/meta contract used by the Campaigns screen:
one entry per campaign with client, platforms, markets, objectives,
last activity date and a derived status (Active within the trailing
window of the newest date in the database, else Completed). Status is
derived, never stored, so these tests also pin the derivation rule.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend.actions import load_demo_dataset
from creative_intel import benchmarks, schema
from test_demo_dataset import _authed_client


def _conn_with(rows):
    conn = sqlite3.connect(":memory:")
    schema.init_db(conn)
    conn.executemany(
        "INSERT INTO ads (campaign, client, platform, market, objective,"
        " date, spend, impressions, clicks) VALUES (?,?,?,?,?,?,?,?,?)",
        rows)
    return conn


def test_meta_lists_every_campaign_once():
    conn = _conn_with([
        ("Alpha", "Acme", "meta", "UK", "Conversions", "2026-08-20", 10, 100, 5),
        ("Alpha", "Acme", "tiktok", "UK", "Conversions", "2026-08-21", 10, 100, 5),
        ("Beta", "Beta Ltd", "meta", "US", "Traffic", "2026-05-01", 10, 100, 5),
    ])
    meta = benchmarks.campaign_meta(conn)
    assert [c["name"] for c in meta["campaigns"]] == ["Alpha", "Beta"]
    alpha = meta["campaigns"][0]
    assert alpha["client"] == "Acme"
    assert alpha["platforms"] == ["meta", "tiktok"]
    assert alpha["markets"] == ["UK"]
    assert alpha["objectives"] == ["Conversions"]
    assert alpha["last_date"] == "2026-08-21"
    # Newest date in the db is 2026-08-21: Alpha is current, Beta lapsed.
    assert alpha["status"] == "Active"
    assert meta["campaigns"][1]["status"] == "Completed"


def test_meta_boundary_and_undated_rows():
    conn = _conn_with([
        ("Newest", "Acme", "meta", "UK", "Conversions", "2026-08-21", 1, 10, 1),
        ("Edge", "Acme", "meta", "UK", "Conversions", "2026-08-07", 1, 10, 1),
        ("Old", "Acme", "meta", "UK", "Conversions", "2026-08-06", 1, 10, 1),
        ("Dateless", "Acme", "meta", "UK", "Conversions", "", 1, 10, 1),
    ])
    # Newest date is 2026-08-21: exactly 14 days back stays Active.
    by_name = {c["name"]: c for c in benchmarks.campaign_meta(conn)["campaigns"]}
    assert by_name["Edge"]["status"] == "Active"
    assert by_name["Old"]["status"] == "Completed"
    assert by_name["Dateless"]["status"] == "Completed"


def test_resolve_converts_status_and_spend_to_campaign_scope():
    conn = _conn_with([
        ("New", "Acme", "meta", "UK", "Conversions", "2026-08-21", 30000, 100, 5),
        ("Old", "Acme", "meta", "UK", "Conversions", "2026-01-01", 100, 100, 5),
    ])
    active = benchmarks.Scope(
        {"status": ["Active"]}).resolve(conn)["campaign"]
    assert active == ["New"]
    rich = benchmarks.Scope({"spend_min": ["10000"]}).resolve(conn)["campaign"]
    assert rich == ["New"]
    band = benchmarks.Scope(
        {"spend_min": ["50"], "spend_max": ["500"]}).resolve(conn)["campaign"]
    assert band == ["Old"]
    # No campaign-level keys: identical to normalized(), no campaign axis.
    plain = benchmarks.Scope({"platform": ["meta"]}).resolve(conn)
    assert "campaign" not in plain
    assert plain["platform"] == ["meta"]


def test_resolve_rejects_bad_values():
    conn = _conn_with([
        ("New", "Acme", "meta", "UK", "Conversions", "2026-08-21", 10, 100, 5),
    ])
    for raw in ({"status": ["Paused"]}, {"spend_min": ["abc"]},
                {"spend_min": ["-5"]},
                {"spend_min": ["500"], "spend_max": ["100"]}):
        try:
            benchmarks.Scope(raw).resolve(conn)
        except ValueError:
            continue
        raise AssertionError("expected ValueError for %r" % (raw,))


def test_meta_demo_dataset_shape(tmp_path, monkeypatch):
    db = str(tmp_path / "meta.db")
    assert load_demo_dataset(db) > 0
    http = _authed_client(tmp_path, db, monkeypatch)
    r = http.get("/api/campaigns/meta")
    assert r.status_code == 200, r.text
    campaigns = r.json()["campaigns"]
    assert len(campaigns) == 10
    by_name = {c["name"]: c for c in campaigns}
    assert by_name["Spring Skincare Launch"]["client"] == "GlowNaturally"
    assert by_name["Everyday Energy"]["platforms"] == ["tiktok"]
    for c in campaigns:
        assert c["status"] in ("Active", "Completed")
        assert c["last_date"] > ""
    # Demo windows end at the trailing edge, so every demo campaign reads Active.
    assert {c["status"] for c in campaigns} == {"Active"}
