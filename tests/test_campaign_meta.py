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
        {"status": ["Active"]}).resolve(conn).normalized()["campaign"]
    assert active == ["New"]
    rich = benchmarks.Scope(
        {"spend_min": ["10000"]}).resolve(conn).normalized()["campaign"]
    assert rich == ["New"]
    band = benchmarks.Scope(
        {"spend_min": ["50"], "spend_max": ["500"]}
        ).resolve(conn).normalized()["campaign"]
    assert band == ["Old"]
    # Explicitly empty allowlist survives end to end (never "everything").
    empty = benchmarks.Scope({"spend_min": ["99999999"]}).resolve(conn)
    assert empty.normalized()["campaign"] == []
    assert empty.describe() == "No Campaigns"
    # No campaign-level keys: identical to normalized(), no campaign axis.
    plain = benchmarks.Scope({"platform": ["meta"]}).resolve(conn)
    assert "campaign" not in plain.normalized()
    assert plain.normalized()["platform"] == ["meta"]


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


def test_zero_match_scopes_stay_empty_end_to_end(tmp_path, monkeypatch):
    # Demo campaigns are all Active: Completed must match nothing —
    # never the whole dataset — on tables, totals and charts alike.
    db = str(tmp_path / "zero.db")
    assert load_demo_dataset(db, media_dir=str(tmp_path / "media")) > 0
    http = _authed_client(tmp_path, db, monkeypatch)
    r = http.get("/api/campaigns", params={"status": "Completed"})
    assert r.status_code == 200, r.text
    assert r.json() == {}
    r = http.get("/api/kpis/compare", params={"status": "Completed"})
    assert r.status_code == 200, r.text
    assert r.json()["comparison"] is None
    # Impossible spend range and conflicting selections behave the same.
    for params in ({"spend_min": "999999999"},
                   {"spend_min": "500", "spend_max": "100"},
                   {"status": "Completed", "campaign": "Spring Skincare Launch"}):
        r = http.get("/api/campaigns", params=params)
        if "spend_min" in params and "spend_max" in params \
                and params["spend_min"] == "500":
            assert r.status_code == 409, r.text
            continue
        assert r.status_code == 200, r.text
        assert r.json() == {}, params
    # Invalid values fail closed with 409, never silent discard.
    for params in ({"status": "Paused"}, {"spend_min": "abc"}):
        r = http.get("/api/campaigns", params=params)
        assert r.status_code == 409, r.text
    # Navigation with filters active: creatives honour the same scope.
    r = http.get("/api/creatives", params={"status": "Completed"})
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_meta_demo_dataset_shape(tmp_path, monkeypatch):
    db = str(tmp_path / "meta.db")
    assert load_demo_dataset(db, media_dir=str(tmp_path / "media")) > 0
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


def test_team_axis_filters_every_surface(tmp_path, monkeypatch):
    # Team is a real row-level dimension: meta exposes it, ?team=
    # scopes campaigns/compare/creatives identically, and an unknown
    # team honestly matches nothing everywhere.
    db = str(tmp_path / "team.db")
    assert load_demo_dataset(db, media_dir=str(tmp_path / "media")) > 0
    http = _authed_client(tmp_path, db, monkeypatch)
    r = http.get("/api/campaigns/meta")
    assert r.status_code == 200, r.text
    by_name = {c["name"]: c for c in r.json()["campaigns"]}
    assert by_name["Spring Skincare Launch"]["team"] == "Growth"
    assert by_name["Adventure Awaits"]["team"] == "Brand"
    assert by_name["Move More"]["team"] == "Performance"
    assert {c["team"] for c in by_name.values()} == {"Growth", "Brand", "Performance"}
    r = http.get("/api/campaigns", params={"team": "Growth"})
    assert r.status_code == 200, r.text
    assert sorted(r.json()) == ["Built For Real Life", "Everyday Energy",
                                "Spring Skincare Launch"]
    r = http.get("/api/kpis/compare", params={"team": "Growth"})
    assert r.status_code == 200, r.text
    assert r.json()["comparison"] == "previous_period"
    r = http.get("/api/creatives", params={"team": "Brand"})
    assert r.status_code == 200, r.text
    assert {c["name"] for c in r.json()} == {"Problem / Solution",
                                            "Creator Testimonial",
                                            "Quick Product Demo"}
    for params in ({"team": "No Such Team"},):
        r = http.get("/api/campaigns", params=params)
        assert r.status_code == 200, r.text
        assert r.json() == {}
        r = http.get("/api/kpis/compare", params=params)
        assert r.status_code == 200, r.text
        assert r.json()["comparison"] is None


def test_scope_construction_preserves_explicit_empty_campaign():
    scope = benchmarks.Scope({"campaign": []})
    assert scope.axes == {"campaign": []}
    assert scope.normalized() == {"campaign": []}
    assert scope.sql() == ("1=0", [])
    assert scope.describe() == "No Campaigns"
    assert not scope.is_empty()
    assert scope.match({"campaign": "Anything"}) is False


def test_scope_double_resolve_matches_single_resolve():
    # Nested helpers (recommendations, reports) may resolve an
    # already-resolved scope: the restriction must be idempotent.
    conn = sqlite3.connect(":memory:")
    try:
        once = benchmarks.Scope({"campaign": []}).resolve(conn)
        twice = once.resolve(conn)
        assert once.axes == {"campaign": []}
        assert twice.axes == {"campaign": []}
        assert once.sql() == ("1=0", [])
        assert twice.sql() == ("1=0", [])
        assert twice.normalized() == {"campaign": []}
        assert twice.match({"campaign": "Anything"}) is False
    finally:
        conn.close()


def test_scope_query_without_campaign_stays_unrestricted():
    # HTTP-absent or all-blank keys never spell "match nothing".
    assert benchmarks.Scope.from_query({}).axes == {}
    assert benchmarks.Scope.from_query({"campaign": [""]}).axes == {}
    assert benchmarks.Scope.from_query({"campaign": ["A", ""]}).axes == {
        "campaign": ["A"]}
    assert benchmarks.Scope.from_query(
        {"campaign": ["A"]}).sql() != ("1=0", [])


def test_zero_match_scope_flows_into_recommendations(tmp_path, monkeypatch):
    # Nested helper path: recommendations over a zero-match scope must
    # report no creatives — never full-dataset advice.
    from urllib.parse import quote

    db = str(tmp_path / "zero-rec.db")
    assert load_demo_dataset(db, media_dir=str(tmp_path / "media")) > 0
    http = _authed_client(tmp_path, db, monkeypatch)
    name = quote("Spring Skincare Launch")
    r = http.get("/api/campaigns/recommendations?name=%s&status=Completed"
                 % name)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["n_creatives"] == 0
    assert "nothing to learn yet" in body["sections"][0]["bullets"][0]["text"]
