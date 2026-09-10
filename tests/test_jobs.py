"""Persistent background jobs: table ops, worker, HTTP job API."""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import worker  # noqa: E402
from ci_backend.config import Settings  # noqa: E402
from conftest import make_client, mint_admin  # noqa: E402
from creative_intel import jobs  # noqa: E402


def memdb():
    conn = sqlite3.connect(":memory:")
    jobs.ensure(conn)
    return conn


def test_enqueue_get_claim_complete():
    conn = memdb()
    job = jobs.enqueue(conn, "ask", {"q": "x"}, owner="e1")
    assert job["status"] == "queued"
    assert job["payload"] == {"q": "x"}
    claimed = jobs.claim(conn)
    assert claimed["id"] == job["id"]
    assert claimed["status"] == "running"
    assert claimed["attempts"] == 1
    assert jobs.claim(conn) is None
    done = jobs.complete(conn, job["id"], {"answer": "y"})
    assert done["status"] == "completed"
    assert done["progress"] == 100
    assert done["result"] == {"answer": "y"}
    conn.close()


def test_fail_retries_then_terminal():
    conn = memdb()
    job = jobs.enqueue(conn, "ask", {}, max_retries=1)
    jobs.claim(conn, job["id"])
    back = jobs.fail(conn, job["id"], "boom")
    assert back["status"] == "queued"  # attempts(1) <= max(1) -> retry
    jobs.claim(conn, job["id"])
    dead = jobs.fail(conn, job["id"], "boom again")
    assert dead["status"] == "failed"
    assert dead["error"] == "boom again"
    conn.close()


def test_cancel_owner_scoped():
    conn = memdb()
    job = jobs.enqueue(conn, "ask", {}, owner="e1")
    assert jobs.cancel(conn, job["id"], owner="e2") is None
    assert jobs.cancel(conn, job["id"], owner="e1")["status"] == "cancelled"
    conn.close()


def test_requeue_interrupted():
    conn = memdb()
    job = jobs.enqueue(conn, "ask", {})
    jobs.claim(conn, job["id"])
    assert jobs.requeue_interrupted(conn) == 1
    assert jobs.get(conn, job["id"])["status"] == "queued"
    conn.close()


def test_run_through_inline_without_worker():
    conn = sqlite3.connect(":memory:")
    from creative_intel import schema
    schema.init_db(conn)
    result = jobs.run_through(conn, "ask", {"question": "hi"}, owner="",
                              timeout_s=30.0, inline_grace_s=0.0, ctx={})
    assert "answer" in result
    conn.close()


def test_worker_once_unknown_kind_fails(tmp_path):
    db = str(tmp_path / "w.db")
    conn = sqlite3.connect(db)
    jobs.ensure(conn)
    jobs.enqueue(conn, "bogus", {}, max_retries=0)
    conn.close()
    assert worker.run_once(db, Settings()) is True
    conn = sqlite3.connect(db)
    try:
        row = jobs.list_for_owner(conn, "")
        assert row[0]["status"] == "failed"
        assert "unknown job kind" in row[0]["error"]
    finally:
        conn.close()


def test_worker_once_ask_completes(tmp_path):
    db = str(tmp_path / "w.db")
    conn = sqlite3.connect(db)
    from creative_intel import schema
    schema.init_db(conn)
    jobs.enqueue(conn, "ask", {"question": "hi"}, owner="e9")
    conn.close()
    assert worker.run_once(db, Settings()) is True
    conn = sqlite3.connect(db)
    try:
        row = jobs.list_for_owner(conn, "e9")
        assert row[0]["status"] == "completed"
    finally:
        conn.close()


def _admin(tmp_db):
    client = make_client(tmp_db)
    client.headers.update(mint_admin(tmp_db))
    return client


def test_pipeline_run_get_cancel(tmp_db):
    client = _admin(tmp_db)
    r = client.post("/api/pipeline/run", json={"creative_key": "  "})
    assert r.status_code == 409
    r = client.post("/api/pipeline/run", json={"creative_key": "a1"})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    r = client.get("/api/pipeline/jobs/%s" % job_id)
    assert r.status_code == 200
    assert r.json()["status"] in ("queued", "running")
    r = client.post("/api/pipeline/jobs/%s/cancel" % job_id)
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert client.get("/api/pipeline/jobs/nope").status_code == 404


def test_ai_endpoints_rate_limit_429(tmp_db):
    from ci_backend.deps import AI_RATE_LIMIT

    admin = _admin(tmp_db)
    codes = set()
    for _ in range(AI_RATE_LIMIT[0] + 2):
        r = admin.post("/api/pipeline/run", json={"creative_key": "a1"})
        codes.add(r.status_code)
    assert 429 in codes


def test_sync_actions_rate_limit_429(tmp_db):
    from ci_backend.deps import SYNC_RATE_LIMIT

    admin = _admin(tmp_db)
    codes = set()
    for _ in range(SYNC_RATE_LIMIT[0] + 2):
        r = admin.post("/api/sync/run", json={})
        codes.add(r.status_code)
    assert 429 in codes


def test_pipeline_job_owner_isolation(tmp_db):
    admin = _admin(tmp_db)
    r = admin.post("/api/pipeline/run", json={"creative_key": "a1"})
    job_id = r.json()["job_id"]
    other = make_client(tmp_db)
    assert other.get("/api/pipeline/jobs/%s" % job_id).status_code == 401


def test_pipeline_full_loop_through_worker(tmp_db):
    from ci_backend import worker as worker_mod

    admin = _admin(tmp_db)
    csv_text = ("Campaign,Ad Name,Creative Name,Amount Spent,Impressions,"
                "Link Clicks,Conversions\n"
                "Alpha,A1,hook-a,100,10000,200,10\n")
    r = admin.post("/api/ingest", json={"platform": "meta", "csv": csv_text})
    assert r.status_code == 200, r.text
    r = admin.post("/api/pipeline/run", json={"creative_key": "hook-a"})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    assert worker_mod.run_once(str(tmp_db), Settings()) is True
    r = admin.get("/api/pipeline/jobs/%s" % job_id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed"
    assert body["result"]["creative_key"] == "hook-a"
    assert body["result"]["stages"]
