"""FastAPI app journeys (pytest + TestClient, Nextly test_api.py pattern).

End-to-end proof over the new stack: default-deny from first launch,
OAuth start/finish with a stubbed WorkOS exchange, pending approval,
RBAC, logout, switching, audit, and product-route parity.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import employees as emp_store
from ci_backend.app import create_app
from ci_backend.config import Settings
from ci_backend.db import make_engine, make_session_factory

IDENT = {"id": "w-ada", "email": "ada@foap.test", "email_verified": True,
         "first_name": "Ada", "last_name": "L", "profile_picture_url": ""}


def make_client(tmp_path, **settings_kw):
    db = str(tmp_path / "app.db")
    settings = Settings(workos_client_id="client_test",
                        key_workos="sk-test-key", **settings_kw)
    app = create_app(db, settings)
    return TestClient(app, raise_server_exceptions=False), db


@pytest.fixture()
def client(tmp_path):
    http, _db = make_client(tmp_path)
    return http


def stub_exchange(monkeypatch, user=None):
    user = user or dict(IDENT)

    def fake(code, verifier, settings=None):
        assert code == "auth_code"
        return {"user": dict(user)}

    monkeypatch.setattr("ci_backend.workos.authenticate_code", fake)


def oauth_login(http, monkeypatch, user=None):
    stub_exchange(monkeypatch, user)
    r = http.post("/api/auth/oauth/start", json={"provider": "google"})
    assert r.status_code == 200, r.text
    state = r.json()["state"]
    r = http.post("/api/auth/oauth/finish",
                  json={"code": "auth_code", "state": state})
    assert r.status_code == 200, r.text
    return r


def test_fresh_db_denies_anonymous(client):
    r = client.get("/api/campaigns")
    assert r.status_code == 401
    assert r.json()["gate"] == "login"
    r = client.get("/api/admin/employees")
    assert r.status_code == 401
    r = client.get("/api/health")
    assert r.status_code == 200


def test_oauth_start_shape(client):
    r = client.post("/api/auth/oauth/start", json={"provider": "google"})
    assert r.status_code == 200
    body = r.json()
    assert "GoogleOAuth" in body["url"] and "code_challenge=" in body["url"]
    assert "sk-test-key" not in body["url"]
    r = client.post("/api/auth/oauth/start", json={"provider": "nope"})
    assert r.status_code == 409


def test_pending_cannot_touch_data(client, monkeypatch):
    r = oauth_login(client, monkeypatch)
    assert r.json()["gate"] == "pending"
    me = client.get("/api/auth/me")
    assert me.json()["gate"] == "pending"
    # Cookie is now set on the client; data APIs still refuse.
    r = client.get("/api/campaigns")
    assert r.status_code == 403
    assert r.json()["gate"] == "pending"
    r = client.get("/api/admin/employees")
    assert r.status_code == 403


def test_bootstrap_first_admin(tmp_path, monkeypatch):
    http, _db = make_client(tmp_path, admin_email="ada@foap.test")
    r = oauth_login(http, monkeypatch)
    assert r.json()["gate"] == "app"
    me = http.get("/api/auth/me").json()
    assert me["is_admin"] is True
    staff = http.get("/api/admin/employees").json()["employees"]
    assert any(e["email"] == "ada@foap.test" and e["role"] == "admin"
               for e in staff)


def test_approve_suspend_reactivate_revoke(tmp_path, monkeypatch):
    http, db = make_client(tmp_path, admin_email="boss@foap.test")
    boss_user = dict(IDENT, id="w-boss", email="boss@foap.test")
    oauth_login(http, monkeypatch, boss_user)
    newcomer = dict(IDENT, id="w-new", email="new@foap.test")
    stub_exchange(monkeypatch, newcomer)

    # Second login on a fresh client = the pending newcomer.
    http2 = TestClient(http.app, raise_server_exceptions=False)
    r = http2.post("/api/auth/oauth/start", json={"provider": "google"})
    state = r.json()["state"]
    r = http2.post("/api/auth/oauth/finish",
                   json={"code": "auth_code", "state": state})
    assert r.json()["gate"] == "pending"

    staff = http.get("/api/admin/employees").json()["employees"]
    target = next(e for e in staff if e["email"] == "new@foap.test")
    r = http.post("/api/admin/employees/%s/approve" % target["id"], json={})
    assert r.status_code == 200
    assert http2.get("/api/auth/me").json()["gate"] == "app"

    r = http.post("/api/admin/employees/%s/suspend" % target["id"], json={})
    assert r.status_code == 200
    # Old session is dead; re-login lands on suspended.
    r = http2.post("/api/auth/oauth/finish",
                   json={"code": "auth_code", "state": "bogus"})
    assert r.status_code == 409
    audit = http.get("/api/admin/audit").json()["events"]
    assert any(e["action"] == "EMPLOYEE_SUSPENDED" for e in audit)


def test_employee_cannot_use_admin_api(tmp_path, monkeypatch):
    http, db = make_client(tmp_path, admin_email="boss@foap.test")
    boss_user = dict(IDENT, id="w-boss", email="boss@foap.test")
    oauth_login(http, monkeypatch, boss_user)
    r = http.post("/api/admin/employees",
                  json={"email": "x@foap.test", "role": "employee"})
    assert r.status_code == 200
    newcomer = dict(IDENT, id="w-x", email="x@foap.test")
    http2 = TestClient(http.app, raise_server_exceptions=False)
    stub_exchange(monkeypatch, newcomer)
    r = http2.post("/api/auth/oauth/start", json={"provider": "google"})
    state = r.json()["state"]
    http2.post("/api/auth/oauth/finish",
               json={"code": "auth_code", "state": state})
    # Pending newcomer: admin list forbidden, not leaked.
    r = http2.get("/api/admin/employees")
    assert r.status_code == 403


def test_last_admin_refused(tmp_path, monkeypatch):
    http, _db = make_client(tmp_path, admin_email="boss@foap.test")
    boss_user = dict(IDENT, id="w-boss", email="boss@foap.test")
    oauth_login(http, monkeypatch, boss_user)
    boss = next(e for e in
                http.get("/api/admin/employees").json()["employees"])
    r = http.post("/api/admin/employees/%s/revoke" % boss["id"], json={})
    assert r.status_code == 409
    assert "admin" in r.json()["error"].lower()


def test_logout_and_callback_hygiene(client, monkeypatch):
    r = oauth_login(client, monkeypatch)
    assert client.get("/api/auth/me").json()["authenticated"] is True
    r = client.post("/api/auth/logout", json={})
    assert r.status_code == 200
    assert client.get("/api/auth/me").json()["gate"] == "login"

    # Callback lands with the session in a cookie, never the URL.
    stub_exchange(monkeypatch)
    r = client.post("/api/auth/oauth/start", json={"provider": "github"})
    state = r.json()["state"]
    assert "GitHubOAuth" in r.json()["url"]
    r = client.get("/api/auth/callback?code=auth_code&state=" + state,
                   follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/"
    assert "ci_session=" not in r.headers["location"]
    assert "ci_session=" in r.headers.get("set-cookie", "")


def test_product_parity_ingest_then_campaigns(tmp_path, monkeypatch):
    http, _db = make_client(tmp_path, admin_email="boss@foap.test")
    boss_user = dict(IDENT, id="w-boss", email="boss@foap.test")
    oauth_login(http, monkeypatch, boss_user)
    csv = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
           "Link Clicks,Conversions\nC1,A1,hook-a,100,10000,200,10\n")
    r = http.post("/api/ingest", json={"platform": "meta", "csv": csv})
    assert r.status_code == 200, r.text
    r = http.get("/api/campaigns")
    assert r.status_code == 200
    assert "C1" in r.text
    r = http.get("/api/creatives")
    assert r.status_code == 200
    assert r.json()[0]["metrics"]["cpa"] == 10.0


def test_legacy_and_new_stores_agree(tmp_path):
    # Same sqlite file: SQLAlchemy store sees legacy-written rows.
    import sqlite3
    db = str(tmp_path / "shared.db")
    legacy = sqlite3.connect(db)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                    "Backend"))
    from creative_intel import auth as legacy_auth
    from creative_intel import schema
    schema.init_db(legacy)
    legacy_auth.admin_create(legacy, "root", "ada@foap.test", role="admin")
    legacy.close()
    engine = make_engine(db)
    with make_session_factory(engine)() as sess:
        found = emp_store.find_employee(sess, "", "ada@foap.test")
        assert found is not None and found.role == "admin"
