"""Scheduled sync runner: dedup/upsert imports with retry and status history.

Every connector import (manual or scheduled) funnels through
import_once(): fetch + parse, store via ingest.upsert_rows() so
re-imports update matching facts instead of duplicating them, and
record the outcome in sync_runs. Successful manual imports also save
their parameters as sync jobs, which the scheduler re-runs; run_once()
adds bounded retries with backoff for the unattended path.

Jobs are organisation assets with their own ids: several jobs may
share one source (Meta Account A, Meta Account B, ...). Only enabled
jobs run on tick(). The scheduler keeps running a job even if its
establishing employee is later suspended or revoked; ownership is
audit info, not an access switch.

All history is local SQLite; tokens stay in Keychain/env via
connectors. No threads are started here — the server owns the daemon
thread, and daemon()/tick() below are plain blocking calls.
"""

import datetime
import json
import sqlite3
import threading
import time
import uuid

MAX_ATTEMPTS = 3
RETRY_DELAYS_S = (2.0, 8.0)

SOURCES = ("meta", "tiktok", "sheets", "drive")


def utcnow():
    return datetime.datetime.now(
        datetime.timezone.utc).isoformat(timespec="seconds")


def _record_start(conn, source, job_id=""):
    try:
        cur = conn.execute(
            "INSERT INTO sync_runs (source, job_id, started_at, status,"
            " attempts) VALUES (?, ?, ?, 'running', 0)",
            (source, job_id or "", utcnow()))
    except Exception:
        # Pre-migration databases without the job_id column.
        cur = conn.execute(
            "INSERT INTO sync_runs (source, started_at, status, attempts)"
            " VALUES (?, ?, 'running', 0)", (source, utcnow()))
    conn.commit()
    return cur.lastrowid


def _record_finish(conn, run_id, status, inserted=0, updated=0,
                   quarantined=0, attempts=1, error=""):
    conn.execute(
        "UPDATE sync_runs SET finished_at=?, status=?, inserted=?,"
        " updated=?, quarantined=?, attempts=?, error=?"
        " WHERE id=?",
        (utcnow(), status, inserted, updated, quarantined, attempts,
         error or "", run_id))
    conn.commit()


def fetch_job(source, params, bearer=None):
    """Fetch + parse one stored job. Returns (rows, quarantined).

    Raises ValueError with a human-readable reason (missing token,
    unconnected Google OAuth, bad payload) — fail closed, never stub
    rows. Pass bearer="..." (a Google access token) for private
    Sheets/Drive files.
    """
    from creative_intel import connectors, ingest
    params = params or {}
    if source == "meta":
        text = connectors.meta_insights_csv(
            params.get("ad_account_id", ""), params.get("since", ""),
            params.get("until", ""))
        return ingest.parse_csv_report(text, "meta", "meta-api")
    if source == "tiktok":
        text = connectors.tiktok_report_csv(
            params.get("advertiser_id", ""), params.get("start_date", ""),
            params.get("end_date", ""))
        return ingest.parse_csv_report(text, "tiktok", "tiktok-api")
    if source == "sheets":
        if not params.get("platform"):
            raise ValueError("sheets import needs a platform")
        text = connectors.fetch_sheet_csv(params.get("url", ""),
                                          bearer=bearer)
        return ingest.parse_csv_report(
            text, params["platform"], "sheets")
    if source == "drive":
        if not params.get("platform"):
            raise ValueError("drive import needs a platform")
        url = connectors.drive_file_url(params.get("url", ""))
        headers = {"Authorization": "Bearer [REDACTED]" % bearer} \
            if bearer else None
        blob = connectors.fetch_bytes(url, headers=headers)
        if blob.startswith(b"PK"):
            return ingest.parse_xlsx_report(
                blob, params["platform"], "drive")
        try:
            text = blob.decode("utf-8-sig")
        except ValueError:
            raise ValueError(
                "Drive file is neither CSV text nor .xlsx")
        if text.lstrip().lower().startswith(("<!doctype html", "<html")):
            raise ValueError(
                "Google returned a login/confirm page: the file is "
                "private. Connect Google Drive in Settings and retry "
                "with Google auth enabled.")
        return ingest.parse_csv_report(text, params["platform"], "drive")
    raise ValueError("unknown sync source: %r" % (source,))


MAX_JOB_NAME = 120


def _check_source(source):
    if source not in SOURCES:
        raise ValueError("unknown sync source: %r (try %s)"
                         % (source, ", ".join(SOURCES)))


def _check_name(name):
    text = (name or "").strip()
    if not text:
        raise ValueError("job needs a name")
    if len(text) > MAX_JOB_NAME:
        raise ValueError("job name must be %d characters or fewer"
                         % MAX_JOB_NAME)
    return text


def _job_dict(row):
    job_id, source, name, params_json, owner, enabled, created, updated = row
    try:
        params = json.loads(params_json or "{}")
    except ValueError:
        params = {}
    if not isinstance(params, dict):
        params = {}
    return {"id": job_id, "source": source, "name": name, "params": params,
            "owner_employee_id": owner or "", "enabled": bool(enabled),
            "created_at": created or "", "updated_at": updated or ""}


def create_job(conn, source, name, params, owner=""):
    """Create a scheduled sync job; returns its dict (with id)."""
    _check_source(source)
    name = _check_name(name)
    if not isinstance(params, dict):
        raise ValueError("job params must be an object")
    job_id = uuid.uuid4().hex
    now = utcnow()
    conn.execute(
        "INSERT INTO sync_jobs (id, source, name, params_json,"
        " owner_employee_id, enabled, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
        (job_id, source, name, json.dumps(params or {}), owner or "",
         now, now))
    conn.commit()
    return get_job(conn, job_id)


def get_job(conn, job_id):
    """One job dict by id, or None."""
    row = conn.execute(
        "SELECT id, source, name, params_json, owner_employee_id,"
        " enabled, created_at, updated_at FROM sync_jobs WHERE id=?",
        (job_id,)).fetchone()
    return _job_dict(row) if row else None


def list_jobs(conn, include_disabled=True):
    """Every sync job, oldest first."""
    rows = conn.execute(
        "SELECT id, source, name, params_json, owner_employee_id,"
        " enabled, created_at, updated_at FROM sync_jobs"
        " ORDER BY created_at, rowid").fetchall()
    jobs = [_job_dict(r) for r in rows]
    if not include_disabled:
        jobs = [j for j in jobs if j["enabled"]]
    return jobs


def update_job(conn, job_id, name=None, params=None):
    """Rename / re-parameterise a job; returns the updated dict."""
    job = get_job(conn, job_id)
    if job is None:
        raise ValueError("unknown sync job")
    if name is not None:
        job["name"] = _check_name(name)
    if params is not None:
        if not isinstance(params, dict):
            raise ValueError("job params must be an object")
        job["params"] = params
    conn.execute("UPDATE sync_jobs SET name=?, params_json=?, updated_at=?"
                 " WHERE id=?",
                 (job["name"], json.dumps(job["params"]), utcnow(), job_id))
    conn.commit()
    return get_job(conn, job_id)


def set_job_enabled(conn, job_id, enabled):
    """Enable/disable a job; disabled jobs are skipped by tick()."""
    if get_job(conn, job_id) is None:
        raise ValueError("unknown sync job")
    conn.execute("UPDATE sync_jobs SET enabled=?, updated_at=? WHERE id=?",
                 (1 if enabled else 0, utcnow(), job_id))
    conn.commit()
    return get_job(conn, job_id)


def delete_job(conn, job_id):
    """Delete a job. Run history in sync_runs is kept."""
    if get_job(conn, job_id) is None:
        raise ValueError("unknown sync job")
    conn.execute("DELETE FROM sync_jobs WHERE id=?", (job_id,))
    conn.commit()


def save_job(conn, source, params, owner=""):
    """Legacy single-job compat: remember an import's parameters.

    Upserts the default job (name == source) so the established
    connect flows keep working; jobs created explicitly via
    create_job keep their own rows and are never clobbered.
    """
    _check_source(source)
    row = conn.execute(
        "SELECT id FROM sync_jobs WHERE source=? AND name=?",
        (source, source)).fetchone()
    if row:
        update_job(conn, row[0], params=params)
        if owner:
            conn.execute("UPDATE sync_jobs SET owner_employee_id=?"
                         " WHERE id=?", (owner, row[0]))
            conn.commit()
        return get_job(conn, row[0])
    return create_job(conn, source, source, params or {}, owner)


def jobs(conn):
    """Legacy compat: {source: params} over enabled jobs.

    When several enabled jobs share a source, the most recently
    updated one wins this mapping; tick() still runs every job.
    """
    out = {}
    for job in list_jobs(conn, include_disabled=False):
        out[job["source"]] = job["params"]
    return out


def import_once(conn, source, fetch, job_id=""):
    """Run one import attempt: fetch, upsert, record the run.

    fetch is a zero-arg callable returning (rows, quarantined).
    Returns {"inserted", "updated", "quarantined", "quarantined_count"}.
    Failures record an error run and re-raise the original exception.
    """
    from creative_intel import ingest
    run_id = _record_start(conn, source, job_id)
    try:
        rows, quarantined = fetch()
        counts = ingest.upsert_rows(conn, rows)
    except Exception as exc:
        _record_finish(conn, run_id, "error", attempts=1,
                       error="%s: %s" % (type(exc).__name__, exc))
        raise
    _record_finish(conn, run_id, "ok", inserted=counts["inserted"],
                   updated=counts["updated"],
                   quarantined=len(quarantined), attempts=1)
    return {"inserted": counts["inserted"], "updated": counts["updated"],
            "quarantined": quarantined,
            "quarantined_count": len(quarantined)}


def run_once(conn, source, fetch, max_attempts=MAX_ATTEMPTS,
             sleep=time.sleep, job_id=""):
    """Run an import with bounded retries for the unattended path.

    One sync_runs row records the whole invocation: attempts counts
    every try, error carries the final failure. Transient failures
    sleep RETRY_DELAYS_S between tries (inject sleep in tests).
    """
    from creative_intel import ingest
    run_id = _record_start(conn, source, job_id)
    attempts = 0
    while True:
        attempts += 1
        try:
            rows, quarantined = fetch()
            counts = ingest.upsert_rows(conn, rows)
        except Exception as exc:  # noqa: BLE001 - recorded, then retried
            if attempts >= max(1, max_attempts):
                _record_finish(conn, run_id, "error", attempts=attempts,
                               error="%s: %s" % (type(exc).__name__, exc))
                raise
            delay = RETRY_DELAYS_S[min(attempts - 1,
                                       len(RETRY_DELAYS_S) - 1)]
            sleep(delay)
            continue
        _record_finish(conn, run_id, "ok", inserted=counts["inserted"],
                       updated=counts["updated"],
                       quarantined=len(quarantined), attempts=attempts)
        return {"inserted": counts["inserted"],
                "updated": counts["updated"],
                "quarantined": quarantined,
                "quarantined_count": len(quarantined),
                "attempts": attempts}


def status(conn, recent_limit=10):
    """Last-run status per source plus recent history for /api/sync/status."""
    sources = {}
    for row in conn.execute(
            "SELECT source, MAX(id) FROM sync_runs GROUP BY source"):
        detail = conn.execute(
            "SELECT started_at, finished_at, status, inserted, updated,"
            " quarantined, attempts, error FROM sync_runs WHERE id=?",
            (row[1],)).fetchone()
        last_success = conn.execute(
            "SELECT MAX(finished_at) FROM sync_runs"
            " WHERE source=? AND status='ok'", (row[0],)).fetchone()[0]
        sources[row[0]] = {
            "last_run_at": detail[0], "last_finished_at": detail[1],
            "last_status": detail[2], "last_inserted": detail[3],
            "last_updated": detail[4], "last_quarantined": detail[5],
            "last_attempts": detail[6], "last_error": detail[7],
            "last_success_at": last_success or "",
        }
    recent = [
        {"id": r[0], "source": r[1], "started_at": r[2],
         "finished_at": r[3], "status": r[4], "inserted": r[5],
         "updated": r[6], "quarantined": r[7], "attempts": r[8],
         "error": r[9]}
        for r in conn.execute(
            "SELECT id, source, started_at, finished_at, status, inserted,"
            " updated, quarantined, attempts, error FROM sync_runs"
            " ORDER BY id DESC LIMIT ?", (recent_limit,))]
    return {"sources": sources, "recent": recent,
            "jobs": sorted(jobs(conn)), "owners": job_owners(conn),
            "job_list": _jobs_with_runs(conn)}


def job_owners(conn):
    """Establishing employee per source ({source: employee_id}).

    Legacy compat: prefers the default (name == source) job, else the
    first job for that source.
    """
    try:
        rows = conn.execute(
            "SELECT source, name, owner_employee_id FROM sync_jobs").fetchall()
    except Exception:
        return {}
    out = {}
    for source, name, owner in rows:
        if source not in out or name == source:
            out[source] = owner or ""
    return out


def _job_last_run(conn, job_id):
    """Latest run summary for one job id, or None."""
    try:
        row = conn.execute(
            "SELECT started_at, finished_at, status, inserted, updated,"
            " quarantined, attempts, error FROM sync_runs WHERE job_id=?"
            " ORDER BY id DESC LIMIT 1", (job_id,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    return {"last_run_at": row[0], "last_finished_at": row[1],
            "last_status": row[2], "last_inserted": row[3],
            "last_updated": row[4], "last_quarantined": row[5],
            "last_attempts": row[6], "last_error": row[7]}


def _jobs_with_runs(conn):
    out = []
    for job in list_jobs(conn):
        info = dict(job)
        info["last_run"] = _job_last_run(conn, job["id"])
        out.append(info)
    return out


def tick(conn):
    """Run every enabled job once with retries. Returns {job_id: result}.

    Several jobs may share one source; each runs independently. A
    failing job records its error run and does not stop the others;
    its exception text is returned under that job's "error" key.
    """
    results = {}
    for job in list_jobs(conn, include_disabled=False):
        source, params = job["source"], job["params"]
        try:
            results[job["id"]] = dict(
                run_once(conn, source,
                         lambda s=source, p=params: fetch_job(s, p),
                         job_id=job["id"]))
            results[job["id"]]["ok"] = True
            results[job["id"]]["source"] = source
            results[job["id"]]["name"] = job["name"]
        except Exception as exc:  # noqa: BLE001 - per-job isolation
            results[job["id"]] = {
                "ok": False, "source": source, "name": job["name"],
                "error": "%s: %s" % (type(exc).__name__, exc)}
    return results


def daemon(db_path, interval_s, stop_event=None, sleep=time.sleep):
    """Blocking scheduler loop: tick() every interval_s seconds.

    Opens a fresh connection per tick (SQLite connections are not
    shared across threads). Returns when stop_event is set.
    """
    stop = stop_event or threading.Event()
    while not stop.is_set():
        if stop.wait(timeout=max(1, interval_s)):
            break
        conn = sqlite3.connect(db_path)
        try:
            from creative_intel import schema as schema_mod
            schema_mod.init_db(conn)
            tick(conn)
        except Exception as exc:  # noqa: BLE001 - daemon must survive
            print("sync tick failed: %s: %s"
                  % (type(exc).__name__, exc))
        finally:
            conn.close()
