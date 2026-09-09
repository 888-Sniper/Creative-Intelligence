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

MAX_BYTES = 100 * 1024 * 1024
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
    created_at TEXT NOT NULL DEFAULT ''
);
"""


def ensure_schema(conn):
    conn.executescript(DDL)
    conn.commit()


def check_key(creative_key):
    if not isinstance(creative_key, str) or not KEY_RE.fullmatch(creative_key):
        raise ValueError("bad creative_key %r" % (creative_key,))


def check_upload(filename, content):
    if not isinstance(filename, str) or "." not in filename:
        raise ValueError("upload needs a named file with an extension")
    ext = filename[filename.rfind("."):].lower()
    if ext not in TYPES:
        raise ValueError("disallowed media type %r (allowed: %s)"
                         % (ext, ", ".join(sorted(TYPES))))
    if not isinstance(content, (bytes, bytearray)) or not content:
        raise ValueError("empty upload")
    if len(content) > MAX_BYTES:
        raise ValueError("upload exceeds %d MB" % (MAX_BYTES // (1024 * 1024)))
    _mime, magics = TYPES[ext]
    if magics and not any(bytes(content).startswith(m) for m in magics):
        raise ValueError("content does not look like %s" % ext)
    return ext, TYPES[ext][0]


def media_dir(base_dir):
    path = os.path.join(base_dir, "Data", "media")
    os.makedirs(path, exist_ok=True)
    return path


def save_media(conn, store, creative_key, filename, content_b64, mime=None):
    """Persist an upload; returns the metadata record (no bytes).

    content_b64 is base64 text (JSON-safe transport). On success the
    creative's annotation gains source_url=/media/<id> so grid/detail
    previews and live providers pick it up; annotation-less creatives
    keep no source_url until annotated (nothing invented).
    """
    from . import creative as creative_mod
    os.makedirs(store, exist_ok=True)
    check_key(creative_key)
    try:
        content = base64.b64decode(content_b64, validate=True)
    except Exception:
        raise ValueError("content_b64 is not valid base64")
    ext, sniffed = check_upload(filename, content)
    if mime and mime != sniffed:
        raise ValueError("mime %r does not match %s content" % (mime, ext))
    ensure_schema(conn)
    digest = hashlib.sha256(bytes(content)).hexdigest()
    dupe = conn.execute(
        "SELECT id, stored_name, mime, bytes, sha256, created_at FROM media"
        " WHERE creative_key=? AND sha256=?", (creative_key, digest)).fetchone()
    if dupe:
        return _record(creative_key, filename, dupe)
    stored = "%s_%s%s" % (creative_key, digest[:12], ext)
    dest = os.path.join(store, stored)
    if os.path.basename(stored) != stored or not os.path.isfile(dest):
        with open(dest, "wb") as fh:
            fh.write(bytes(content))
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO media (creative_key, filename, stored_name, mime,"
        " bytes, sha256, created_at) VALUES (?,?,?,?,?,?,?)",
        (creative_key, os.path.basename(filename), stored, sniffed,
         len(content), digest, now))
    conn.commit()
    row = (cur.lastrowid, stored, sniffed, len(content), digest, now)
    _link_source_url(conn, creative_key, cur.lastrowid)
    return _record(creative_key, filename, row)


def _record(creative_key, filename, row):
    rid, _stored, mime, nbytes, digest, created = row
    return {"id": rid, "creative_key": creative_key,
            "filename": os.path.basename(filename), "mime": mime,
            "bytes": nbytes, "sha256": digest, "created_at": created,
            "url": "/media/%d" % rid}


def _link_source_url(conn, creative_key, rid):
    from . import creative as creative_mod
    import json
    got = conn.execute("SELECT annotation_json FROM annotations WHERE creative_key=?",
                       (creative_key,)).fetchone()
    if not got:
        return
    try:
        ann = json.loads(got[0])
    except ValueError:
        return
    if not isinstance(ann, dict) or ann.get("source_url"):
        return
    ann["source_url"] = "/media/%d" % rid
    creative_mod.save_annotation(conn, creative_key, ann)


def load_bytes(conn, store, rid):
    """(content, mime, filename) for GET /media/<id>; 404-style ValueError."""
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
    with open(path, "rb") as fh:
        return fh.read(), mime, filename


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
