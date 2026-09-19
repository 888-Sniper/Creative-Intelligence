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
    done = jobs.complete(conn, job["id"], {"answer": "y"},
                         run_token=claimed["run_token"])
    assert done["status"] == "completed"
    assert done["progress"] == 100
    assert done["result"] == {"answer": "y"}
    conn.close()


def test_fail_retries_then_terminal():
    conn = memdb()
    job = jobs.enqueue(conn, "ask", {}, max_retries=1)
    first = jobs.claim(conn, job["id"])
    back = jobs.fail(conn, job["id"], "boom",
                     run_token=first["run_token"])
    assert back["status"] == "queued"  # attempts(1) <= max(1) -> retry
    second = jobs.claim(conn, job["id"])
    dead = jobs.fail(conn, job["id"], "boom again",
                     run_token=second["run_token"])
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
    # Fresh lease: the worker may be alive (web restarted alone) —
    # recovery must NOT duplicate it.
    assert jobs.requeue_interrupted(conn) == 0
    assert jobs.get(conn, job["id"])["status"] == "running"
    # Expired lease: the worker is dead — requeue exactly once.
    conn.execute("UPDATE worker_jobs SET lease_expires_at='2000-01-01T00:00:00+00:00'"
                 " WHERE id=?", (job["id"],))
    conn.commit()
    assert jobs.requeue_interrupted(conn) == 1
    assert jobs.get(conn, job["id"])["status"] == "queued"
    conn.close()


def test_stale_completion_rejected_after_recovery():
    # A12: web restarts, dead lease requeued, replacement attempt
    # claimed — the original execution's late complete/fail must be
    # ignored instead of settling the replacement attempt.
    conn = memdb()
    job = jobs.enqueue(conn, "ask", {}, max_retries=0)
    first = jobs.claim(conn, job["id"])
    conn.execute("UPDATE worker_jobs SET lease_expires_at='2000-01-01T00:00:00+00:00'"
                 " WHERE id=?", (job["id"],))
    conn.commit()
    assert jobs.requeue_interrupted(conn) == 1
    second = jobs.claim(conn, job["id"])
    assert second["run_token"] != first["run_token"]
    # Stale original execution tries to settle: both fenced out.
    stale_done = jobs.complete(conn, job["id"], {"answer": "stale"},
                               run_token=first["run_token"])
    assert stale_done["status"] == "running"
    stale_fail = jobs.fail(conn, job["id"], "stale boom",
                           run_token=first["run_token"])
    assert stale_fail["status"] == "running"
    # Current holder still settles normally.
    done = jobs.complete(conn, job["id"], {"answer": "fresh"},
                         run_token=second["run_token"])
    assert done["status"] == "completed"
    assert done["result"] == {"answer": "fresh"}
    conn.close()


def test_legacy_leaseless_row_recovers():
    # Rows minted before fencing carry no lease and are treated as
    # interrupted, so old databases still recover on upgrade.
    conn = memdb()
    job = jobs.enqueue(conn, "ask", {})
    conn.execute("UPDATE worker_jobs SET status='running', started_at='x'"
                 " WHERE id=?", (job["id"],))
    conn.commit()
    assert jobs.requeue_interrupted(conn) == 1
    conn.close()


def test_run_through_inline_without_worker():
    conn = sqlite3.connect(":memory:")
    from creative_intel import schema
    schema.init_db(conn)
    result = jobs.run_through(conn, "ask", {"question": "hi"}, owner="",
                              timeout_s=30.0, inline_grace_s=0.0, ctx={})
    assert "answer" in result
    conn.close()


def test_sync_job_update_delete_need_owner_or_admin(tmp_path):
    from conftest import make_client, mint_admin
    db = str(tmp_path / "o.db")
    owner = make_client(db)
    owner.headers.update(mint_admin(db, email="owner@foap.test",
                                    role="employee"))
    other = make_client(db)
    other.headers.update(mint_admin(db, email="other@foap.test",
                                    role="employee"))
    boss = make_client(db)
    boss.headers.update(mint_admin(db, email="boss@foap.test",
                                   role="admin"))
    r = owner.post("/api/sync/jobs", json={
        "source": "sheets", "name": "O",
        "params": {"url": "https://docs.google.com/x",
                   "google_auth": True}})
    assert r.status_code == 200, r.text
    job_id = r.json()["job"]["id"]
    # Another employee can neither re-target nor delete it.
    r = other.patch("/api/sync/jobs/%s" % job_id, json={
        "params": {"url": "https://evil.example/x"}})
    assert r.status_code == 403, r.text
    r = other.delete("/api/sync/jobs/%s" % job_id)
    assert r.status_code == 403, r.text
    # Owner and admin can.
    r = owner.patch("/api/sync/jobs/%s" % job_id,
                    json={"name": "O2"})
    assert r.status_code == 200, r.text
    r = boss.patch("/api/sync/jobs/%s" % job_id,
                   json={"name": "O3"})
    assert r.status_code == 200, r.text
    r = boss.delete("/api/sync/jobs/%s" % job_id)
    assert r.status_code == 200, r.text


def test_run_through_retries_inline_after_transient_failure():
    import ci_backend.worker_handlers as wh
    from creative_intel import schema
    calls = []
    real_run = wh.run

    def flaky(conn, kind, payload, owner, ctx, job_id, run_token=None):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("transient")
        return {"answer": "recovered"}

    wh.run = flaky
    conn = sqlite3.connect(":memory:")
    try:
        schema.init_db(conn)
        result = jobs.run_through(conn, "ask", {"question": "hi"}, owner="",
                                  timeout_s=30.0, inline_grace_s=0.0, ctx={})
        assert result == {"answer": "recovered"}
        assert len(calls) == 2
    finally:
        wh.run = real_run
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


def test_replay_skips_provider_backed_actions(tmp_path, monkeypatch):
    from creative_intel import replay, sync
    db = str(tmp_path / "r.db")
    http = _admin(db)
    seed = ("Campaign,Ad,Impressions,Clicks,Conversions\n"
            "C,A,100,5,1\n")
    r = http.post("/api/ingest", json={"platform": "meta", "csv": seed})
    assert r.status_code == 200, r.text
    conn = sqlite3.connect(db)
    try:
        replay.log(conn, "sync-now", {"source": "meta"})
    finally:
        conn.close()

    def _boom(source, params):
        raise AssertionError("replay must not call providers")

    monkeypatch.setattr(sync, "fetch_job", _boom)
    r = http.post("/api/replay/run")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["skipped_provider_actions"] == 1
    assert body["matches_live"] is True


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


def test_require_live_attempt_fails_closed():
    """Recheck defensive guard: a job-bound attempt must prove
    exists → running → claim-token match. Missing/unreadable rows,
    token mismatch, and non-running states all raise StaleAttempt;
    only the explicit job-less call skips the check."""
    conn = memdb()
    # Job-less dev/direct runs stay a separate explicit path.
    jobs.require_live_attempt(conn, None, None)
    jobs.require_live_attempt(conn, "", "")
    # Missing row refuses (no code path deletes rows, so
    # unestablishable ownership never publishes).
    try:
        jobs.require_live_attempt(conn, "ghost", "tok")
    except jobs.StaleAttempt:
        pass
    else:
        raise AssertionError("missing row must refuse")
    # Unreadable table refuses too.
    bare = sqlite3.connect(":memory:")
    try:
        jobs.require_live_attempt(bare, "ghost", "tok")
    except jobs.StaleAttempt:
        pass
    else:
        raise AssertionError("unreadable table must refuse")
    finally:
        bare.close()
    job = jobs.enqueue(conn, "ask", {}, owner="e1")
    claimed = jobs.claim(conn, job["id"], lease_owner="w1")
    token = claimed["run_token"]
    # Live attempt passes.
    jobs.require_live_attempt(conn, job["id"], token)
    # Another attempt's token refuses.
    try:
        jobs.require_live_attempt(conn, job["id"], "other-token")
    except jobs.StaleAttempt:
        pass
    else:
        raise AssertionError("token mismatch must refuse")
    # Owner cancel keeps the row under our token: the guard passes
    # so the cancellation path raises JobCancelled downstream.
    jobs.cancel(conn, job["id"])
    jobs.require_live_attempt(conn, job["id"], token)
    # Terminal states refuse even with the old token.
    conn.execute("UPDATE worker_jobs SET status='completed', run_token=''"
                 " WHERE id=?", (job["id"],))
    conn.commit()
    try:
        jobs.require_live_attempt(conn, job["id"], token)
    except jobs.StaleAttempt:
        pass
    else:
        raise AssertionError("completed job must refuse")
    conn.close()
