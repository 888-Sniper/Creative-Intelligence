"""Observability tests (pytest + TestClient).

JSON access log lines carry request ID/method/path/status/duration —
never query strings. Slow requests log at WARNING. The admin ops
endpoint reports storage, job durations and recent sync failures with
warnings, and refuses non-admins.
"""

import json
import logging
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import employees as emp_store  # noqa: E402
from ci_backend.app import create_app  # noqa: E402
from ci_backend.config import Settings  # noqa: E402
from ci_backend.db import make_engine, make_session_factory  # noqa: E402
from creative_intel import jobs as jobs_mod  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def make_clients(tmp_path, monkeypatch, **settings_kw):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    monkeypatch.setenv("CREATIVE_INTEL_MEDIA_DIR", str(media_dir))
    db = str(tmp_path / "app.db")
    settings = Settings(workos_client_id="client_test",
                        key_workos="[REDACTED]", **settings_kw)
    app = create_app(db, settings)
    engine = make_engine(db)
    with make_session_factory(engine)() as sess:
        boss = emp_store.admin_create(sess, "root", "boss@foap.test",
                                      role="admin")
        staff = emp_store.admin_create(sess, "root", "staff@foap.test",
                                       role="employee")
        boss_cookie = "ci_session=" + emp_store.create_session(
            sess, boss.id, "")
        staff_cookie = "ci_session=" + emp_store.create_session(
            sess, staff.id, "")

    def client_for(cookie):
        http = TestClient(app, raise_server_exceptions=False)
        http.headers.update({"Cookie": cookie})
        return http

    return client_for(boss_cookie), client_for(staff_cookie), db


def access_records(caplog):
    return [r for r in caplog.records if r.name == "ci.access"]


def test_access_log_hides_query_string(tmp_path, monkeypatch, caplog):
    admin, _staff, _db = make_clients(tmp_path, monkeypatch)
    with caplog.at_level(logging.INFO, logger="ci.access"):
        resp = admin.get("/health?code=supersecret-code&next=/")
    assert resp.status_code == 200
    records = access_records(caplog)
    assert records, "expected one JSON access line"
    line = json.loads(records[-1].getMessage())
    assert line["request_id"] == resp.headers["x-request-id"]
    assert line["method"] == "GET"
    assert line["path"] == "/health"
    assert line["status"] == 200
    assert "supersecret-code" not in records[-1].getMessage()


def test_slow_requests_log_at_warning(tmp_path, monkeypatch, caplog):
    admin, _staff, _db = make_clients(
        tmp_path, monkeypatch, slow_request_ms=0)
    with caplog.at_level(logging.INFO, logger="ci.access"):
        admin.get("/health")
    records = access_records(caplog)
    assert records and records[-1].levelno == logging.WARNING
    assert json.loads(records[-1].getMessage())["slow"] is True


def test_ops_endpoint_reports_storage_and_jobs(tmp_path, monkeypatch):
    admin, staff, db = make_clients(tmp_path, monkeypatch)
    conn = sqlite3.connect(db)
    job = jobs_mod.enqueue(conn, "pipeline", {"a": 1},
                           owner="someone", max_retries=0)
    assert jobs_mod.claim(conn, job["id"]) is not None
    jobs_mod.fail(conn, job["id"], "boom")
    conn.commit()
    conn.close()
    resp = admin.get("/api/admin/ops")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == {"storage", "jobs", "sync", "warnings"}
    assert body["storage"]["db_bytes"] > 0
    assert body["storage"]["disk_total_bytes"] > 0
    assert body["jobs"]["failed_24h"] == 1
    assert any("failed" in w for w in body["warnings"])
    assert staff.get("/api/admin/ops").status_code == 403
