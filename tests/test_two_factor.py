"""Authenticator two-factor: setup, confirm, sign-in challenge, disable.

The authenticator math is local. No network and no keychain: the
master key is the committed test fixture.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import employees as emp_store  # noqa: E402
from ci_backend import oauth as oauth_mod  # noqa: E402
from ci_backend import totp as totp_mod  # noqa: E402
from ci_backend.app import create_app  # noqa: E402
from ci_backend.config import Settings  # noqa: E402
from ci_backend.db import make_engine, make_session_factory  # noqa: E402

TEST_MASTER_KEY = "r6I4teiO8U9i7HlJkR4tLghv5kqp69HfLWMcczM8UUs="

IDENT = {"id": "w-ada", "email": "ada@foap.test", "email_verified": True,
         "first_name": "Ada", "last_name": "L", "profile_picture_url": ""}


@pytest.fixture()
def http(tmp_path):
    db_path = str(tmp_path / "totp.db")
    settings = Settings(
        workos_client_id="client_test", key_workos="sk-test-key",
        master_key=TEST_MASTER_KEY, admin_email="ada@foap.test")
    app = create_app(db_path, settings)
    client = TestClient(app, raise_server_exceptions=False)
    yield client, db_path, settings


def _session(http, monkeypatch):
    def fake(code, verifier, settings=None):
        assert code == "auth_code"
        return {"user": dict(IDENT)}

    monkeypatch.setattr("ci_backend.workos.authenticate_code", fake)
    started = http.post("/api/auth/oauth/start", json={"provider": "google"})
    assert started.status_code == 200, started.text
    state = started.json()["state"]
    finished = http.post("/api/auth/oauth/finish",
                         json={"code": "auth_code", "state": state})
    assert finished.status_code == 200, finished.text
    assert finished.json()["gate"] == "app"
    return finished


def _code_for(secret: str) -> str:
    step = int(__import__("time").time()) // totp_mod.STEP_SECONDS
    return totp_mod._hotp(totp_mod._decode_b32(secret), step)


def test_recovery_code_opens_one_session_when_two_checks_overlap(
        tmp_path, monkeypatch):
    import datetime
    import json
    import threading

    from ci_backend import token_crypto
    from ci_backend.db import EmployeeTotp, TotpChallenge, init_db

    db_path = tmp_path / "race.db"
    settings = Settings(master_key=TEST_MASTER_KEY, admin_email="ada@foap.test")
    engine = make_engine(db_path)
    init_db(engine)
    factory = make_session_factory(engine)
    code = "ABCD-EFGH"
    token = "race-token"
    try:
        with factory() as sess:
            admin = emp_store.admin_create(
                sess, "root", "ada@foap.test", role="admin")
            now = totp_mod._now()
            sess.add(EmployeeTotp(
                employee_id=admin.id,
                secret_enc=token_crypto.encrypt_secret(
                    "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", settings),
                enabled=1,
                recovery_hashes=json.dumps([totp_mod._recovery_hash(code)]),
                last_step=0,
                updated_at=now.isoformat(timespec="seconds")))
            sess.add(TotpChallenge(
                token_hash=totp_mod._hash(token),
                employee_id=admin.id,
                attempts=0,
                created_at=now.isoformat(timespec="seconds"),
                expires_at=(now + datetime.timedelta(seconds=300)
                            ).isoformat(timespec="seconds")))
            sess.commit()
            employee_id = admin.id
        gate = threading.Barrier(2)
        real_hashes = totp_mod._hashes

        def wait_for_both(row):
            parsed = real_hashes(row)
            gate.wait(timeout=5)
            return parsed

        monkeypatch.setattr(totp_mod, "_hashes", wait_for_both)
        results = []

        def once():
            with factory() as sess:
                try:
                    employee = totp_mod.take_challenge(
                        sess, token, code, settings)
                    emp_store.create_session(
                        sess, employee.id, employee.workos_user_id or "")
                    results.append("ok")
                except emp_store.StoreError:
                    results.append("denied")
                except Exception as exc:  # noqa: BLE001 - the assertion prints it
                    results.append("%s: %s" % (type(exc).__name__, exc))

        threads = [threading.Thread(target=once), threading.Thread(target=once)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        assert results.count("ok") == 1, results
        assert results.count("denied") == 1, results
        with factory() as sess:
            assert emp_store.count_live_sessions(sess, employee_id) == 1
            row = sess.get(EmployeeTotp, employee_id)
            assert totp_mod._recovery_hash(code) not in (row.recovery_hashes or "")
    finally:
        engine.dispose()


def test_rfc_vector():
    # RFC 6238 appendix B, SHA1, the well-known 20-byte secret.
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp_mod.matching_step(secret, "287082", now=59) == 1
    assert totp_mod.matching_step(secret, "081804", now=1111111109) == 37037036


def test_setup_confirm_and_challenge(http, monkeypatch):
    client, db_path, settings = http
    _session(client, monkeypatch)
    assert client.get("/api/auth/2fa/status").json() == {"enabled": False}
    setup = client.post("/api/auth/2fa/setup")
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert secret not in setup.json()["otpauth_uri"] or "secret=" in setup.json()["otpauth_uri"]
    assert "otpauth://totp/" in setup.json()["otpauth_uri"]
    bad = client.post("/api/auth/2fa/confirm", json={"code": "000000"})
    assert bad.status_code == 409
    assert bad.json()["error"] == "That code is not valid."
    assert client.get("/api/auth/2fa/status").json()["enabled"] is False
    good = client.post("/api/auth/2fa/confirm", json={"code": _code_for(secret)})
    assert good.status_code == 200, good.text
    codes = good.json()["recovery_codes"]
    assert len(codes) == 8
    assert client.get("/api/auth/2fa/status").json() == {"enabled": True}
    # The secret and the recovery codes are not on the status payload.
    assert secret not in client.get("/api/auth/2fa/status").text
    assert codes[0] not in client.get("/api/auth/2fa/status").text

    client.post("/api/auth/logout")
    again = client.post("/api/auth/oauth/finish", json={
        "code": "auth_code",
        "state": client.post("/api/auth/oauth/start",
                             json={"provider": "google"}).json()["state"],
    })
    # The stub is still installed. Finish must not open a session.
    assert again.status_code == 200, again.text
    assert again.json()["gate"] == "mfa"
    assert again.json()["authenticated"] is False
    assert client.get("/api/auth/me").json()["authenticated"] is False

    wrong = client.post("/api/auth/2fa/verify", json={"code": "000000"})
    assert wrong.status_code == 409
    assert client.get("/api/auth/me").json()["authenticated"] is False
    # Confirm already spent this time step, so sign-in uses a recovery code.
    verified = client.post("/api/auth/2fa/verify", json={"code": codes[0]})
    assert verified.status_code == 200, verified.text
    assert verified.json()["gate"] == "app"
    assert client.get("/api/auth/me").json()["authenticated"] is True
    me = client.get("/api/auth/me").json()["employee"]
    engine = make_engine(db_path)
    try:
        with make_session_factory(engine)() as sess:
            from ci_backend.db import EmployeeTotp
            row = sess.get(EmployeeTotp, me["id"])
            row.last_step = 10 ** 12
            sess.commit()
    finally:
        engine.dispose()
    replay = client.post("/api/auth/2fa/disable", json={"code": _code_for(secret)})
    assert replay.status_code == 409

    off = client.post("/api/auth/2fa/disable", json={"code": codes[1]})
    assert off.status_code == 200, off.text
    assert off.json() == {"enabled": False}
    spent = client.post("/api/auth/2fa/setup")
    assert spent.status_code == 200
    # A spent recovery code must not confirm the new secret.
    reused = client.post("/api/auth/2fa/confirm", json={"code": codes[0]})
    assert reused.status_code == 409


def test_callback_redirects_to_the_challenge(http, monkeypatch):
    client, db_path, settings = http
    _session(client, monkeypatch)
    secret = client.post("/api/auth/2fa/setup").json()["secret"]
    assert client.post("/api/auth/2fa/confirm",
                       json={"code": _code_for(secret)}).status_code == 200
    client.post("/api/auth/logout")
    started = client.post("/api/auth/oauth/start", json={"provider": "google"})
    state = started.json()["state"]
    callback = client.get(
        "/api/auth/callback?code=auth_code&state=" + state,
        follow_redirects=False)
    assert callback.status_code == 302
    assert callback.headers["location"] == "/?mfa=1"
    cookie = callback.headers.get("set-cookie", "")
    assert "ci_2fa=" in cookie
    assert "ci_session=" not in cookie
    _ = db_path, settings


def test_open_login_skips_the_challenge_when_off(tmp_path):
    db_path = str(tmp_path / "plain.db")
    settings = Settings(master_key=TEST_MASTER_KEY, admin_email="ada@foap.test")
    app = create_app(db_path, settings)
    engine = make_engine(db_path)
    try:
        with make_session_factory(engine)() as sess:
            kind, _token, employee = oauth_mod.open_login(sess, {
                "workos_user_id": "w-ada", "email": "ada@foap.test",
                "verified": True, "provider": "email",
                "first_name": "Ada", "last_name": "L",
            }, settings)
            assert kind == "session"
            assert employee.email == "ada@foap.test"
            assert emp_store.count_live_sessions(sess, employee.id) == 1
    finally:
        engine.dispose()
        _ = app
