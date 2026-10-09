"""Meta, TikTok, and GA4 OAuth. Provider HTTP is stubbed.

No test here touches the network, a real ad account, or the keychain.
"""

import os
import sys

import pytest
import sqlalchemy
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import employees as emp_store  # noqa: E402
from ci_backend import integrations_oauth as integ  # noqa: E402
from ci_backend import token_crypto  # noqa: E402
from ci_backend.app import create_app  # noqa: E402
from ci_backend.config import Settings  # noqa: E402
from ci_backend.db import OAuthToken, make_engine, make_session_factory  # noqa: E402

TEST_MASTER_KEY = "r6I4teiO8U9i7HlJkR4tLghv5kqp69HfLWMcczM8UUs="


@pytest.fixture()
def http(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_INTEL_META_CLIENT_SECRET", "meta-secret")
    monkeypatch.setenv("CREATIVE_INTEL_TIKTOK_CLIENT_SECRET", "tiktok-secret")
    monkeypatch.setenv("CREATIVE_INTEL_GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.delenv("CREATIVE_INTEL_MASTER_KEY", raising=False)
    db_path = str(tmp_path / "ads.db")
    settings = Settings(
        master_key=TEST_MASTER_KEY,
        meta_client_id="meta-client",
        meta_redirect_uri="http://127.0.0.1:4321/api/auth/integrations/meta/callback",
        tiktok_client_id="tiktok-client",
        tiktok_redirect_uri="http://127.0.0.1:4321/api/auth/integrations/tiktok/callback",
        google_client_id="google-client",
        ga4_redirect_uri="http://127.0.0.1:4321/api/auth/integrations/ga4/callback",
    )
    app = create_app(db_path, settings)
    engine = make_engine(db_path)
    try:
        with make_session_factory(engine)() as sess:
            employee = emp_store.admin_create(
                sess, "test-helper", "staff@example.com", role="admin")
            token = emp_store.create_session(sess, employee.id, "")
        client = TestClient(app, raise_server_exceptions=False)
        client.cookies.set("ci_session", token)
        yield client, engine, settings
    finally:
        engine.dispose()


def _fake_http(monkeypatch, routes):
    class FakeResponse:
        def __init__(self, status, body):
            self.status_code = status
            self._body = body

        def json(self):
            return self._body

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None, headers=None):
            routes.append({"method": "GET", "url": url, "params": dict(params or {})})
            if "adaccounts" in url:
                return FakeResponse(200, {"data": [{"account_id": "998877"}]})
            if "accountSummaries" in url:
                return FakeResponse(200, {"accountSummaries": [{
                    "propertySummaries": [{"property": "properties/123"}],
                }]})
            return FakeResponse(200, {
                "access_token": "meta-access", "expires_in": 3600,
            })

        def post(self, url, data=None, json=None):
            routes.append({"method": "POST", "url": url,
                           "data": dict(data or {}), "json": dict(json or {})})
            if "tiktok" in url:
                return FakeResponse(200, {"code": 0, "data": {
                    "access_token": "tt-access",
                    "refresh_token": "tt-refresh",
                    "expires_in": 86400,
                    "advertiser_ids": ["555"],
                }})
            return FakeResponse(200, {
                "access_token": "ga-access",
                "refresh_token": "ga-refresh",
                "expires_in": 3600,
                "scope": integ._GA4_SCOPE,
            })

        def delete(self, url, params=None):
            routes.append({"method": "DELETE", "url": url})
            return FakeResponse(200, {"ok": True})

    monkeypatch.setattr(integ.httpx, "Client", FakeClient)


def _connect(client, provider, code="auth-code"):
    started = client.post("/api/auth/integrations/%s/start" % provider)
    assert started.status_code == 200, started.text
    state = client.cookies.get("ci_integration_state")
    assert state
    return client.get(
        "/api/auth/integrations/%s/callback?code=%s&state=%s"
        % (provider, code, state), follow_redirects=False)


def test_start_refuses_when_unconfigured(tmp_path):
    settings = Settings(master_key=TEST_MASTER_KEY)
    app = create_app(str(tmp_path / "bare.db"), settings)
    engine = make_engine(str(tmp_path / "bare.db"))
    # create_app already migrated the path above. Open a second engine
    # only to mint a session on that same file.
    try:
        with make_session_factory(engine)() as sess:
            employee = emp_store.admin_create(
                sess, "test-helper", "staff@example.com", role="admin")
            token = emp_store.create_session(sess, employee.id, "")
        client = TestClient(app, raise_server_exceptions=False)
        client.cookies.set("ci_session", token)
        for provider, name in (("meta", "Meta Ads"), ("tiktok", "TikTok Ads"),
                              ("ga4", "Google Analytics 4")):
            response = client.post("/api/auth/integrations/%s/start" % provider)
            assert response.status_code == 409, response.text
            assert response.json()["error"] == "%s is not configured." % name
    finally:
        engine.dispose()


def test_meta_connect_stores_encrypted_token(http, monkeypatch):
    client, engine, settings = http
    calls = []
    _fake_http(monkeypatch, calls)
    assert client.get("/api/auth/integrations/meta/status").json() == {
        "connected": False}
    response = _connect(client, "meta")
    assert response.status_code == 302
    assert response.headers["location"].endswith(
        "integration=meta&result=connected")
    status = client.get("/api/auth/integrations/meta/status").json()
    assert status["connected"] is True
    assert status["account"] == "998877"
    assert "meta-access" not in response.headers["location"]
    assert "meta-secret" not in client.get(
        "/api/auth/integrations/meta/status").text
    with make_session_factory(engine)() as sess:
        row = sess.scalars(sqlalchemy.select(OAuthToken).where(
            OAuthToken.provider == "meta")).one()
        assert row.access_token == ""
        assert token_crypto.decrypt_secret(row.access_token_enc, settings) \
            == "meta-access"
        assert "meta-secret" not in (row.access_token_enc + row.scope)
    gone = client.post("/api/auth/integrations/meta/disconnect")
    assert gone.json() == {"ok": True}
    assert client.get("/api/auth/integrations/meta/status").json() == {
        "connected": False}


def test_tiktok_and_ga4_connect(http, monkeypatch):
    client, engine, settings = http
    calls = []
    _fake_http(monkeypatch, calls)
    tiktok = _connect(client, "tiktok")
    assert "result=connected" in tiktok.headers["location"]
    assert client.get("/api/auth/integrations/tiktok/status").json()["account"] \
        == "555"
    ga4 = _connect(client, "ga4")
    assert "result=connected" in ga4.headers["location"]
    assert client.get("/api/auth/integrations/ga4/status").json()["account"] \
        == "properties/123"
    start = client.post("/api/auth/integrations/ga4/start")
    assert "analytics.readonly" in start.json()["url"]
    assert "code_challenge=" in start.json()["url"]
    with make_session_factory(engine)() as sess:
        row = sess.scalars(sqlalchemy.select(OAuthToken).where(
            OAuthToken.provider == "ga4")).one()
        assert token_crypto.decrypt_secret(row.refresh_token_enc, settings) \
            == "ga-refresh"


def test_callback_does_not_store_under_a_different_employee(http, monkeypatch):
    client, engine, _settings = http
    calls = []
    _fake_http(monkeypatch, calls)
    started_as = client.cookies.get("ci_session")
    started = client.post("/api/auth/integrations/meta/start")
    assert started.status_code == 200, started.text
    state = client.cookies.get("ci_integration_state")
    with make_session_factory(engine)() as sess:
        other = emp_store.admin_create(
            sess, "root", "other@example.com", role="employee")
        other_token = emp_store.create_session(sess, other.id, "w-other")
        other_id = other.id
    client.cookies.set("ci_session", other_token)
    response = client.get(
        "/api/auth/integrations/meta/callback?code=auth-code&state=%s" % state,
        follow_redirects=False)
    assert response.status_code == 302
    assert "result=failed" in response.headers["location"]
    assert "meta-access" not in response.headers["location"]
    with make_session_factory(engine)() as sess:
        rows = sess.scalars(sqlalchemy.select(OAuthToken).where(
            OAuthToken.provider == "meta")).all()
    assert rows == []
    client.cookies.set("ci_session", started_as)
    assert client.get("/api/auth/integrations/meta/status").json() == {
        "connected": False}
    client.cookies.set("ci_session", other_token)
    assert client.get("/api/auth/integrations/meta/status").json() == {
        "connected": False}
    _ = other_id


def test_callback_rejects_a_foreign_state(http):
    client, _engine, _settings = http
    client.post("/api/auth/integrations/meta/start")
    response = client.get(
        "/api/auth/integrations/meta/callback?code=x&state=nope",
        follow_redirects=False)
    assert response.status_code == 302
    assert "result=expired" in response.headers["location"]
    assert client.get("/api/auth/integrations/meta/status").json() == {
        "connected": False}


def test_unknown_provider_is_not_found(http):
    client, _engine, _settings = http
    assert client.get("/api/auth/integrations/snap/status").status_code == 404


def test_scheduler_resolver_uses_a_connected_ads_token(tmp_path, monkeypatch):
    import ci_backend.google_oauth as goog
    from ci_backend.main import _google_bearer_resolver

    def status(_db, provider, employee_id):
        if employee_id == "off":
            return {"connected": False}
        return {"connected": True, "account": "1", "provider": provider}

    def access(_db, provider, employee_id, settings=None):
        assert provider == "meta"
        assert employee_id == "on"
        _ = settings
        return "meta-access"

    def google(_db, employee_id, settings=None):
        assert employee_id == "sheet-owner"
        _ = settings
        return "goog-access"

    monkeypatch.setattr(integ, "status", status)
    monkeypatch.setattr(integ, "access_token_for", access)
    monkeypatch.setattr(goog, "access_token_for", google)
    resolve = _google_bearer_resolver(
        str(tmp_path / "sched.db"), Settings(master_key=TEST_MASTER_KEY))
    assert resolve({"owner_employee_id": "on", "source": "meta"}) == "meta-access"
    assert resolve({"owner_employee_id": "off", "source": "tiktok"}) is None
    assert resolve({
        "owner_employee_id": "sheet-owner", "source": "sheets",
    }) == "goog-access"
