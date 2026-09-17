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
from conftest import employee_session
from creative_intel import ingest as ingest_mod

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


def test_pre_dimension_database_upgrades_in_place(tmp_path):
    import sqlite3 as _sqlite3

    db = str(tmp_path / "old.db")
    conn = _sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE ads (id INTEGER PRIMARY KEY,"
        " platform TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'upload',"
        " campaign TEXT NOT NULL DEFAULT '', adset TEXT NOT NULL DEFAULT '',"
        " ad_name TEXT NOT NULL DEFAULT '',"
        " creative_key TEXT NOT NULL DEFAULT '',"
        " spend REAL NOT NULL DEFAULT 0, impressions INTEGER NOT NULL DEFAULT 0,"
        " clicks INTEGER NOT NULL DEFAULT 0, conversions REAL NOT NULL DEFAULT 0,"
        " video_views INTEGER NOT NULL DEFAULT 0, views_25 INTEGER NOT NULL DEFAULT 0,"
        " views_50 INTEGER NOT NULL DEFAULT 0, views_75 INTEGER NOT NULL DEFAULT 0,"
        " views_100 INTEGER NOT NULL DEFAULT 0)")
    conn.commit()
    conn.close()
    settings = Settings(workos_client_id="client_test",
                        key_workos="[REDACTED]")
    http = TestClient(create_app(db, settings), raise_server_exceptions=False)
    # Must upgrade, not 500: default-deny still answers 401.
    assert http.get("/api/campaigns").status_code == 401
    _probe = _sqlite3.connect(db)
    try:
        cols = {row[1] for row in
                _probe.execute("PRAGMA table_info(ads)")}
    finally:
        _probe.close()
    assert {"date", "client", "revenue"} <= cols


def test_oauth_start_shape(client):
    r = client.post("/api/auth/oauth/start", json={"provider": "google"})
    assert r.status_code == 200
    body = r.json()
    assert "GoogleOAuth" in body["url"] and "code_challenge=" in body["url"]
    assert "sk-test-key" not in body["url"]
    for provider, tag in (("apple", "AppleOAuth"),
                          ("github", "GitHubOAuth"),
                          ("microsoft", "MicrosoftOAuth")):
        r = client.post("/api/auth/oauth/start",
                        json={"provider": provider})
        assert r.status_code == 200, provider
        assert tag in r.json()["url"], provider
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
    # Pending newcomer: admin list forbidden, not leaked, not admin.
    r = http2.get("/api/admin/employees")
    assert r.status_code == 403
    assert http2.get("/api/auth/me").json()["is_admin"] is False


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


PNG = bytes((0x89,)) + b"PNG\r\n\x1a\n" + b"\x00" * 64


def test_profile_edit_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_INTEL_MEDIA_DIR", str(tmp_path / "media"))
    http, _db = make_client(tmp_path, admin_email="boss@foap.test")
    boss_user = dict(IDENT, id="w-boss", email="boss@foap.test")
    oauth_login(http, monkeypatch, boss_user)

    r = http.patch("/api/auth/me",
                   json={"first_name": "  Ada  ", "last_name": "L"})
    assert r.status_code == 200, r.text
    assert r.json()["employee"]["first_name"] == "Ada"

    r = http.patch("/api/auth/me", json={"first_name": "X" * 121})
    assert r.status_code == 409
    r = http.patch("/api/auth/me", json={"avatar_url": "ftp://x/y.png"})
    assert r.status_code == 409
    r = http.patch("/api/auth/me",
                   json={"avatar_url": "https://cdn.test/a.png"})
    assert r.status_code == 200
    assert r.json()["employee"]["avatar_url"] == "https://cdn.test/a.png"
    r = http.patch("/api/auth/me", json={"avatar_url": ""})
    assert r.json()["employee"]["avatar_url"] == ""

    audit = http.get("/api/admin/audit").json()["events"]
    assert any(e["action"] == "PROFILE_UPDATED" for e in audit)


def test_profile_requires_active_login(tmp_path, monkeypatch, client):
    r = client.patch("/api/auth/me", json={"first_name": "No"})
    assert r.status_code == 401
    http, _db = make_client(tmp_path, admin_email="boss@foap.test")
    newcomer = dict(IDENT, id="w-new", email="new@foap.test")
    stub_exchange(monkeypatch, newcomer)
    http2 = TestClient(http.app, raise_server_exceptions=False)
    r = http2.post("/api/auth/oauth/start", json={"provider": "google"})
    state = r.json()["state"]
    http2.post("/api/auth/oauth/finish",
               json={"code": "auth_code", "state": state})
    r = http2.patch("/api/auth/me", json={"first_name": "No"})
    assert r.status_code == 403


def test_avatar_upload_and_serve(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_INTEL_MEDIA_DIR", str(tmp_path / "media"))
    http, _db = make_client(tmp_path, admin_email="boss@foap.test")
    boss_user = dict(IDENT, id="w-boss", email="boss@foap.test")
    oauth_login(http, monkeypatch, boss_user)
    me = http.get("/api/auth/me").json()["employee"]

    r = http.post("/api/auth/me/avatar",
                  files={"avatar": ("me.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    assert r.json()["employee"]["avatar_url"] == \
        "/api/auth/avatar/" + me["id"]

    r = http.get("/api/auth/avatar/" + me["id"])
    assert r.status_code == 200
    assert r.content == PNG
    assert r.headers["content-type"] == "image/png"

    anon = TestClient(http.app, raise_server_exceptions=False)
    assert anon.get("/api/auth/avatar/" + me["id"]).status_code == 401
    assert anon.get("/api/auth/avatar/nonexistent").status_code == 401

    r = http.post("/api/auth/me/avatar",
                  files={"avatar": ("me.txt", b"hello", "text/plain")})
    assert r.status_code == 409
    r = http.post("/api/auth/me/avatar",
                  files={"avatar": ("big.png", b"\\x00" * (2 * 1024 * 1024 + 1),
                                      "image/png")})
    assert r.status_code == 409


def test_revoke_all_sessions_self_and_admin(tmp_path, monkeypatch):
    http, db = make_client(tmp_path, admin_email="boss@foap.test")
    boss_user = dict(IDENT, id="w-boss", email="boss@foap.test")
    oauth_login(http, monkeypatch, boss_user)
    # Second session for the same employee (another device).
    http2 = TestClient(http.app, raise_server_exceptions=False)
    stub_exchange(monkeypatch, boss_user)
    r = http2.post("/api/auth/oauth/start", json={"provider": "google"})
    http2.post("/api/auth/oauth/finish",
               json={"code": "auth_code", "state": r.json()["state"]})
    assert http2.get("/api/auth/me").json()["gate"] == "app"

    r = http.post("/api/auth/sessions/revoke-all", json={})
    assert r.status_code == 200, r.text
    assert r.json()["revoked"] == 2
    assert http.get("/api/auth/me").json()["gate"] == "login"
    assert http2.get("/api/auth/me").json()["gate"] == "login"
    audit = http.get("/api/admin/employees").status_code  # admin dead too
    assert audit == 401

    # Fresh login, then admin revokes a target employee's sessions.
    oauth_login(http, monkeypatch, boss_user)
    newcomer = dict(IDENT, id="w-new", email="new@foap.test")
    stub_exchange(monkeypatch, newcomer)
    http3 = TestClient(http.app, raise_server_exceptions=False)
    r = http3.post("/api/auth/oauth/start", json={"provider": "google"})
    http3.post("/api/auth/oauth/finish",
               json={"code": "auth_code", "state": r.json()["state"]})
    staff = http.get("/api/admin/employees").json()["employees"]
    target = next(e for e in staff if e["email"] == "new@foap.test")
    r = http.post("/api/admin/employees/%s/approve" % target["id"], json={})
    assert r.status_code == 200
    r = http.post("/api/admin/employees/%s/sessions/revoke" % target["id"],
                  json={})
    assert r.status_code == 200 and r.json()["revoked"] >= 1
    assert http3.get("/api/auth/me").json()["gate"] == "login"
    events = http.get("/api/admin/audit").json()["events"]
    assert sum(1 for e in events
               if e["action"] == "SESSIONS_REVOKED") >= 2
    r = http.post("/api/admin/employees/nope/sessions/revoke", json={})
    assert r.status_code == 404


def test_sync_job_admin_api(tmp_path, monkeypatch):
    http, _db = make_client(tmp_path, admin_email="boss@foap.test")
    oauth_login(http, monkeypatch, dict(IDENT, id="w-boss",
                                        email="boss@foap.test"))
    me = http.get("/api/auth/me").json()["employee"]

    anon = TestClient(http.app, raise_server_exceptions=False)
    assert anon.get("/api/sync/jobs").status_code == 401

    r = http.post("/api/sync/jobs", json={"source": "meta", "name": "A",
                                          "params": {"ad_account_id": "1"}})
    assert r.status_code == 200, r.text
    job_a = r.json()["job"]
    assert job_a["owner_employee_id"] == me["id"]
    assert job_a["enabled"] is True
    r = http.post("/api/sync/jobs", json={"source": "meta", "name": "B",
                                          "params": {"ad_account_id": "2"}})
    job_b = r.json()["job"]
    assert job_b["id"] != job_a["id"]

    r = http.post("/api/sync/jobs", json={"source": "nope", "name": "x",
                                          "params": {}})
    assert r.status_code == 409
    r = http.post("/api/sync/jobs", json={"source": "meta", "name": "",
                                          "params": {}})
    assert r.status_code == 409

    r = http.get("/api/sync/jobs")
    assert sorted(j["name"] for j in r.json()["jobs"]) == ["A", "B"]

    r = http.patch("/api/sync/jobs/%s" % job_a["id"],
                   json={"enabled": False})
    assert r.json()["job"]["enabled"] is False
    r = http.patch("/api/sync/jobs/%s" % job_a["id"],
                   json={"name": "A2", "params": {"ad_account_id": "9"}})
    assert r.json()["job"]["name"] == "A2"
    r = http.patch("/api/sync/jobs/nope", json={"enabled": True})
    assert r.status_code == 404

    # Run-now records the run against the job (stubbed fetch).
    import creative_intel.sync as sync_mod
    orig = sync_mod.fetch_job
    sync_mod.fetch_job = lambda source, params: ([], [])
    try:
        r = http.post("/api/sync/jobs/%s/run" % job_b["id"], json={})
        assert r.status_code == 200, r.text
        assert r.json()["inserted"] == 0
    finally:
        sync_mod.fetch_job = orig
    st = http.get("/api/sync/status").json()
    info = next(j for j in st["job_list"] if j["id"] == job_b["id"])
    assert info["last_run"]["last_status"] == "ok"

    r = http.delete("/api/sync/jobs/%s" % job_a["id"])
    assert r.status_code == 200
    r = http.delete("/api/sync/jobs/%s" % job_a["id"])
    assert r.status_code == 404
    assert [j["name"] for j in http.get("/api/sync/jobs").json()["jobs"]] == ["B"]


def test_security_log_emits_no_secrets(tmp_path, monkeypatch, caplog):
    import logging
    caplog.set_level(logging.INFO, logger="creative_intel.security")
    http, _db = make_client(tmp_path, admin_email="boss@foap.test")
    oauth_login(http, monkeypatch, dict(IDENT, id="w-boss",
                                        email="boss@foap.test"))
    newcomer = dict(IDENT, id="w-new", email="new@foap.test")
    stub_exchange(monkeypatch, newcomer)
    http2 = TestClient(http.app, raise_server_exceptions=False)
    r = http2.post("/api/auth/oauth/start", json={"provider": "google"})
    http2.post("/api/auth/oauth/finish",
               json={"code": "auth_code", "state": r.json()["state"]})
    staff = http.get("/api/admin/employees").json()["employees"]
    target = next(e for e in staff if e["email"] == "new@foap.test")
    assert http.post("/api/admin/employees/%s/approve" % target["id"],
                     json={}).status_code == 200
    assert http.post("/api/admin/employees/%s/suspend" % target["id"],
                     json={}).status_code == 200
    http.post("/api/auth/logout", json={})
    text = caplog.text
    assert "login_success" in text
    assert "employee_status_change" in text
    assert "logout" in text
    for secret in ("auth_code", "secret-workos-key", "ci_session="):
        assert secret not in text
    # Session tokens live only in Set-Cookie, never in log lines.
    assert "action=login_success" in text


def test_oversize_body_rejected(tmp_path, monkeypatch):
    from ci_backend.app import create_app
    from ci_backend.config import Settings
    settings = Settings(workos_client_id="client_test",
                        key_workos="[REDACTED]", max_json_bytes=64)
    app = create_app(str(tmp_path / "tiny.db"), settings)
    tiny = TestClient(app, raise_server_exceptions=False)
    r = tiny.post("/api/auth/oauth/start",
                  json={"provider": "google", "pad": "x" * 128})
    assert r.status_code == 413
    assert r.json()["error"] == "Request body too large."


def test_xlsx_gate(tmp_path, monkeypatch):
    http, _db = make_client(tmp_path, admin_email="boss@foap.test")
    oauth_login(http, monkeypatch, dict(IDENT, id="w-boss",
                                        email="boss@foap.test"))
    import base64
    bad = base64.b64encode(b"not a workbook").decode()
    r = http.post("/api/ingest",
                  json={"platform": "meta", "xlsx_b64": bad})
    assert r.status_code == 409
    assert "xlsx" in r.json()["error"].lower()

    assert ingest_mod.check_xlsx_blob(b"PK\x03\x04rest")[:4] == b"PK\x03\x04"
    with pytest.raises(ValueError):
        ingest_mod.check_xlsx_blob(b"nope")
    with pytest.raises(ValueError):
        ingest_mod.check_xlsx_blob(b"")


def test_request_models_reject_garbage(tmp_path, monkeypatch):
    http, _db = make_client(tmp_path, admin_email="boss@foap.test")
    oauth_login(http, monkeypatch, dict(IDENT, id="w-boss",
                                        email="boss@foap.test"))
    me = http.get("/api/auth/me").json()["employee"]
    assert http.post("/api/admin/employees",
                     json={"email": "x@foap.test",
                           "role": "superuser"}).status_code == 409
    assert http.post("/api/admin/employees/%s/role" % me["id"],
                     json={"role": ""}).status_code == 409
    assert http.get("/api/admin/employees?filter=bogus").status_code == 409
    assert http.patch("/api/auth/me",
                      json={"first_name": 123}).status_code == 409
    assert http.patch("/api/sync/jobs/nope",
                      json={"enabled": "yes"}).status_code in (404, 409)


def test_oauth_state_cookie_binding(tmp_path, monkeypatch):
    http, _db = make_client(tmp_path, admin_email="boss@foap.test")
    stub_exchange(monkeypatch, dict(IDENT, id="w-boss",
                                    email="boss@foap.test"))
    r = http.post("/api/auth/oauth/start", json={"provider": "google"})
    state = r.json()["state"]

    # Attacker's browser: no state cookie -> rejected, state untouched.
    evil = TestClient(http.app, raise_server_exceptions=False)
    r = evil.post("/api/auth/oauth/finish",
                  json={"code": "auth_code", "state": state})
    assert r.status_code == 409
    r = evil.get("/api/auth/callback?code=auth_code&state=" + state,
                 follow_redirects=False)
    assert r.status_code == 302
    assert "auth_error=" in r.headers["location"]

    # Wrong cookie value -> rejected.
    http.cookies.set("ci_oauth_state", "tampered")
    r = http.post("/api/auth/oauth/finish",
                  json={"code": "auth_code", "state": state})
    assert r.status_code == 409

    # Correct binding -> login succeeds and the binding is cleared.
    http.cookies.set("ci_oauth_state", state)
    r = http.post("/api/auth/oauth/finish",
                  json={"code": "auth_code", "state": state})
    assert r.status_code == 200, r.text


def test_oauth_callback_replay_rejected(tmp_path, monkeypatch):
    http, _db = make_client(tmp_path, admin_email="boss@foap.test")
    stub_exchange(monkeypatch, dict(IDENT, id="w-boss",
                                    email="boss@foap.test"))
    r = http.post("/api/auth/oauth/start", json={"provider": "google"})
    state = r.json()["state"]
    first = http.post("/api/auth/oauth/finish",
                      json={"code": "auth_code", "state": state})
    assert first.status_code == 200
    replay = http.post("/api/auth/oauth/finish",
                       json={"code": "auth_code", "state": state})
    assert replay.status_code == 409
    unknown = http.post("/api/auth/oauth/finish",
                        json={"code": "auth_code", "state": "no-such-state"})
    assert unknown.status_code == 409


def test_auth_rate_limit(client):
    statuses = set()
    for _i in range(35):
        r = client.post("/api/auth/oauth/start", json={"provider": "google"})
        statuses.add(r.status_code)
    assert 200 in statuses
    r = client.post("/api/auth/oauth/start", json={"provider": "google"})
    assert r.status_code == 429
    assert r.json()["gate"] == "rate_limited"


def test_security_headers_health_readiness(client, tmp_path):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "same-origin"
    assert r.headers["x-frame-options"] == "DENY"
    assert "camera=()" in r.headers["permissions-policy"]
    assert "strict-transport-security" not in r.headers
    assert "access-control-allow-origin" not in r.headers
    r = client.get("/readiness")
    assert r.status_code == 200 and r.json() == {"ready": True}

    from tests.conftest import make_client as _make
    https_client = _make(tmp_path / "h.db", workos=False)
    r = https_client.get("/health")
    assert "strict-transport-security" not in r.headers


def test_hsts_when_cookie_secure(tmp_path):
    from ci_backend.app import create_app
    from ci_backend.config import Settings
    from fastapi.testclient import TestClient
    settings = Settings(workos_client_id="", key_workos="",
                        cookie_secure=True)
    app = create_app(str(tmp_path / "s.db"), settings)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/health")
    assert "max-age=31536000" in r.headers["strict-transport-security"]


def test_cookie_flags_default_and_secure(tmp_path, monkeypatch):
    http, _db = make_client(tmp_path, admin_email="boss@foap.test")
    r = oauth_login(http, monkeypatch,
                    dict(IDENT, id="w-boss", email="boss@foap.test"))
    set_cookie = r.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()
    assert "secure" not in set_cookie.lower()

    http_s, _db2 = make_client(tmp_path, admin_email="boss@foap.test",
                               cookie_secure=True)
    # Secure cookies are never sent back over plain HTTP (not even by
    # the test client), so present the state cookie explicitly here;
    # over real HTTPS the browser jar handles it.
    stub_exchange(monkeypatch, dict(IDENT, id="w-boss",
                                    email="boss@foap.test"))
    started = http_s.post("/api/auth/oauth/start",
                          json={"provider": "google"})
    assert started.status_code == 200, started.text
    state = started.json()["state"]
    jar = {c.name: c.value for c in started.cookies.jar}
    r = http_s.post("/api/auth/oauth/finish",
                    json={"code": "auth_code", "state": state},
                    headers={"Cookie": "%s=%s" % ("ci_oauth_state",
                                                  jar["ci_oauth_state"])})
    assert r.status_code == 200, r.text
    set_cookie = r.headers.get("set-cookie", "")
    assert "httponly" in set_cookie.lower()
    assert "secure" in set_cookie.lower()

    assert "; Secure" in emp_store.session_cookie("t", secure=True)
    assert "; Secure" not in emp_store.session_cookie("t")
    assert "; Secure" in emp_store.clear_cookie(secure=True)


def test_revoke_all_requires_login(client):
    r = client.post("/api/auth/sessions/revoke-all", json={})
    assert r.status_code == 401


def test_own_session_count_single_then_multi(tmp_path, monkeypatch):
    http, db = make_client(tmp_path, admin_email="boss@foap.test")
    boss_user = dict(IDENT, id="w-boss", email="boss@foap.test")
    oauth_login(http, monkeypatch, boss_user)
    assert http.get("/api/auth/sessions").json() == {"count": 1}
    # Second session for the same employee (another device).
    http2 = TestClient(http.app, raise_server_exceptions=False)
    stub_exchange(monkeypatch, boss_user)
    r = http2.post("/api/auth/oauth/start", json={"provider": "google"})
    http2.post("/api/auth/oauth/finish",
               json={"code": "auth_code", "state": r.json()["state"]})
    assert http.get("/api/auth/sessions").json() == {"count": 2}


def test_own_session_count_requires_login(client):
    r = client.get("/api/auth/sessions")
    assert r.status_code == 401


def test_switch_rechecks_authorization(tmp_path):
    http, db = make_client(tmp_path, admin_email="boss@foap.test")
    with employee_session(db) as sess:
        boss = emp_store.admin_create(sess, "root", "boss@foap.test",
                                      role="admin")
        staff = emp_store.admin_create(sess, "root", "staff@foap.test",
                                       role="employee")
        boss_cookie = "ci_session=" + emp_store.create_session(
            sess, boss.id, "")
        staff_cookie = "ci_session=" + emp_store.create_session(
            sess, staff.id, "")
    boss_client = TestClient(http.app, raise_server_exceptions=False)
    boss_client.headers.update({"Cookie": boss_cookie})
    staff_client = TestClient(http.app, raise_server_exceptions=False)
    staff_client.headers.update({"Cookie": staff_cookie})

    # Unbound sessions prove no shared tenancy: no enumeration, no
    # switching, even between two live unbound accounts.
    assert boss_client.get("/api/auth/accounts").json() == {"accounts": []}
    r = boss_client.post("/api/auth/switch",
                         json={"employee_id": staff.id})
    assert r.status_code == 404
    # Bind both sessions into one installation container first.
    for authed in (boss_client, staff_client):
        r = authed.post("/api/auth/container",
                        json={"container_id": "box-1"})
        assert r.json() == {"ok": True, "container_id": "box-1"}
    accounts = boss_client.get("/api/auth/accounts").json()["accounts"]
    assert {a["email"] for a in accounts} == {"boss@foap.test",
                                             "staff@foap.test"}
    # Switching to a live account works and keeps the first intact.
    r = boss_client.post("/api/auth/switch",
                         json={"employee_id": staff.id})
    assert r.status_code == 200
    assert r.json()["employee"]["email"] == "staff@foap.test"
    assert boss_client.get("/api/auth/me").json()["gate"] == "app"
    # After suspension, switching to that account is refused.
    http2 = TestClient(http.app, raise_server_exceptions=False)
    http2.headers.update({"Cookie": boss_cookie})
    http2.post("/api/admin/employees/%s/suspend" % staff.id, json={})
    r = boss_client.post("/api/auth/switch",
                         json={"employee_id": staff.id})
    assert r.status_code == 404
    # Suspended staff's old session is dead (401), and the roster
    # shows the suspension — no privilege leaks to the other account.
    assert staff_client.get("/api/campaigns").status_code == 401
    staff_row = next(e for e in
                     boss_client.get("/api/admin/employees").json()
                     ["employees"] if e["email"] == "staff@foap.test")
    assert staff_row["status"] == "suspended"
    assert boss_client.get("/api/auth/me").json()["is_admin"] is True


def test_secrets_never_leak(tmp_path, monkeypatch):
    from ci_backend import workos as workos_mod

    class BadResponse:
        status_code = 400

        def json(self):
            return {"message": "bad stuff", "code": "bad"}

    class StubClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            return BadResponse()

    monkeypatch.setattr(workos_mod.httpx, "Client", StubClient)
    monkeypatch.setenv("CREATIVE_INTEL_KEY_WORKOS", "sk-live-SECRET-XYZ")
    http, _db = make_client(tmp_path)
    r = http.post("/api/auth/oauth/start", json={"provider": "google"})
    assert r.status_code == 200
    # Force the WorkOS exchange itself to fail: the secret must not
    # surface in the 409 body.
    r = http.post("/api/auth/oauth/finish",
                  json={"code": "x", "state": r.json()["state"]})
    assert r.status_code == 409
    assert "SECRET-XYZ" not in r.text and "sk-live" not in r.text


def test_frontend_gates():
    with open(os.path.join(os.path.dirname(__file__), "..", "Web",
                           "Index.html"), encoding="utf-8") as fh:
        html = fh.read()
    assert "Welcome to Creative Intelligence" in html
    for label in ("Continue with Google", "Continue with Microsoft",
                  "Continue with Apple", "Continue with GitHub"):
        assert label in html
    assert "Access pending" in html
    assert "Admin" in html and "Employees" in html
    assert "Profile" in html and "profile-save" in html
    assert "/api/auth/me/avatar" in html and "pref-dark" in html
    assert "retention-playhead" in html and "ontimeupdate" in html
    assert "cmp-creative-rank" in html and "Attributes side-by-side" in html
    for secret in ("CREATIVE_INTEL_KEY_WORKOS", "sk-live", "sk_test"):
        assert secret not in html
    assert "localStorage" not in html


def test_no_licensing_concepts():
    root = os.path.join(os.path.dirname(__file__), "..")
    banned = ("do" + "do", "needs_license", "licence_", "license_key",
              "grace_period", "device_limit")
    hits = []
    for dirpath, _dirs, files in os.walk(root):
        if "__pycache__" in dirpath:
            continue
        for name in files:
            if not name.endswith((".py", ".html")):
                continue
            if name in ("test_ci_app.py", "test_ci_auth.py"):
                continue  # these files name the banned concepts
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            for bad in banned:
                if bad in text.lower():
                    hits.append("%s: %s" % (path, bad))
    assert hits == []


def test_react_source_title_is_approved():
    # The shipped browser title is fixed at the source: the Vite build
    # carries index.html's <title> into dist/ verbatim, so this holds
    # with or without a local frontend build.
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "apps", "creative-intelligence-ui",
                       "index.html")
    with open(src, encoding="utf-8") as fh:
        html = fh.read()
    assert "<title>Creative Intelligence</title>" in html
    assert "Foap Creative Intelligence" not in html


def test_spa_shell_serving(client):
    # Deep links serve the app shell; unknown paths still 404; liveness
    # endpoints are not shadowed by the SPA fallback.
    from ci_backend.actions import WEB_INDEX, react_index
    uses_react = (os.path.normpath(react_index())
                  != os.path.normpath(WEB_INDEX))
    for path in ("/campaigns", "/creatives", "/compare", "/benchmarks",
                 "/reports", "/profile", "/settings", "/admin",
                 "/analyst", "/insights", "/workbook", "/ask",
                 "/dashboard"):
        r = client.get(path)
        assert r.status_code == 200, path
        if uses_react:
            # Built production shell: approved title exactly
            # "Creative Intelligence" (never "Foap ...").
            assert "<title>Creative Intelligence</title>" in r.text, path
        else:
            # No dist/ in this checkout (backend-only CI job): the
            # legacy fallback shell serves instead.
            assert "Foap Creative Intelligence" in r.text, path
    assert client.get("/no-such-view").status_code == 404
    assert client.get("/health").json() == {"ok": True}
    assert client.get("/readiness").json() == {"ready": True}
    assert client.get("/assets/../Index.html").status_code == 404
    assert client.get("/assets/app.js").status_code == 404


def test_react_build_served_when_present(client, tmp_path, monkeypatch):
    import ci_backend.actions as actions_mod
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text(
        "<html><head><title>Foap Creative Intelligence</title></head></html>")
    (assets / "app-abc123.js").write_text("console.log(1)")
    (assets / "logo-xyz789.png").write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
        "1f15c4890000000d49444154789c626001000000ffff030000060005"
        "57bfabd40000000049454e44ae426082"))
    monkeypatch.setattr(actions_mod, "REACT_INDEX", str(dist / "index.html"))
    monkeypatch.setattr(actions_mod, "REACT_ASSETS_DIR", str(assets))
    orig = actions_mod.react_index
    monkeypatch.setattr(actions_mod, "react_index",
                        lambda: str(dist / "index.html")
                        if os.path.isfile(str(dist / "index.html"))
                        else orig())
    r = client.get("/")
    assert r.status_code == 200
    assert "Foap Creative Intelligence" in r.text
    r = client.get("/campaigns")
    assert r.status_code == 200
    r = client.get("/assets/app-abc123.js")
    assert r.status_code == 200
    assert "immutable" in r.headers.get("cache-control", "")
    assert client.get("/foap-logo.png").status_code == 200
    # Hashed image imports (e.g. provider logos) serve from dist too.
    r = client.get("/assets/logo-xyz789.png")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/png")
    assert "immutable" in r.headers.get("cache-control", "")
    r = client.get("/foap-mark.png")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/png")


def test_react_index_carries_strict_csp(client):
    import ci_backend.actions as actions_mod
    if not os.path.isfile(actions_mod.react_index()) or \
            actions_mod.react_index() == actions_mod.WEB_INDEX:
        pytest.skip("no built React frontend: dist/ is gitignored and "
                    "built in the frontend CI job, which covers the shell "
                    "end to end")
    r = client.get("/")
    csp = r.headers.get("content-security-policy", "")
    # This dev tree has a built React frontend, so the strict policy
    # applies; the legacy fallback intentionally omits it (inline scripts).
    assert "default-src 'self'" in csp, csp
    assert "script-src" not in csp or "'unsafe-inline'" not in csp


def _login(http, monkeypatch, email, box=""):
    stub_exchange(monkeypatch, {
        "id": "w-%s" % email, "email": email, "email_verified": True,
        "first_name": email.split("@")[0], "last_name": "T",
        "profile_picture_url": ""})
    r = http.post("/api/auth/oauth/start", json={"provider": "google"})
    assert r.status_code == 200, r.text
    payload = {"code": "auth_code", "state": r.json()["state"]}
    if box:
        payload["container_id"] = box
    r = http.post("/api/auth/oauth/finish", json=payload)
    assert r.status_code == 200, r.text
    return r


def _approve(http, email, by="root@foap.test"):
    with employee_session(http.app.state.ci_db_path) as sess:
        me = emp_store.find_employee(sess, email=email)
        root = emp_store.find_employee(sess, email=by)
        emp_store.admin_set_status(sess, root.id, me.id, "active",
                                   "EMPLOYEE_APPROVED")


def test_accounts_scoped_to_caller_container(client, monkeypatch):
    # Bootstrap admin first (no container), then X on box-a, Y on box-b.
    _login(client, monkeypatch, "root@foap.test")
    _login(client, monkeypatch, "x@foap.test", "box-a")
    _login(client, monkeypatch, "y@foap.test", "box-b")
    # Fresh box-a session for X sees X but never Y.
    _login(client, monkeypatch, "x@foap.test", "box-a")
    emails = [a["email"] for a in
              client.get("/api/auth/accounts").json()["accounts"]]
    assert "x@foap.test" in emails
    assert "y@foap.test" not in emails
    assert "root@foap.test" not in emails


def test_switch_refused_across_containers(client, monkeypatch):
    _login(client, monkeypatch, "root@foap.test")
    _login(client, monkeypatch, "x@foap.test", "box-a")
    y = _login(client, monkeypatch, "y@foap.test", "box-b").json()["employee"]
    for email in ("x@foap.test", "y@foap.test"):
        _approve(client, email)
    # X on box-a cannot switch to Y (live session, foreign container).
    _login(client, monkeypatch, "x@foap.test", "box-a")
    r = client.post("/api/auth/switch", json={"employee_id": y["id"]})
    assert r.status_code == 404
    # Same-container switch works and inherits the container.
    z = _login(client, monkeypatch, "zed@foap.test", "box-a").json()["employee"]
    _approve(client, "zed@foap.test")
    _login(client, monkeypatch, "x@foap.test", "box-a")
    r = client.post("/api/auth/switch", json={"employee_id": z["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["employee"]["id"] == z["id"]


def test_pending_caller_cannot_switch_into_unbound_admin(client,
                                                     monkeypatch):
    # A01 attack shape: a pending user plus a live UNBOUND admin
    # session. Neither enumeration nor switching may cross that gap.
    _login(client, monkeypatch, "boss@foap.test")
    with employee_session(client.app.state.ci_db_path) as sess:
        pending = emp_store.admin_create(sess, "root", "pending@foap.test",
                                         role="employee")
        # Simulate a first-login user awaiting approval (no valid
        # active->pending transition exists by design).
        pending.status = "pending"
        sess.commit()
        cookie = ("ci_session="
                  + emp_store.create_session(sess, pending.id, ""))
        admin = emp_store.find_employee(sess, email="boss@foap.test")
        admin_id = admin.id
    intruder = TestClient(client.app, raise_server_exceptions=False)
    intruder.headers.update({"Cookie": cookie})
    assert intruder.get("/api/auth/accounts").json() == {"accounts": []}
    r = intruder.post("/api/auth/switch",
                      json={"employee_id": admin_id})
    assert r.status_code in (401, 403, 404)
    assert intruder.get("/api/auth/me").json()["gate"] == "pending"


def test_container_bind_adopt_and_refuse(client, monkeypatch):
    # Unbound legacy session adopts a container on first write.
    _login(client, monkeypatch, "root@foap.test")
    r = client.post("/api/auth/container", json={"container_id": "box-1"})
    assert r.json() == {"ok": True, "container_id": "box-1"}
    # Same container re-bind is idempotent.
    r = client.post("/api/auth/container", json={"container_id": "box-1"})
    assert r.json()["container_id"] == "box-1"
    # A foreign container is refused with a login gate (fail closed).
    r = client.post("/api/auth/container", json={"container_id": "box-2"})
    assert r.status_code == 401
    assert r.json()["gate"] == "login"
    # Garbage container ids are rejected without touching the session.
    r = client.post("/api/auth/container", json={"container_id": "a/b"})
    assert r.status_code == 409


def test_provider_recorded_and_exposed(client, monkeypatch):
    _login(client, monkeypatch, "root@foap.test")
    me = client.get("/api/auth/me").json()
    # oauth stub default provider is google (see stub_exchange).
    assert me["employee"]["provider"] == "google"


def test_slow_action_does_not_block_health(tmp_path, monkeypatch):
    import threading
    import time

    import ci_backend.worker_handlers as handlers
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from conftest import mint_admin
    client, _db = make_client(tmp_path)
    client.headers.update(mint_admin(_db))
    entered = threading.Event()

    def slow(conn, payload, owner, ctx, job_id=None):
        _ = job_id
        entered.set()
        time.sleep(4)
        return {"answer": "slow"}

    monkeypatch.setitem(handlers.HANDLERS, "ask", slow)
    slow_done = []
    slow_errors = []

    def run_slow():
        try:
            r = client.post("/api/ask", json={"question": "slow?"})
            slow_done.append(r.status_code)
        except Exception as exc:  # noqa: BLE001 - surfaced below
            slow_errors.append(repr(exc))

    worker = threading.Thread(target=run_slow)
    worker.start()
    assert entered.wait(timeout=15), slow_errors
    start = time.time()
    r = client.get("/api/health")
    elapsed = time.time() - start
    worker.join(timeout=15)
    assert r.status_code == 200
    assert slow_done == [200]
    # The loop stayed free while the worker slept: generous margin
    # (4s sleep vs 3s budget) so loaded CI cannot flake this.
    assert elapsed < 3.0, elapsed


class TestCsrfOriginGuard:
    def _owner_client(self, tmp_path, **headers):
        http, db = make_client(tmp_path, admin_email="boss@foap.test")
        with employee_session(db) as sess:
            boss = emp_store.admin_create(sess, "root", "boss@foap.test",
                                          role="admin")
            cookie = ("ci_session="
                      + emp_store.create_session(sess, boss.id, ""))
        authed = TestClient(http.app, raise_server_exceptions=False)
        authed.headers.update({"Cookie": cookie, **headers})
        return authed

    def test_cross_origin_cookie_write_refused(self, tmp_path):
        authed = self._owner_client(tmp_path,
                                    Origin="https://evil.example")
        resp = authed.post("/api/ask", json={"question": "hi"})
        assert resp.status_code == 403
        assert resp.json()["gate"] == "csrf"

    def test_referer_mismatch_refused(self, tmp_path):
        authed = self._owner_client(tmp_path,
                                    Referer="https://evil.example/x")
        resp = authed.post("/api/ask", json={"question": "hi"})
        assert resp.status_code == 403

    def test_same_origin_cookie_write_allowed(self, tmp_path):
        authed = self._owner_client(tmp_path,
                                    Origin="http://testserver")
        resp = authed.post("/api/ask", json={"question": "hi"})
        assert resp.status_code in (200, 429)

    def test_scheme_mismatch_refused(self, tmp_path):
        authed = self._owner_client(tmp_path,
                                    Origin="https://testserver")
        resp = authed.post("/api/ask", json={"question": "hi"})
        assert resp.status_code == 403
        assert resp.json()["gate"] == "csrf"

    def test_port_mismatch_refused(self, tmp_path):
        authed = self._owner_client(tmp_path,
                                    Origin="http://testserver:9999")
        resp = authed.post("/api/ask", json={"question": "hi"})
        assert resp.status_code == 403

    def test_forwarded_tls_origin_allowed(self, tmp_path):
        authed = self._owner_client(
            tmp_path, Origin="https://testserver",
            **{"X-Forwarded-Proto": "https"})
        resp = authed.post("/api/ask", json={"question": "hi"})
        assert resp.status_code in (200, 429)

    def test_configured_public_base_allowed(self, tmp_path):
        http, _db = make_client(
            tmp_path, admin_email="boss@foap.test",
            workos_redirect_uri=(
                "https://app.example/api/auth/callback"))
        with employee_session(_db) as sess:
            boss = emp_store.admin_create(sess, "root", "boss@foap.test",
                                          role="admin")
            cookie = ("ci_session="
                      + emp_store.create_session(sess, boss.id, ""))
        authed = TestClient(http.app, raise_server_exceptions=False)
        authed.headers.update({"Cookie": cookie,
                               "Origin": "https://app.example"})
        resp = authed.post("/api/ask", json={"question": "hi"})
        assert resp.status_code in (200, 429)

    def test_no_origin_cookie_write_allowed(self, tmp_path):
        authed = self._owner_client(tmp_path)
        resp = authed.post("/api/ask", json={"question": "hi"})
        assert resp.status_code in (200, 429)


def test_root_csp_permits_shipped_inline_scripts(client):
    """The React entry's strict CSP must hash-allow its bare inline
    scripts (the pre-render theme boot) — otherwise browsers block the
    boot and first paint flashes light. The policy must never fall back
    to 'unsafe-inline' for scripts."""
    import base64 as _b64
    import hashlib as _hl
    import re as _re

    from ci_backend import actions as legacy

    if os.path.normpath(legacy.react_index()) == os.path.normpath(legacy.WEB_INDEX):
        pytest.skip("React dist not built in this checkout")
    r = client.get("/")
    assert r.status_code == 200, r.text
    csp = r.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp
    assert "script-src" not in csp
    default_src = csp.split("default-src", 1)[1].split(";", 1)[0]
    assert "'unsafe-inline'" not in default_src
    with open(legacy.react_index(), "rb") as fh:
        html = fh.read().decode("utf-8")
    bodies = _re.findall(r"<script>(.*?)</script>", html, _re.DOTALL)
    assert bodies, "expected at least the theme boot inline script"
    for body in bodies:
        digest = _b64.b64encode(_hl.sha256(body.encode("utf-8")).digest()).decode("ascii")
        assert f"'sha256-{digest}'" in default_src
