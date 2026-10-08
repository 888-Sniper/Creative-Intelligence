"""Campaign drawer and the three table CSV exports.

The Campaigns drawer reads GET /api/campaigns/{name}. Campaign, Creative,
and Benchmark Export read POST /api/exports/campaigns, /creatives, and
/benchmarks. Group By Format and the vertical count both call
/api/benchmarks?group_by=, so format and vertical must be groupable.
"""

import os
import sqlite3
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import schema
from test_demo_dataset import _authed_client


def _db(tmp_path):
    path = str(tmp_path / "tables.db")
    conn = sqlite3.connect(path)
    schema.init_db(conn)
    conn.execute(
        "INSERT INTO creatives (creative_key, platform, name) VALUES (?,?,?)",
        ("clip-a", "meta", "Clip A"))
    conn.execute(
        "INSERT INTO ads (campaign, platform, format, vertical, creative_key,"
        " spend, impressions, clicks, conversions, revenue, date)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("Alpha", "meta", "reel", "Beauty", "clip-a",
         10, 100, 5, 1, 20, "2026-08-01"))
    conn.execute(
        "INSERT INTO ads (campaign, platform, format, vertical, creative_key,"
        " spend, impressions, clicks, conversions, revenue, date)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("Beta", "tiktok", "story", "Fashion", "clip-b",
         4, 40, 2, 0, 0, "2026-08-02"))
    conn.commit()
    conn.close()
    return path


def test_campaign_detail_totals_and_creative(tmp_path, monkeypatch):
    http = _authed_client(tmp_path, _db(tmp_path), monkeypatch)
    detail = http.get("/api/campaigns/Alpha")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["name"] == "Alpha"
    assert body["totals"]["impressions"] == 100
    assert body["totals"]["spend"] == 10
    assert [row["creative_key"] for row in body["top_creatives"]] == ["clip-a"]
    assert body["top_creatives"][0]["format"] == "reel"
    assert isinstance(body["recommendations"], list)
    assert body["recommendations"]

    missing = http.get("/api/campaigns/Nope")
    assert missing.status_code == 404
    assert missing.json()["error"] == "No campaign matches the current filters."

    meta = http.get("/api/campaigns/meta")
    assert meta.status_code == 200
    assert {row["name"] for row in meta.json()["campaigns"]} == {"Alpha", "Beta"}

    reco = http.get("/api/campaigns/recommendations", params={"name": "Alpha"})
    assert reco.status_code == 200, reco.text


def test_format_and_vertical_group(tmp_path, monkeypatch):
    http = _authed_client(tmp_path, _db(tmp_path), monkeypatch)
    by_format = http.get("/api/benchmarks", params={"group_by": "format"})
    assert by_format.status_code == 200, by_format.text
    assert set(by_format.json()) == {"reel", "story"}
    by_vertical = http.get("/api/benchmarks", params={"group_by": "vertical"})
    assert by_vertical.status_code == 200, by_vertical.text
    assert set(by_vertical.json()) == {"Beauty", "Fashion"}


def test_table_csv_exports(tmp_path, monkeypatch):
    http = _authed_client(tmp_path, _db(tmp_path), monkeypatch)
    campaigns = http.post("/api/exports/campaigns", json={
        "names": ["Alpha", "Missing"],
        "filters": {"platform": ["meta"]},
    })
    assert campaigns.status_code == 200, campaigns.text
    assert "text/csv" in campaigns.headers["content-type"]
    assert campaigns.headers["content-disposition"].endswith('filename="campaigns.csv"')
    text = campaigns.text
    assert text.splitlines()[0].startswith("name,")
    assert "Alpha" in text
    assert "Beta" not in text
    assert "Missing" not in text

    creatives = http.post("/api/exports/creatives", json={
        "creative_keys": ["clip-a", "absent"],
    })
    assert creatives.status_code == 200, creatives.text
    assert "clip-a" in creatives.text
    assert "absent" not in creatives.text

    benchmarks = http.post("/api/exports/benchmarks", json={"group_by": "format"})
    assert benchmarks.status_code == 200, benchmarks.text
    assert "reel" in benchmarks.text
    assert "story" in benchmarks.text

    empty = http.post("/api/exports/campaigns", json={"names": []})
    assert empty.status_code == 409
    bad = http.post("/api/exports/benchmarks", json={"group_by": "nope"})
    assert bad.status_code == 409


def _ads(conn, rows):
    conn.executemany(
        "INSERT INTO ads (campaign, platform, format, vertical, creative_key,"
        " spend, impressions, clicks, conversions, revenue, date)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        rows)
    conn.commit()


def test_drawer_metrics_stay_inside_one_campaign(tmp_path, monkeypatch):
    path = _db(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO ads (campaign, platform, format, vertical, creative_key,"
        " ad_name, spend, impressions, clicks, conversions, revenue, date)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("Beta", "tiktok", "story", "Fashion", "clip-a", "beta-clip-a",
         40, 900, 9, 0, 0, "2026-08-02"))
    conn.commit()
    conn.close()
    http = _authed_client(tmp_path, path, monkeypatch)
    alpha = http.get("/api/campaigns/Alpha")
    assert alpha.status_code == 200, alpha.text
    body = alpha.json()
    assert body["totals"]["impressions"] == 100
    assert body["top_creatives"][0]["metrics"]["impressions"] == 100
    beta = http.get("/api/campaigns/Beta")
    assert beta.status_code == 200, beta.text
    assert beta.json()["top_creatives"][0]["metrics"]["impressions"] == 900


def test_campaign_names_with_slash_or_percent(tmp_path, monkeypatch):
    path = _db(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO creatives (creative_key, platform, name) VALUES (?,?,?)",
        ("clip-slash", "meta", "Slash"))
    conn.execute(
        "INSERT INTO creatives (creative_key, platform, name) VALUES (?,?,?)",
        ("clip-pct", "meta", "Percent"))
    _ads(conn, [
        ("Spring/Summer", "meta", "reel", "Beauty", "clip-slash",
         3, 30, 1, 0, 0, "2026-08-03"),
        ("Offer%20Special", "meta", "reel", "Beauty", "clip-pct",
         2, 20, 1, 0, 0, "2026-08-04"),
    ])
    conn.close()
    http = _authed_client(tmp_path, path, monkeypatch)

    slash = http.get("/api/campaigns/" + quote("Spring/Summer", safe=""))
    assert slash.status_code == 200, slash.text
    assert slash.json()["name"] == "Spring/Summer"
    assert slash.json()["totals"]["impressions"] == 30

    percent = http.get("/api/campaigns/" + quote("Offer%20Special", safe=""))
    assert percent.status_code == 200, percent.text
    assert percent.json()["name"] == "Offer%20Special"
    assert percent.json()["totals"]["impressions"] == 20

    meta = http.get("/api/campaigns/meta")
    assert meta.status_code == 200
    assert "campaigns" in meta.json()


def test_meta_prefix_campaign_keeps_platform_filter(tmp_path, monkeypatch):
    path = _db(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO creatives (creative_key, platform, name) VALUES (?,?,?)",
        ("clip-meta", "meta", "Meta launch"))
    _ads(conn, [
        ("meta-launch", "meta", "reel", "Beauty", "clip-meta",
         8, 100, 4, 1, 10, "2026-08-01"),
        ("meta-launch", "tiktok", "story", "Beauty", "clip-meta",
         80, 900, 9, 0, 0, "2026-08-02"),
    ])
    conn.close()
    http = _authed_client(tmp_path, path, monkeypatch)
    detail = http.get("/api/campaigns/meta-launch", params={"platform": "meta"})
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["totals"]["impressions"] == 100
    assert body["top_creatives"][0]["metrics"]["impressions"] == 100


def test_empty_campaign_filter_exports_no_creatives(tmp_path, monkeypatch):
    http = _authed_client(tmp_path, _db(tmp_path), monkeypatch)
    creatives = http.post("/api/exports/creatives", json={
        "creative_keys": ["clip-a", "clip-b"],
        "filters": {"campaign": []},
    })
    assert creatives.status_code == 200, creatives.text
    lines = [line for line in creatives.text.splitlines() if line]
    assert lines[0].startswith("creative_key,")
    assert len(lines) == 1
    campaigns = http.post("/api/exports/campaigns", json={
        "names": ["Alpha", "Beta"],
        "filters": {"campaign": []},
    })
    assert campaigns.status_code == 200, campaigns.text
    assert "Alpha" not in campaigns.text
    assert "Beta" not in campaigns.text


def test_creative_csv_accepts_string_filters(tmp_path, monkeypatch):
    http = _authed_client(tmp_path, _db(tmp_path), monkeypatch)

    def export(filters):
        response = http.post("/api/exports/creatives", json={
            "creative_keys": ["clip-a"],
            "filters": filters,
        })
        assert response.status_code == 200, response.text
        return response.text.splitlines()

    platform = export({"platform": "meta"})
    assert platform[1].split(",")[0] == "clip-a"
    assert platform[1].split(",")[5] == "100"
    assert export({"platform": ["meta"]})[1].split(",")[5] == "100"

    assert len(export({"date_from": "2026-09-01"})) == 1
    assert len(export({"date_from": ["2026-09-01"]})) == 1
    assert export({"date_from": "2026-08-01"})[1].split(",")[0] == "clip-a"
