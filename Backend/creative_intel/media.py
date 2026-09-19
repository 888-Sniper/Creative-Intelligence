"""Creative media store: upload, link, and serve review assets.

Files live under <repo>/Data/media/ (gitignored, never in the repo);
only metadata rows live in SQLite. Served same-origin at /media/<id>
so the web UI can preview uploads without remote hosts.

Fail-closed: unknown keys, disallowed types, oversize payloads, and
path tricks are rejected with ValueError before anything is written.
"""

import base64
import datetime
import hashlib
import os
import re
import sqlite3

MAX_BYTES = 100 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
KEY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")

# extension -> (mime, magic-prefix check or None)
TYPES = {
    ".mp4": ("video/mp4", (b"\x00\x00\x00",)),
    ".mov": ("video/quicktime", None),
    ".webm": ("video/webm", (b"\x1a\x45\xdf\xa3",)),
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".png": ("image/png", (b"\x89PNG",)),
    ".webp": ("image/webp", (b"RIFF",)),
    ".wav": ("audio/wav", (b"RIFF",)),
    ".mp3": ("audio/mpeg", (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")),
    ".m4a": ("audio/mp4", None),
}

DDL = """
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY,
    creative_key TEXT NOT NULL,
    filename TEXT NOT NULL DEFAULT '',
    stored_name TEXT NOT NULL DEFAULT '',
    mime TEXT NOT NULL DEFAULT '',
    bytes INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '',
    uploaded_by TEXT NOT NULL DEFAULT ''
);
"""


def ensure_schema(conn):
    conn.executescript(DDL)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(media)")]
    _ADDED = {"width": "INTEGER NOT NULL DEFAULT 0",
              "height": "INTEGER NOT NULL DEFAULT 0",
              "uploaded_by": "TEXT NOT NULL DEFAULT ''"}
    for name, decl in _ADDED.items():
        if name in cols:
            continue
        try:
            conn.execute("ALTER TABLE media ADD COLUMN %s %s" % (name, decl))
        except sqlite3.OperationalError as exc:
            # Concurrent first-touch race: another request added the
            # column between our PRAGMA check and this ALTER. Only a
            # duplicate-column conflict is safe to absorb.
            if "duplicate column" not in str(exc).lower():
                raise
    conn.commit()


def png_dimensions(content):
    """(width, height) from PNG IHDR bytes; (0, 0) when unparseable."""
    try:
        if bytes(content)[:8] != b"\x89PNG\r\n\x1a\n":
            return 0, 0
        w = int.from_bytes(bytes(content)[16:20], "big")
        h = int.from_bytes(bytes(content)[20:24], "big")
        if w > 0 and h > 0 and w <= 16384 and h <= 16384:
            return w, h
    except Exception:
        pass
    return 0, 0


def check_key(creative_key):
    if not isinstance(creative_key, str) or not KEY_RE.fullmatch(creative_key):
        raise ValueError("bad creative_key %r" % (creative_key,))


def check_upload(filename, content):
    if not isinstance(content, (bytes, bytearray)):
        raise ValueError("empty upload")
    return check_upload_head(filename, bytes(content)[:32], len(content))


def check_upload_head(filename, head, total):
    """Validate extension + magic from the head bytes + total size.

    Same rules as check_upload() for the streaming path, which never
    holds the whole file: magic prefixes sit in the first bytes, so a
    32-byte head plus the counted total enforces everything.
    """
    if not isinstance(filename, str) or "." not in filename:
        raise ValueError("upload needs a named file with an extension")
    ext = filename[filename.rfind("."):].lower()
    if ext not in TYPES:
        raise ValueError("disallowed media type %r (allowed: %s)"
                         % (ext, ", ".join(sorted(TYPES))))
    if not head or not total:
        raise ValueError("empty upload")
    if total > MAX_BYTES:
        raise ValueError("upload exceeds %d MB" % (MAX_BYTES // (1024 * 1024)))
    _mime, magics = TYPES[ext]
    if magics and not any(bytes(head).startswith(m) for m in magics):
        raise ValueError("content does not look like %s" % ext)
    return ext, TYPES[ext][0]


def check_upload_path(filename, path):
    """Head validation for a streamed temp file. Returns (ext, mime)."""
    total = os.path.getsize(path)
    with open(path, "rb") as fh:
        head = fh.read(32)
    return check_upload_head(filename, head, total)


def save_media_file(conn, store, creative_key, filename, tmp_path, total,
                    digest, mime=None, uploaded_by=""):
    """Persist a streamed upload: validate, atomically rename, record.

    tmp_path is a complete temp file on the same filesystem as store
    (the handler streams request chunks there while counting bytes and
    hashing). Magic/MIME validation reads only the head; the file is
    then atomically renamed into place, so a crash can never leave a
    partial asset behind. Duplicate bytes reuse the stored file and the
    temp file is always consumed (renamed or removed).
    """
    os.makedirs(store, exist_ok=True)
    try:
        check_key(creative_key)
        ext, sniffed = check_upload_path(filename, tmp_path)
        if mime and mime != sniffed:
            raise ValueError("mime %r does not match %s content"
                             % (mime, ext))
        ensure_schema(conn)
        dupes = conn.execute(
            "SELECT id, stored_name, mime, bytes, sha256, created_at,"
            " uploaded_by FROM media WHERE creative_key=? AND sha256=?"
            " ORDER BY id",
            (creative_key, digest)).fetchall()
        for dupe in dupes:
            if (dupe[6] if len(dupe) > 6 else "") == (uploaded_by or ""):
                return _record(creative_key, filename, dupe)
        if dupes:
            # Same bytes, different attribution: adopt the stored file
            # under a separately attributable row. Aliasing the other
            # employee's row would inherit (or be denied) their
            # entitlement; a re-upload proves possession of the bytes,
            # so it earns its own record.
            return _adopt_shared(conn, creative_key, filename, dupes[0],
                                 uploaded_by)
        stored = "%s_%s%s" % (creative_key, digest[:12], ext)
        dest = os.path.join(store, stored)
        if os.path.basename(stored) != stored:
            raise ValueError("bad creative_key %r" % (creative_key,))
        if os.path.isfile(dest):
            return _existing(conn, creative_key, filename, stored,
                             sniffed, total, digest, uploaded_by)
        os.replace(tmp_path, dest)
        tmp_path = None
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO media (creative_key, filename, stored_name, mime,"
            " bytes, sha256, created_at, uploaded_by)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (creative_key, os.path.basename(filename), stored, sniffed,
             total, digest, now, uploaded_by or ""))
        conn.commit()
        row = (cur.lastrowid, stored, sniffed, total, digest, now)
        _link_source_url(conn, creative_key, cur.lastrowid)
        return _record(creative_key, filename, row)
    finally:
        if tmp_path is not None and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _adopt_shared(conn, creative_key, filename, source, uploaded_by):
    """New attributable row over an identical stored file.

    source is a (id, stored_name, mime, bytes, sha256, created_at,
    uploaded_by) row for the same key+digest. No bytes are rewritten;
    the file is shared until no referencing row remains (see
    delete_media's refcount).
    """
    _sid, stored, mime, nbytes, digest, _created, _by = source[:7]
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO media (creative_key, filename, stored_name, mime,"
        " bytes, sha256, created_at, uploaded_by)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (creative_key, os.path.basename(filename), stored, mime,
         nbytes, digest, now, uploaded_by or ""))
    conn.commit()
    row = (cur.lastrowid, stored, mime, nbytes, digest, now)
    _link_source_url(conn, creative_key, cur.lastrowid)
    return _record(creative_key, filename, row)


def _existing(conn, creative_key, filename, stored, sniffed, total,
              digest, uploaded_by=""):
    """Adopt an identical stored file (same name <=> same content)."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO media (creative_key, filename, stored_name, mime,"
        " bytes, sha256, created_at, uploaded_by)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (creative_key, os.path.basename(filename), stored, sniffed,
         total, digest, now, uploaded_by or ""))
    conn.commit()
    row = (cur.lastrowid, stored, sniffed, total, digest, now)
    _link_source_url(conn, creative_key, cur.lastrowid)
    return _record(creative_key, filename, row)


def media_dir(base_dir):
    path = os.path.join(base_dir, "Data", "media")
    os.makedirs(path, exist_ok=True)
    return path


def save_media(conn, store, creative_key, filename, content_b64, mime=None,
               uploaded_by=""):
    """Persist a base64 upload (legacy JSON transport); returns metadata."""
    try:
        content = base64.b64decode(content_b64 or "", validate=True)
    except Exception:
        raise ValueError("content_b64 is not valid base64")
    return save_media_bytes(conn, store, creative_key, filename,
                            bytes(content), mime, uploaded_by=uploaded_by)


def save_media_bytes(conn, store, creative_key, filename, content, mime=None,
                     width=0, height=0, uploaded_by=""):
    """Persist raw upload bytes; returns the metadata record (no bytes).

    The multipart path: bytes ride outside JSON so the real 100 MB
    limit applies instead of the JSON body cap. On success the
    creative's annotation gains source_url=/media/<id> so grid/detail
    previews and live providers pick it up; annotation-less creatives
    keep no source_url until annotated (nothing invented).
    """
    os.makedirs(store, exist_ok=True)
    check_key(creative_key)
    content = bytes(content or b"")
    ext, sniffed = check_upload(filename, content)
    if mime and mime != sniffed:
        raise ValueError("mime %r does not match %s content" % (mime, ext))
    ensure_schema(conn)
    digest = hashlib.sha256(bytes(content)).hexdigest()
    dupes = conn.execute(
        "SELECT id, stored_name, mime, bytes, sha256, created_at, width,"
        " height, uploaded_by FROM media"
        " WHERE creative_key=? AND sha256=? ORDER BY id",
        (creative_key, digest)).fetchall()
    for dupe in dupes:
        if (dupe[8] if len(dupe) > 8 else "") == (uploaded_by or ""):
            return _record(creative_key, filename, dupe)
    if dupes:
        # Same bytes, different attribution: adopt the stored file
        # under a separately attributable row (see save_media_file).
        first = dupes[0]
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        width, height = (first[6], first[7]) if len(first) > 7 else (0, 0)
        cur = conn.execute(
            "INSERT INTO media (creative_key, filename, stored_name, mime,"
            " bytes, sha256, created_at, width, height, uploaded_by)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (creative_key, os.path.basename(filename), first[1], first[2],
             first[3], first[4], now, int(width or 0), int(height or 0),
             uploaded_by or ""))
        conn.commit()
        row = (cur.lastrowid, first[1], first[2], first[3], first[4],
               now, int(width or 0), int(height or 0))
        _link_source_url(conn, creative_key, cur.lastrowid)
        return _record(creative_key, filename, row)
    stored = "%s_%s%s" % (creative_key, digest[:12], ext)
    dest = os.path.join(store, stored)
    if os.path.basename(stored) != stored or not os.path.isfile(dest):
        with open(dest, "wb") as fh:
            fh.write(bytes(content))
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if not width or not height:
        width, height = png_dimensions(content)
    cur = conn.execute(
        "INSERT INTO media (creative_key, filename, stored_name, mime,"
        " bytes, sha256, created_at, width, height, uploaded_by)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (creative_key, os.path.basename(filename), stored, sniffed,
         len(content), digest, now, int(width or 0), int(height or 0),
         uploaded_by or ""))
    conn.commit()
    row = (cur.lastrowid, stored, sniffed, len(content), digest, now,
           int(width or 0), int(height or 0))
    _link_source_url(conn, creative_key, cur.lastrowid)
    return _record(creative_key, filename, row)


def _record(creative_key, filename, row):
    rid, _stored, mime, nbytes, digest, created = row[:6]
    width, height = (row[6], row[7]) if len(row) > 7 else (0, 0)
    rec = {"id": rid, "creative_key": creative_key,
           "filename": os.path.basename(filename), "mime": mime,
           "bytes": nbytes, "sha256": digest, "created_at": created,
           "url": "/media/%d" % rid}
    if width and height:
        rec["width"] = width
        rec["height"] = height
    return rec


def _link_source_url(conn, creative_key, rid):
    import json

    from . import creative as creative_mod
    # Scope the upload link to the asset versions actually bound to
    # this media row: a new upload under a shared creative name must
    # never rewrite a sibling version's source. Videos with no bound
    # analysis fall back to the legacy '' row (global annotate flow).
    try:
        targets = [row[0] for row in conn.execute(
            "SELECT id FROM videos WHERE media_id=?", (int(rid),))]
    except (TypeError, ValueError):
        return
    if not targets:
        targets = [""]
    for video_id in targets:
        try:
            got = conn.execute(
                "SELECT annotation_json FROM annotations"
                " WHERE creative_key=? AND video_id=?",
                (creative_key, video_id)).fetchone()
        except Exception:
            continue
        if not got:
            continue
        try:
            ann = json.loads(got[0])
        except ValueError:
            continue
        if not isinstance(ann, dict) or ann.get("source_url"):
            continue
        ann["source_url"] = "/media/%d" % int(rid)
        try:
            creative_mod.save_annotation(conn, creative_key, ann,
                                         video_id=video_id)
        except ValueError:
            continue


def delete_media(conn, store, rid):
    """Delete a media row and its stored file. Returns True when a
    row was removed. Callers must first establish the row is
    unreferenced (shared assets are never deleted blindly); a
    missing file does not fail the row delete. Identical bytes
    re-uploaded by another employee share one stored file across
    separately attributable rows: the file goes only when its last
    referencing row does."""
    try:
        rid = int(rid)
    except (TypeError, ValueError):
        raise ValueError("bad media id")
    ensure_schema(conn)
    row = conn.execute("SELECT stored_name FROM media WHERE id=?",
                       (rid,)).fetchone()
    if not row:
        return False
    stored = row[0] or ""
    shared = conn.execute("SELECT COUNT(*) FROM media WHERE stored_name=?"
                          " AND id<>?", (stored, rid)).fetchone()[0] \
        if stored else 0
    if stored and not shared and os.path.basename(stored) == stored:
        # File first: if the filesystem delete fails, the row stays
        # as the recovery record (retryable) instead of pointing at
        # nothing. A file that is already gone is not a failure.
        try:
            os.unlink(os.path.join(store, stored))
        except FileNotFoundError:
            pass
        except OSError:
            return False
    conn.execute("DELETE FROM media WHERE id=?", (rid,))
    conn.commit()
    return True


def _locate(conn, store, rid):
    """(path, mime, filename) for GET /media/<id>; 404-style ValueError."""
    try:
        rid = int(rid)
    except (TypeError, ValueError):
        raise ValueError("bad media id")
    ensure_schema(conn)
    row = conn.execute("SELECT stored_name, mime, filename FROM media WHERE id=?",
                       (rid,)).fetchone()
    if not row:
        raise ValueError("unknown media id %r" % (rid,))
    stored, mime, filename = row
    if os.path.basename(stored) != stored:
        raise ValueError("bad media id")
    path = os.path.join(store, stored)
    if not os.path.isfile(path):
        raise ValueError("media file missing for id %r" % (rid,))
    return path, mime, filename


def load_bytes(conn, store, rid):
    """(content, mime, filename) for GET /media/<id>; 404-style ValueError."""
    path, mime, filename = _locate(conn, store, rid)
    with open(path, "rb") as fh:
        return fh.read(), mime, filename


def file_path(conn, store, rid):
    """On-disk path for GET /media/<id> (range-capable serving)."""
    path, _mime, _filename = _locate(conn, store, rid)
    return path


def describe(conn, store, rid):
    """{mime, filename, bytes} headers for GET /media/<id>."""
    _path, mime, filename = _locate(conn, store, rid)
    row = conn.execute("SELECT bytes FROM media WHERE id=?",
                       (int(rid),)).fetchone()
    return {"mime": mime, "filename": filename,
            "bytes": row[0] if row else 0}


def entitled(conn, rid, employee_id, is_admin=False):
    """Whether an employee may use a media asset.

    Permission is established independently of draft connections:
    administrators, the original uploader, and owners of a draft
    already bound to the asset are entitled. Anyone else — even
    with a guessed media id — is not, so attaching an id to one's
    own draft can never launder access to another's upload.
    """
    if is_admin:
        return True
    try:
        rid = int(rid)
    except (TypeError, ValueError):
        return False
    ensure_schema(conn)
    try:
        row = conn.execute("SELECT uploaded_by FROM media WHERE id=?",
                           (rid,)).fetchone()
    except sqlite3.OperationalError:
        row = None
    if row and row[0] and row[0] == (employee_id or ""):
        return True
    try:
        bound = conn.execute(
            "SELECT COUNT(*) FROM videos JOIN drafts"
            " ON drafts.id = videos.draft_id"
            " WHERE videos.media_id = ?"
            " AND drafts.owner_employee_id = ?",
            (rid, employee_id or "")).fetchone()[0]
    except sqlite3.OperationalError:
        bound = 0
    return bool(bound)


def list_for_creative(conn, creative_key):
    check_key(creative_key)
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT id, filename, mime, bytes, sha256, created_at FROM media"
        " WHERE creative_key=? ORDER BY id", (creative_key,)).fetchall()
    return [{"id": r[0], "creative_key": creative_key, "filename": r[1],
             "mime": r[2], "bytes": r[3], "sha256": r[4],
             "created_at": r[5], "url": "/media/%d" % r[0]} for r in rows]


def find_for_creative(conn, store, creative_key):
    """Media bundle for the pipeline: {"audio": (bytes, mime)|None,
    "images": [jpeg/png/webp bytes]}. Reads files; missing files skipped."""
    check_key(creative_key)
    ensure_schema(conn)
    audio, images, videos, has_video = None, [], [], False
    for row in conn.execute(
            "SELECT id, stored_name, mime FROM media WHERE creative_key=?"
            " ORDER BY id", (creative_key,)).fetchall():
        rid, stored, mime = row
        if os.path.basename(stored) != stored:
            continue
        path = os.path.join(store, stored)
        if not os.path.isfile(path):
            continue
        if mime.startswith("video/"):
            videos.append(path)
            has_video = True
            continue
        with open(path, "rb") as fh:
            blob = fh.read()
        if mime.startswith("audio/"):
            if audio is None:
                audio = (blob, mime)
        elif mime.startswith("image/"):
            images.append(blob)
    return {"audio": audio, "images": images, "videos": videos,
            "has_video": has_video}
