"""Streaming media-upload tests (pytest + TestClient).

Multipart uploads must stream to a temp file (counted + hashed),
validate from the head, and rename atomically — never buffering the
whole file in RAM, and never leaving temp files behind.
"""

import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import employees as emp_store  # noqa: E402
from ci_backend.app import create_app  # noqa: E402
from ci_backend.config import Settings  # noqa: E402
from ci_backend.db import make_engine, make_session_factory  # noqa: E402
from creative_intel import media as media_mod  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PNG_HEAD = b"\x89PNG\r\n\x1a\n"


def make_owner(tmp_path, monkeypatch):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    monkeypatch.setenv("CREATIVE_INTEL_MEDIA_DIR", str(media_dir))
    db = str(tmp_path / "app.db")
    settings = Settings(workos_client_id="client_test",
                        key_workos="[REDACTED]")
    app = create_app(db, settings)
    engine = make_engine(db)
    with make_session_factory(engine)() as sess:
        boss = emp_store.admin_create(sess, "root", "boss@foap.test",
                                      role="admin")
        cookie = "ci_session=" + emp_store.create_session(
            sess, boss.id, "")
    http = TestClient(app, raise_server_exceptions=False)
    http.headers.update({"Cookie": cookie})
    return http, media_dir


def leftovers(media_dir):
    return [f for f in os.listdir(str(media_dir))
            if f.startswith(".upload-")]


def test_multichunk_upload_roundtrip(tmp_path, monkeypatch):
    http, media_dir = make_owner(tmp_path, monkeypatch)
    blob = PNG_HEAD + b"\x00" * (3 * 1024 * 1024)
    resp = http.post("/api/media/upload",
                     data={"creative_key": "big1"},
                     files={"file": ("spot.png", blob, "image/png")})
    assert resp.status_code == 200, resp.text
    rec = resp.json()
    assert rec["bytes"] == len(blob)
    assert rec["sha256"] == hashlib.sha256(blob).hexdigest()
    # The record URL is /media/<id>; the stored file must hold our bytes.
    by_content = [f for f in os.listdir(str(media_dir))
                  if not f.startswith(".") and open(
                      str(media_dir / f), "rb").read() == blob]
    assert len(by_content) == 1
    assert leftovers(media_dir) == []


def test_oversize_upload_rejected_without_leftovers(tmp_path, monkeypatch):
    http, media_dir = make_owner(tmp_path, monkeypatch)
    monkeypatch.setattr(media_mod, "MAX_BYTES", 1024)
    resp = http.post("/api/media/upload",
                     data={"creative_key": "big2"},
                     files={"file": ("spot.png", PNG_HEAD + b"\x00" * 2048,
                                     "image/png")})
    assert resp.status_code == 409, resp.text
    assert "exceeds" in resp.json()["error"]
    assert leftovers(media_dir) == []
    assert [f for f in os.listdir(str(media_dir))
            if not f.startswith(".")] == []


def test_mime_mismatch_rejected(tmp_path, monkeypatch):
    http, media_dir = make_owner(tmp_path, monkeypatch)
    resp = http.post("/api/media/upload",
                     data={"creative_key": "mm1"},
                     files={"file": ("spot.png", PNG_HEAD + b"\x00" * 64,
                                     "image/jpeg")})
    assert resp.status_code == 409, resp.text
    assert leftovers(media_dir) == []


def test_duplicate_upload_reuses_stored_file(tmp_path, monkeypatch):
    http, media_dir = make_owner(tmp_path, monkeypatch)
    blob = PNG_HEAD + b"\x01" * 128
    first = http.post("/api/media/upload",
                      data={"creative_key": "dup1"},
                      files={"file": ("a.png", blob, "image/png")})
    second = http.post("/api/media/upload",
                       data={"creative_key": "dup1"},
                       files={"file": ("b.png", blob, "image/png")})
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["sha256"] == second.json()["sha256"]
    stored = [f for f in os.listdir(str(media_dir))
              if not f.startswith(".")]
    assert len(stored) == 1
    assert leftovers(media_dir) == []
