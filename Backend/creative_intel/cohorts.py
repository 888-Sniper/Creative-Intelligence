"""Named benchmark cohorts: multi-filter definitions persisted in SQLite.

A cohort is a saved, reusable filter set over the canonical ads dataset:
vertical / platform / funnel / objective / market / client plus
include/exclude project lists (project = row["project"] or campaign).
Building a cohort runs the spend-weighted benchmark over matching rows
with p25/median/p75 bands and a min-n guard (see benchmarks.py).

Stdlib only. No secrets here.
"""

import datetime
import json

from .benchmarks import benchmark_filtered, normalize_filters

COHORT_DDL = """
CREATE TABLE IF NOT EXISTS cohorts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    filters_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT ''
);
"""


def init_cohorts_table(conn):
    conn.execute(COHORT_DDL)
    conn.commit()


def _row_to_cohort(row):
    return {"id": row[0], "name": row[1],
            "filters": json.loads(row[2] or "{}"), "created_at": row[3]}


def save_cohort(conn, name, filters=None):
    """Persist a named cohort; returns the cohort dict."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("cohort name must be a non-empty string")
    filt = normalize_filters(filters or {})
    init_cohorts_table(conn)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        cur = conn.execute(
            "INSERT INTO cohorts (name, filters_json, created_at)"
            " VALUES (?, ?, ?)",
            (name.strip(), json.dumps(filt), now))
    except Exception as exc:
        raise ValueError("cohort %r already exists" % name.strip()) from exc
    conn.commit()
    return {"id": cur.lastrowid, "name": name.strip(),
            "filters": filt, "created_at": now}


def list_cohorts(conn):
    init_cohorts_table(conn)
    return [_row_to_cohort(r) for r in conn.execute(
        "SELECT id, name, filters_json, created_at FROM cohorts ORDER BY name")]


def get_cohort(conn, cohort_id=None, name=None):
    """Fetch one cohort by id or name; raises ValueError when missing."""
    init_cohorts_table(conn)
    if cohort_id is not None:
        row = conn.execute(
            "SELECT id, name, filters_json, created_at FROM cohorts WHERE id=?",
            (cohort_id,)).fetchone()
    elif name is not None:
        row = conn.execute(
            "SELECT id, name, filters_json, created_at FROM cohorts WHERE name=?",
            (name,)).fetchone()
    else:
        raise ValueError("pass cohort_id or name")
    if not row:
        raise ValueError("unknown cohort %r" % (cohort_id if cohort_id is not None else name,))
    return _row_to_cohort(row)


def delete_cohort(conn, cohort_id=None, name=None):
    cohort = get_cohort(conn, cohort_id=cohort_id, name=name)
    conn.execute("DELETE FROM cohorts WHERE id=?", (cohort["id"],))
    conn.commit()
    return {"ok": True, "deleted": cohort["name"]}


def build_cohort(conn, cohort_id=None, name=None, filters=None, metric="cpa"):
    """Run the benchmark for a saved cohort (by id/name) or ad-hoc filters."""
    if filters is not None:
        filt = normalize_filters(filters)
        cohort = {"id": None, "name": "(ad-hoc)", "filters": filt}
    else:
        cohort = get_cohort(conn, cohort_id=cohort_id, name=name)
        filt = cohort["filters"]
    result = benchmark_filtered(conn, filt, metric)
    result["cohort"] = cohort
    return result
