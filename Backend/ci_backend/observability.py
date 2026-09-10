"""Production observability without sensitive data.

- JSON access log: one line per request (request ID, method, path,
  status, duration). Slow requests log at WARNING. The query string,
  headers, cookies and bodies are NEVER logged — OAuth codes, tokens
  and question text must not reach the logs.
- Ops summary: storage sizes, disk space, job durations/counts and
  recent sync failures for the authenticated admin endpoint, with
  plain-language warnings. Error strings are truncated metadata.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import shutil
import time

access_logger = logging.getLogger("ci.access")

DISK_FREE_WARN_BYTES = 1 * 1024 * 1024 * 1024
DB_SIZE_WARN_BYTES = 500 * 1024 * 1024
LOOKBACK_HOURS = 24


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _cutoff(hours: int = LOOKBACK_HOURS) -> str:
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=hours)).isoformat()


async def access_log_middleware(request, call_next):
    """Time the request and emit one JSON access line.

    Reads ``request.state.request_id`` set by the request-ID
    middleware (falls back to "-" when absent, e.g. in unit tests
    that bypass middleware). Only ``url.path`` is logged: the query
    string can carry OAuth codes and must never reach the logs.
    """
    settings = getattr(request.app.state, "ci_settings", None)
    if settings is not None and not getattr(settings, "access_log", True):
        return await call_next(request)
    slow_ms = getattr(settings, "slow_request_ms", 2000)
    if slow_ms is None:
        slow_ms = 2000
    start = time.perf_counter()
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception:
        status = 500
        raise
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
    rid = getattr(getattr(request, "state", None), "request_id", "") or "-"
    slow = duration_ms > slow_ms
    access_logger.log(
        logging.WARNING if slow else logging.INFO,
        json.dumps({
            "ts": _utcnow(), "request_id": rid,
            "method": request.method, "path": request.url.path,
            "status": status, "duration_ms": round(duration_ms, 1),
            "slow": slow}))
    return response


def _dir_bytes(path: str) -> int:
    total = 0
    if not path or not os.path.isdir(path):
        return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return total


def _parse_ts(raw: str):
    try:
        return datetime.datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None


def ops_summary(conn, *, db_path: str = "", media_dir: str = "",
                backup_dir: str = "") -> dict:
    """Storage + job + sync health for the admin ops endpoint."""
    from creative_intel import jobs as jobs_mod

    jobs_mod.ensure(conn)
    try:
        conn.execute("SELECT 1 FROM sync_runs LIMIT 1")
        has_runs = True
    except Exception:
        has_runs = False

    counts = {r[0]: r[1] for r in conn.execute(
        "SELECT status, COUNT(*) FROM worker_jobs GROUP BY status")}
    cutoff = _cutoff()
    failed_jobs = conn.execute(
        "SELECT COUNT(*) FROM worker_jobs"
        " WHERE status='failed' AND finished_at > ?", (cutoff,)).fetchone()
    failed_jobs = failed_jobs[0] if failed_jobs else 0
    durations = []
    for started, finished in conn.execute(
            "SELECT started_at, finished_at FROM worker_jobs"
            " WHERE status='completed' ORDER BY finished_at DESC LIMIT 50"):
        begin, end = _parse_ts(started), _parse_ts(finished)
        if begin is not None and end is not None and end >= begin:
            durations.append((end - begin).total_seconds())
    avg_duration = (round(sum(durations) / len(durations), 2)
                    if durations else None)

    failed_syncs = 0
    last_sync_error = ""
    if has_runs:
        row = conn.execute(
            "SELECT COUNT(*) FROM sync_runs"
            " WHERE status='error' AND started_at > ?",
            (cutoff,)).fetchone()
        failed_syncs = row[0] if row else 0
        err = conn.execute(
            "SELECT error FROM sync_runs WHERE status='error'"
            " ORDER BY started_at DESC LIMIT 1").fetchone()
        if err and err[0]:
            last_sync_error = str(err[0])[:200]

    db_bytes = 0
    if db_path and os.path.isfile(db_path):
        try:
            db_bytes = os.path.getsize(db_path)
        except OSError:
            db_bytes = 0
    media_bytes = _dir_bytes(media_dir)
    backup_bytes = _dir_bytes(backup_dir)
    anchor = (os.path.dirname(os.path.abspath(db_path))
              if db_path else (media_dir or backup_dir or "/tmp"))
    try:
        disk = shutil.disk_usage(anchor)
        disk_free, disk_total = disk.free, disk.total
    except OSError:
        disk_free, disk_total = 0, 0

    warnings = []
    if disk_total and disk_free < DISK_FREE_WARN_BYTES:
        warnings.append("disk free space is low (%d MB left)"
                        % (disk_free // (1024 * 1024)))
    if db_bytes > DB_SIZE_WARN_BYTES:
        warnings.append("database file exceeds %d MB"
                        % (DB_SIZE_WARN_BYTES // (1024 * 1024)))
    if failed_jobs:
        warnings.append("%d worker job(s) failed in the last %dh"
                        % (failed_jobs, LOOKBACK_HOURS))
    if failed_syncs:
        warnings.append("%d sync run(s) failed in the last %dh"
                        % (failed_syncs, LOOKBACK_HOURS))
    if counts.get("queued", 0) > 50:
        warnings.append("%d worker job(s) queued" % counts["queued"])
    return {
        "storage": {"db_bytes": db_bytes, "media_bytes": media_bytes,
                    "backup_bytes": backup_bytes,
                    "disk_free_bytes": disk_free,
                    "disk_total_bytes": disk_total},
        "jobs": {"by_status": counts, "failed_24h": failed_jobs,
                 "avg_completed_duration_s": avg_duration},
        "sync": {"failed_runs_24h": failed_syncs,
                 "last_error": last_sync_error},
        "warnings": warnings,
    }
