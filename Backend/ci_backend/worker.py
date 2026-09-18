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
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from creative_intel import jobs, schema  # noqa: E402

from ci_backend import worker_handlers  # noqa: E402
from ci_backend.config import Settings  # noqa: E402


def _connect(db_path):
    conn = sqlite3.connect(db_path, timeout=30.0)
    schema.init_db(conn)
    return conn


def _heartbeat_loop(db_path, job_id, run_token, stop):
    """Renew the attempt lease while the handler runs (A12).

    A live worker keeps prolonging its lease so boot recovery never
    mistakes it for dead; a dead worker stops renewing and its job
    becomes requeueable once the lease lapses.
    """
    while not stop.wait(jobs.LEASE_S / 3.0):
        try:
            conn = sqlite3.connect(db_path, timeout=30.0)
            try:
                alive = jobs.heartbeat(conn, job_id, run_token)
            finally:
                conn.close()
        except Exception:  # noqa: BLE001 - renewal is best-effort
            alive = True
        if not alive:
            print("job %s lease lost; completion will be fenced"
                  % (job_id,), flush=True)
            return


def run_once(db_path, settings, media_dir=None):
    """Claim and run a single job; returns True when work was done."""
    conn = _connect(db_path)
    try:
        job = jobs.claim(conn, lease_owner="worker")
        if job is None:
            return False
        token = job.get("run_token")
        ctx = {"settings": settings, "media_dir": media_dir}
        stop = threading.Event()
        pulse = threading.Thread(target=_heartbeat_loop,
                                 args=(db_path, job["id"], token, stop),
                                 daemon=True)
        pulse.start()
        try:
            result = worker_handlers.run(conn, job["kind"],
                                         job.get("payload") or {},
                                         job.get("owner_employee_id") or "",
                                         ctx, job["id"])
        except jobs.JobCancelled:
            # Owner cancelled mid-run: keep the cancelled state, never a
            # failure. In-flight provider work already stopped chaining.
            jobs.cancel(conn, job["id"])
            print("job %s (%s) cancelled" % (job["id"], job["kind"]),
                  flush=True)
            return True
        except Exception as exc:  # noqa: BLE001 - recorded on the job
            jobs.fail(conn, job["id"], exc, run_token=token)
            print("job %s (%s) failed: %s" % (job["id"], job["kind"], exc),
                  flush=True)
            return True
        finally:
            stop.set()
        jobs.complete(conn, job["id"], result, run_token=token)
        print("job %s (%s) completed" % (job["id"], job["kind"]), flush=True)
        return True
    finally:
        conn.close()


def daemon(db_path, settings, poll=5.0, stop=None):
    """Run the claim-and-dispatch loop until stop is set. Lets a host
    process (e.g. the web app on single-service deploys) run the
    worker in-process instead of provisioning a second service."""
    import threading as _threading
    halt = stop or _threading.Event()
    try:
        conn = _connect(db_path)
        try:
            revived = jobs.requeue_interrupted(conn)
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - requeue must not kill boot
        print("worker requeue error: %s" % exc, flush=True)
        revived = 0
    if revived:
        print("requeued %d interrupted job(s)" % revived, flush=True)
    while not halt.is_set():
        try:
            did_work = run_once(db_path, settings)
        except Exception as exc:  # noqa: BLE001 - worker must not die
            print("worker loop error: %s" % exc, flush=True)
            did_work = False
        if not did_work:
            halt.wait(max(0.5, poll))


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
