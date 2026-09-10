"""Product audit tests (pytest + TestClient).

Production writes (ask, pipeline runs, uploads, annotation checks,
sync starts, reports, connector changes) must leave an audit row with
request ID, employee ID, action, target, result and timestamp — and
must never persist payloads (question text, annotations, bytes) or
secrets. The audit trail is admin-visible at /api/admin/audit/product.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import employees as emp_store  # noqa: E402
from ci_backend.app import create_app  # noqa: E402
from ci_backend.config import Settings  # noqa: E402
from conftest import employee_session  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def make_owner(tmp_path, **settings_kw):
    db = str(tmp_path / "app.db")
    settings = Settings(workos_client_id="client_test",
                        key_workos="[REDACTED]", **settings_kw)
    app = create_app(db, settings)
    with employee_session(db) as sess:
        boss = emp_store.admin_create(sess, "root", "boss@foap.test",
                                      role="admin")
        cookie = "ci_session=" + emp_store.create_session(
            sess, boss.id, "")
        boss_id = boss.id
    http = TestClient(app, raise_server_exceptions=False)
    http.headers.update({"Cookie": cookie})
    return http, db, boss_id


def audit_rows(db):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(
            "SELECT request_id, employee_id, action, target, result,"
            " created_at FROM product_audit").fetchall()
    finally:
        conn.close()


def test_request_id_header(tmp_path):
    http, _db, _boss = make_owner(tmp_path)
    resp = http.get("/health")
    assert resp.status_code == 200
    rid = resp.headers.get("x-request-id", "")
    assert len(rid) == 16
    int(rid, 16)


def test_ask_audited_without_question_text(tmp_path):
    http, db, boss_id = make_owner(tmp_path)
    resp = http.post("/api/ask", json={"question": "stats-secret-xyz"})
    assert resp.status_code == 200, resp.text
    rows = audit_rows(db)
    assert len(rows) == 1
    rid, employee, action, target, result, _ts = rows[0]
    assert action == "ask"
    assert employee == boss_id
    assert result == "ok"
    assert rid == resp.headers["x-request-id"]
    assert "stats-secret-xyz" not in repr(rows)


def test_pipeline_run_audited_as_queued(tmp_path):
    http, db, boss_id = make_owner(tmp_path)
    resp = http.post("/api/pipeline/run", json={"creative_key": "k1"})
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]
    rows = audit_rows(db)
    assert [(r[2], r[3], r[4]) for r in rows] == [
        ("pipeline_run", job_id, "queued")]
    assert rows[0][1] == boss_id
    assert rows[0][0] == resp.headers["x-request-id"]


def test_sync_create_and_run_audited(tmp_path, monkeypatch):
    import creative_intel.sync as sync_mod
    monkeypatch.setattr(sync_mod, "fetch_job",
                        lambda source, params, **kw: ([], []))
    http, db, _boss = make_owner(tmp_path)
    resp = http.post("/api/sync/jobs",
                     json={"source": "meta", "name": "m", "params": {}})
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job"]["id"]
    resp = http.post("/api/sync/jobs/%s/run" % job_id)
    assert resp.status_code == 200, resp.text
    got = {(r[2], r[3], r[4]) for r in audit_rows(db)}
    assert ("sync_job_created", job_id, "ok") in got
    assert ("sync_started", job_id, "ok") in got


def test_upload_audited_without_bytes(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_INTEL_MEDIA_DIR",
                       str(tmp_path / "media"))
    http, db, _boss = make_owner(tmp_path)
    resp = http.post("/api/media/upload",
                     data={"creative_key": "m1"},
                     files={"file": ("spot.png", PNG, "image/png")})
    assert resp.status_code == 200, resp.text
    rows = audit_rows(db)
    assert [(r[2], r[3], r[4]) for r in rows] == [
        ("creative_uploaded", "m1", "ok")]
    assert PNG not in repr(rows).encode()


def test_reviews_mark_audited(tmp_path):
    from creative_intel import qa as qa_mod

    http, db, _boss = make_owner(tmp_path)
    conn = sqlite3.connect(db)
    qa_mod.ensure(conn)
    review_id = conn.execute(
        "INSERT INTO qa_reviews (ts, question, answer)"
        " VALUES ('t', 'q', 'a')").lastrowid
    conn.commit()
    conn.close()
    resp = http.post("/api/reviews/mark", json={"review_id": review_id})
    assert resp.status_code == 200, resp.text
    rows = audit_rows(db)
    assert [(r[2], r[3], r[4]) for r in rows] == [
        ("annotation_verified", str(review_id), "ok")]


def test_failed_verify_audited_as_error(tmp_path):
    http, db, _boss = make_owner(tmp_path)
    resp = http.post("/api/creatives/nope/verify", json={})
    assert resp.status_code == 409, resp.text
    rows = audit_rows(db)
    assert [(r[2], r[3], r[4]) for r in rows] == [
        ("annotation_verified", "nope", "error")]


def test_admin_product_audit_lists_rows(tmp_path):
    http, _db, _boss = make_owner(tmp_path)
    http.post("/api/ask", json={"question": "hi"})
    resp = http.get("/api/admin/audit/product")
    assert resp.status_code == 200, resp.text
    events = resp.json()["events"]
    assert any(e["action"] == "ask" and e["result"] == "ok"
               for e in events)
    event = next(e for e in events if e["action"] == "ask")
    assert set(event) == {"id", "request_id", "employee_id", "action",
                          "target", "result", "created_at"}


def test_admin_product_audit_requires_admin(tmp_path):
    http, db, _boss = make_owner(tmp_path)
    with employee_session(db) as sess:
        staff = emp_store.admin_create(sess, "root", "staff@foap.test",
                                       role="employee")
        cookie = "ci_session=" + emp_store.create_session(
            sess, staff.id, "")
    staff_client = TestClient(http.app, raise_server_exceptions=False)
    staff_client.headers.update({"Cookie": cookie})
    resp = staff_client.get("/api/admin/audit/product")
    assert resp.status_code == 403
