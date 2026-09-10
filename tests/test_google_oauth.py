"""Google OAuth for private Drive/Sheets (item 31).

Deterministic: Google HTTP is stubbed at httpx.Client, the keychain is
an in-memory fake. No test here touches the network or real secrets.
"""

import os
import sys
import types

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import employees as emp_store  # noqa: E402
from ci_backend import google_oauth as goog  # noqa: E402
from ci_backend.app import create_app  # noqa: E402
from ci_backend.config import Settings  # noqa: E402
from ci_backend.db import make_engine, make_session_factory  # noqa: E402

GSET = dict(google_client_id="g-client",
            google_redirect_uri="http://127.0.0.1:4321/api/auth/google/callback")


@pytest.fixture()
def app_data(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_INTEL_GOOGLE_CLIENT_SECRET", "g-secret")
    db_path = str(tmp_path / "google.db")
    settings = Settings(**GSET)
    app = create_app(db_path, settings)
    engine = make_engine(db_path)
    with make_session_factory(engine)() as sess:
        employee = emp_store.admin_create(sess, "test-helper",
                                          "staff@example.com", role="admin")
        token = emp_store.create_session(sess, employee.id, "")
    http = TestClient(app, raise_server_exceptions=False)
    http.cookies.set("ci_session", token)
    return http, engine


@pytest.fixture()
def fake_keyring(monkeypatch):
    store = {}

    fake = types.ModuleType("keyring")

    def get_password(service, account):
        return store.get((service, account))

    def set_password(service, account, value):
        store[(service, account)] = value

    def delete_password(service, account):
        store.pop((service, account), None)

    fake.get_password = get_password
    fake.set_password = set_password
    fake.delete_password = delete_password
    monkeypatch.setitem(sys.modules, "keyring", fake)
    return store


def fake_google(monkeypatch, calls, body=None, status=200):
    body = body if body is not None else {
        "access_token": "ya-access", "refresh_token": "ya-refresh",
        "expires_in": 3600}

    class FakeResponse:
        status_code = status

        def json(self):
            return dict(body)

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, data=None):
            calls.append({"url": url, "data": dict(data or {})})
            assert "client_secret" not in str(url)
            return FakeResponse()

    monkeypatch.setattr(goog.httpx, "Client", FakeClient)


def test_start_needs_config(app_data):
    http, _engine = app_data
    r = http.post("/api/auth/google/start")
    assert r.status_code == 200, r.text
    assert r.json()["url"].startswith(
        "https://accounts.google.com/o/oauth2/v2/auth?")
    assert "code_challenge" in r.json()["url"]
    assert http.cookies.get("ci_google_state")


def test_callback_rejects_bad_state(app_data):
    http, _engine = app_data
    r = http.get("/api/auth/google/callback?code=x&state=nope",
                 follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].endswith("?google=expired")


def test_full_connect_status_disconnect(app_data, fake_keyring, monkeypatch):
    http, engine = app_data
    calls = []
    fake_google(monkeypatch, calls)
    assert http.get("/api/auth/google/status").json() == {"connected": False}
    r = http.post("/api/auth/google/start")
    state = http.cookies.get("ci_google_state")
    assert state
    r = http.get("/api/auth/google/callback?code=auth-code&state=%s" % state,
                 follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].endswith("?google=connected")
    assert calls and calls[0]["url"] == goog.GOOGLE_TOKEN_URL
    sent = calls[0]["data"]
    assert sent["grant_type"] == "authorization_code"
    assert sent["code"] == "auth-code"
    assert "client_secret" not in sent or sent.get("client_secret")
    # Replay the same callback: single-use state is gone.
    r = http.get("/api/auth/google/callback?code=auth-code&state=%s" % state,
                 follow_redirects=False)
    assert r.headers["location"].endswith("?google=expired")
    status = http.get("/api/auth/google/status").json()
    assert status["connected"] is True
    # Refresh token went to the keychain, access token to the database.
    assert len(fake_keyring) == 1
    with make_session_factory(engine)() as sess:
        row = sess.get(goog.OAuthToken, ("google", sess.execute(
            __import__("sqlalchemy").select(emp_store.Employee.id).where(
                emp_store.Employee.email == "staff@example.com")
        ).scalar_one()))
        assert row is not None and row.access_token == "ya-access"
        assert "ya-refresh" not in (row.access_token + row.scope)
    r = http.post("/api/auth/google/disconnect")
    assert r.json() == {"ok": True}
    assert http.get("/api/auth/google/status").json() == {"connected": False}
    assert fake_keyring == {}


def test_exchange_failure_redirects(app_data, fake_keyring, monkeypatch):
    http, _engine = app_data
    calls = []
    fake_google(monkeypatch, calls, body={"error": "bad"}, status=400)
    http.post("/api/auth/google/start")
    state = http.cookies.get("ci_google_state")
    r = http.get("/api/auth/google/callback?code=bad&state=%s" % state,
                 follow_redirects=False)
    assert r.headers["location"].endswith("?google=failed")
    assert http.get("/api/auth/google/status").json() == {"connected": False}


def test_expired_access_token_refreshes(app_data, fake_keyring, monkeypatch):
    http, engine = app_data
    calls = []
    fake_google(monkeypatch, calls)
    http.post("/api/auth/google/start")
    state = http.cookies.get("ci_google_state")
    http.get("/api/auth/google/callback?code=c&state=%s" % state,
             follow_redirects=False)
    # Age the access token out, then ask for headers: refresh fires.
    with make_session_factory(engine)() as sess:
        emp_id = sess.execute(
            __import__("sqlalchemy").select(emp_store.Employee.id).where(
                emp_store.Employee.email == "staff@example.com")).scalar_one()
        row = sess.get(goog.OAuthToken, ("google", emp_id))
        row.expires_at = "2000-01-01T00:00:00"
        sess.commit()
    with make_session_factory(engine)() as sess:
        headers = goog.bearer_headers(sess, emp_id)
    assert headers["Authorization"] == "Bearer ya-access"
    assert calls[-1]["data"]["grant_type"] == "refresh_token"


def test_no_secret_in_status_or_logs(app_data, fake_keyring, monkeypatch,
                                     caplog):
    import logging
    http, _engine = app_data
    calls = []
    fake_google(monkeypatch, calls)
    http.post("/api/auth/google/start")
    state = http.cookies.get("ci_google_state")
    with caplog.at_level(logging.INFO):
        http.get("/api/auth/google/callback?code=c&state=%s" % state,
                 follow_redirects=False)
    blob = (http.get("/api/auth/google/status").text + caplog.text)
    assert "ya-access" not in blob and "ya-refresh" not in blob
    assert "g-secret" not in blob
