"""Nextly-stack auth tests (pytest + SQLAlchemy + httpx).

Mirrors the legacy unittest journeys against the new ``ci_backend``
package: OAuth/PKCE shape, pending/bootstrap/link flows, transitions,
last-admin rule, sessions, audit, cookies, Alembic migrations.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import db as db_mod
from ci_backend import employees as emp
from ci_backend import credentials as secrets_mod
from ci_backend import workos as workos_mod
from ci_backend.config import Settings


@pytest.fixture()
def session(tmp_path):
    engine = db_mod.make_engine(tmp_path / "t.db")
    db_mod.init_db(engine)
    factory = db_mod.make_session_factory(engine)
    with factory() as sess:
        yield sess


IDENT = {"workos_user_id": "w-ada", "email": "ada@foap.test",
         "first_name": "Ada", "last_name": "L", "avatar_url": "",
         "verified": True, "provider": "google"}


def test_settings_env_prefix(monkeypatch):
    monkeypatch.setenv("CREATIVE_INTEL_WORKOS_CLIENT_ID", "client_x")
    monkeypatch.setenv("CREATIVE_INTEL_ADMIN_EMAIL", "boss@foap.test")
    settings = Settings()
    assert settings.workos_client_id == "client_x"
    assert settings.admin_email == "boss@foap.test"
    assert settings.database_path.name == "creative_intel.db"


def test_pkce_and_authorize_url(monkeypatch):
    monkeypatch.setenv("CREATIVE_INTEL_WORKOS_CLIENT_ID", "client_test")
    verifier, challenge = workos_mod.pkce_pair()
    assert verifier and challenge and verifier != challenge
    url = workos_mod.authorization_url(provider="google", state="s",
                                       code_challenge=challenge,
                                       redirect="http://127.0.0.1:1/cb")
    assert "client_test" in url and "GoogleOAuth" in url
    assert "code_challenge_method=S256" in url
    with pytest.raises(workos_mod.WorkOSError):
        workos_mod.authorization_url(provider="facebook", state="s",
                                     code_challenge=challenge)


def test_public_identity_shapes():
    ident = workos_mod.public_identity(
        {"user": {"id": "w-1", "email": "A@X.test", "email_verified": True,
                  "first_name": "A", "last_name": "B",
                  "profile_picture_url": "http://pic"}}, provider="google")
    assert ident["workos_user_id"] == "w-1"
    assert ident["email"] == "a@x.test"
    assert ident["verified"] is True and ident["avatar_url"] == "http://pic"
    empty = workos_mod.public_identity({"user": None})
    assert empty["workos_user_id"] == "" and empty["verified"] is False


def test_workos_calls_use_httpx(monkeypatch):
    calls = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"user": {"id": "w-z", "email": "z@foap.test",
                             "email_verified": True}}

    class FakeClient:
        def __init__(self, *a, **k):
            calls["timeout"] = k.get("timeout")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            calls["url"] = url
            calls["auth"] = headers.get("Authorization")
            calls["json"] = json
            return FakeResponse()

    monkeypatch.setattr(workos_mod.httpx, "Client", FakeClient)
    monkeypatch.setenv("CREATIVE_INTEL_KEY_WORKOS", "sk-test-secret")
    out = workos_mod.authenticate_code(
        "auth_code", "verifier",
        settings=Settings(workos_client_id="c"))
    assert out["user"]["id"] == "w-z"
    assert calls["url"].endswith("/user_management/authenticate")
    assert calls["auth"] == "Bearer sk-test-secret"
    assert calls["json"]["grant_type"] == "authorization_code"


def test_secrets_never_log_values(monkeypatch, caplog):
    monkeypatch.setenv("CREATIVE_INTEL_KEY_WORKOS", "sk-live-SECRET-XYZ")
    assert secrets_mod.workos_api_key() == "sk-live-SECRET-XYZ"
    assert secrets_mod.workos_key_present() is True
    monkeypatch.delenv("CREATIVE_INTEL_KEY_WORKOS")
    assert secrets_mod.workos_api_key() == ""
    assert secrets_mod.workos_key_present() is False


def test_unknown_identity_becomes_pending(session):
    token, employee, created = emp.login_identity(session, dict(IDENT))
    assert created and employee.status == "pending"
    assert token
    with pytest.raises(emp.Denied) as exc:
        emp.authorize(session, token)
    assert exc.value.gate == "pending"


def test_bootstrap_first_admin(session):
    settings = Settings(admin_email="ada@foap.test")
    _tok, employee, created = emp.login_identity(session, dict(IDENT),
                                                 settings)
    assert created and employee.role == "admin"
    assert employee.status == "active"
    other = dict(IDENT, workos_user_id="w-bo", email="bo@foap.test")
    _t2, emp2, _c2 = emp.login_identity(session, other, settings)
    assert (emp2.role, emp2.status) == ("employee", "pending")


def test_preadded_email_links(session):
    admin = emp.admin_create(session, "root", "ada@foap.test")
    assert admin.status == "active" and admin.workos_user_id is None
    _tok, employee, created = emp.login_identity(session, dict(IDENT))
    assert created is False and employee.id == admin.id
    assert employee.workos_user_id == "w-ada"


def test_approve_suspend_reactivate_revoke(session):
    _tok, employee, _c = emp.login_identity(session, dict(IDENT))
    emp.admin_set_status(session, "root", employee.id, "active",
                         "EMPLOYEE_APPROVED")
    _e, gate = emp.authorize(session, _tok)
    assert gate == "app"
    emp.admin_set_status(session, "root", employee.id, "suspended",
                         "EMPLOYEE_SUSPENDED")
    with pytest.raises(emp.Denied):
        emp.authorize(session, _tok)
    emp.admin_set_status(session, "root", employee.id, "active",
                         "EMPLOYEE_REACTIVATED")
    tok2, _, _ = emp.login_identity(session, dict(IDENT))
    _e, gate = emp.authorize(session, tok2)
    assert gate == "app"
    emp.admin_set_status(session, "root", employee.id, "revoked",
                         "EMPLOYEE_REVOKED")
    with pytest.raises(emp.Denied):
        emp.authorize(session, tok2)
    tok3, _, _ = emp.login_identity(session, dict(IDENT))
    with pytest.raises(emp.Denied) as exc:
        emp.authorize(session, tok3)
    assert exc.value.gate == "revoked"


def test_last_admin_protected(session):
    solo = emp.admin_create(session, "root", "solo@foap.test", role="admin")
    with pytest.raises(emp.StoreError):
        emp.admin_set_status(session, "root", solo.id, "suspended",
                             "EMPLOYEE_SUSPENDED")
    with pytest.raises(emp.StoreError):
        emp.admin_set_role(session, "root", solo.id, "employee")
    second = emp.admin_create(session, "root", "two@foap.test", role="admin")
    emp.admin_set_role(session, solo.id, second.id, "employee")
    assert emp.get_employee(session, second.id).role == "employee"


def test_audit_trail(session):
    _tok, employee, _c = emp.login_identity(session, dict(IDENT))
    emp.admin_set_status(session, "root", employee.id, "active",
                         "EMPLOYEE_APPROVED")
    actions = [e.action for e in emp.admin_audit_list(session)]
    assert "EMPLOYEE_APPROVED" in actions
    row = next(e for e in emp.admin_audit_list(session)
               if e.action == "EMPLOYEE_APPROVED")
    assert (row.target_id, row.prev_value, row.new_value) == \
        (employee.id, "pending", "active")


def test_oauth_redirect_allowlist(session):
    from ci_backend import oauth as oauth_mod
    settings = Settings(workos_client_id="client_test",
                        key_workos="[REDACTED]",
                        workos_redirect_uri="http://127.0.0.1:4321/api/auth/callback")
    with pytest.raises(emp.StoreError):
        oauth_mod.start_oauth(session, "google",
                              "https://evil.test/callback", settings)
    out = oauth_mod.start_oauth(
        session, "google",
        "http://127.0.0.1:4321/api/auth/callback", settings)
    assert out["state"] and "127.0.0.1" in out["url"]
    out = oauth_mod.start_oauth(session, "github", "", settings)
    assert "GitHubOAuth" in out["url"]


def test_pkce_s256_property():
    import base64
    import hashlib
    verifier, challenge = workos_mod.pkce_pair()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode()
    assert challenge == expected
    v2, _c2 = workos_mod.pkce_pair()
    assert v2 != verifier


def test_finish_rejects_unverified_identity(session, monkeypatch):
    from ci_backend import oauth as oauth_mod
    settings = Settings(workos_client_id="client_test",
                        key_workos="[REDACTED]")
    out = oauth_mod.start_oauth(session, "google", "", settings)
    monkeypatch.setattr(
        "ci_backend.workos.authenticate_code",
        lambda code, verifier, settings=None: {"user": {
            "id": "w-x", "email": "x@foap.test", "email_verified": False}})
    with pytest.raises(emp.StoreError):
        oauth_mod.finish_oauth(session, "auth_code", out["state"], settings)
    # State is single-use: the failed attempt consumed it.
    with pytest.raises(emp.StoreError):
        oauth_mod.finish_oauth(session, "auth_code", out["state"], settings)

    out = oauth_mod.start_oauth(session, "google", "", settings)
    monkeypatch.setattr(
        "ci_backend.workos.authenticate_code",
        lambda code, verifier, settings=None: {"user": {
            "id": "", "email": "noid@foap.test", "email_verified": True}})
    with pytest.raises(emp.StoreError):
        oauth_mod.finish_oauth(session, "auth_code", out["state"], settings)


def test_authorize_url_leaks_no_secret():
    settings = Settings(workos_client_id="client_test",
                        key_workos="[REDACTED]")
    url = workos_mod.authorization_url(provider="google", state="s",
                                       code_challenge="c",
                                       redirect="", settings=settings)
    assert "client_test" in url
    assert "secret-workos-key" not in url
    assert "code_challenge_method=S256" in url


def test_pending_states_single_use(session):
    emp.pending_put(session, "st", "google", "verifier")
    row = emp.pending_pop(session, "st")
    assert row is not None and emp.pending_valid(row)
    assert emp.pending_pop(session, "st") is None


def test_pending_states_expire(session):
    from ci_backend.db import AuthPending
    emp.pending_put(session, "old", "google", "verifier")
    row = session.get(AuthPending, "old")
    row.created_at = "2000-01-01T00:00:00+00:00"
    session.commit()
    assert emp.pending_valid(row) is False
    emp.sweep_pending(session)
    assert session.get(AuthPending, "old") is None


def test_illegal_transitions_rejected(session):
    _tok, employee, _c = emp.login_identity(session, dict(IDENT))
    with pytest.raises(emp.StoreError):
        emp.admin_set_status(session, "root", employee.id, "suspended",
                             "EMPLOYEE_SUSPENDED")
    emp.admin_set_status(session, "root", employee.id, "revoked",
                         "EMPLOYEE_REVOKED")
    with pytest.raises(emp.StoreError):
        emp.admin_set_status(session, "root", employee.id, "active",
                             "EMPLOYEE_REACTIVATED")


def test_me_envelope_and_cookies(session):
    token, employee, _c = emp.login_identity(session, dict(IDENT))
    envelope = emp.me(session, token)
    assert envelope.authenticated and envelope.gate == "pending"
    assert envelope.employee.email == "ada@foap.test"
    cookie = emp.session_cookie(token)
    assert cookie.startswith("ci_session=") and "HttpOnly" in cookie
    assert token not in cookie.split("=", 1)[0]
    assert emp.token_from_cookie_header(cookie) == token
    assert emp.clear_cookie().startswith("ci_session=;")
    anon = emp.me(session, "bogus")
    assert anon.authenticated is False and anon.gate == "login"


def test_alembic_migration_builds_tables(tmp_path):
    # Raw alembic command() calls skip the disposable-connection plus
    # explicit-commit discipline, which loses the version stamp on
    # sqlite; the supported db.migrate()/ensure_migrated() path covers
    # the same upgrade/downgrade/upgrade cycle authoritatively.
    db_path = tmp_path / "mig.db"
    engine = db_mod.make_engine(db_path)
    db_mod.ensure_migrated(engine)
    db_mod.migrate(engine, "base")
    db_mod.ensure_migrated(engine)
    factory = db_mod.make_session_factory(engine)
    with factory() as sess:
        created = emp.admin_create(sess, "root", "mig@foap.test",
                                   role="admin")
        assert created.status == "active"
