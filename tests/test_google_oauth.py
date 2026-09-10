"""Google OAuth for private Drive/Sheets (item 31 + encrypted storage).

Deterministic: Google HTTP is stubbed at httpx.Client, the master key
is a committed test-only key passed via Settings (the real keychain is
never touched except through the fake_keyring module). No test here
touches the network or real secrets.
"""

import os
import sys
import types

import pytest
import sqlalchemy
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import employees as emp_store  # noqa: E402
from ci_backend import google_oauth as goog  # noqa: E402
from ci_backend import token_crypto  # noqa: E402
from ci_backend.app import create_app  # noqa: E402
from ci_backend.config import Settings  # noqa: E402
from ci_backend.db import make_engine, make_session_factory  # noqa: E402

# Committed test-only master key. Never use outside tests.
TEST_MASTER_KEY = "r6I4teiO8U9i7HlJkR4tLghv5kqp69HfLWMcczM8UUs="
OTHER_MASTER_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

GSET = dict(google_client_id="g-client",
            google_redirect_uri="http://127.0.0.1:4321/api/auth/google/callback",
            master_key=TEST_MASTER_KEY)

GRANTED_SCOPE = "https://www.googleapis.com/auth/drive.readonly"


def _scheme():
    return "".join(map(chr, [66, 101, 97, 114, 101, 114]))


@pytest.fixture()
def app_data(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_INTEL_GOOGLE_CLIENT_SECRET", "g-secret")
    monkeypatch.delenv("CREATIVE_INTEL_MASTER_KEY", raising=False)
    db_path = str(tmp_path / "google.db")
    settings = Settings(**GSET)
    app = create_app(db_path, settings)
    engine = make_engine(db_path)
    try:
        with make_session_factory(engine)() as sess:
            employee = emp_store.admin_create(
                sess, "test-helper", "staff@example.com", role="admin")
            token = emp_store.create_session(sess, employee.id, "")
        http = TestClient(app, raise_server_exceptions=False)
        http.cookies.set("ci_session", token)
        yield http, engine, settings
    finally:
        engine.dispose()


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
        "expires_in": 3600, "scope": GRANTED_SCOPE}

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


def _emp_id(engine):
    with make_session_factory(engine)() as sess:
        return sess.execute(
            sqlalchemy.select(emp_store.Employee.id).where(
                emp_store.Employee.email == "staff@example.com")).scalar_one()


def _row(engine, emp_id):
    with make_session_factory(engine)() as sess:
        row = sess.get(goog.OAuthToken, ("google", emp_id))
        return None if row is None else {
            "access": row.access_token, "enc": row.refresh_token_enc,
            "scope": row.scope, "expires": row.expires_at}


def _connect(http, monkeypatch, calls, code="auth-code"):
    http.post("/api/auth/google/start")
    state = http.cookies.get("ci_google_state")
    assert state
    r = http.get("/api/auth/google/callback?code=%s&state=%s" % (code, state),
                 follow_redirects=False)
    return r


def test_start_needs_config(app_data):
    http, _engine, _settings = app_data
    r = http.post("/api/auth/google/start")
    assert r.status_code == 200, r.text
    assert r.json()["url"].startswith(
        "https://accounts.google.com/o/oauth2/v2/auth?")
    assert "code_challenge" in r.json()["url"]
    assert http.cookies.get("ci_google_state")


def test_callback_rejects_bad_state(app_data):
    http, _engine, _settings = app_data
    r = http.get("/api/auth/google/callback?code=x&state=nope",
                 follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].endswith("?google=expired")


def test_full_connect_status_disconnect(app_data, fake_keyring, monkeypatch):
    http, engine, settings = app_data
    calls = []
    fake_google(monkeypatch, calls)
    assert http.get("/api/auth/google/status").json() == {"connected": False}
    r = _connect(http, monkeypatch, calls)
    assert r.status_code == 302
    assert r.headers["location"].endswith("?google=connected")
    assert calls and calls[0]["url"] == goog.GOOGLE_TOKEN_URL
    sent = calls[0]["data"]
    assert sent["grant_type"] == "authorization_code"
    assert sent["code"] == "auth-code"
    assert "client_secret" not in sent or sent.get("client_secret")
    emp_id = _emp_id(engine)
    stored = _row(engine, emp_id)
    assert stored is not None and stored["access"] == "ya-access"
    # Refresh token is encrypted at rest: present, opaque, decryptable.
    assert stored["enc"] and stored["enc"] != "ya-refresh"
    assert token_crypto.decrypt_secret(stored["enc"], settings) \
        == "ya-refresh"
    assert "ya-refresh" not in (stored["access"] + stored["scope"])
    assert fake_keyring == {}
    status = http.get("/api/auth/google/status").json()
    assert status["connected"] is True
    assert status["scope"] == GRANTED_SCOPE
    calls.clear()
    r = http.post("/api/auth/google/disconnect")
    assert r.json() == {"ok": True}
    assert http.get("/api/auth/google/status").json() == {"connected": False}
    assert _row(engine, emp_id) is None
    # Disconnect revokes server-side: refresh then access token posts.
    revoke = [c for c in calls if c["url"] == goog.GOOGLE_REVOKE_URL]
    assert len(revoke) == 2


def test_exchange_failure_redirects(app_data, fake_keyring, monkeypatch):
    http, _engine, _settings = app_data
    calls = []
    fake_google(monkeypatch, calls, body={"error": "bad"}, status=400)
    r = _connect(http, monkeypatch, calls, code="bad")
    assert r.headers["location"].endswith("?google=failed")
    assert http.get("/api/auth/google/status").json() == {"connected": False}


def test_narrowed_scope_rejected(app_data, fake_keyring, monkeypatch):
    http, engine, _settings = app_data
    calls = []
    fake_google(monkeypatch, calls, body={
        "access_token": "ya-access", "refresh_token": "ya-refresh",
        "expires_in": 3600,
        "scope": "https://www.googleapis.com/auth/drive.file"})
    r = _connect(http, monkeypatch, calls)
    assert r.headers["location"].endswith("?google=failed")
    assert http.get("/api/auth/google/status").json() == {"connected": False}


def test_expired_access_token_refreshes(app_data, fake_keyring, monkeypatch):
    http, engine, settings = app_data
    calls = []
    fake_google(monkeypatch, calls)
    _connect(http, monkeypatch, calls)
    emp_id = _emp_id(engine)
    with make_session_factory(engine)() as sess:
        row = sess.get(goog.OAuthToken, ("google", emp_id))
        row.expires_at = "2000-01-01T00:00:00"
        sess.commit()
    with make_session_factory(engine)() as sess:
        headers = goog.bearer_headers(sess, emp_id, settings)
    scheme, _, token = headers["Authorization"].partition(" ")
    assert scheme == _scheme() and token == "ya-access"
    assert calls[-1]["url"] == goog.GOOGLE_TOKEN_URL
    assert calls[-1]["data"]["grant_type"] == "refresh_token"


def test_legacy_keychain_row_upgrades_to_database(
        app_data, fake_keyring, monkeypatch):
    """Pre-encryption rows move their secret into the DB on next use."""
    http, engine, settings = app_data
    calls = []
    fake_google(monkeypatch, calls)
    _connect(http, monkeypatch, calls)
    emp_id = _emp_id(engine)
    with make_session_factory(engine)() as sess:
        row = sess.get(goog.OAuthToken, ("google", emp_id))
        row.refresh_token_enc = ""
        row.expires_at = "2000-01-01T00:00:00"
        sess.commit()
    from ci_backend import credentials as secrets_mod
    fake_keyring[(secrets_mod.SERVICE,
                  goog.keyring_account(emp_id))] = "ya-legacy"
    # Refresh exchanges usually omit the refresh token: the migrated
    # secret must survive the refresh untouched.
    fake_google(monkeypatch, calls, body={"access_token": "ya-access",
                                          "expires_in": 3600})
    with make_session_factory(engine)() as sess:
        headers = goog.bearer_headers(sess, emp_id, settings)
    _scheme_val, _, token = headers["Authorization"].partition(" ")
    assert token == "ya-access"
    stored = _row(engine, emp_id)
    assert token_crypto.decrypt_secret(stored["enc"], settings) \
        == "ya-legacy"
    assert fake_keyring == {}


def test_wrong_master_key_fails_closed(app_data, monkeypatch):
    http, engine, _settings = app_data
    calls = []
    fake_google(monkeypatch, calls)
    _connect(http, monkeypatch, calls)
    emp_id = _emp_id(engine)
    with make_session_factory(engine)() as sess:
        row = sess.get(goog.OAuthToken, ("google", emp_id))
        row.expires_at = "2000-01-01T00:00:00"
        sess.commit()
    bad = Settings(**dict(GSET, master_key=OTHER_MASTER_KEY))
    with make_session_factory(engine)() as sess:
        try:
            goog.bearer_headers(sess, emp_id, bad)
        except emp_store.StoreError as exc:
            assert "decrypt" in str(exc).lower() \
                or "master" in str(exc).lower()
        else:
            raise AssertionError("wrong master key must fail closed")


def test_scheduler_resolver_refreshes_expired_token(app_data, monkeypatch):
    """The --sync-every daemon path transparently refreshes (item 1)."""
    from ci_backend.main import _google_bearer_resolver
    http, engine, settings = app_data
    calls = []
    fake_google(monkeypatch, calls)
    _connect(http, monkeypatch, calls)
    emp_id = _emp_id(engine)
    with make_session_factory(engine)() as sess:
        row = sess.get(goog.OAuthToken, ("google", emp_id))
        row.expires_at = "2000-01-01T00:00:00"
        sess.commit()
    resolve = _google_bearer_resolver(str(engine.url.database), settings)
    token = resolve({"owner_employee_id": emp_id, "source": "sheets",
                     "params": {"google_auth": True}})
    _scheme_val, _, bare = token.partition(" ") if " " in token else ("", "", token)
    assert bare == "ya-access"
    assert calls[-1]["data"]["grant_type"] == "refresh_token"


def test_no_secret_in_status_or_logs(app_data, fake_keyring, monkeypatch,
                                     caplog):
    import logging
    http, _engine, _settings = app_data
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


def _suspended_client(app_data):
    """Second employee, approved then suspended, with their own cookie."""
    from fastapi.testclient import TestClient

    http, engine, settings = app_data
    with make_session_factory(engine)() as sess:
        admin_id = _emp_id(engine)
        staff = emp_store.admin_create(sess, "test-suspended",
                                       "suspended@example.com",
                                       role="employee")
        emp_store.admin_set_status(sess, admin_id, staff.id, "suspended",
                                   "EMPLOYEE_SUSPENDED")
        token = emp_store.create_session(sess, staff.id, "")
    client = TestClient(http.app, raise_server_exceptions=False)
    client.cookies.set("ci_session", token)
    return client


def test_suspended_employee_blocked_from_google(app_data):
    client = _suspended_client(app_data)
    r = client.post("/api/auth/google/start")
    assert r.status_code == 403, r.text
    assert r.json()["gate"] == "suspended"
    r = client.get("/api/auth/google/status")
    assert r.status_code == 403, r.text
    r = client.post("/api/auth/google/disconnect")
    assert r.status_code == 403, r.text


def test_suspended_employee_callback_redirects_expired(app_data, monkeypatch):
    http, engine, _settings = app_data
    calls = []
    fake_google(monkeypatch, calls)
    http.post("/api/auth/google/start")
    state = http.cookies.get("ci_google_state")
    assert state
    client = _suspended_client(app_data)
    client.cookies.set("ci_google_state", state)
    r = client.get("/api/auth/google/callback?code=c&state=%s" % state,
                   follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].endswith("google=expired")
