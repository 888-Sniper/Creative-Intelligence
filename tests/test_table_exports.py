"""Campaign drawer and the three table CSV exports.

The Campaigns drawer reads GET /api/campaigns/{name}. Campaign, Creative,
and Benchmark Export read POST /api/exports/campaigns, /creatives, and
/benchmarks. Group By Format and the vertical count both call
/api/benchmarks?group_by=, so format and vertical must be groupable.
"""

import os
import sqlite3
import sys

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
