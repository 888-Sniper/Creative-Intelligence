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
    finished_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS worker_jobs_status ON worker_jobs (status);
CREATE INDEX IF NOT EXISTS worker_jobs_owner ON worker_jobs (owner_employee_id);
"""


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def ensure(conn) -> None:
    conn.executescript(DDL)
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


def claim(conn, job_id=None):
    """Atomically move one queued job (or the given id) to running."""
    ensure(conn)
    if job_id is None:
        row = conn.execute(
            "SELECT id FROM worker_jobs WHERE status='queued'"
            " ORDER BY created_at LIMIT 1").fetchone()
        if row is None:
            return None
        job_id = row[0]
    now = utcnow()
    cur = conn.execute(
        "UPDATE worker_jobs SET status='running', started_at=?,"
        " attempts=attempts+1, updated_at=? WHERE id=? AND status='queued'",
        (now, now, job_id))
    conn.commit()
    if cur.rowcount != 1:
        return None
    return get(conn, job_id)


def set_progress(conn, job_id, progress):
    ensure(conn)
    conn.execute("UPDATE worker_jobs SET progress=?, updated_at=?"
                 " WHERE id=? AND status='running'",
                 (max(0, min(100, int(progress))), utcnow(), job_id))
    conn.commit()


def complete(conn, job_id, result=None):
    ensure(conn)
    now = utcnow()
    conn.execute("UPDATE worker_jobs SET status='completed', progress=100,"
                 " result_json=?, finished_at=?, updated_at=?"
                 " WHERE id=? AND status='running'",
                 (json.dumps(result or {}), now, now, job_id))
    conn.commit()
    return get(conn, job_id)


def fail(conn, job_id, error):
    """Record failure; requeues while attempts remain, else terminal."""
    ensure(conn)
    job = get(conn, job_id)
    if job is None or job["status"] != "running":
        return job
    now = utcnow()
    if job["attempts"] <= max(0, job["max_retries"]):
        conn.execute("UPDATE worker_jobs SET status='queued', error=?,"
                     " started_at='', updated_at=? WHERE id=?",
                     (str(error or "")[:500], now, job_id))
    else:
        conn.execute("UPDATE worker_jobs SET status='failed', error=?,"
                     " finished_at=?, updated_at=? WHERE id=?",
                     (str(error or "")[:500], now, now, job_id))
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
    """Boot recovery: work marked running by a dead process waits again."""
    ensure(conn)
    now = utcnow()
    cur = conn.execute(
        "UPDATE worker_jobs SET status='queued',"
        " error='interrupted by restart', started_at='', updated_at=?"
        " WHERE status='running'", (now,))
    conn.commit()
    return cur.rowcount


class JobFailed(Exception):
    pass


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
    ran_inline = False
    while True:
        row = get(conn, job_id)
        if row is None:
            raise JobFailed("job vanished")
        if row["status"] == "completed":
            return row["result"]
        if row["status"] in ("failed", "cancelled"):
            raise JobFailed(row["error"] or row["status"])
        now = time.monotonic()
        if (not ran_inline and now >= inline_at
                and row["status"] == "queued" and claim(conn, job_id)):
            ran_inline = True
            try:
                result = worker_handlers.run(conn, kind, payload, owner,
                                             ctx or {}, job_id)
            except Exception as exc:  # noqa: BLE001 - recorded, not raised raw
                fail(conn, job_id, exc)
                continue
            complete(conn, job_id, result)
            continue
        if now >= deadline:
            raise JobTimeout("job %s did not complete in %.0fs"
                             % (job_id, timeout_s))
        time.sleep(0.2)
