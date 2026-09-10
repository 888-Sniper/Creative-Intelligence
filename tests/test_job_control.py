"""Job cancellation + progress tests (pytest).

Cancellation is cooperative: handlers poll the job row at stage
boundaries and raise JobCancelled, which the worker and the inline
fallback translate to a lasting cancelled state — never a failure.
Progress is reported through the same boundaries.
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import worker as worker_mod  # noqa: E402
from ci_backend import worker_handlers  # noqa: E402
from creative_intel import jobs as jobs_mod  # noqa: E402


def make_conn(path=":memory:"):
    conn = sqlite3.connect(path, check_same_thread=False)
    jobs_mod.ensure(conn)
    return conn


def test_cancelled_pipeline_stops_before_work():
    conn = make_conn()
    job = jobs_mod.enqueue(conn, "pipeline",
                           {"creative_key": "never-touched"}, owner="o")
    assert jobs_mod.claim(conn, job["id"]) is not None
    jobs_mod.cancel(conn, job["id"])
    with pytest.raises(jobs_mod.JobCancelled):
        worker_handlers.run(conn, "pipeline",
                            {"creative_key": "never-touched"},
                            "o", {}, job["id"])
    row = jobs_mod.get(conn, job["id"])
    assert row["status"] == "cancelled"
    assert row["error"] == ""
    conn.close()


def test_ask_reports_progress_marks():
    from creative_intel import schema as schema_mod

    conn = make_conn()
    schema_mod.init_db(conn)
    job = jobs_mod.enqueue(conn, "ask", {"question": "hi"}, owner="o")
    assert jobs_mod.claim(conn, job["id"]) is not None
    out = worker_handlers.run(conn, "ask", {"question": "hi"},
                              "o", {}, job["id"])
    assert isinstance(out, dict)
    assert jobs_mod.get(conn, job["id"])["progress"] == 90
    conn.close()


def test_worker_keeps_midrun_cancellation(tmp_path, monkeypatch):
    db = str(tmp_path / "jobs.db")

    def stub(conn, payload, owner, ctx, job_id):
        jobs_mod.cancel(conn, job_id)
        raise jobs_mod.JobCancelled("stop here")

    monkeypatch.setitem(worker_handlers.HANDLERS, "pipeline", stub)
    conn = make_conn(db)
    job = jobs_mod.enqueue(conn, "pipeline", {"creative_key": "k"},
                           owner="o")
    conn.close()
    from ci_backend.config import Settings
    assert worker_mod.run_once(db, Settings()) is True
    conn = make_conn(db)
    row = jobs_mod.get(conn, job["id"])
    assert row["status"] == "cancelled"
    assert row["error"] == ""
    conn.close()
    assert job["id"]


def test_run_through_maps_cancellation_to_failed_cancelled(monkeypatch):
    conn = make_conn()

    def stub(conn, kind, payload, owner, ctx, job_id):
        raise jobs_mod.JobCancelled("stop here")

    monkeypatch.setattr(worker_handlers, "run", stub)
    with pytest.raises(jobs_mod.JobFailed) as exc:
        jobs_mod.run_through(conn, "ask", {"question": "hi"}, owner="o",
                             timeout_s=10.0, inline_grace_s=0)
    assert "cancelled" in str(exc.value)
    rows = conn.execute(
        "SELECT status FROM worker_jobs").fetchall()
    assert rows and all(r[0] == "cancelled" for r in rows)
    conn.close()
