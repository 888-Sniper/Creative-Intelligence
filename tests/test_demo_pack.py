"""One-time presentation pack lifecycle: import once, edit/delete
normally, deleted stays deleted, batch-scoped removal.

Covers goal tests A-F, H, I, K, L at the backend level (isolated
temp DBs, never the live team database); J at the HTTP layer.
"""

import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

import pytest
from auth_help import authed
from ci_backend.app import create_app
from ci_backend.config import Settings
from creative_intel import demo_pack, schema as S
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _isolated_media_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_INTEL_MEDIA_DIR",
                       str(tmp_path / "media"))


def _db(tmp_path, name="pack.db"):
    db = str(tmp_path / name)
    conn = sqlite3.connect(db)
    S.init_db(conn)
    return db, conn


def _import(conn, md):
    r = demo_pack.import_pack(conn, imported_by="admin1",
                              workspace="test", media_dir=md)
    fin = demo_pack.finalize_pack(conn, r["batch_id"], media_dir=md,
                                  core_counts=r["counts"])
    return r["batch_id"], fin


def test_a_import_creates_ten_and_thirty_real_untouched(tmp_path):
    db, conn = _db(tmp_path)
    md = os.path.join(str(tmp_path), "media")
    conn.execute(
        "INSERT INTO ads (platform, source, campaign, ad_name,"
        " creative_key, date, campaign_id, spend) VALUES"
        " ('meta','upload','Real Co','Ad','real-1','2026-01-01',"
        " 'REAL-1', 5.0)")
    conn.commit()
    bid, fin = _import(conn, md)
    assert fin["counts"]["campaigns"] == 10
    assert fin["counts"]["creatives"] == 30
    assert conn.execute(
        "SELECT COUNT(DISTINCT campaign_id) FROM ads WHERE import_id=?",
        (bid,)).fetchone()[0] == 10
    assert conn.execute(
        "SELECT COUNT(*) FROM creatives WHERE creative_key LIKE 'smp-%'"
    ).fetchone()[0] == 30
    real = conn.execute(
        "SELECT campaign, spend FROM ads WHERE campaign_id='REAL-1'"
    ).fetchone()
    assert real == ("Real Co", 5.0)
    assert demo_pack.pack_status(conn)["status"] == "added"


def test_b_repeat_and_rerun_create_nothing_new(tmp_path):
    db, conn = _db(tmp_path)
    md = os.path.join(str(tmp_path), "media")
    bid, _fin = _import(conn, md)
    ads0 = conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0]
    again = demo_pack.import_pack(conn, imported_by="admin1",
                                  workspace="test", media_dir=md)
    assert again.get("created") is False
    assert again["receipt"]["batch_id"] == bid
    assert conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0] == ads0
    # Simulated concurrent second caller collapses onto the receipt.
    conn2 = sqlite3.connect(db)
    third = demo_pack.import_pack(conn2, imported_by="admin2",
                                  workspace="test", media_dir=md)
    assert third.get("created") is False
    assert conn.execute("SELECT COUNT(*) FROM demo_packs").fetchone()[0] == 1
    conn2.close()


def test_d_rename_persists_and_keeps_provenance(tmp_path):
    db, conn = _db(tmp_path)
    md = os.path.join(str(tmp_path), "media")
    bid, _fin = _import(conn, md)
    demo_pack.rename_campaign(conn, bid, "SMP-02", "Renamed Evening")
    conn2 = sqlite3.connect(db)  # fresh read (refresh)
    assert conn2.execute(
        "SELECT DISTINCT campaign FROM ads WHERE campaign_id='SMP-02'"
    ).fetchone()[0] == "Renamed Evening"
    # Rename did not break batch cleanup identity.
    demo_pack.delete_campaign(conn2, bid, "SMP-02")
    assert conn2.execute(
        "SELECT COUNT(*) FROM ads WHERE campaign_id='SMP-02'"
    ).fetchone()[0] == 0
    conn2.close()


def test_e_delete_campaign_removes_dependents(tmp_path):
    db, conn = _db(tmp_path)
    md = os.path.join(str(tmp_path), "media")
    bid, _fin = _import(conn, md)
    ads0 = conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0]
    impact = demo_pack.campaign_impact(conn, bid, "SMP-01")
    assert impact["campaign"] == "First Light Ritual"
    assert impact["creatives"] == 3
    assert impact["ads_rows"] > 0
    demo_pack.delete_campaign(conn, bid, "SMP-01")
    assert conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0] < ads0
    assert conn.execute(
        "SELECT COUNT(*) FROM creatives WHERE creative_key LIKE"
        " 'smp-first-light-%'").fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM retention WHERE creative_key LIKE"
        " 'smp-first-light-%'").fetchone()[0] == 0


def test_f_deleted_campaign_not_restored(tmp_path):
    db, conn = _db(tmp_path)
    md = os.path.join(str(tmp_path), "media")
    bid, _fin = _import(conn, md)
    demo_pack.delete_campaign(conn, bid, "SMP-01")
    again = demo_pack.import_pack(conn, imported_by="admin1",
                                  workspace="test", media_dir=md)
    assert again.get("created") is False
    assert conn.execute(
        "SELECT COUNT(*) FROM ads WHERE campaign_id='SMP-01'"
    ).fetchone()[0] == 0
    assert demo_pack.pack_status(conn)["status"] == "partially_removed"


def test_g_receipt_survives_reconnect(tmp_path):
    db, conn = _db(tmp_path)
    md = os.path.join(str(tmp_path), "media")
    bid, _fin = _import(conn, md)
    demo_pack.delete_campaign(conn, bid, "SMP-03")
    conn.close()
    conn2 = sqlite3.connect(db)
    st = demo_pack.pack_status(conn2)
    assert st["receipt"]["batch_id"] == bid
    assert st["status"] == "partially_removed"
    conn2.close()


def test_h_delete_everything_keeps_receipt(tmp_path):
    db, conn = _db(tmp_path)
    md = os.path.join(str(tmp_path), "media")
    bid, _fin = _import(conn, md)
    for i in range(1, 11):
        try:
            demo_pack.delete_campaign(conn, bid, "SMP-%02d" % i)
        except ValueError:
            pass
    for (cid,) in conn.execute("SELECT id FROM analyst_conversations"):
        demo_pack.delete_conversation(conn, bid, cid)
    st = demo_pack.pack_status(conn)
    assert st["receipt"] is not None
    assert st["receipt"]["batch_id"] == bid
    assert st["status"] in ("partially_removed", "added")


def test_i_remove_all_keeps_real_rows(tmp_path):
    db, conn = _db(tmp_path)
    md = os.path.join(str(tmp_path), "media")
    conn.execute(
        "INSERT INTO ads (platform, source, campaign, ad_name,"
        " creative_key, date, campaign_id) VALUES"
        " ('meta','upload','Real Co','Ad','real-1','2026-01-01',"
        " 'REAL-1')")
    conn.execute(
        "INSERT INTO saved_views (name, state_json) VALUES"
        " ('Real View', '{}')")
    conn.commit()
    bid, _fin = _import(conn, md)
    out = demo_pack.remove_pack(conn, bid, media_dir=md)
    assert out["removed"] is True
    assert conn.execute("SELECT COUNT(*) FROM ads").fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM saved_views WHERE name='Real View'"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM creatives WHERE creative_key LIKE 'smp-%'"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM analyst_conversations").fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM sample_files").fetchone()[0] == 0
    st = demo_pack.pack_status(conn)
    assert st["status"] == "removed"
    assert st["receipt"]["batch_id"] == bid
    # Removed pack cannot be re-added.
    again = demo_pack.import_pack(conn, imported_by="admin1",
                                  workspace="test", media_dir=md)
    assert again.get("created") is False


def test_k_thumbnails_decode(tmp_path):
    db, conn = _db(tmp_path)
    md = os.path.join(str(tmp_path), "media")
    bid, _fin = _import(conn, md)
    rows = conn.execute(
        "SELECT stored_name FROM media").fetchall()
    assert len(rows) == 30
    for (stored,) in rows:
        path = os.path.join(md, stored)
        with open(path, "rb") as fh:
            head = fh.read(8)
        assert head == b"\x89PNG\r\n\x1a\n", stored
        assert os.path.getsize(path) > 1000


def test_l_sample_files_valid(tmp_path):
    import zipfile

    db, conn = _db(tmp_path)
    md = os.path.join(str(tmp_path), "media")
    bid, fin = _import(conn, md)
    files = conn.execute(
        "SELECT name, format FROM sample_files").fetchall()
    assert len(files) == 9  # 6 reports + 3 workbooks
    for name, fmt in files:
        matches = []
        for root, _ds, fs in os.walk(os.path.join(md, "sample", bid)):
            matches += [os.path.join(root, f) for f in fs if f == name]
        assert matches, name
        size = os.path.getsize(matches[0])
        assert size > 200, name
        if name.endswith(".xlsx"):
            assert zipfile.is_zipfile(matches[0]), name
        if fmt == "one-pager":
            text = open(matches[0], encoding="utf-8").read()
            assert "Sample" in text or "sample" in text


def _pack_client(tmp_path, role):
    db = str(tmp_path / "api.db")
    settings = Settings(workos_client_id="client_test",
                        key_workos="sk_test_demo",
                        workos_redirect_uri="https://t.test/cb",
                        admin_email="a@foap.test",
                        provider_mode="live", cookie_secure=True,
                        environment="demo", data_dir=str(tmp_path))
    http = TestClient(create_app(db, settings),
                      raise_server_exceptions=False)
    email = "a@foap.test" if role == "admin" else "e@foap.test"
    cookie = authed(db, email=email, role=role)
    return http, {"Cookie": cookie}


def test_j_non_admin_blocked_admin_allowed(tmp_path):
    http, user = _pack_client(tmp_path, "employee")
    r = http.post("/api/admin/demo/pack/import", headers=user)
    assert r.status_code in (401, 403), r.text
    r = http.get("/api/admin/demo/pack/status", headers=user)
    assert r.status_code in (401, 403), r.text
    http, admin = _pack_client(tmp_path, "admin")
    r = http.get("/api/admin/demo/pack/preview", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["pack_key"] == "foap-presentation-pack-v1"
    r = http.post("/api/admin/demo/pack/import", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["created"] is True
    r = http.post("/api/admin/demo/pack/import", headers=admin)
    assert r.status_code == 200
    assert r.json()["created"] is False
    # Legacy refill route is retired.
    r = http.post("/api/admin/demo/seed", headers=admin)
    assert r.status_code == 410, r.text
