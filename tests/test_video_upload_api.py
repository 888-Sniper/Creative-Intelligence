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


def test_candidates_scoped_and_view_carries_match(tmp_path, monkeypatch):
    import sqlite3
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    # No dataset yet: empty, not an error.
    assert http.get("/api/drafts/%s/candidates" % did).json() == {
        "candidates": [], "version": ""}
    imp = import_fixture_csv(http, did)
    body = http.get("/api/drafts/%s/candidates" % did).json()
    assert body["version"] == imp["version"]
    assert [r["id"] for r in body["candidates"]] == sorted(
        r["id"] for r in body["candidates"])
    assert len(body["candidates"]) == 3
    assert sum(r["impressions"] for r in body["candidates"]) == 6000
    # A second, unrelated import is invisible to this draft.
    did2 = http.post("/api/drafts", json={}).json()["draft"]["id"]
    with open(CSV_PATH) as fh:
        # Distinct campaign/adset/ad grain: the product sync key does
        # not include creative_key, so same-named ads would update the
        # first draft's facts instead (last write wins, by design).
        other_csv = fh.read().replace("Sample Launch", "Other Launch")
    resp = http.post("/api/datasets/import",
                     json={"draft_id": did2, "platform": "meta",
                           "csv": other_csv})
    assert resp.status_code == 200, resp.text
    assert len(http.get("/api/drafts/%s/candidates" % did).json()[
        "candidates"]) == 3
    # Confirm from the listed ids; the draft view carries the match.
    rowids = [r["id"] for r in body["candidates"]]
    rec = upload_fixture_video(http)
    http.post("/api/videos/validate",
              json={"media_id": rec["id"], "draft_id": did})
    assert http.post("/api/drafts/%s/matches/confirm" % did,
                     json={"creative_key": "video-upload-sample",
                           "method": "platform_id",
                           "ad_rowids": rowids}).status_code == 200
    view = http.get("/api/drafts/%s" % did).json()["draft"]
    assert len(view["matches"]) == 1
    assert view["matches"][0]["confirmed"] == 1
    assert view["live_job_id"] == ""


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


def _rowids(db, version):
    import sqlite3
    conn = sqlite3.connect(db)
    try:
        return [r[0] for r in conn.execute(
            "SELECT id FROM ads WHERE import_id=? ORDER BY id", (version,))]
    finally:
        conn.close()


def _confirmed_setup(http, db, email="owner@foap.test"):
    """Owner draft with validated video + imported dataset and a
    confirmed client/campaign destination; returns
    (draft_id, import_version, rowids)."""
    authed(http, db, email)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    rec = upload_fixture_video(http)
    assert http.post("/api/videos/validate",
                     json={"media_id": rec["id"],
                           "draft_id": did}).status_code == 200
    imp = import_fixture_csv(http, did)
    assert http.patch(
        "/api/drafts/%s" % did,
        json={"spec": {"client": "Foap", "campaign": "Sample Launch",
                       "clientConfirmed": True}}).status_code == 200
    return did, imp["version"], _rowids(db, imp["version"])


def test_stranger_write_matrix_all_403(tmp_path, monkeypatch):
    """Every mutating draft endpoint enforces owner-or-admin, not
    just PATCH/DELETE: validate, import, propose, confirm, analyze."""
    db, http = make_app(tmp_path, monkeypatch)
    did, _version, rowids = _confirmed_setup(http, db)
    rec = upload_fixture_video(http)
    http.headers.clear()
    authed(http, db, "stranger@foap.test", role="employee")
    assert http.post("/api/videos/validate",
                     json={"media_id": rec["id"],
                           "draft_id": did}).status_code == 403
    with open(CSV_PATH) as fh:
        csv_text = fh.read()
    assert http.post("/api/datasets/import",
                     json={"draft_id": did, "platform": "meta",
                           "csv": csv_text}).status_code == 403
    match = {"creative_key": "video-upload-sample",
             "method": "platform_id", "ad_rowids": rowids}
    assert http.post("/api/drafts/%s/matches/propose" % did,
                     json=match).status_code == 403
    assert http.post("/api/drafts/%s/matches/confirm" % did,
                     json=match).status_code == 403
    assert http.post("/api/drafts/%s/analyze" % did,
                     json={}).status_code == 403
    # Reads are owner-or-admin like writes: matched records and
    # analysis must not leak across employees (only the shared
    # media library stays open).
    assert http.get("/api/drafts/%s" % did).status_code == 403
    assert http.get(
        "/api/drafts/%s/candidates" % did).status_code == 403
    assert http.get(
        "/api/drafts/%s/analysis" % did).status_code == 403


def test_cross_draft_rowids_rejected(tmp_path, monkeypatch):
    """Row ids from another draft's dataset version never confirm."""
    db, http = make_app(tmp_path, monkeypatch)
    did1, _v1, r1 = _confirmed_setup(http, db, "owner@foap.test")
    http.headers.clear()
    authed(http, db, "owner2@foap.test")
    did2 = http.post("/api/drafts", json={}).json()["draft"]["id"]
    # Distinct campaign grain so the second import does not upsert
    # the first draft's rows (sync key excludes creative_key).
    with open(CSV_PATH) as fh:
        other_csv = fh.read().replace("Sample Launch", "Other Launch")
    imp2 = http.post("/api/datasets/import",
                     json={"draft_id": did2, "platform": "meta",
                           "csv": other_csv}).json()
    r2 = _rowids(db, imp2["version"])
    assert len(r2) == 3
    http.headers.clear()
    authed(http, db, "owner@foap.test")
    resp = http.post("/api/drafts/%s/matches/confirm" % did1,
                     json={"creative_key": "video-upload-sample",
                           "method": "platform_id", "ad_rowids": r2})
    assert resp.status_code == 409, resp.text
    # Same-draft ids still confirm fine.
    resp = http.post("/api/drafts/%s/matches/confirm" % did1,
                     json={"creative_key": "video-upload-sample",
                           "method": "platform_id", "ad_rowids": r1})
    assert resp.status_code == 200, resp.text


def test_video_swap_clears_confirmation(tmp_path, monkeypatch):
    """Validating a replacement video invalidates the old match."""
    db, http = make_app(tmp_path, monkeypatch)
    did, _version, rowids = _confirmed_setup(http, db)
    assert http.post("/api/drafts/%s/matches/confirm" % did,
                     json={"creative_key": "video-upload-sample",
                           "method": "platform_id",
                           "ad_rowids": rowids}).status_code == 200
    assert len(http.get("/api/drafts/%s" % did).json()["draft"][
        "matches"]) == 1
    rec = upload_fixture_video(http)
    assert http.post("/api/videos/validate",
                     json={"media_id": rec["id"],
                           "draft_id": did}).status_code == 200
    assert http.get("/api/drafts/%s" % did).json()["draft"][
        "matches"] == []


def test_evil_match_key_rejected(tmp_path, monkeypatch):
    """Confirm/propose with an unvalidated key fails, even with real
    row ids: the key must be a validated video on this draft."""
    db, http = make_app(tmp_path, monkeypatch)
    did, _version, rowids = _confirmed_setup(http, db)
    evil = {"creative_key": "../../etc/passwd",
            "method": "platform_id", "ad_rowids": rowids}
    assert http.post("/api/drafts/%s/matches/propose" % did,
                     json=evil).status_code == 409
    resp = http.post("/api/drafts/%s/matches/confirm" % did,
                     json=evil)
    assert resp.status_code == 409, resp.text
    assert "validated video" in resp.json()["error"]


def test_draft_id_collision_across_owners(tmp_path, monkeypatch):
    """A colliding client draft id from another owner is rejected,
    not served as the foreign draft; same-owner retry stays put."""
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db, "owner@foap.test")
    mine = http.post("/api/drafts",
                     json={"draft_id": "shared-id"}).json()["draft"]
    assert mine["owner_employee_id"] != ""
    http.headers.clear()
    authed(http, db, "stranger@foap.test", role="employee")
    resp = http.post("/api/drafts", json={"draft_id": "shared-id"})
    assert resp.status_code == 409, resp.text
    http.headers.clear()
    authed(http, db, "owner@foap.test")
    again = http.post("/api/drafts",
                      json={"draft_id": "shared-id"}).json()["draft"]
    assert again["id"] == mine["id"]


def test_candidates_carry_hand_verifiable_totals(tmp_path, monkeypatch):
    """The HTTP chain (CSV -> DB -> candidates) preserves exact
    counts: 6000 impressions, 150 link clicks, pooled CTR 2.50%."""
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    imp = import_fixture_csv(http, did)
    rows = http.get("/api/drafts/%s/candidates" % did).json()["candidates"]
    assert len(rows) == 3
    total_imp = sum(r["impressions"] for r in rows)
    total_clk = sum(r["link_clicks"] for r in rows)
    assert (total_imp, total_clk) == (6000, 150)
    assert round(total_clk / total_imp * 100, 2) == 2.50
    assert imp["rows"] == 3


def test_oversize_csv_rejected(tmp_path, monkeypatch):
    """CSV payloads past the ingest cap fail closed (M9)."""
    from creative_intel import ingest
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    monkeypatch.setattr(ingest, "MAX_CSV_CHARS", 64)
    with open(CSV_PATH) as fh:
        csv_text = fh.read()
    assert len(csv_text) > 64
    resp = http.post("/api/datasets/import",
                     json={"draft_id": did, "platform": "meta",
                           "csv": csv_text})
    assert resp.status_code == 409, resp.text
    assert "too large" in resp.json()["error"]


def test_validate_probe_unavailable(tmp_path, monkeypatch):
    """No ffprobe on PATH is an honest verdict, not a crash (M4)."""
    from creative_intel import video_validate
    monkeypatch.setenv("PATH", str(tmp_path))
    assert video_validate.validate(
        MP4_PATH, filename="sample.mp4")["reason"] == "probe_unavailable"


def test_validate_unit_rejections(tmp_path):
    """ffprobe verdict codes without HTTP: oversize, too long,
    empty, bad container, corrupt (M4)."""
    from creative_intel import video_validate
    empty = str(tmp_path / "empty.mp4")
    open(empty, "wb").close()
    assert video_validate.validate(empty)["reason"] == "empty"
    assert video_validate.validate(
        MP4_PATH, filename="clip.avi")["reason"] == "unsupported_container"
    assert video_validate.validate(
        MP4_PATH, max_bytes=10)["reason"] == "oversize"
    assert video_validate.validate(
        MP4_PATH, max_duration_s=1.0)["reason"] == "too_long"
    assert video_validate.validate(
        MP4_PATH, filename="sample.mp4")["status"] == "valid"
    # Garbage that passes the magic prefix fails at ffprobe.
    bad = str(tmp_path / "bad.mp4")
    with open(bad, "wb") as fh:
        fh.write(b"\x00\x00\x00\x18ftyp" + b"not a video" * 64)
    assert video_validate.validate(bad)["reason"] == "corrupt"


def test_patch_rejects_worker_mirrored_status(tmp_path, monkeypatch):
    """Recheck M1: queued/analyzing/failed are worker-mirrored; a
    client PATCH claiming them is a 409, and the draft is untouched."""
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db, "owner@foap.test", role="employee")
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    for forged in ("queued", "analyzing", "failed"):
        resp = http.patch("/api/drafts/%s" % did,
                          json={"status": forged})
        assert resp.status_code == 409, (forged, resp.text)
    draft = http.get("/api/drafts/%s" % did).json()["draft"]
    assert draft["status"] == "draft"
    # Reviewed is a recorded verdict, never a free flip: even the
    # owner gets a 409 pointing at the review operation.
    no_free = http.patch("/api/drafts/%s" % did,
                         json={"status": "reviewed"})
    assert no_free.status_code == 409, no_free.text
    assert "/review" in no_free.json()["error"]
    ok = http.patch("/api/drafts/%s" % did,
                    json={"status": "needs_confirmation"})
    assert ok.status_code == 200, ok.text


def test_validate_without_draft_mints_owned_draft(tmp_path, monkeypatch):
    """Recheck M2/M6: draft-less validation binds the video to a new
    caller-owned draft instead of 409ing on an orphan row."""
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db, "owner@foap.test", role="employee")
    rec = upload_fixture_video(http)
    resp = http.post("/api/videos/validate",
                     json={"media_id": rec["id"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["video_id"] != ""
    assert body["draft_id"] != ""
    draft = http.get("/api/drafts/%s" % body["draft_id"]).json()["draft"]
    assert [v["id"] for v in draft["videos"]] == [body["video_id"]]
    # The minted draft is owned: a stranger cannot touch it.
    http.headers.clear()
    authed(http, db, "stranger@foap.test", role="employee")
    assert http.patch("/api/drafts/%s" % body["draft_id"],
                      json={"status": "cancelled"}).status_code == 403


def test_replace_video_supersedes(tmp_path, monkeypatch):
    """Audit A2: re-validating replaces the draft's video rows — one
    active version, and the binder resolves the latest one."""
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db)
    rec = upload_fixture_video(http)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    first = http.post("/api/videos/validate",
                      json={"media_id": rec["id"],
                            "draft_id": did}).json()
    rec2 = upload_fixture_video(http)
    second = http.post("/api/videos/validate",
                       json={"media_id": rec2["id"],
                             "draft_id": did}).json()
    assert second["video_id"] != first["video_id"]
    videos = http.get("/api/drafts/%s" % did).json()["draft"]["videos"]
    assert [v["id"] for v in videos] == [second["video_id"]]


def test_delete_videos_endpoint(tmp_path, monkeypatch):
    """Audit A2: explicit removal drops the stored relationship, so a
    removed video cannot resurrect on reopen."""
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db, "owner@foap.test", role="employee")
    rec = upload_fixture_video(http)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    assert http.post("/api/videos/validate",
                     json={"media_id": rec["id"],
                           "draft_id": did}).status_code == 200
    gone = http.delete("/api/drafts/%s/videos" % did)
    assert gone.status_code == 200, gone.text
    assert gone.json()["removed"] == 1
    assert http.get("/api/drafts/%s" % did).json()["draft"][
        "videos"] == []
    http.headers.clear()
    authed(http, db, "stranger@foap.test", role="employee")
    assert http.delete(
        "/api/drafts/%s/videos" % did).status_code == 403


def test_campaign_scope_enforced(tmp_path, monkeypatch):
    """Audit A3: with a confirmed campaign, propose/confirm accept
    only rows of that campaign; unconfirmed drafts stay permissive."""
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
    rec = upload_fixture_video(http)
    assert http.post("/api/videos/validate",
                     json={"media_id": rec["id"],
                           "draft_id": did}).status_code == 200
    # Confirmed campaign "Sample Launch": its own rows pass...
    assert http.patch(
        "/api/drafts/%s" % did,
        json={"spec": {"client": "Foap", "campaign": "Sample Launch",
                       "clientConfirmed": True}}).status_code == 200
    good = {"creative_key": "video-upload-sample", "method": "manual",
            "ad_rowids": rowids}
    assert http.post("/api/drafts/%s/matches/confirm" % did,
                     json=good).status_code == 200
    # ...while foreign-campaign rows are refused at propose and
    # confirm alike.
    other_csv = ("Campaign Name,Ad Set Name,Ad Name,Creative Name,"
                 "Amount Spent,Impressions,Link Clicks\n"
                 "Other Campaign,Prospecting,Other Ad,"
                 "video-upload-sample,5.00,500,10\n")
    other = http.post("/api/datasets/import",
                      json={"draft_id": did, "platform": "meta",
                            "filename": "other.csv",
                            "csv": other_csv}).json()
    conn = sqlite3.connect(db)
    try:
        foreign = [r[0] for r in conn.execute(
            "SELECT id FROM ads WHERE import_id=?", (other["version"],))]
    finally:
        conn.close()
    assert len(foreign) == 1
    evil = {"creative_key": "video-upload-sample", "method": "manual",
            "ad_rowids": foreign}
    assert http.post("/api/drafts/%s/matches/propose" % did,
                     json=evil).status_code == 409
    assert http.post("/api/drafts/%s/matches/confirm" % did,
                     json=evil).status_code == 409


def _seed_reviewable(conn, draft_id, revision="r1"):
    """Insert a fully valid stored analysis whose snapshot matches
    the draft's live inputs (what a real pipeline run persists)."""
    import json as _json
    from creative_intel import creative as creative_mod
    seed = creative_mod.blank_annotation()
    seed["schema_version"] = "v0"
    seed["status"] = "auto"
    import json as _spec_json
    try:
        _spec = _spec_json.loads(conn.execute(
            "SELECT spec_json FROM drafts WHERE id=?",
            (draft_id,)).fetchone()[0] or "{}")
    except ValueError:
        _spec = {}
    video = conn.execute(
        "SELECT id, media_id, sha256 FROM videos WHERE draft_id=?",
        (draft_id,)).fetchone()
    seed["analysis"] = {
        "version": "v1", "revision": revision,
        "snapshot": {
            "video_id": video[0],
            "media_id": video[1],
            "video_sha256": video[2],
            "dataset_version": conn.execute(
                "SELECT dataset_version FROM drafts WHERE id=?",
                (draft_id,)).fetchone()[0],
            "match_confirmed_at": conn.execute(
                "SELECT confirmed_at FROM matches WHERE draft_id=?",
                (draft_id,)).fetchone()[0],
            "client": _spec.get("client") or "",
            "campaign": _spec.get("campaign") or "",
            "match_method": "manual"}}
    creative_mod.save_annotation(conn, "video-upload-sample", seed,
                                 video_id=video[0])
    conn.commit()


def test_reconfirm_invalidates_review(tmp_path, monkeypatch):
    """Audit followup (major): a confirmation recorded after a review
    supersedes the approval — the draft falls back out of reviewed."""
    import json as _json
    import sqlite3
    db, http = make_app(tmp_path, monkeypatch)
    did, _version, rowids = _confirmed_setup(http, db)
    match = {"creative_key": "video-upload-sample", "method": "manual",
             "ad_rowids": rowids}
    assert http.post("/api/drafts/%s/matches/confirm" % did,
                     json=match).status_code == 200
    conn = sqlite3.connect(db)
    try:
        _seed_reviewable(conn, did, revision="r0")
    finally:
        conn.close()
    assert http.patch("/api/drafts/%s" % did,
                      json={"status": "ready_for_review"}).status_code == 200
    done = http.post("/api/drafts/%s/review" % did,
                     json={"analysis_version": "v1", "revision": "r0"})
    assert done.status_code == 200, done.text
    assert done.json()["draft"]["status"] == "reviewed"
    again = http.post("/api/drafts/%s/matches/confirm" % did,
                      json=match)
    assert again.status_code == 200, again.text
    draft = http.get("/api/drafts/%s" % did).json()["draft"]
    assert draft["status"] == "needs_confirmation"
    assert draft["review"] == {}


def test_campaign_scope_permissive_until_confirmed(tmp_path, monkeypatch):
    """Audit followup: without a confirmed selection, cross-campaign
    rows stay explorable (propose 200); confirmation is the gate."""
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
    rec = upload_fixture_video(http)
    assert http.post("/api/videos/validate",
                     json={"media_id": rec["id"],
                           "draft_id": did}).status_code == 200
    # Unconfirmed selection recorded but not confirmed: permissive.
    assert http.patch(
        "/api/drafts/%s" % did,
        json={"spec": {"client": "Foap", "campaign": "Sample Launch",
                       "clientConfirmed": False}}).status_code == 200
    loose = {"creative_key": "video-upload-sample", "method": "manual",
             "ad_rowids": rowids}
    assert http.post("/api/drafts/%s/matches/propose" % did,
                     json=loose).status_code == 200


def test_review_op_and_invalidation(tmp_path, monkeypatch):
    """Audit A7: review is version-bound with reviewer identity, and
    a later material input change invalidates it."""
    import json as _json
    import sqlite3
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db, "owner@foap.test", role="employee")
    rec = upload_fixture_video(http)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    assert http.post("/api/videos/validate",
                     json={"media_id": rec["id"],
                           "draft_id": did}).status_code == 200
    imp = import_fixture_csv(http, did)
    assert http.patch(
        "/api/drafts/%s" % did,
        json={"spec": {"client": "Foap", "campaign": "Sample Launch",
                       "clientConfirmed": True}}).status_code == 200
    conn = sqlite3.connect(db)
    try:
        rowids = [r[0] for r in conn.execute(
            "SELECT id FROM ads WHERE import_id=?", (imp["version"],))]
    finally:
        conn.close()
    match = {"creative_key": "video-upload-sample", "method": "manual",
             "ad_rowids": rowids}
    assert http.post("/api/drafts/%s/matches/confirm" % did,
                     json=match).status_code == 200
    conn = sqlite3.connect(db)
    try:
        _seed_reviewable(conn, did, revision="r0")
    finally:
        conn.close()
    assert http.patch("/api/drafts/%s" % did,
                      json={"status": "ready_for_review"}).status_code == 200
    stale = http.post("/api/drafts/%s/review" % did,
                      json={"analysis_version": "v0", "revision": "r0"})
    assert stale.status_code == 409, stale.text
    done = http.post("/api/drafts/%s/review" % did,
                     json={"analysis_version": "v1", "revision": "r0",
                           "note": "checked totals"})
    assert done.status_code == 200, done.text
    assert done.json()["draft"]["status"] == "reviewed"
    assert done.json()["review"]["analysis_version"] == "v1"
    assert done.json()["review"]["note"] == "checked totals"
    # A material input change invalidates the approval.
    assert http.post("/api/videos/validate",
                     json={"media_id": rec["id"],
                           "draft_id": did}).status_code == 200
    draft = http.get("/api/drafts/%s" % did).json()["draft"]
    assert draft["status"] == "needs_confirmation"
    assert draft["review"] == {}
    # Strangers cannot review someone else's draft.
    http.headers.clear()
    authed(http, db, "stranger@foap.test", role="employee")
    assert http.post("/api/drafts/%s/review" % did,
                     json={"analysis_version": "v1"}).status_code == 403


def test_delete_draft_erases_unreferenced_content(tmp_path, monkeypatch):
    """Audit A9: deleting a draft erases its unreferenced media file,
    media row, and annotation — but keeps assets another draft still
    references."""
    import json as _json
    import os
    import sqlite3
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db)
    rec = upload_fixture_video(http)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    assert http.post("/api/videos/validate",
                     json={"media_id": rec["id"],
                           "draft_id": did}).status_code == 200
    did2 = http.post("/api/drafts", json={}).json()["draft"]["id"]
    assert http.post("/api/videos/validate",
                     json={"media_id": rec["id"],
                           "draft_id": did2}).status_code == 200
    conn = sqlite3.connect(db)
    try:
        path = conn.execute(
            "SELECT stored_name FROM media WHERE id=?",
            (rec["id"],)).fetchone()[0]
        conn.execute(
            "INSERT INTO annotations (creative_key, schema_version,"
            " annotation_json, updated_at) VALUES ("
            "'video-upload-sample', 'v0', ?, '')",
            (_json.dumps({"status": "auto"}),))
        conn.commit()
    finally:
        conn.close()
    media_dir = os.environ["CREATIVE_INTEL_MEDIA_DIR"]
    assert os.path.isfile(os.path.join(media_dir, path))
    # Shared by did2: the first delete keeps everything.
    assert http.delete("/api/drafts/%s" % did).status_code == 200
    conn = sqlite3.connect(db)
    try:
        kept = conn.execute("SELECT COUNT(*) FROM media WHERE id=?",
                            (rec["id"],)).fetchone()[0]
    finally:
        conn.close()
    assert kept == 1
    assert os.path.isfile(os.path.join(media_dir, path))
    # Last reference gone: row, file, and annotation are erased.
    assert http.delete("/api/drafts/%s" % did2).status_code == 200
    conn = sqlite3.connect(db)
    try:
        kept = conn.execute("SELECT COUNT(*) FROM media WHERE id=?",
                            (rec["id"],)).fetchone()[0]
        ann = conn.execute(
            "SELECT COUNT(*) FROM annotations WHERE creative_key=?",
            ("video-upload-sample",)).fetchone()[0]
    finally:
        conn.close()
    assert kept == 0
    assert ann == 0
    assert not os.path.isfile(os.path.join(media_dir, path))


def test_media_serving_requires_draft_binding(tmp_path, monkeypatch):
    """Recheck round 3: /media/{id} serves owners/admins bound via a
    draft, and 403s authenticated strangers."""
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db, "owner@foap.test", role="employee")
    rec = upload_fixture_video(http)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    assert http.post("/api/videos/validate",
                     json={"media_id": rec["id"],
                           "draft_id": did}).status_code == 200
    assert http.get("/media/%s" % rec["id"]).status_code == 200
    http.headers.clear()
    authed(http, db, "stranger@foap.test", role="employee")
    resp = http.get("/media/%s" % rec["id"])
    assert resp.status_code == 403, resp.text
    http.headers.clear()
    authed(http, db)
    assert http.get("/media/%s" % rec["id"]).status_code == 200


def test_patch_dataset_version_allow_listed(tmp_path, monkeypatch):
    """Recheck round 3: the version pointer only accepts this draft's
    own imports — never an arbitrary import id."""
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    imp = import_fixture_csv(http, did)
    ok = http.patch("/api/drafts/%s" % did,
                    json={"dataset_version": imp["version"]})
    assert ok.status_code == 200, ok.text
    assert http.patch("/api/drafts/%s" % did,
                      json={"dataset_version": "deadbeefcafe"}
                      ).status_code == 409


def test_review_binds_revision_and_snapshot(tmp_path, monkeypatch):
    """Recheck round 3: approval needs the stored unique revision and
    a snapshot that still matches live inputs; success marks the
    annotation human_verified for the export gate."""
    import json as _json
    import sqlite3
    db, http = make_app(tmp_path, monkeypatch)
    did, _version, rowids = _confirmed_setup(http, db)
    match = {"creative_key": "video-upload-sample", "method": "manual",
             "ad_rowids": rowids}
    assert http.post("/api/drafts/%s/matches/confirm" % did,
                     json=match).status_code == 200
    conn = sqlite3.connect(db)
    try:
        _seed_reviewable(conn, did, revision="r1")
    finally:
        conn.close()
    assert http.patch("/api/drafts/%s" % did,
                      json={"status": "ready_for_review"}).status_code == 200
    # Wrong revision: refused even though the version matches.
    assert http.post("/api/drafts/%s/review" % did,
                     json={"analysis_version": "v1",
                           "revision": "stale"}).status_code == 409
    done = http.post("/api/drafts/%s/review" % did,
                     json={"analysis_version": "v1", "revision": "r1"})
    assert done.status_code == 200, done.text
    conn = sqlite3.connect(db)
    try:
        status = _json.loads(conn.execute(
            "SELECT annotation_json FROM annotations WHERE creative_key=?",
            ("video-upload-sample",)).fetchone()[0])["status"]
    finally:
        conn.close()
    assert status == "human_verified"
    # Inputs change after the run: the same revision is now stale.
    with open(CSV_PATH) as fh:
        csv_text = fh.read()
    assert http.post("/api/datasets/import",
                     json={"draft_id": did, "platform": "meta",
                           "filename": "fixture.csv",
                           "csv": csv_text}).status_code == 200
    assert http.patch("/api/drafts/%s" % did,
                      json={"status": "ready_for_review"}).status_code == 200
    stale = http.post("/api/drafts/%s/review" % did,
                      json={"analysis_version": "v1", "revision": "r1"})
    assert stale.status_code == 409, stale.text


def test_replace_reaps_old_media(tmp_path, monkeypatch):
    """Recheck round 3: replacing the video erases the displaced
    media row and file when nothing else references them."""
    import os
    import sqlite3
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db)
    first = upload_fixture_video(http)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    assert http.post("/api/videos/validate",
                     json={"media_id": first["id"],
                           "draft_id": did}).status_code == 200
    # Genuinely different bytes (identical uploads dedup to the same
    # media row, which must then be kept as still-referenced).
    with open(MP4_PATH, "rb") as fh:
        blob = fh.read() + b"\x00" * 64
    resp = http.post("/api/media/upload",
                     data={"creative_key": "video-upload-sample"},
                     files={"file": ("sample2.mp4", blob, "video/mp4")})
    assert resp.status_code == 200, resp.text
    second = resp.json()
    assert second["id"] != first["id"]
    assert http.post("/api/videos/validate",
                     json={"media_id": second["id"],
                           "draft_id": did}).status_code == 200
    media_dir = os.environ["CREATIVE_INTEL_MEDIA_DIR"]
    conn = sqlite3.connect(db)
    try:
        gone = conn.execute("SELECT stored_name FROM media WHERE id=?",
                            (first["id"],)).fetchone()
    finally:
        conn.close()
    assert gone is None


def test_client_enforced_when_both_sides_carry_it(tmp_path,
                                                  monkeypatch):
    """Recheck round 3: records naming a different client than the
    confirmed selection are refused; client-less rows stay usable."""
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    two_clients = ("Campaign Name,Ad Set Name,Ad Name,Creative Name,"
                   "Client,Amount Spent,Impressions,Link Clicks\n"
                   "Sample Launch,Prospecting,Sample Story V1,"
                   "video-upload-sample,Foap,10.00,1000,25\n"
                   "Sample Launch,Prospecting,Sample Story V1,"
                   "video-upload-sample,Rival,10.00,1000,25\n")
    imp = http.post("/api/datasets/import",
                    json={"draft_id": did, "platform": "meta",
                          "filename": "clients.csv",
                          "csv": two_clients}).json()
    assert imp["rows"] == 2, imp
    import sqlite3
    conn = sqlite3.connect(db)
    try:
        ids = {r[0]: r[1] for r in conn.execute(
            "SELECT id, client FROM ads WHERE import_id=?",
            (imp["version"],))}
    finally:
        conn.close()
    rec = upload_fixture_video(http)
    assert http.post("/api/videos/validate",
                     json={"media_id": rec["id"],
                           "draft_id": did}).status_code == 200
    assert http.patch(
        "/api/drafts/%s" % did,
        json={"spec": {"client": "Foap", "campaign": "Sample Launch",
                       "clientConfirmed": True}}).status_code == 200
    rival = [rid for rid, client in ids.items() if client == "Rival"]
    assert len(rival) == 1
    evil = {"creative_key": "video-upload-sample", "method": "manual",
            "ad_rowids": rival}
    assert http.post("/api/drafts/%s/matches/confirm" % did,
                     json=evil).status_code == 409
    own = [rid for rid, client in ids.items() if client == "Foap"]
    good = {"creative_key": "video-upload-sample", "method": "manual",
            "ad_rowids": own}
    assert http.post("/api/drafts/%s/matches/confirm" % did,
                     json=good).status_code == 200


def test_delete_draft_cancels_bound_jobs(tmp_path, monkeypatch):
    """Deleting a draft cancels its queued/running analysis jobs so
    no orphan job lingers or mirrors onto a gone draft."""
    import sqlite3
    from creative_intel import jobs as jobs_mod
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    conn = sqlite3.connect(db)
    try:
        jobs_mod.ensure(conn)
        job = jobs_mod.enqueue(conn, "video_analysis",
                               {"snapshot": {"draft_id": did}}, owner="")
        conn.commit()
        jid = job["id"]
    finally:
        conn.close()
    assert http.delete("/api/drafts/%s" % did).status_code == 200
    conn = sqlite3.connect(db)
    try:
        status = conn.execute(
            "SELECT status FROM worker_jobs WHERE id=?",
            (jid,)).fetchone()[0]
    finally:
        conn.close()
    assert status == "cancelled"


def test_media_entitlement_blocks_attach_then_download(tmp_path, monkeypatch):
    """Recheck round 4: validating another employee's media id against
    one's own draft 403s — the new binding can never launder download
    access. Uploader, draft-bound owner, and admin keep access."""
    import sqlite3
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db, "alice@foap.test", role="employee")
    rec = upload_fixture_video(http)
    alice_did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    assert http.post("/api/videos/validate",
                     json={"media_id": rec["id"],
                           "draft_id": alice_did}).status_code == 200
    assert http.get("/media/%s" % rec["id"]).status_code == 200
    # Bob has no connection: download denied...
    http.headers.clear()
    authed(http, db, "bob@foap.test", role="employee")
    assert http.get("/media/%s" % rec["id"]).status_code == 403
    # ...and attaching Alice's id to Bob's own draft is refused, so
    # the binding that would satisfy the download check is never
    # created.
    bob_did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    resp = http.post("/api/videos/validate",
                     json={"media_id": rec["id"], "draft_id": bob_did})
    assert resp.status_code == 403, resp.text
    assert http.get("/media/%s" % rec["id"]).status_code == 403
    conn = sqlite3.connect(db)
    try:
        bound = conn.execute(
            "SELECT COUNT(*) FROM videos WHERE draft_id=? AND media_id=?",
            (bob_did, rec["id"])).fetchone()[0]
    finally:
        conn.close()
    assert bound == 0
    # Bob's own upload validates and serves fine.
    own = upload_fixture_video(http)
    assert http.post("/api/videos/validate",
                     json={"media_id": own["id"],
                           "draft_id": bob_did}).status_code == 200
    assert http.get("/media/%s" % own["id"]).status_code == 200
    # Admins stay exempt for support/debugging.
    http.headers.clear()
    authed(http, db, "root@foap.test", role="admin")
    assert http.get("/media/%s" % rec["id"]).status_code == 200


def test_corrections_rewrite_findings_and_invalidate_review(
        tmp_path, monkeypatch):
    """Recheck round 4: transcript/hook/timestamp/test corrections
    land on the stored finding with a fresh revision, and supersede
    any approval of the old content. Unknown fields and test ids 409;
    strangers 403."""
    import json as _json
    import sqlite3
    db, http = make_app(tmp_path, monkeypatch)
    did, _version, rowids = _confirmed_setup(http, db)
    match = {"creative_key": "video-upload-sample", "method": "manual",
             "ad_rowids": rowids}
    assert http.post("/api/drafts/%s/matches/confirm" % did,
                     json=match).status_code == 200
    conn = sqlite3.connect(db)
    try:
        _seed_reviewable(conn, did, revision="r0")
    finally:
        conn.close()
    assert http.patch("/api/drafts/%s" % did,
                      json={"status": "ready_for_review"}).status_code == 200
    # Nothing to aim at without suggested tests: seed one.
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            "SELECT annotation_json FROM annotations WHERE creative_key=?",
            ("video-upload-sample",)).fetchone()[0]
        ann = _json.loads(row)
        ann["analysis"]["suggested_tests"] = [
            {"id": "hook-clarity", "hypothesis": "Try a clearer hook.",
             "why": "uncertain hook", "evidence": [],
             "status": "suggested"}]
        conn.execute("UPDATE annotations SET annotation_json=? "
                     "WHERE creative_key=?",
                     (_json.dumps(ann), "video-upload-sample"))
        conn.commit()
    finally:
        conn.close()
    # Approve the old content first: the correction must supersede it.
    done = http.post("/api/drafts/%s/review" % did,
                     json={"analysis_version": "v1", "revision": "r0"})
    assert done.status_code == 200, done.text
    fixed = http.post(
        "/api/drafts/%s/corrections" % did,
        json={"transcript": "corrected words",
              "hook_type": "bold_claim", "hook_confidence": 0.8,
              "frame_labels": [{"t_sec": 2.5, "label": "opening",
                                "cta_visible": True}],
              "tests": [{"id": "hook-clarity", "status": "accepted"}]})
    assert fixed.status_code == 200, fixed.text
    body = fixed.json()
    assert body["revision"] != "r0"
    stored = body["annotation"]
    assert stored["hook_type"] == "bold_claim"
    assert stored["hook_confidence"] == 0.8
    assert stored["confirmed"]["hook_type"] == "bold_claim"
    assert stored["frame_labels"] == [
        {"t_sec": 2.5, "label": "opening", "cta_visible": True,
         "text_overlay": ""}]
    assert stored["analysis"]["suggested_tests"][0]["status"] == "accepted"
    assert stored["analysis"]["corrections"][0]["fields"] == [
        "frame_labels", "hook_confidence", "hook_type", "tests",
        "transcript"]
    conn = sqlite3.connect(db)
    try:
        words = conn.execute(
            "SELECT transcript FROM creatives WHERE creative_key=?",
            ("video-upload-sample",)).fetchone()[0]
    finally:
        conn.close()
    assert words == "corrected words"
    # The old approval no longer covers the new content.
    draft = body["draft"]
    assert draft["review"] == {}
    assert draft["status"] != "reviewed"
    # Re-review binds the fresh revision.
    assert http.patch("/api/drafts/%s" % did,
                      json={"status": "ready_for_review"}).status_code == 200
    again = http.post(
        "/api/drafts/%s/review" % did,
        json={"analysis_version": "v1", "revision": body["revision"]})
    assert again.status_code == 200, again.text
    # Fail-closed inputs.
    assert http.post("/api/drafts/%s/corrections" % did,
                     json={"hook_type": "not_a_hook"}).status_code == 409
    assert http.post("/api/drafts/%s/corrections" % did,
                     json={"tests": [{"id": "nope",
                                      "status": "accepted"}]}).status_code \
        == 409
    assert http.post("/api/drafts/%s/corrections" % did,
                     json={"colour": "teal"}).status_code == 409
    assert http.post("/api/drafts/%s/corrections" % did,
                     json={}).status_code == 409
    http.headers.clear()
    authed(http, db, "stranger@foap.test", role="employee")
    assert http.post("/api/drafts/%s/corrections" % did,
                     json={"hook_type": "question"}).status_code == 403


def test_analyze_requires_confirmed_destination(tmp_path, monkeypatch):
    """Recheck round 4: an unconfirmed (or unnamed) client/campaign
    selection blocks combined analysis at bind time, while saving the
    incomplete draft stays allowed."""
    import sqlite3
    db, http = make_app(tmp_path, monkeypatch)
    did, _version, rowids = _confirmed_setup(http, db)
    match = {"creative_key": "video-upload-sample", "method": "manual",
             "ad_rowids": rowids}
    assert http.post("/api/drafts/%s/matches/confirm" % did,
                     json=match).status_code == 200
    # Drop the confirmation: saving is fine, analysing refuses.
    assert http.patch(
        "/api/drafts/%s" % did,
        json={"spec": {"client": "Foap", "campaign": "Sample Launch",
                       "clientConfirmed": False}}).status_code == 200
    resp = http.post("/api/drafts/%s/analyze" % did, json={})
    assert resp.status_code == 409, resp.text
    assert "confirm the client and campaign" in resp.json()["error"]
    # Confirmed flag but no names: still refused.
    assert http.patch(
        "/api/drafts/%s" % did,
        json={"spec": {"client": "", "campaign": "",
                       "clientConfirmed": True}}).status_code == 200
    resp = http.post("/api/drafts/%s/analyze" % did, json={})
    assert resp.status_code == 409, resp.text
    conn = sqlite3.connect(db)
    try:
        live = conn.execute("SELECT COUNT(*) FROM worker_jobs WHERE kind=?"
                            " AND status IN ('queued','running')",
                            ("video_analysis",)).fetchone()[0]
    finally:
        conn.close()
    assert live == 0


def test_delete_draft_clears_generated_transcript(tmp_path, monkeypatch):
    """Recheck round 4: the last referencing draft's delete clears the
    generated transcript and pipeline record with the annotation (the
    creatives row itself stays as reporting identity)."""
    import sqlite3
    db, http = make_app(tmp_path, monkeypatch)
    authed(http, db)
    rec = upload_fixture_video(http)
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    assert http.post("/api/videos/validate",
                     json={"media_id": rec["id"],
                           "draft_id": did}).status_code == 200
    conn = sqlite3.connect(db)
    try:
        conn.execute("INSERT INTO creatives (creative_key, transcript,"
                     " pipeline_json) VALUES (?, ?, ?)",
                     ("video-upload-sample", "generated words",
                      "[{\"stage\": \"x\"}]"))
        conn.commit()
    finally:
        conn.close()
    assert http.delete("/api/drafts/%s" % did).status_code == 200
    conn = sqlite3.connect(db)
    try:
        row = conn.execute("SELECT transcript, pipeline_json FROM creatives"
                           " WHERE creative_key=?",
                           ("video-upload-sample",)).fetchone()
    finally:
        conn.close()
    assert row == ("", "{}")


def test_confirm_dedupes_record_ids(tmp_path, monkeypatch):
    """Round-6 validation: confirming [id, id] freezes one record,
    so the canonical selected-record set counts its impressions
    once, not twice."""
    import json as _json
    db, http = make_app(tmp_path, monkeypatch)
    did, _version, rowids = _confirmed_setup(http, db)
    match = {"creative_key": "video-upload-sample",
             "method": "platform_id",
             "ad_rowids": [rowids[0], rowids[0]]}
    done = http.post("/api/drafts/%s/matches/confirm" % did, json=match)
    assert done.status_code == 200, done.text
    stored = _json.loads(done.json()["match"]["record_json"])
    assert [r["id"] for r in stored] == [rowids[0]]


def test_confirm_freezes_complete_snapshot_and_video(tmp_path, monkeypatch):
    """Round-6 recheck 2 (HTTP): the frozen snapshot carries every
    ads column — revenue, reach, market, conversion event — and the
    match freezes the bound video version for later reporting."""
    import json as _json
    import sqlite3
    db, http = make_app(tmp_path, monkeypatch)
    did, _version, rowids = _confirmed_setup(http, db)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "UPDATE ads SET revenue=240.0, revenue_reported=1,"
            " reach=4500, market='MY', conversion_event='purchase',"
            " client='' WHERE id=?", (rowids[0],))
        conn.commit()
    finally:
        conn.close()
    match = {"creative_key": "video-upload-sample",
             "method": "platform_id", "ad_rowids": [rowids[0]]}
    done = http.post("/api/drafts/%s/matches/confirm" % did, json=match)
    assert done.status_code == 200, done.text
    stored = _json.loads(done.json()["match"]["record_json"])
    assert stored[0]["revenue"] == 240.0
    assert stored[0]["reach"] == 4500
    assert stored[0]["market"] == "MY"
    assert stored[0]["conversion_event"] == "purchase"
    conn = sqlite3.connect(db)
    try:
        frozen = conn.execute(
            "SELECT video_id FROM matches WHERE draft_id=?",
            (did,)).fetchone()[0]
        valid = [vid for vid, vj in conn.execute(
            "SELECT id, validation_json FROM videos WHERE draft_id=?",
            (did,)).fetchall() if '"valid"' in (vj or "")]
    finally:
        conn.close()
    assert frozen != ""
    assert frozen in valid
