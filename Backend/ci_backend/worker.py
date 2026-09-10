"""Standalone bounded worker service (P0 production jobs).

One job at a time, forever: claim the oldest queued worker job,
dispatch it, record completion or failure. Crash-safe: jobs left
running by a dead process are requeued at startup (retries honoured).

    python -m ci_backend.worker --db /var/lib/creative-intelligence/creative_intel.db

Runs under systemd as creative-intelligence-worker.service on Oracle.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from creative_intel import jobs, schema  # noqa: E402

from ci_backend import worker_handlers  # noqa: E402
from ci_backend.config import Settings  # noqa: E402


def _connect(db_path):
    conn = sqlite3.connect(db_path, timeout=30.0)
    schema.init_db(conn)
    return conn


def run_once(db_path, settings, media_dir=None):
    """Claim and run a single job; returns True when work was done."""
    conn = _connect(db_path)
    try:
        job = jobs.claim(conn)
        if job is None:
            return False
        ctx = {"settings": settings, "media_dir": media_dir}
        try:
            result = worker_handlers.run(conn, job["kind"],
                                         job.get("payload") or {},
                                         job.get("owner_employee_id") or "",
                                         ctx, job["id"])
        except Exception as exc:  # noqa: BLE001 - recorded on the job
            jobs.fail(conn, job["id"], exc)
            print("job %s (%s) failed: %s" % (job["id"], job["kind"], exc),
                  flush=True)
            return True
        jobs.complete(conn, job["id"], result)
        print("job %s (%s) completed" % (job["id"], job["kind"]), flush=True)
        return True
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="")
    ap.add_argument("--poll", type=float, default=5.0,
                    help="idle seconds between queue polls")
    ap.add_argument("--once", action="store_true",
                    help="run a single job then exit (tests/smoke)")
    args = ap.parse_args()

    settings = Settings()
    db_path = args.db or str(settings.database_path)
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    conn = _connect(db_path)
    try:
        revived = jobs.requeue_interrupted(conn)
    finally:
        conn.close()
    if revived:
        print("requeued %d interrupted job(s)" % revived, flush=True)

    print("worker up on %s (poll %.1fs)" % (db_path, args.poll), flush=True)
    while True:
        try:
            did_work = run_once(db_path, settings)
        except Exception as exc:  # noqa: BLE001 - worker must not die
            print("worker loop error: %s" % exc, flush=True)
            did_work = False
        if args.once:
            return
        if not did_work:
            time.sleep(max(0.5, args.poll))


if __name__ == "__main__":
    main()
