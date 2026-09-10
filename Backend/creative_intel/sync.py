"""Scheduled sync runner: dedup/upsert imports with retry and status history.

Every connector import (manual or scheduled) funnels through
import_once(): fetch + parse, store via ingest.upsert_rows() so
re-imports update matching facts instead of duplicating them, and
record the outcome in sync_runs. Successful manual imports also save
their parameters as sync_jobs, which the scheduler re-runs; run_once()
adds bounded retries with backoff for the unattended path.

All history is local SQLite; tokens stay in Keychain/env via
connectors. No threads are started here — server.py owns the daemon
thread, and daemon()/tick() below are plain blocking calls.
"""

import datetime
import json
import sqlite3
import threading
import time

MAX_ATTEMPTS = 3
RETRY_DELAYS_S = (2.0, 8.0)

SOURCES = ("meta", "tiktok", "sheets", "drive")


def utcnow():
    return datetime.datetime.now(
        datetime.timezone.utc).isoformat(timespec="seconds")


def _record_start(conn, source):
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


def fetch_job(source, params):
    """Fetch + parse one stored job. Returns (rows, quarantined).

    Raises ValueError with a human-readable reason (missing token,
    parked OAuth, bad payload) — fail closed, never stub rows.
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
        text = connectors.fetch_sheet_csv(params.get("url", ""))
        return ingest.parse_csv_report(
            text, params["platform"], "sheets")
    if source == "drive":
        if not params.get("platform"):
            raise ValueError("drive import needs a platform")
        url = connectors.drive_file_url(params.get("url", ""))
        blob = connectors.fetch_bytes(url)
        if blob.startswith(b"PK"):
            return ingest.parse_xlsx_report(
                blob, params["platform"], "drive")
        try:
            text = blob.decode("utf-8-sig")
        except ValueError:
            raise ValueError(
                "Drive file is neither CSV text nor .xlsx")
        if text.lstrip().lower().startswith(("<!doctype html", "<html")):
            raise ValueError("Google returned a login/confirm page: "
                             "private Drive files need OAuth (parked)")
        return ingest.parse_csv_report(text, params["platform"], "drive")
    raise ValueError("unknown sync source: %r" % (source,))


def save_job(conn, source, params, owner=""):
    """Remember a successful import's parameters for scheduled re-runs.

    owner is the establishing employee's id (audit info). Sync jobs are
    organisation assets: the scheduler keeps running them even if the
    establishing employee is later suspended or revoked.
    """
    if source not in SOURCES:
        raise ValueError("unknown sync source: %r" % (source,))
    conn.execute(
        "INSERT INTO sync_jobs (source, params_json, updated_at,"
        " owner_employee_id)"
        " VALUES (?, ?, ?, ?)"
        " ON CONFLICT(source) DO UPDATE SET params_json=excluded.params_json,"
        " updated_at=excluded.updated_at,"
        " owner_employee_id=excluded.owner_employee_id",
        (source, json.dumps(params or {}), utcnow(), owner or ""))
    conn.commit()


def jobs(conn):
    """Return {source: params} for every stored sync job."""
    out = {}
    for source, params_json in conn.execute(
            "SELECT source, params_json FROM sync_jobs"):
        try:
            out[source] = json.loads(params_json or "{}")
        except ValueError:
            out[source] = {}
    return out


def import_once(conn, source, fetch):
    """Run one import attempt: fetch, upsert, record the run.

    fetch is a zero-arg callable returning (rows, quarantined).
    Returns {"inserted", "updated", "quarantined", "quarantined_count"}.
    Failures record an error run and re-raise the original exception.
    """
    from creative_intel import ingest
    run_id = _record_start(conn, source)
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
             sleep=time.sleep):
    """Run an import with bounded retries for the unattended path.

    One sync_runs row records the whole invocation: attempts counts
    every try, error carries the final failure. Transient failures
    sleep RETRY_DELAYS_S between tries (inject sleep in tests).
    """
    from creative_intel import ingest
    run_id = _record_start(conn, source)
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
            "jobs": sorted(jobs(conn)), "owners": job_owners(conn)}


def job_owners(conn):
    """Establishing employee per source ({source: employee_id})."""
    try:
        rows = conn.execute(
            "SELECT source, owner_employee_id FROM sync_jobs").fetchall()
    except Exception:
        return {}
    return {source: owner or "" for source, owner in rows}


def tick(conn):
    """Run every stored job once with retries. Returns {source: result}.

    A failing job records its error run and does not stop the others;
    its exception text is returned under that source's "error" key.
    """
    results = {}
    for source, params in sorted(jobs(conn).items()):
        try:
            results[source] = dict(
                run_once(conn, source,
                         lambda s=source, p=params: fetch_job(s, p)))
            results[source]["ok"] = True
        except Exception as exc:  # noqa: BLE001 - per-job isolation
            results[source] = {
                "ok": False,
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
