"""Owner-scoped video-upload drafts and their linked records.

A draft binds one video, one dataset version, and one explicitly
confirmed video-to-record match. Drafts survive navigation/refresh
(they live in SQLite, not browser state); the API layer enforces
owner-or-admin writes and revalidates every match server-side.

Draft lifecycle (DRAFT_STATUSES) tracks the *flow*; execution
lifecycle (queued/running/...) stays in worker_jobs. Editing the
video, dataset, or match after confirmation must clear the
confirmation (clear_matches) and invalidate dependent review —
callers enforce that, this module provides the primitive.
"""

import datetime
import json
import uuid

DRAFT_STATUSES = (
    "draft",
    "validating",
    "needs_confirmation",
    "queued",
    "analyzing",
    "ready_for_review",
    "reviewed",
    "failed",
    "cancelled",
    "expired",
)

# Match proposal methods, most reliable first. Fuzzy filename
# suggestions may propose candidates but must never auto-confirm:
# only confirm_match() with an explicit human action sets confirmed.
MATCH_METHODS = (
    "platform_id",
    "exact_filename",
    "explicit_tag",
    "fuzzy_filename",
    "manual",
)


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


def _require(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("drafts: %s is required" % name)
    return value.strip()


def _dump(payload) -> str:
    return json.dumps(payload or {}, sort_keys=True, default=str)


def _row(conn, sql, args=()):
    cur = conn.execute(sql, args)
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip([d[0] for d in cur.description], row))


def _rows(conn, sql, args=()):
    cur = conn.execute(sql, args)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def create_draft(conn, owner_employee_id, draft_id=None, spec=None):
    """Create a draft. Idempotent: a repeated call with the same
    draft_id returns the existing row untouched (safe for retries
    and double clicks)."""
    owner = _require(owner_employee_id, "owner_employee_id")
    did = (draft_id or "").strip() or new_id()
    now = utcnow()
    conn.execute(
        "INSERT OR IGNORE INTO drafts (id, owner_employee_id, status,"
        " spec_json, dataset_version, created_at, updated_at)"
        " VALUES (?, ?, 'draft', ?, '', ?, ?)",
        (did, owner, _dump(spec), now, now))
    conn.commit()
    return did


def get_draft(conn, draft_id):
    return _row(conn, "SELECT * FROM drafts WHERE id = ?",
                (_require(draft_id, "draft_id"),))


def list_drafts(conn, owner_employee_id):
    """Owner-scoped listing, newest first. Admin-wide listing is an
    API-layer concern, not a broader default here."""
    return _rows(
        conn,
        "SELECT * FROM drafts WHERE owner_employee_id = ?"
        " ORDER BY updated_at DESC, rowid DESC",
        (_require(owner_employee_id, "owner_employee_id"),))


def update_draft(conn, draft_id, status=None, spec=None,
                 dataset_version=None):
    """Patch mutable draft fields; unknown statuses are rejected
    fail-closed. Returns True when the row exists."""
    did = _require(draft_id, "draft_id")
    sets, args = [], []
    if status is not None:
        if status not in DRAFT_STATUSES:
            raise ValueError("drafts: unknown status %r" % (status,))
        sets.append("status = ?")
        args.append(status)
    if spec is not None:
        sets.append("spec_json = ?")
        args.append(_dump(spec))
    if dataset_version is not None:
        sets.append("dataset_version = ?")
        args.append(str(dataset_version))
    if not sets:
        return get_draft(conn, did) is not None
    sets.append("updated_at = ?")
    args.append(utcnow())
    args.append(did)
    cur = conn.execute("UPDATE drafts SET %s WHERE id = ?"
                       % ", ".join(sets), args)
    conn.commit()
    return cur.rowcount > 0


def add_video(conn, draft_id, creative_key, media_id=0, duration_s=0.0,
              width=0, height=0, sha256="", validation=None):
    did = _require(draft_id, "draft_id")
    key = _require(creative_key, "creative_key")
    vid = new_id()
    conn.execute(
        "INSERT INTO videos (id, draft_id, creative_key, media_id,"
        " duration_s, width, height, sha256, validation_json,"
        " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (vid, did, key, int(media_id or 0), float(duration_s or 0.0),
         int(width or 0), int(height or 0), sha256 or "",
         _dump(validation), utcnow()))
    conn.commit()
    return vid


def list_videos(conn, draft_id):
    return _rows(conn, "SELECT * FROM videos WHERE draft_id = ?"
                       " ORDER BY rowid",
                 (_require(draft_id, "draft_id"),))


def add_dataset(conn, draft_id, filename, rows=0, version=None,
                sha256=""):
    did = _require(draft_id, "draft_id")
    dsid = new_id()
    conn.execute(
        "INSERT INTO datasets (id, draft_id, filename, rows, version,"
        " sha256, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (dsid, did, filename or "", int(rows or 0),
         version if version is not None else (sha256 or "")[:12],
         sha256 or "", utcnow()))
    conn.commit()
    return dsid


def list_datasets(conn, draft_id):
    return _rows(conn, "SELECT * FROM datasets WHERE draft_id = ?"
                       " ORDER BY rowid",
                 (_require(draft_id, "draft_id"),))


def propose_match(conn, draft_id, creative_key, method, records):
    """Record match *candidates* without confirming. Fuzzy methods
    must only ever reach this, never confirm_match, on their own."""
    did = _require(draft_id, "draft_id")
    key = _require(creative_key, "creative_key")
    if method not in MATCH_METHODS:
        raise ValueError("drafts: unknown match method %r" % (method,))
    conn.execute(
        "INSERT INTO matches (draft_id, creative_key, method,"
        " record_json, confirmed) VALUES (?, ?, ?, ?, 0)"
        " ON CONFLICT (draft_id, creative_key) DO UPDATE SET"
        " method = excluded.method, record_json = excluded.record_json,"
        " confirmed = 0, confirmed_by = '', confirmed_at = ''",
        (did, key, method,
         json.dumps(records or [], sort_keys=True, default=str)))
    conn.commit()


def confirm_match(conn, draft_id, creative_key, confirmed_by,
                  method="manual", records=None):
    """Explicit human confirmation of a video-to-record set. Records
    must already have been revalidated server-side by the caller."""
    did = _require(draft_id, "draft_id")
    key = _require(creative_key, "creative_key")
    who = _require(confirmed_by, "confirmed_by")
    if method not in MATCH_METHODS:
        raise ValueError("drafts: unknown match method %r" % (method,))
    now = utcnow()
    if records is None:
        conn.execute(
            "UPDATE matches SET confirmed = 1, confirmed_by = ?,"
            " confirmed_at = ? WHERE draft_id = ? AND creative_key = ?",
            (who, now, did, key))
    else:
        conn.execute(
            "INSERT INTO matches (draft_id, creative_key, method,"
            " record_json, confirmed, confirmed_by, confirmed_at)"
            " VALUES (?, ?, ?, ?, 1, ?, ?)"
            " ON CONFLICT (draft_id, creative_key) DO UPDATE SET"
            " method = excluded.method,"
            " record_json = excluded.record_json, confirmed = 1,"
            " confirmed_by = excluded.confirmed_by,"
            " confirmed_at = excluded.confirmed_at",
            (did, key, method,
             json.dumps(records, sort_keys=True, default=str),
             who, now))
    conn.commit()


def get_match(conn, draft_id, creative_key):
    return _row(conn, "SELECT * FROM matches WHERE draft_id = ?"
                      " AND creative_key = ?",
                (_require(draft_id, "draft_id"),
                 _require(creative_key, "creative_key")))


def clear_matches(conn, draft_id):
    """Drop confirmations after a material input change (new video,
    new dataset version, edited mapping). Dependent review must be
    invalidated by the caller alongside this."""
    conn.execute("DELETE FROM matches WHERE draft_id = ?",
                 (_require(draft_id, "draft_id"),))
    conn.commit()
