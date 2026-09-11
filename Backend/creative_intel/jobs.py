"""Persistent background jobs (P0 production worker).

The in-process threadpool loses tasks when Uvicorn restarts. Jobs
recorded here survive crashes: queued work waits, interrupted running
work is requeued on boot, and owners can poll progress. A separate
bounded worker service (`ci_backend/worker.py`, one job at a time)
claims jobs; HTTP handlers never run provider work inline when a
worker is available, and fall back to in-process execution only when
no worker claims the job (tests, single-process dev).
"""

from __future__ import annotations

import datetime
import json
import sqlite3
import time
import uuid

STATUSES = ("queued", "running", "completed", "failed", "cancelled")
TERMINAL = ("completed", "failed", "cancelled")

DDL = """
CREATE TABLE IF NOT EXISTS worker_jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    owner_employee_id TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT '',
    run_token TEXT NOT NULL DEFAULT '',
    lease_owner TEXT NOT NULL DEFAULT '',
    lease_expires_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS worker_jobs_status ON worker_jobs (status);
CREATE INDEX IF NOT EXISTS worker_jobs_owner ON worker_jobs (owner_employee_id);
"""

# A12: execution fencing. Every claim mints a run_token + lease; only
# the holder may complete/fail/prolong, and boot recovery requeues
# solely leases that are genuinely stale. Without this a web restart
# duplicates a still-running worker's job, and the original execution
# can then complete the replacement attempt.
LEASE_COLUMNS = (("run_token", "TEXT"), ("lease_owner", "TEXT"),
                 ("lease_expires_at", "TEXT"))
LEASE_S = 300.0


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def ensure(conn) -> None:
    conn.executescript(DDL)
    cols = {r[1] for r in
            conn.execute("PRAGMA table_info(worker_jobs)").fetchall()}
    for name, ctype in LEASE_COLUMNS:
        if name not in cols:
            conn.execute("ALTER TABLE worker_jobs ADD COLUMN %s %s"
                         " NOT NULL DEFAULT ''" % (name, ctype))
    conn.commit()


def _row_to_dict(row):
    if row is None:
        return None
    out = dict(row)
    for key in ("payload", "result"):
        raw = out.pop(key + "_json", "{}")
        try:
            out[key] = json.loads(raw or "{}")
        except ValueError:
            out[key] = {}
    return out


def enqueue(conn, kind, payload=None, owner="", max_retries=1):
    """Record a queued job; returns its public dict."""
    ensure(conn)
    job_id = uuid.uuid4().hex
    now = utcnow()
    conn.execute(
        "INSERT INTO worker_jobs (id, kind, status, payload_json,"
        " owner_employee_id, max_retries, created_at, updated_at)"
        " VALUES (?, ?, 'queued', ?, ?, ?, ?, ?)",
        (job_id, kind, json.dumps(payload or {}), owner, max_retries, now,
         now))
    conn.commit()
    return get(conn, job_id)


def get(conn, job_id):
    ensure(conn)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM worker_jobs WHERE id=?",
                           (job_id,)).fetchone()
    finally:
        conn.row_factory = None
    return _row_to_dict(row)


def list_for_owner(conn, owner, limit=50):
    ensure(conn)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM worker_jobs WHERE owner_employee_id=?"
            " ORDER BY created_at DESC LIMIT ?", (owner, limit)).fetchall()
    finally:
        conn.row_factory = None
    return [_row_to_dict(r) for r in rows]


def _lease_until(lease_s):
    return (datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=max(1.0, lease_s))).isoformat()


def claim(conn, job_id=None, lease_owner="", lease_s=LEASE_S):
    """Atomically move one queued job (or the given id) to running.

    Mints the execution fence (run_token + lease): only the holder
    may complete/fail/heartbeat this attempt.
    """
    ensure(conn)
    if job_id is None:
        row = conn.execute(
            "SELECT id FROM worker_jobs WHERE status='queued'"
            " ORDER BY created_at LIMIT 1").fetchone()
        if row is None:
            return None
        job_id = row[0]
    now = utcnow()
    token = uuid.uuid4().hex
    cur = conn.execute(
        "UPDATE worker_jobs SET status='running', started_at=?,"
        " attempts=attempts+1, updated_at=?, run_token=?,"
        " lease_owner=?, lease_expires_at=?"
        " WHERE id=? AND status='queued'",
        (now, now, token, lease_owner or "", _lease_until(lease_s),
         job_id))
    conn.commit()
    if cur.rowcount != 1:
        return None
    return get(conn, job_id)


def heartbeat(conn, job_id, run_token, lease_s=LEASE_S):
    """Renew a live attempt's lease; False when fenced out (stale)."""
    ensure(conn)
    cur = conn.execute(
        "UPDATE worker_jobs SET lease_expires_at=?, updated_at=?"
        " WHERE id=? AND status='running' AND run_token=?"
        " AND run_token != ''",
        (_lease_until(lease_s), utcnow(), job_id, run_token or ""))
    conn.commit()
    return cur.rowcount == 1


def set_progress(conn, job_id, progress):
    ensure(conn)
    conn.execute("UPDATE worker_jobs SET progress=?, updated_at=?"
                 " WHERE id=? AND status='running'",
                 (max(0, min(100, int(progress))), utcnow(), job_id))
    conn.commit()


def _holds_fence(job, run_token):
    # Rows minted before leases (or test rows without a claim) carry
    # no token and stay governable; otherwise the caller must present
    # the attempt's token or the write is a stale execution's.
    if job is None or job["status"] != "running":
        return False
    if not job.get("run_token"):
        return True
    return bool(run_token) and run_token == job["run_token"]


def complete(conn, job_id, result=None, run_token=None):
    """Complete a running attempt; stale tokens are ignored (A12).

    The fence lives in the UPDATE itself, so a superseded execution
    cannot slip between the read and the write.
    """
    ensure(conn)
    now = utcnow()
    cur = conn.execute(
        "UPDATE worker_jobs SET status='completed', progress=100,"
        " result_json=?, finished_at=?, updated_at=?,"
        " run_token='', lease_owner='', lease_expires_at=''"
        " WHERE id=? AND status='running'"
        " AND (run_token='' OR run_token=?)",
        (json.dumps(result or {}), now, now, job_id, run_token or ""))
    conn.commit()
    if cur.rowcount != 1:
        return get(conn, job_id)
    return get(conn, job_id)


def fail(conn, job_id, error, run_token=None):
    """Record failure; requeues while attempts remain, else terminal.

    Stale tokens are ignored so a superseded execution cannot fail
    the replacement attempt (A12).
    """
    ensure(conn)
    job = get(conn, job_id)
    if not _holds_fence(job, run_token):
        return job
    now = utcnow()
    fence = " AND (run_token='' OR run_token=?)"
    fence_arg = run_token or ""
    if job["attempts"] <= max(0, job["max_retries"]):
        conn.execute("UPDATE worker_jobs SET status='queued', error=?,"
                     " started_at='', updated_at=?, run_token='',"
                     " lease_owner='', lease_expires_at='' WHERE id=?"
                     + fence,
                     (str(error or "")[:500], now, job_id, fence_arg))
    else:
        conn.execute("UPDATE worker_jobs SET status='failed', error=?,"
                     " finished_at=?, updated_at=? WHERE id=?" + fence,
                     (str(error or "")[:500], now, now, job_id, fence_arg))
    conn.commit()
    return get(conn, job_id)


def cancel(conn, job_id, owner=""):
    """Owner (or admin via empty owner check upstream) cancels queued work."""
    ensure(conn)
    job = get(conn, job_id)
    if job is None:
        return None
    if owner and job["owner_employee_id"] != owner:
        return None
    if job["status"] not in ("queued", "running"):
        return job
    now = utcnow()
    conn.execute("UPDATE worker_jobs SET status='cancelled', finished_at=?,"
                 " updated_at=? WHERE id=?", (now, now, job_id))
    conn.commit()
    return get(conn, job_id)


def requeue_interrupted(conn):
    """Boot recovery: requeue only genuinely stale leases (A12).

    A running job whose lease is still fresh belongs to a live
    worker (e.g. the web restarted but the worker service kept
    running) and must NOT be duplicated. Lease-less rows predate
    fencing and are treated as interrupted.
    """
    ensure(conn)
    now = utcnow()
    cur = conn.execute(
        "UPDATE worker_jobs SET status='queued',"
        " error='interrupted by restart', started_at='', updated_at=?,"
        " run_token='', lease_owner='', lease_expires_at=''"
        " WHERE status='running'"
        " AND (lease_expires_at='' OR lease_expires_at <= ?)", (now, now))
    conn.commit()
    return cur.rowcount


class JobFailed(Exception):
    pass


class JobCancelled(Exception):
    """Cooperative cancellation: the owner cancelled mid-run.

    Handlers raise this at stage boundaries when the job row reads
    cancelled. It is never recorded as a failure: the job stays
    cancelled and partially completed provider work is simply dropped.
    """


class JobTimeout(Exception):
    pass


def run_through(conn, kind, payload, owner="", timeout_s=180.0,
                inline_grace_s=2.0, ctx=None):
    """Enqueue work, then wait for the worker; run inline if none comes.

    Returns the job's result dict. Raises JobFailed on error/cancel and
    JobTimeout when nobody completes the work in time. The inline
    fallback keeps single-process deployments and tests working; with
    the worker service running, jobs complete there first.
    """
    from ci_backend import worker_handlers  # local import: no cycle at import

    job = enqueue(conn, kind, payload, owner)
    job_id = job["id"]
    deadline = time.monotonic() + timeout_s
    inline_at = time.monotonic() + inline_grace_s
    while True:
        row = get(conn, job_id)
        if row is None:
            raise JobFailed("job vanished")
        if row["status"] == "completed":
            return row["result"]
        if row["status"] in ("failed", "cancelled"):
            raise JobFailed(row["error"] or row["status"])
        now = time.monotonic()
        # Inline fallback honors the same retry budget as the worker:
        # requeued work (attempts still within max_retries) may run
        # inline again instead of polling to a misleading JobTimeout.
        # fail() parks the job terminal once attempts run out, so the
        # real error surfaces via JobFailed above.
        budget = max(0, row.get("max_retries", 1))
        claimed = None
        if (now >= inline_at and row["status"] == "queued"
                and row.get("attempts", 0) <= budget):
            claimed = claim(conn, job_id, lease_owner="inline")
        if claimed:
            token = claimed.get("run_token")
            try:
                result = worker_handlers.run(conn, kind, payload, owner,
                                             ctx or {}, job_id)
            except JobCancelled:
                cancel(conn, job_id)
                raise JobFailed("cancelled")
            except Exception as exc:  # noqa: BLE001 - recorded, not raised raw
                fail(conn, job_id, exc, run_token=token)
                continue
            complete(conn, job_id, result, run_token=token)
            continue
        if now >= deadline:
            raise JobTimeout("job %s did not complete in %.0fs"
                             % (job_id, timeout_s))
        time.sleep(0.2)
