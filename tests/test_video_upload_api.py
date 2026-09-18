"""WP2+WP3: video-upload API (validate, drafts, datasets, matches).

End to end through TestClient with the real fixture pair:
fixtures/Video Upload Sample 720p.mp4 (15s, 1280x720, h264+aac)
fixtures/Video Upload Sample Dataset.csv (3 rows, pooled CTR 2.50%).
"""

import base64
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import employees as emp_store  # noqa: E402
from ci_backend.app import create_app  # noqa: E402
from ci_backend.config import Settings  # noqa: E402
from conftest import employee_session  # noqa: E402
from creative_intel import ooxml  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")
MP4_PATH = os.path.join(FIXTURES, "Video Upload Sample 720p.mp4")
CSV_PATH = os.path.join(FIXTURES, "Video Upload Sample Dataset.csv")


def make_app(tmp_path, monkeypatch):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    monkeypatch.setenv("CREATIVE_INTEL_MEDIA_DIR", str(media_dir))
    db = str(tmp_path / "app.db")
    settings = Settings(workos_client_id="client_test",
                        key_workos="[REDACTED]")
    app = create_app(db, settings)
    return db, TestClient(app, raise_server_exceptions=False)


def cookie_for(db, email, role="admin"):
    with employee_session(db) as sess:
        try:
            person = emp_store.admin_create(sess, "test-helper", email,
                                            role=role)
        except emp_store.StoreError:
            person = emp_store.find_employee(sess, "", email)
        token = emp_store.create_session(sess, person.id,
                                         person.workos_user_id or "")
    return {"Cookie": "ci_session=%s" % token}


def authed(http, db, email="owner@foap.test", role="admin"):
    http.headers.update(cookie_for(db, email, role))
    return http


def upload_fixture_video(http):
    with open(MP4_PATH, "rb") as fh:
        blob = fh.read()
    resp = http.post("/api/media/upload",
                     data={"creative_key": "video-upload-sample"},
                     files={"file": ("sample.mp4", blob, "video/mp4")})
    assert resp.status_code == 200, resp.text
    rec = resp.json()
    assert rec["sha256"] == hashlib.sha256(blob).hexdigest()
    return rec


def import_fixture_csv(http, draft_id):
    with open(CSV_PATH) as fh:
        csv_text = fh.read()
    resp = http.post("/api/datasets/import",
                     json={"draft_id": draft_id, "platform": "meta",
                           "filename": "Video Upload Sample Dataset.csv",
                           "csv": csv_text})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_limits_and_auth(tmp_path, monkeypatch):
    db, http = make_app(tmp_path, monkeypatch)
    assert http.get("/api/videos/limits").status_code in (401, 403)
    authed(http, db)
    resp = http.get("/api/videos/limits")
    assert resp.status_code == 200, resp.text
    assert resp.json()["containers"] == [".mp4", ".mov"]


def test_draft_crud_and_owner_matrix(tmp_path, monkeypatch):
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db, "owner@foap.test")
    resp = http.post("/api/drafts", json={"spec": {"client": "Foap"}})
    assert resp.status_code == 200, resp.text
    did = resp.json()["draft"]["id"]
    # Idempotent retry with the same client id: one row.
    again = http.post("/api/drafts",
                      json={"draft_id": did, "spec": {"client": "X"}})
    assert again.json()["draft"]["id"] == did
    assert again.json()["draft"]["spec"] == {"client": "Foap"}
    # A second employee cannot read-change the draft...
    http.headers.clear()
    authed(http, db, "stranger@foap.test", role="employee")
    assert http.patch("/api/drafts/%s" % did,
                      json={"status": "cancelled"}).status_code == 403
    assert http.delete("/api/drafts/%s" % did).status_code == 403
    # ...but an admin can.
    http.headers.clear()
    authed(http, db, "root@foap.test")
    assert http.patch("/api/drafts/%s" % did,
                      json={"status": "cancelled"}).status_code == 200
    assert http.delete("/api/drafts/%s" % did).status_code == 200
    assert http.get("/api/drafts/%s" % did).status_code == 404
    # Unknown statuses are rejected fail-closed.
    resp = http.post("/api/drafts", json={})
    did2 = resp.json()["draft"]["id"]
    bad = http.patch("/api/drafts/%s" % did2, json={"status": "teleport"})
    assert bad.status_code == 409


def test_dataset_import_and_no_double_count(tmp_path, monkeypatch):
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    first = import_fixture_csv(http, did)
    assert (first["inserted"], first["updated"],
            first["quarantined"]) == (3, 0, 0)
    assert first["rows"] == 3
    draft = http.get("/api/drafts/%s" % did).json()["draft"]
    assert draft["dataset_version"] == first["version"]
    assert draft["datasets"][0]["rows"] == 3
    # Re-importing the same file updates facts instead of doubling.
    second = import_fixture_csv(http, did)
    assert (second["inserted"], second["updated"]) == (0, 3)
    import sqlite3
    conn = sqlite3.connect(db)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM ads WHERE creative_key=?",
            ("video-upload-sample",)).fetchone()[0]
    finally:
        conn.close()
    assert count == 3


def test_video_validate_fixture_clip(tmp_path, monkeypatch):
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db)
    rec = upload_fixture_video(http)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    resp = http.post("/api/videos/validate",
                     json={"media_id": rec["id"], "draft_id": did})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["validation"]["status"] == "valid"
    assert body["duration_s"] == 15.0
    assert (body["width"], body["height"]) == (1280, 720)
    assert body["validation"]["has_audio"] is True
    assert body["video_id"] != ""
    draft = http.get("/api/drafts/%s" % did).json()["draft"]
    assert draft["videos"][0]["sha256"] == rec["sha256"]


def test_video_validate_rejects_garbage(tmp_path, monkeypatch):
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db)
    # Passes the media store's magic prefix check but is no video:
    # ffprobe must fail it at validation time.
    resp = http.post("/api/media/upload",
                     data={"creative_key": "bogus"},
                     files={"file": ("bogus.mp4", b"\x00\x00\x00\x18ftyp"
                                     b"not a video" * 64, "video/mp4")})
    assert resp.status_code == 200, resp.text
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    resp = http.post("/api/videos/validate",
                     json={"media_id": resp.json()["id"],
                           "draft_id": did})
    assert resp.status_code == 200, resp.text
    assert resp.json()["validation"]["status"] == "invalid"
    assert resp.json()["video_id"] == ""


def test_match_confirm_guards(tmp_path, monkeypatch):
    import sqlite3
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    imp = import_fixture_csv(http, did)
    conn = sqlite3.connect(db)
    try:
        rowids = [r[0] for r in conn.execute(
            "SELECT id FROM ads WHERE import_id=? ORDER BY id",
            (imp["version"],))]
    finally:
        conn.close()
    assert len(rowids) == 3
    # Confirm before any video is validated: refused.
    refused = http.post("/api/drafts/%s/matches/confirm" % did,
                        json={"creative_key": "video-upload-sample",
                              "method": "platform_id",
                              "ad_rowids": rowids})
    assert refused.status_code == 409
    # Unknown row ids are refused, never trusted.
    assert http.post("/api/drafts/%s/matches/propose" % did,
                     json={"creative_key": "video-upload-sample",
                           "method": "fuzzy_filename",
                           "ad_rowids": [999999]}).status_code == 409
    # Validate the video, then propose (unconfirmed) and confirm.
    rec = upload_fixture_video(http)
    assert http.post("/api/videos/validate",
                     json={"media_id": rec["id"],
                           "draft_id": did}).status_code == 200
    prop = http.post("/api/drafts/%s/matches/propose" % did,
                     json={"creative_key": "video-upload-sample",
                           "method": "fuzzy_filename",
                           "ad_rowids": rowids})
    assert prop.json()["match"]["confirmed"] == 0
    done = http.post("/api/drafts/%s/matches/confirm" % did,
                     json={"creative_key": "video-upload-sample",
                           "method": "platform_id",
                           "ad_rowids": rowids})
    assert done.status_code == 200, done.text
    match = done.json()["match"]
    assert match["confirmed"] == 1
    assert len(__import__("json").loads(match["record_json"])) == 3
    # New dataset input invalidates the confirmation.
    import_fixture_csv(http, did)
    conn = sqlite3.connect(db)
    try:
        cleared = conn.execute(
            "SELECT COUNT(*) FROM matches WHERE draft_id=?",
            (did,)).fetchone()[0]
    finally:
        conn.close()
    assert cleared == 0


def test_xlsx_sheet_gate(tmp_path, monkeypatch):
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    header = ["Campaign Name", "Ad Set Name", "Ad Name", "Creative Name",
              "Amount Spent", "Impressions", "Link Clicks"]
    blob = ooxml.build_xlsx([
        {"name": "Meta", "header": header,
         "rows": [["C", "S", "A", "video-upload-sample", 10, 1000, 25]]},
        {"name": "Notes", "header": ["note"], "rows": [["hi"]]},
    ])
    payload = {"draft_id": did, "platform": "meta",
               "filename": "two-sheets.xlsx",
               "xlsx_b64": base64.b64encode(blob).decode()}
    resp = http.post("/api/datasets/import", json=payload)
    assert resp.status_code == 409, resp.text
    assert resp.json()["sheets"] == ["Meta", "Notes"]
    payload["sheet"] = "Meta"
    resp = http.post("/api/datasets/import", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["sheet"] == "Meta"
    assert resp.json()["rows"] == 1
