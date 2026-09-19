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

# Statuses mirrored by the video_analysis worker itself (submit ->
# queued -> analyzing -> ready_for_review/failed/cancelled). The
# PATCH /api/drafts/{id} endpoint rejects these so a client can
# never forge pipeline state around the worker and its staleness
# guard; the worker keeps writing them via update_draft directly.
WORKER_MIRRORED_STATUSES = frozenset({"queued", "analyzing", "failed"})

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
    and double clicks). A colliding id owned by someone else is
    rejected instead of leaking the foreign draft."""
    owner = _require(owner_employee_id, "owner_employee_id")
    did = (draft_id or "").strip() or new_id()
    now = utcnow()
    conn.execute(
        "INSERT OR IGNORE INTO drafts (id, owner_employee_id, status,"
        " spec_json, dataset_version, created_at, updated_at)"
        " VALUES (?, ?, 'draft', ?, '', ?, ?)",
        (did, owner, _dump(spec), now, now))
    conn.commit()
    row = get_draft(conn, did)
    if row is not None and (row.get("owner_employee_id") or "") != owner:
        raise ValueError("draft id is already in use")
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
                 dataset_version=None, commit=True):
    """Patch mutable draft fields; unknown statuses are rejected
    fail-closed. Returns True when the row exists. commit=False
    defers the commit for a caller-owned transaction."""
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
    if commit:
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


def active_video(conn, draft_id):
    """The draft's bound video version, or None.

    Newest valid row wins: validation replaces (never appends
    history), so the active version is the latest valid one even if
    an older row somehow survives. The row id is the immutable
    asset-version identity used to scope analysis reads and writes.
    """
    for cand in reversed(list_videos(conn, draft_id)):
        try:
            verdict = json.loads(cand.get("validation_json") or "{}")
        except ValueError:
            continue
        if verdict.get("status") == "valid":
            return cand
    return None


def set_video_transcript(conn, video_id, text, commit=True):
    """Store a video version's own transcript on its immutable row.

    Per-version transcripts die with the draft (video rows are
    draft-owned); the creatives copy stays the global display record.
    """
    conn.execute("UPDATE videos SET transcript=? WHERE id=?",
                 (text or "", _require(video_id, "video_id")))
    if commit:
        conn.commit()


def get_video_transcript(conn, video_id):
    """One asset version's own transcript, or ''.

    Exact video-row read — never the shared creatives copy — so an
    export pairs the selected annotation with the same version's
    words."""
    try:
        row = conn.execute("SELECT transcript FROM videos WHERE id = ?",
                           (_require(video_id, "video_id"),)).fetchone()
    except Exception:
        return ""
    if not row or row[0] is None:
        return ""
    return row[0]


def clear_videos(conn, draft_id):
    """Remove every video row bound to a draft. Replacement and
    removal are explicit backend operations: a draft has exactly
    one active video version, never an ambiguous history where the
    analysis could bind the oldest row while the form shows the
    newest. Returns the removed row count."""
    did = _require(draft_id, "draft_id")
    cur = conn.execute("DELETE FROM videos WHERE draft_id = ?", (did,))
    conn.commit()
    return cur.rowcount


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
                  method="manual", records=None, video_id=""):
    """Explicit human confirmation of a video-to-record set. Records
    must already have been revalidated server-side by the caller.
    video_id freezes the bound asset version the confirmation was
    made against, so reporting and export can later select the same
    video's own annotation and transcript even if the draft's
    active video has since changed."""
    did = _require(draft_id, "draft_id")
    key = _require(creative_key, "creative_key")
    who = _require(confirmed_by, "confirmed_by")
    if method not in MATCH_METHODS:
        raise ValueError("drafts: unknown match method %r" % (method,))
    now = utcnow()
    vid = video_id or ""
    if records is None:
        conn.execute(
            "UPDATE matches SET confirmed = 1, confirmed_by = ?,"
            " confirmed_at = ?, video_id = ?"
            " WHERE draft_id = ? AND creative_key = ?",
            (who, now, vid, did, key))
    else:
        conn.execute(
            "INSERT INTO matches (draft_id, creative_key, method,"
            " record_json, confirmed, confirmed_by, confirmed_at,"
            " video_id)"
            " VALUES (?, ?, ?, ?, 1, ?, ?, ?)"
            " ON CONFLICT (draft_id, creative_key) DO UPDATE SET"
            " method = excluded.method,"
            " record_json = excluded.record_json, confirmed = 1,"
            " confirmed_by = excluded.confirmed_by,"
            " confirmed_at = excluded.confirmed_at,"
            " video_id = excluded.video_id",
            (did, key, method,
             json.dumps(records, sort_keys=True, default=str),
             who, now, vid))
    conn.commit()


def get_match(conn, draft_id, creative_key):
    return _row(conn, "SELECT * FROM matches WHERE draft_id = ?"
                      " AND creative_key = ?",
                (_require(draft_id, "draft_id"),
                 _require(creative_key, "creative_key")))


def confirmed_records_for_key(conn, creative_key, owner=None,
                               admin=False):
    """Latest confirmed match snapshots for one creative name, or None.

    Owner-scoped: the viewer's own draft-owned confirmation wins;
    administrators may use any owner's. Match selections are private
    draft data, so one employee's selection is never borrowed for
    another employee's views — without your own confirmation you see
    key-equal rows, never someone else's pick.
    """
    try:
        rows = conn.execute(
            "SELECT m.record_json, d.owner_employee_id FROM matches m"
            " JOIN drafts d ON d.id = m.draft_id"
            " WHERE m.creative_key = ? AND m.confirmed = 1"
            " ORDER BY m.confirmed_at DESC",
            (_require(creative_key, "creative_key"),)).fetchall()
    except Exception:
        return None
    for record_json, match_owner in rows or []:
        if not admin and owner is not None \
                and (match_owner or "") != owner:
            continue
        try:
            records = json.loads(record_json or "[]")
        except ValueError:
            continue
        if isinstance(records, list) and records:
            return records
    return None


def confirmed_bundle_for_key(conn, creative_key, owner=None,
                               admin=False):
    """Applicable confirmation as one identity bundle, or None.

    Owner-scoped like confirmed_records_for_key: the viewer's own
    draft-owned confirmation wins; administrators may use any
    owner's. Returns {records, video_id, draft_id, client, campaign,
    method, confirmed_at}. video_id is the asset version frozen at
    confirm time (falling back to that draft's current active video
    for confirmations predating the freeze); client/campaign come
    from the confirming draft's spec so report rows without a
    client column still carry the authorised destination."""
    try:
        rows = conn.execute(
            "SELECT m.record_json, m.video_id, m.method,"
            " m.confirmed_at, m.draft_id, d.owner_employee_id,"
            " d.spec_json FROM matches m"
            " JOIN drafts d ON d.id = m.draft_id"
            " WHERE m.creative_key = ? AND m.confirmed = 1"
            " ORDER BY m.confirmed_at DESC",
            (_require(creative_key, "creative_key"),)).fetchall()
    except Exception:
        return None
    for record_json, frozen_vid, method, confirmed_at, did, \
            match_owner, spec_json in rows or []:
        if not admin and owner is not None \
                and (match_owner or "") != owner:
            continue
        try:
            records = json.loads(record_json or "[]")
        except ValueError:
            continue
        if not isinstance(records, list) or not records:
            continue
        try:
            spec = json.loads(spec_json or "{}")
        except ValueError:
            spec = {}
        if not isinstance(spec, dict):
            spec = {}
        vid = frozen_vid or ""
        if not vid:
            try:
                active = active_video(conn, did)
            except Exception:
                active = None
            vid = active["id"] if isinstance(active, dict) else ""
        return {"records": records, "video_id": vid or "",
                "draft_id": did, "client": spec.get("client") or "",
                "campaign": spec.get("campaign") or "",
                "method": method or "",
                "confirmed_at": confirmed_at or ""}
    return None


def performance_rows_for_key(conn, creative_key, ads_rows, owner=None,
                             admin=False):
    """Canonical per-key performance for reporting surfaces.

    The confirmed video-to-record set replaces key equality (never
    unions with it): a confirmed 6,000-impression match shows instead
    of a key-query 0 when the video and report identifiers differ.
    Without an applicable confirmation, the key-equal ads rows stand.
    Stored snapshots are complete ads rows (every column is frozen
    at confirm time), so known values like revenue and reach are
    never reconstructed from defaults; only columns absent from an
    older partial snapshot take type-safe fills. Rows whose own
    client/campaign is empty inherit the confirming draft's
    authorised destination, so client-filterable surfaces stay
    connected to the confirmed association.
    """
    bundle = confirmed_bundle_for_key(
        conn, creative_key, owner=owner, admin=admin)
    if bundle is None:
        return ads_rows
    confirmed = bundle["records"]
    # Shape snapshots exactly like ads rows: columns a frozen
    # snapshot does not carry take the ads table's own defaults, so
    # downstream sums, scope filters, and money helpers behave
    # identically to key-equal rows.
    try:
        info = conn.execute("PRAGMA table_info(ads)").fetchall()
    except Exception:
        info = []
    fills = {}
    for col in info:
        ctype = str(col[2] or "").upper()
        fills[col[1]] = 0 if ("INT" in ctype or "REAL" in ctype
                              or "FLOA" in ctype or "DOUB" in ctype
                              or "NUM" in ctype) else ""
    import math as _math
    shaped = []
    for rec in confirmed:
        if not isinstance(rec, dict):
            continue
        if fills:
            row = {}
            for col, fill in fills.items():
                val = rec.get(col)
                if val is None:
                    row[col] = fill
                elif isinstance(val, float) \
                        and not _math.isfinite(val):
                    # Historic NaN/inf snapshots (or JSON
                    # round-trips) degrade to the column default
                    # rather than poisoning downstream sums.
                    row[col] = fill
                else:
                    row[col] = val
        else:
            row = dict(rec)
        if not row.get("client") and bundle["client"]:
            row["client"] = bundle["client"]
        if not row.get("campaign") and bundle["campaign"]:
            row["campaign"] = bundle["campaign"]
        shaped.append(row)
    return shaped


def confirmed_match_keys(conn, owner=None, admin=False):
    """Creative names with an applicable confirmed match.

    Lets campaign listings surface videos whose confirmed records
    live under a different report-side identifier: the key set is
    the union of observed ads keys and confirmed match keys, with
    the same owner scoping as confirmed_records_for_key.
    """
    try:
        rows = conn.execute(
            "SELECT m.creative_key, d.owner_employee_id FROM matches m"
            " JOIN drafts d ON d.id = m.draft_id"
            " WHERE m.confirmed = 1").fetchall()
    except Exception:
        return set()
    keys = set()
    for key, match_owner in rows or []:
        if not key:
            continue
        if not admin and owner is not None \
                and (match_owner or "") != owner:
            continue
        keys.add(key)
    return keys


def clear_matches(conn, draft_id):
    """Drop confirmations after a material input change (new video,
    new dataset version, edited mapping). Dependent review must be
    invalidated by the caller alongside this."""
    conn.execute("DELETE FROM matches WHERE draft_id = ?",
                 (_require(draft_id, "draft_id"),))
    conn.commit()


def get_review(conn, draft_id):
    """The recorded human review ({by, at, analysis_version, note}),
    or {} when the draft was never reviewed via the review op."""
    row = _row(conn, "SELECT review_json FROM drafts WHERE id = ?",
               (_require(draft_id, "draft_id"),))
    if not row:
        return {}
    try:
        review = json.loads(row.get("review_json") or "{}")
    except ValueError:
        return {}
    return review if isinstance(review, dict) else {}


def set_review(conn, draft_id, reviewer, analysis_version, note=""):
    """Record a version-bound human review. The caller must have
    verified the draft is ready and the version is current."""
    did = _require(draft_id, "draft_id")
    review = {"by": _require(reviewer, "reviewer"),
              "at": utcnow(),
              "analysis_version": _require(analysis_version,
                                           "analysis_version"),
              "note": note or ""}
    conn.execute("UPDATE drafts SET review_json = ?, status = 'reviewed',"
                 " updated_at = ? WHERE id = ?",
                 (_dump(review), utcnow(), did))
    conn.commit()
    return review


def clear_review(conn, draft_id):
    """Invalidate a recorded review after a material input change. A
    reviewed draft falls back to needs_confirmation: the approval
    belonged to the old inputs, never to the new ones."""
    did = _require(draft_id, "draft_id")
    conn.execute("UPDATE drafts SET review_json = '{}',"
                 " status = CASE WHEN status = 'reviewed'"
                 " THEN 'needs_confirmation' ELSE status END,"
                 " updated_at = ? WHERE id = ?",
                 (utcnow(), did))
    conn.commit()
