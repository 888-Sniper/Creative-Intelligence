"""Synthetic demo dataset: seed totals, idempotency, real comparisons.

The demo UI (dashboard, charts, KpiTrend) computes from seeded rows, so
these tests pin the dataset contract: ten synthetic campaigns and ten
annotated creatives, reference-scale totals, source="demo" identity,
no duplication on reload, and genuinely positive current-vs-previous
comparisons from the growth ramp.
"""

import os
import sqlite3
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend.actions import load_demo_dataset
from ci_backend.app import create_app
from ci_backend.config import Settings

IDENT = {"id": "w-demo", "email": "demo@foap.test", "email_verified": True,
         "first_name": "Demo", "last_name": "User", "profile_picture_url": ""}


def _seeded_db(tmp_path):
    db = str(tmp_path / "demo.db")
    inserted = load_demo_dataset(db)
    return db, inserted


def _authed_client(tmp_path, db, monkeypatch):
    settings = Settings(workos_client_id="client_test",
                        key_workos="sk_test_demo",
                        admin_email="demo@foap.test",
                        data_dir=str(tmp_path))
    http = TestClient(create_app(db, settings), raise_server_exceptions=False)

    def fake(code, verifier, settings=None):
        assert code == "auth_code"
        return {"user": dict(IDENT)}

    monkeypatch.setattr("ci_backend.workos.authenticate_code", fake)
    r = http.post("/api/auth/oauth/start", json={"provider": "google"})
    assert r.status_code == 200, r.text
    r = http.post("/api/auth/oauth/finish",
                  json={"code": "auth_code", "state": r.json()["state"]})
    assert r.json()["gate"] == "app", r.text
    return http


def _totals(db):
    with sqlite3.connect(db) as conn:
        return conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT campaign),"
            " SUM(impressions), SUM(clicks), SUM(spend), SUM(revenue)"
            " FROM ads").fetchone()


def test_demo_seed_shape_and_totals(tmp_path):
    db, inserted = _seeded_db(tmp_path)
    assert inserted > 2000
    n_rows, n_campaigns, impr, clicks, spend, revenue = _totals(db)
    assert n_rows == inserted
    assert n_campaigns == 10
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM creatives").fetchone()[0] == 10
        assert conn.execute("SELECT COUNT(*) FROM annotations").fetchone()[0] == 10
        assert conn.execute(
            "SELECT COUNT(DISTINCT source) FROM ads").fetchone()[0] == 1
        assert conn.execute(
            "SELECT DISTINCT source FROM ads").fetchone()[0] == "demo"
    assert 115_000_000 < impr < 136_000_000
    assert 1_650_000 < clicks < 1_950_000
    assert 380_000 < spend < 445_000
    assert 3.4 < revenue / spend < 3.8


def test_demo_seed_reload_inserts_nothing(tmp_path):
    db, inserted = _seeded_db(tmp_path)
    before = _totals(db)
    assert load_demo_dataset(db) == 0
    assert _totals(db) == before
    assert inserted > 0


def test_demo_seed_drives_real_comparisons(tmp_path, monkeypatch):
    import datetime as _dt

    db, _ = _seeded_db(tmp_path)
    http = _authed_client(tmp_path, db, monkeypatch)
    end = _dt.date.today() - _dt.timedelta(days=1)
    start = end - _dt.timedelta(days=29)
    params = {"date_from": start.isoformat(), "date_to": end.isoformat()}
    r = http.get("/api/kpis/compare", params=params)
    assert r.status_code == 200, r.text
    metrics = r.json()["metrics"]
    for key in ("impressions", "clicks", "spend"):
        assert metrics[key]["direction"] == "up", (key, metrics[key])
        assert metrics[key]["percent_change"] > 0
    r = http.get("/api/kpis/daily", params={"days": 30})
    assert r.status_code == 200, r.text
    days = r.json()["days"]
    assert len(days) == 30
    assert [d["date"] for d in days] == sorted(d["date"] for d in days)
    assert sum(d["impressions"] for d in days) > 0
    r = http.get("/api/campaigns")
    assert r.status_code == 200, r.text
    assert len(r.json()) == 10
    r = http.get("/api/kpis/daily", params={"days": 0})
    assert r.status_code == 409
