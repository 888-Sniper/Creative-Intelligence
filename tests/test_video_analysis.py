"""WP5+WP6: analysis math, snapshot binding, run, endpoints.

Provider doubles are explicit test stubs (never production mocks):
the no-live-provider path is asserted honest, and the full run uses
the real fixture clip through real ffmpeg (skipped without it).
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import employees as emp_store  # noqa: E402
from ci_backend.app import create_app  # noqa: E402
from ci_backend.config import Settings  # noqa: E402
from conftest import employee_session  # noqa: E402
from creative_intel import creative as creative_mod  # noqa: E402
from creative_intel import drafts, ingest, jobs as jobs_mod  # noqa: E402
from creative_intel import media as media_mod  # noqa: E402
from creative_intel import schema, video as video_mod  # noqa: E402
from creative_intel import video_analysis as va  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")
MP4_PATH = os.path.join(FIXTURES, "Video Upload Sample 720p.mp4")
CSV_PATH = os.path.join(FIXTURES, "Video Upload Sample Dataset.csv")

NEEDS_FFMPEG = pytest.mark.skipif(
    not video_mod.have_ffmpeg(), reason="ffmpeg not installed")

RECORDS = [
    {"id": 1, "import_id": "imp", "platform": "meta",
     "campaign": "Sample Launch", "adset": "Prospecting AU",
     "ad_name": "Sample Story V1", "creative_key": "video-upload-sample",
     "spend": 10.0, "impressions": 1000, "clicks": 30, "link_clicks": 25,
     "conversions": 2, "video_views": 400, "views_25": 300,
     "views_50": 200, "views_75": 100, "views_100": 50,
     "currency": "USD", "date": "", "client": "", "placement": ""},
    {"id": 2, "import_id": "imp", "platform": "meta",
     "campaign": "Sample Launch", "adset": "Retargeting AU",
     "ad_name": "Sample Story V1", "creative_key": "video-upload-sample",
     "spend": 20.0, "impressions": 2000, "clicks": 60, "link_clicks": 50,
     "conversions": 4, "video_views": 800, "views_25": 600,
     "views_50": 400, "views_75": 200, "views_100": 100,
     "currency": "USD", "date": "", "client": "", "placement": ""},
    {"id": 3, "import_id": "imp", "platform": "meta",
     "campaign": "Sample Launch", "adset": "Broad AU",
     "ad_name": "Sample Story V1", "creative_key": "video-upload-sample",
     "spend": 30.0, "impressions": 3000, "clicks": 90, "link_clicks": 75,
     "conversions": 6, "video_views": 1200, "views_25": 900,
     "views_50": 600, "views_75": 300, "views_100": 150,
     "currency": "USD", "date": "", "client": "", "placement": ""},
]


def test_measured_pools_before_dividing():
    measured = va.measured_from_records(RECORDS)
    assert measured["totals"]["impressions"] == 6000
    assert measured["totals"]["link_clicks"] == 150
    # Pooled 150/6000*100, not the average of row rates.
    assert measured["pooled_link_ctr_pct"] == 2.5
    assert measured["totals"]["spend"] == 60.0
    assert measured["warnings"] == []


def test_measured_zero_denominator_yields_no_rate():
    measured = va.measured_from_records(
        [dict(RECORDS[0], impressions=0, link_clicks=0)])
    assert measured["pooled_link_ctr_pct"] is None
    assert any("no rate computed" in w for w in measured["warnings"])


def test_measured_mixed_currency_warns():
    recs = [dict(RECORDS[0]), dict(RECORDS[1], currency="PLN")]
    measured = va.measured_from_records(recs)
    assert any("mixed currencies" in w for w in measured["warnings"])


def test_suggest_tests_grounded_in_absences():
    ann = {"hook_confidence": 0.2, "frame_labels": [
        {"t_sec": 1.0, "cta_visible": False}],
        "execution": {"product_first_s": None}}
    tests = va.suggest_tests(ann, {}, transcript="")
    ids = [t["id"] for t in tests]
    assert ids == ["hook-clarity", "cta-presence", "product-timing",
                   "silent-cut"]
    assert all(t["status"] == "suggested" for t in tests)
    assert "guarantee" not in json.dumps(tests).lower()
    # Confident hook + visible CTA + product + speech: nothing to suggest.
    ann2 = {"hook_confidence": 0.9, "frame_labels": [
        {"t_sec": 1.0, "cta_visible": True}],
        "execution": {"product_first_s": 1.0}}
    assert va.suggest_tests(ann2, {}, transcript="hello") == []


def bound_db(tmp_path):
    """Product db with a fully confirmable draft (no providers)."""
    db = str(tmp_path / "va.db")
    conn = sqlite3.connect(db)
    schema.init_db(conn)
    media_mod.ensure_schema(conn)
    store = str(tmp_path / "media")
    os.makedirs(store)
    fd, tmp = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    shutil.copy(MP4_PATH, tmp)
    rec = media_mod.save_media_file(
        conn, store, "video-upload-sample", "sample.mp4", tmp,
        os.path.getsize(tmp), "sha", "video/mp4")
    if os.path.exists(tmp):
        os.unlink(tmp)
    did = drafts.create_draft(conn, "emp-1")
    # Combined analysis needs the authorised, confirmed campaign
    # destination on the draft's own spec.
    drafts.update_draft(conn, did, spec={"client": "Foap",
                                         "campaign": "Sample Launch",
                                         "clientConfirmed": True})
    drafts.add_video(conn, did, "video-upload-sample",
                     media_id=rec["id"], duration_s=15.0, width=1280,
                     height=720, sha256=rec["sha256"],
                     validation={"status": "valid"})
    with open(CSV_PATH) as fh:
        rep = ingest.import_report(conn, fh.read(), "meta",
                                   filename="Video Upload Sample Dataset.csv",
                                   imported_by="emp-1")
    drafts.add_dataset(conn, did, "Video Upload Sample Dataset.csv",
                       rows=3, version=rep["import_id"])
    drafts.update_draft(conn, did, dataset_version=rep["import_id"])
    drafts.confirm_match(conn, did, "video-upload-sample", "emp-1",
                         method="platform_id", records=RECORDS)
    return conn, store, did


def test_bind_snapshot_guards(tmp_path):
    conn, _store, did = bound_db(tmp_path)
    snap = va.bind_snapshot(conn, did)
    assert snap["creative_key"] == "video-upload-sample"
    assert snap["dataset_version"] != ""
    assert len(snap["records"]) == 3
    # Cleared confirmation blocks binding.
    drafts.clear_matches(conn, did)
    with pytest.raises(va.AnalysisUnavailable):
        va.bind_snapshot(conn, did)
    conn.close()


class StubStt:
    def transcribe(self, creative_key, audio_bytes=None, mime=None,
                   timings_out=None):
        words = [{"word": "watch", "start": 1.0, "end": 1.4}]
        if timings_out is not None:
            timings_out.extend(
                {"w": w["word"], "t": w["start"], "end": w["end"],
                 "level": "word"} for w in words)
        return ("watch this", 0.9)


class StubVision:
    roster = [("test", "test-frames", "active")]

    def annotate(self, frames, images=None):
        return [{"t_sec": 1.0, "label": "opening", "brand_visible": False,
                 "product_visible": False, "logo_visible": False,
                 "text_overlay": "", "cta_visible": False,
                 "end_frame": False, "cut": True, "confidence": 0.8}]


class StubLlm:
    def structure(self, transcript, labels):
        ann = creative_mod.blank_annotation()
        ann["hook_type"] = "question"
        return ann


class StubProviders:
    stt = StubStt()
    vision = StubVision()
    llm = StubLlm()


@NEEDS_FFMPEG
def test_full_run_persists_reviewable_analysis(tmp_path):
    conn, store, did = bound_db(tmp_path)
    snap = va.bind_snapshot(conn, did)
    out = va.run(conn, snap, owner="emp-1", media_dir=store,
                 providers=StubProviders())
    assert out["creative_key"] == "video-upload-sample"
    assert out["measured"]["pooled_link_ctr_pct"] == 2.5
    assert drafts.get_draft(conn, did)["status"] == "ready_for_review"
    row = conn.execute(
        "SELECT annotation_json FROM annotations WHERE creative_key=?",
        ("video-upload-sample",)).fetchone()
    ann = json.loads(row[0])
    assert ann["status"] == "auto"  # never self-approved
    assert ann["analysis"]["version"] == "v1"
    assert ann["analysis"]["snapshot"]["dataset_version"] == \
        snap["dataset_version"]
    assert ann["analysis"]["measured"]["totals"]["impressions"] == 6000
    assert isinstance(ann["analysis"]["suggested_tests"], list)
    assert conn.execute(
        "SELECT transcript FROM creatives WHERE creative_key=?",
        ("video-upload-sample",)).fetchone()[0] == "watch this"
    conn.close()


@NEEDS_FFMPEG
def test_stale_snapshot_and_late_result_guard(tmp_path):
    conn, store, did = bound_db(tmp_path)
    snap = va.bind_snapshot(conn, did)
    # Inputs change after binding: the job must abort, not analyse.
    drafts.clear_matches(conn, did)
    drafts.confirm_match(conn, did, "video-upload-sample", "emp-1",
                         method="manual", records=RECORDS[:1])
    with pytest.raises(va.AnalysisUnavailable):
        va.check_snapshot(conn, snap)
    # A late result never overwrites a newer analysis.
    fresh = va.bind_snapshot(conn, did)
    va.run(conn, fresh, owner="emp-1", media_dir=store,
           providers=StubProviders(), queued_at="2000-01-01T00:00:00")
    with pytest.raises(va.AnalysisUnavailable):
        va.run(conn, fresh, owner="emp-1", media_dir=store,
               providers=StubProviders(), queued_at="2000-01-01T00:00:00")
    conn.close()


def make_client(tmp_path, monkeypatch):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    monkeypatch.setenv("CREATIVE_INTEL_MEDIA_DIR", str(media_dir))
    db = str(tmp_path / "app.db")
    settings = Settings(workos_client_id="client_test",
                        key_workos="[REDACTED]")
    app = create_app(db, settings)
    http = TestClient(app, raise_server_exceptions=False)
    with employee_session(db) as sess:
        boss = emp_store.admin_create(sess, "root", "boss@foap.test",
                                      role="admin")
        token = emp_store.create_session(sess, boss.id, "")
    http.headers.update({"Cookie": "ci_session=%s" % token})
    return http, db


def test_analyze_honest_without_live_provider(tmp_path, monkeypatch):
    http, _db = make_client(tmp_path, monkeypatch)
    with open(MP4_PATH, "rb") as fh:
        blob = fh.read()
    rec = http.post("/api/media/upload",
                    data={"creative_key": "video-upload-sample"},
                    files={"file": ("sample.mp4", blob,
                                    "video/mp4")}).json()
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    # Preconditions enforced in guided order before provider readiness:
    # video, then confirmed client/campaign, then dataset, then match.
    resp = http.post("/api/drafts/%s/analyze" % did, json={})
    assert resp.status_code == 409
    assert "validate the video" in resp.json()["error"]
    http.post("/api/videos/validate",
              json={"media_id": rec["id"], "draft_id": did})
    resp = http.post("/api/drafts/%s/analyze" % did, json={})
    assert resp.status_code == 409
    assert "confirm the client and campaign" in resp.json()["error"]
    assert http.patch(
        "/api/drafts/%s" % did,
        json={"spec": {"client": "Foap", "campaign": "Sample Launch",
                       "clientConfirmed": True}}).status_code == 200
    resp = http.post("/api/drafts/%s/analyze" % did, json={})
    assert resp.status_code == 409
    assert "import performance data" in resp.json()["error"]
    with open(CSV_PATH) as fh:
        imp = http.post("/api/datasets/import",
                        json={"draft_id": did, "platform": "meta",
                              "csv": fh.read()}).json()
    import sqlite3 as _sql
    conn = _sql.connect(_db_path(http))
    try:
        rowids = [r[0] for r in conn.execute(
            "SELECT id FROM ads WHERE import_id=?", (imp["version"],))]
    finally:
        conn.close()
    assert http.post("/api/drafts/%s/matches/confirm" % did,
                     json={"creative_key": "video-upload-sample",
                           "method": "platform_id",
                           "ad_rowids": rowids}).status_code == 200
    # Fully confirmable, but no live provider in tests: honest 409,
    # naming recovery — never a mock analysis.
    resp = http.post("/api/drafts/%s/analyze" % did, json={})
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"] != ""
    # Nothing enqueued, analysis reads back empty.
    reading = http.get("/api/drafts/%s/analysis" % did).json()
    assert reading["annotation"] is None
    assert reading["status"] != "analyzing"


def _db_path(http):
    return http.app.state.ci_db_path


def test_analyze_rejects_double_submit(tmp_path, monkeypatch):
    http, db = make_client(tmp_path, monkeypatch)
    with open(MP4_PATH, "rb") as fh:
        blob = fh.read()
    rec = http.post("/api/media/upload",
                    data={"creative_key": "video-upload-sample"},
                    files={"file": ("sample.mp4", blob,
                                    "video/mp4")}).json()
    did = http.post("/api/drafts", json={}).json()["draft"]["id"]
    http.post("/api/videos/validate",
              json={"media_id": rec["id"], "draft_id": did})
    with open(CSV_PATH) as fh:
        imp = http.post("/api/datasets/import",
                        json={"draft_id": did, "platform": "meta",
                              "csv": fh.read()}).json()
    import sqlite3 as _sql
    conn = _sql.connect(_db_path(http))
    try:
        jobs_mod.ensure(conn)
        rowids = [r[0] for r in conn.execute(
            "SELECT id FROM ads WHERE import_id=?", (imp["version"],))]
    finally:
        conn.close()
    assert http.post("/api/drafts/%s/matches/confirm" % did,
                     json={"creative_key": "video-upload-sample",
                           "method": "platform_id",
                           "ad_rowids": rowids}).status_code == 200
    conn = _sql.connect(_db_path(http))
    try:
        jobs_mod.enqueue(conn, "video_analysis",
                         {"snapshot": {"draft_id": did}}, owner="x")
        conn.commit()
    finally:
        conn.close()
    resp = http.post("/api/drafts/%s/analyze" % did, json={})
    assert resp.status_code == 409
    assert resp.json()["job_id"] != ""


def test_handler_cancel_before_start_marks_cancelled(tmp_path):
    """A revoked job lands the draft in cancelled, never stranded
    in queued/analyzing (M5/M12)."""
    from ci_backend import worker_handlers
    conn, _store, did = bound_db(tmp_path)
    snap = va.bind_snapshot(conn, did)
    jobs_mod.ensure(conn)
    job = jobs_mod.enqueue(conn, "video_analysis", {"snapshot": snap},
                           owner="emp-1")
    jobs_mod.cancel(conn, job["id"], owner="emp-1")
    with pytest.raises(jobs_mod.JobCancelled):
        worker_handlers.run_video_analysis(
            conn, {"snapshot": snap}, "emp-1", {"media_dir": _store},
            job["id"])
    assert drafts.get_draft(conn, did)["status"] == "cancelled"
    conn.close()


def test_handler_unexpected_error_marks_failed(tmp_path, monkeypatch):
    """Provider blowups (not just AnalysisUnavailable) fail the
    draft instead of stranding it in analyzing (M1)."""
    from ci_backend import worker_handlers
    conn, store, did = bound_db(tmp_path)
    snap = va.bind_snapshot(conn, did)

    def boom(*args, **kwargs):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(va, "run", boom)
    with pytest.raises(RuntimeError):
        worker_handlers.run_video_analysis(
            conn, {"snapshot": snap}, "emp-1", {"media_dir": store})
    assert drafts.get_draft(conn, did)["status"] == "failed"
    conn.close()


def test_requeue_interrupted_recovers_stale_running(tmp_path):
    """Worker restart requeues only expired-lease running jobs (M5)."""
    conn, _store, did = bound_db(tmp_path)
    jobs_mod.ensure(conn)
    job = jobs_mod.enqueue(conn, "video_analysis",
                           {"snapshot": {"draft_id": did}}, owner="emp-1")
    assert jobs_mod.claim(conn, job["id"], lease_owner="w1") is not None
    # Simulate a crash an hour ago: backdate the lease expiry.
    conn.execute("UPDATE worker_jobs SET lease_expires_at='2000-01-01T00:00:00'"
                 " WHERE id=?", (job["id"],))
    conn.commit()
    assert jobs_mod.requeue_interrupted(conn) == 1
    assert jobs_mod.get(conn, job["id"])["status"] == "queued"
    # A fresh lease belongs to a live worker: left alone.
    job2 = jobs_mod.enqueue(conn, "video_analysis",
                            {"snapshot": {"draft_id": did}}, owner="emp-1")
    assert jobs_mod.claim(conn, job2["id"], lease_owner="w1") is not None
    assert jobs_mod.requeue_interrupted(conn) == 0
    assert jobs_mod.get(conn, job2["id"])["status"] == "running"
    conn.close()


def test_pipeline_preserves_prior_analysis_stamp(tmp_path):
    """The intermediate pipeline save must not wipe a concurrent
    finisher's stamped block (M2)."""
    conn, _store, _did = bound_db(tmp_path)
    conn.execute(
        "INSERT OR IGNORE INTO creatives (creative_key, platform,"
        " name, status) VALUES ('video-upload-sample', 'meta',"
        " 'video-upload-sample', 'auto')")
    ann = creative_mod.blank_annotation()
    ann["analysis"] = {"version": "v1", "at": "2026-01-01T00:00:00",
                       "model": "test/stub"}
    creative_mod.save_annotation(conn, "video-upload-sample", ann)
    media = {"audio": (None, None), "images": [b"fake"],
             "image_times": [1.0], "duration_s": 15.0}
    creative_mod.run_pipeline(conn, "video-upload-sample",
                              StubProviders(), media=media)
    assert va._analysis_at(conn,
                           "video-upload-sample") == "2026-01-01T00:00:00"
    conn.close()


@NEEDS_FFMPEG
def test_concurrent_finisher_aborts_mid_run(tmp_path, monkeypatch):
    """A newer stamp landing mid-run aborts before persistence (M2)."""
    conn, store, did = bound_db(tmp_path)
    snap = va.bind_snapshot(conn, did)
    real_identity = va._analysis_identity
    calls = {"n": 0}

    def fake_identity(conn, key, video_id=""):
        calls["n"] += 1
        if calls["n"] > 1:
            return ("", "2999-01-01T00:00:00")  # B finished mid-run
        return real_identity(conn, key, video_id)

    monkeypatch.setattr(va, "_analysis_identity", fake_identity)
    with pytest.raises(va.AnalysisUnavailable):
        va.run(conn, snap, owner="emp-1", media_dir=store,
               providers=StubProviders(), queued_at="2000-01-01T00:00:00")
    conn.close()


def test_check_snapshot_rejects_identity_swap(tmp_path):
    """Recheck minor: swapping the video/media/key under a bound
    snapshot aborts even when hashes and versions still match."""
    conn, _store, did = bound_db(tmp_path)
    snap = va.bind_snapshot(conn, did)
    va.check_snapshot(conn, snap)  # unmodified baseline passes
    for key, evil in (("video_id", "deadbeef"), ("media_id", 424242),
                      ("creative_key", "someone-else")):
        tampered = dict(snap)
        tampered[key] = evil
        with pytest.raises(va.AnalysisUnavailable):
            va.check_snapshot(conn, tampered)
    conn.close()


def test_guard_not_stale_parses_mixed_offsets(tmp_path):
    """Recheck minor: the late-result guard compares instants, not
    raw strings, so mixed +00:00/Z stamps still order correctly."""
    conn, _store, _did = bound_db(tmp_path)
    key = "video-upload-sample"
    conn.execute(
        "INSERT INTO annotations (creative_key, schema_version,"
        " annotation_json, updated_at) VALUES (?, 'v0', ?, '')",
        (key, json.dumps(
            {"analysis": {"at": "2026-03-01T12:00:00+00:00"}})))
    conn.commit()
    with pytest.raises(va.AnalysisUnavailable):
        va._guard_not_stale(conn, key, "2026-03-01T11:00:00Z")
    # The same instant is not newer: passes quietly.
    va._guard_not_stale(conn, key, "2026-03-01T12:00:00+00:00")
    conn.close()


def test_missing_metrics_not_zero_and_currency_split(tmp_path):
    """Audit A4: blank-at-import metrics never read as zero, and
    mixed-currency spend is kept per-currency, never summed."""
    _conn, _store, _did = bound_db(tmp_path)
    records = [
        {"id": 1, "impressions": 6000, "link_clicks": 150,
         "spend": 100.0, "currency": "USD", "missing_json": "[]"},
        {"id": 2, "impressions": 4000, "link_clicks": 0,
         "spend": 50.0, "currency": "USD",
         "missing_json": "[\"link_clicks\"]"},
        {"id": 3, "impressions": 2000, "link_clicks": 40,
         "spend": 100.0, "currency": "MYR", "missing_json": "[]"},
    ]
    measured = va.measured_from_records(records)
    # Record 2's unknown clicks are excluded from the CTR pool
    # (190/8000 = 2.38%), but its known impressions are preserved.
    assert measured["pooled_link_ctr_pct"] == 2.38
    assert measured["totals"]["impressions"] == 12000
    assert measured["totals"]["link_clicks"] == 190
    # Incompatible spend is not combined: unavailable, never zero.
    assert measured["totals"]["spend"] is None
    assert measured["coverage"]["spend_by_currency"] == {
        "USD": 150.0, "MYR": 100.0}
    assert any("per-currency" in w for w in measured["warnings"])
    # The control case is untouched: complete data still pools.
    control = va.measured_from_records([
        {"id": 1, "impressions": 6000, "link_clicks": 150,
         "spend": 60.0, "missing_json": "[]"}])
    assert control["pooled_link_ctr_pct"] == 2.5
    assert control["totals"]["spend"] == 60.0
    _conn.close()


def test_known_totals_survive_missing_clicks(tmp_path):
    """Recheck round 3: known impressions are preserved while CTR
    reports unavailable, and a bare null reads as unknown."""
    _conn, _store, _did = bound_db(tmp_path)
    only = va.measured_from_records([
        {"id": 1, "impressions": 1000, "link_clicks": 0,
         "missing_json": "[\"link_clicks\"]"}])
    assert only["totals"]["impressions"] == 1000
    assert only["pooled_link_ctr_pct"] is None
    bare_null = va.measured_from_records([
        {"id": 1, "impressions": 1000, "link_clicks": None}])
    assert bare_null["pooled_link_ctr_pct"] is None
    # Unknown is not zero: no known click contributor, so the total
    # reads "not supplied" instead of a false 0.
    assert bare_null["totals"]["link_clicks"] is None
    mixed_unspecified = va.measured_from_records([
        {"id": 1, "impressions": 1000, "link_clicks": 25,
         "spend": 100.0, "currency": "USD", "missing_json": "[]"},
        {"id": 2, "impressions": 1000, "link_clicks": 25,
         "spend": 100.0, "currency": "", "missing_json": "[]"},
    ])
    # Unspecified is its own bucket: never assumed to be USD.
    assert mixed_unspecified["totals"]["spend"] is None
    assert mixed_unspecified["pooled_link_ctr_pct"] == 2.5
    _conn.close()


@NEEDS_FFMPEG
def test_restore_paths_cancel_and_provider_failure(tmp_path):
    """Audit followup: cancellation and provider failure also roll
    back to the pre-run rows."""
    conn, _store, did = bound_db(tmp_path)
    snap = va.bind_snapshot(conn, did)
    key = "video-upload-sample"
    conn.execute("INSERT INTO creatives (creative_key, transcript)"
                 " VALUES (?, ?) ON CONFLICT (creative_key) DO UPDATE"
                 " SET transcript = excluded.transcript",
                 (key, "prior words"))
    conn.execute("INSERT INTO annotations (creative_key, schema_version,"
                 " annotation_json, updated_at) VALUES (?, 'v0', ?, '')"
                 " ON CONFLICT (creative_key, video_id) DO UPDATE SET"
                 " annotation_json = excluded.annotation_json",
                 (key, json.dumps({"status": "auto",
                                   "analysis": {"version": "v0"}})))
    conn.commit()
    media = {"images": [b"fake-jpeg"], "image_times": [1.0]}

    calls = {"n": 0}

    def cancel_late(stage=""):
        # Trip inside the pipeline (after the transcript write), not
        # at the pre-pipeline checkpoints.
        calls["n"] += 1
        return calls["n"] >= 6

    with pytest.raises(jobs_mod.JobCancelled):
        va.run(conn, snap, owner="emp-1", media_dir=_store,
               providers=StubProviders(), cancelled=cancel_late,
               queued_at="2000-01-01T00:00:00")
    assert conn.execute("SELECT transcript FROM creatives"
                        " WHERE creative_key=?", (key,)).fetchone()[0] \
        == "prior words"

    class BoomVision(StubVision):
        def annotate(self, frames, images=None):
            raise RuntimeError("provider down")

    class BoomProviders(StubProviders):
        vision = BoomVision()

    with pytest.raises(RuntimeError):
        va.run(conn, snap, owner="emp-1", media_dir=_store,
               providers=BoomProviders(),
               queued_at="2000-01-01T00:00:00")
    assert json.loads(conn.execute(
        "SELECT annotation_json FROM annotations WHERE creative_key=?",
        (key,)).fetchone()[0])["analysis"] == {"version": "v0"}
    conn.close()


def test_worker_daemon_requeues_and_processes(tmp_path, capsys):
    """Audit followup: the in-proc loop revives stale leases and
    drives a queued job to a terminal state."""
    import threading
    from ci_backend import worker as worker_mod
    db = str(tmp_path / "w2.db")
    conn = sqlite3.connect(db)
    schema.init_db(conn)
    jobs_mod.ensure(conn)
    job = jobs_mod.enqueue(conn, "video_analysis",
                           {"snapshot": {"draft_id": "ghost"}},
                           owner="emp-1")
    claimed = jobs_mod.claim(conn, lease_owner="t")
    assert claimed["id"] == job["id"]
    conn.execute("UPDATE worker_jobs SET lease_expires_at="
                 "'2000-01-01T00:00:00' WHERE id=?", (job["id"],))
    conn.commit()
    conn.close()
    stop = threading.Event()
    timer = threading.Timer(1.5, stop.set)
    timer.start()
    try:
        worker_mod.daemon(db, Settings(), poll=0.2, stop=stop)
    finally:
        timer.cancel()
    assert "requeued 1 interrupted" in capsys.readouterr().out
    conn = sqlite3.connect(db)
    try:
        status = conn.execute("SELECT status FROM worker_jobs WHERE id=?",
                              (job["id"],)).fetchone()[0]
    finally:
        conn.close()
    # Unknown draft: the job ran and failed honestly, never stranded.
    assert status == "failed"


def test_worker_daemon_stops_and_flags(tmp_path, monkeypatch):
    """Audit A8: the in-proc worker loop honours stop, and the web
    entrypoint enables it on hosted deploys (or explicit flag) only."""
    import threading
    from ci_backend import main as main_mod
    from ci_backend import worker as worker_mod
    db = str(tmp_path / "w.db")
    conn = sqlite3.connect(db)
    schema.init_db(conn)
    conn.close()
    stop = threading.Event()
    stop.set()
    worker_mod.daemon(db, Settings(), poll=0.1, stop=stop)
    monkeypatch.delenv("CREATIVE_INTEL_RUN_WORKER", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    assert main_mod._worker_enabled() is False
    monkeypatch.setenv("PORT", "8080")
    assert main_mod._worker_enabled() is True
    monkeypatch.setenv("CREATIVE_INTEL_RUN_WORKER", "0")
    assert main_mod._worker_enabled() is False
    monkeypatch.setenv("CREATIVE_INTEL_RUN_WORKER", "true")
    assert main_mod._worker_enabled() is True


@NEEDS_FFMPEG
def test_newer_finisher_survives_abort(tmp_path, monkeypatch):
    """Recheck round 3: when B publishes mid-run and A aborts as
    stale, A's rollback stands down — B's newer result is intact."""
    conn, store, did = bound_db(tmp_path)
    snap = va.bind_snapshot(conn, did)
    key = "video-upload-sample"
    calls = {"n": 0}
    real_identity = va._analysis_identity

    def fake_identity(conn, key, video_id=""):
        calls["n"] += 1
        if calls["n"] > 1:
            # B finishes while A is still running, publishing to the
            # same asset version's scoped row.
            seed = creative_mod.blank_annotation()
            seed["analysis"] = {
                "version": "v1", "revision": "newer-B",
                "at": "2026-05-01T00:00:00"}
            creative_mod.save_annotation(
                conn, key, seed, video_id=snap["video_id"])
            conn.execute("UPDATE creatives SET transcript=?"
                         " WHERE creative_key=?", ("B words", key))
            conn.commit()
            return ("newer-B", "2026-05-01T00:00:00")
        return real_identity(conn, key, video_id)

    monkeypatch.setattr(va, "_analysis_identity", fake_identity)
    with pytest.raises(va.AnalysisUnavailable):
        va.run(conn, snap, owner="emp-1", media_dir=store,
               providers=StubProviders(), queued_at="")
    assert conn.execute("SELECT transcript FROM creatives"
                        " WHERE creative_key=?", (key,)).fetchone()[0] \
        == "B words"
    final = creative_mod.scoped_annotation(conn, key, snap["video_id"])
    assert final["analysis"]["revision"] == "newer-B"
    assert final["analysis"]["at"] == "2026-05-01T00:00:00"
    conn.close()


@NEEDS_FFMPEG
def test_cancel_after_pipeline_restores(tmp_path, monkeypatch):
    """Recheck round 3: cancellation detected after the pipeline
    (post-publish checkpoints) still rolls back partial output."""
    conn, store, did = bound_db(tmp_path)
    snap = va.bind_snapshot(conn, did)
    key = "video-upload-sample"
    conn.execute("INSERT INTO creatives (creative_key, transcript)"
                 " VALUES (?, ?) ON CONFLICT (creative_key) DO UPDATE"
                 " SET transcript = excluded.transcript",
                 (key, "prior words"))
    conn.commit()
    calls = {"n": 0}

    def cancel_at_measured(stage=""):
        calls["n"] += 1
        return calls["n"] >= 8

    with pytest.raises(jobs_mod.JobCancelled):
        va.run(conn, snap, owner="emp-1", media_dir=store,
               providers=StubProviders(), cancelled=cancel_at_measured,
               queued_at="")
    assert conn.execute("SELECT transcript FROM creatives"
                        " WHERE creative_key=?", (key,)).fetchone()[0] \
        == "prior words"
    conn.close()


@NEEDS_FFMPEG
def test_stale_abort_restores_prior_rows(tmp_path, monkeypatch):
    """Audit A6: a job aborted as stale leaves the pre-run
    transcript and annotation behind — never partial output."""
    conn, store, did = bound_db(tmp_path)
    snap = va.bind_snapshot(conn, did)
    key = "video-upload-sample"
    conn.execute("INSERT INTO creatives (creative_key, transcript)"
                 " VALUES (?, ?) ON CONFLICT (creative_key) DO UPDATE"
                 " SET transcript = excluded.transcript",
                 (key, "prior words"))
    conn.execute("INSERT INTO annotations (creative_key, schema_version,"
                 " annotation_json, updated_at, video_id)"
                 " VALUES (?, 'v0', ?, '', ?)"
                 " ON CONFLICT (creative_key, video_id) DO UPDATE SET"
                 " annotation_json = excluded.annotation_json",
                 (key, json.dumps({"status": "auto",
                                   "analysis": {"version": "v0"}}),
                  snap["video_id"]))
    conn.commit()
    real_identity = va._analysis_identity
    calls = {"n": 0}

    def fake_identity(conn, key, video_id=""):
        calls["n"] += 1
        if calls["n"] == 2:
            return ("", "2999-01-01T00:00:00")  # B finished mid-run
        # Later reads hit the real store: nobody else published, so
        # the aborted run leaves the pre-run rows behind.
        return real_identity(conn, key, video_id)

    monkeypatch.setattr(va, "_analysis_identity", fake_identity)
    drafts.update_draft(conn, did, status="analyzing")
    with pytest.raises(va.AnalysisUnavailable):
        va.run(conn, snap, owner="emp-1", media_dir=store,
               providers=StubProviders(), queued_at="2000-01-01T00:00:00")
    assert conn.execute("SELECT transcript FROM creatives"
                        " WHERE creative_key=?", (key,)).fetchone()[0] \
        == "prior words"
    # Nothing published: the aborted run never flipped the draft to
    # ready_for_review.
    assert drafts.get_draft(conn, did)["status"] == "analyzing"
    assert json.loads(conn.execute(
        "SELECT annotation_json FROM annotations WHERE creative_key=?",
        (key,)).fetchone()[0]) == {
            "status": "auto", "analysis": {"version": "v0"}}
    conn.close()


def test_intermediate_save_restores_null_analysis(tmp_path):
    """Recheck minor: a structurer returning an explicit null
    analysis block still keeps the prior stamp across the
    intermediate save (not only a missing key)."""
    conn, _store, _did = bound_db(tmp_path)
    key = "video-upload-sample"
    prior = {"version": "v1", "at": "2026-01-01T00:00:00+00:00",
             "model": "test/test-frames"}
    seed = creative_mod.blank_annotation()
    seed["analysis"] = dict(prior)
    conn.execute(
        "INSERT INTO annotations (creative_key, schema_version,"
        " annotation_json, updated_at) VALUES (?, 'v0', ?, '')",
        (key, json.dumps(seed)))
    conn.commit()

    class NullLlm:
        def structure(self, transcript, labels):
            ann = creative_mod.blank_annotation()
            ann["hook_type"] = "question"
            ann["analysis"] = None
            return ann

    class NullProviders(StubProviders):
        llm = NullLlm()

    out = creative_mod.run_pipeline(
        conn, key, NullProviders(),
        media={"images": [b"fake-jpeg"], "image_times": [1.0]})
    assert out["annotation"]["analysis"] == prior
    conn.close()


def test_independent_totals_survive_missing_pairs():
    """Recheck round 4: a missing CTR denominator erases nothing —
    spend, conversions, and views accumulate on their own."""
    recs = [
        {"id": 1, "spend": 100.0, "currency": "USD", "conversions": 5,
         "video_views": 500, "impressions": None, "link_clicks": None,
         "missing_json": "[\"impressions\", \"link_clicks\"]"},
        {"id": 2, "spend": 0.0, "currency": "USD", "conversions": 0,
         "video_views": 0, "impressions": 0, "link_clicks": 0,
         "missing_json": "[\"impressions\", \"link_clicks\"]"},
    ]
    measured = va.measured_from_records(recs)
    assert measured["totals"]["spend"] == 100.0
    assert measured["totals"]["conversions"] == 5.0
    assert measured["totals"]["video_views"] == 500
    assert measured["pooled_link_ctr_pct"] is None
    # Known clicks with missing impressions: total kept, rate withheld.
    clicks = va.measured_from_records([
        {"id": 3, "impressions": None, "link_clicks": 25,
         "missing_json": "[\"impressions\"]"}])
    assert clicks["totals"]["link_clicks"] == 25
    assert clicks["totals"]["impressions"] is None
    assert clicks["pooled_link_ctr_pct"] is None


def test_bind_snapshot_needs_confirmed_destination(tmp_path):
    """Recheck round 4: combined analysis binds only with a confirmed
    client/campaign destination, which the snapshot then inherits."""
    conn, _store, did = bound_db(tmp_path)
    snap = va.bind_snapshot(conn, did)
    assert snap["client"] == "Foap"
    assert snap["campaign"] == "Sample Launch"
    drafts.update_draft(conn, did, spec={"client": "Foap",
                                         "campaign": "Sample Launch",
                                         "clientConfirmed": False})
    with pytest.raises(va.AnalysisUnavailable):
        va.bind_snapshot(conn, did)
    drafts.update_draft(conn, did, spec={"client": "", "campaign": "",
                                         "clientConfirmed": True})
    with pytest.raises(va.AnalysisUnavailable):
        va.bind_snapshot(conn, did)
    conn.close()


@NEEDS_FFMPEG
def test_stale_job_never_relabels_newer_findings(tmp_path, monkeypatch):
    """Recheck round 4 (the interleaving): B publishes hook=bold_claim
    under revision newer-B; the older job A then aborts as stale. Its
    generated classification (question) must never land under B's
    revision — the final stored annotation is byte-identical to B's."""
    conn, store, did = bound_db(tmp_path)
    snap = va.bind_snapshot(conn, did)
    key = "video-upload-sample"
    real_identity = va._analysis_identity
    calls = {"n": 0}

    def fake_identity(conn, key, video_id=""):
        calls["n"] += 1
        if calls["n"] > 1:
            # B finishes while A is still running: bold_claim under
            # revision newer-B, published to the same version row.
            newer = creative_mod.blank_annotation()
            newer["hook_type"] = "bold_claim"
            newer["analysis"] = {
                "version": "v1", "revision": "newer-B",
                "at": "2026-05-01T00:00:00+00:00",
                "model": "test/test-frames",
                "snapshot": dict(snap, records=[]),
                "measured": {}, "suggested_tests": []}
            creative_mod.save_annotation(conn, key, newer,
                                         video_id=snap["video_id"])
            return ("newer-B", "2026-05-01T00:00:00+00:00")
        return real_identity(conn, key, video_id)

    monkeypatch.setattr(va, "_analysis_identity", fake_identity)
    with pytest.raises(va.AnalysisUnavailable):
        va.run(conn, snap, owner="emp-1", media_dir=store,
               providers=StubProviders(), queued_at="")
    final = creative_mod.scoped_annotation(conn, key, snap["video_id"])
    assert final["hook_type"] == "bold_claim"
    assert final["analysis"]["revision"] == "newer-B"
    conn.close()


def test_apply_corrections_rewrites_findings(tmp_path):
    """Recheck round 4: corrections land on the stored finding, lock
    dimensions, mint a fresh revision with a log entry — and reject
    unknown fields, bad enums, and unknown test ids."""
    conn, _store, _did = bound_db(tmp_path)
    key = "video-upload-sample"
    seed = creative_mod.blank_annotation()
    seed["analysis"] = {"version": "v1", "revision": "rev-0",
                        "at": "2026-01-01T00:00:00+00:00",
                        "model": "test/test-frames",
                        "snapshot": {}, "measured": {},
                        "suggested_tests": [
                            {"id": "hook-clarity",
                             "hypothesis": "Try a clearer hook.",
                             "why": "uncertain hook", "evidence": [],
                             "status": "suggested"}]}
    creative_mod.save_annotation(conn, key, seed)
    conn.execute("INSERT INTO creatives (creative_key, transcript)"
                 " VALUES (?, ?) ON CONFLICT (creative_key) DO UPDATE"
                 " SET transcript = excluded.transcript",
                 (key, "raw words"))
    conn.commit()
    ann = va.apply_corrections(
        conn, key,
        {"transcript": "fixed words", "hook_type": "bold_claim",
         "hook_confidence": 0.7,
         "frame_labels": [{"t_sec": 2.5, "label": "opening",
                           "cta_visible": True}],
         "tests": [{"id": "hook-clarity", "status": "rejected"}]},
        by="emp-1", expected_revision="rev-0")
    assert ann["hook_type"] == "bold_claim"
    assert ann["confirmed"]["hook_type"] == "bold_claim"
    assert ann["frame_labels"][0]["t_sec"] == 2.5
    assert ann["analysis"]["suggested_tests"][0]["status"] == "rejected"
    assert ann["analysis"]["revision"] != "rev-0"
    assert ann["analysis"]["corrections"][0]["by"] == "emp-1"
    assert conn.execute("SELECT transcript FROM creatives"
                        " WHERE creative_key=?", (key,)).fetchone()[0] \
        == "fixed words"
    # Blind corrections (no revision) are rejected once the stored
    # result carries one; field validation still runs afterwards.
    with pytest.raises(ValueError):
        va.apply_corrections(conn, key, {"hook_type": "bold_claim"},
                             by="emp-1")
    rev = ann["analysis"]["revision"]
    with pytest.raises(ValueError):
        va.apply_corrections(conn, key, {"hook_type": "nope"}, by="emp-1",
                             expected_revision=rev)
    with pytest.raises(ValueError):
        va.apply_corrections(conn, key, {"tests": [{"id": "ghost",
                                                   "status": "accepted"}]},
                             by="emp-1", expected_revision=rev)
    with pytest.raises(ValueError):
        va.apply_corrections(conn, key, {"colour": "teal"}, by="emp-1",
                             expected_revision=rev)
    with pytest.raises(ValueError):
        va.apply_corrections(conn, key, {}, by="emp-1",
                             expected_revision=rev)
    with pytest.raises(ValueError):
        va.apply_corrections(conn, "missing-key", {"hook_type": "other"})
    with pytest.raises(ValueError):
        va.apply_corrections(
            conn, key,
            {"tests": [{"id": "hook-clarity", "status": "accepted"},
                       {"id": "hook-clarity", "status": "rejected"}]},
            by="emp-1", expected_revision=rev)
    conn.close()


def _seed_versioned(conn, key, video_id, hook, status, transcript,
                    revision):
    """One video version's own annotation + transcript rows."""
    ann = creative_mod.blank_annotation()
    ann["hook_type"] = hook
    ann["status"] = status
    ann["analysis"] = {"version": "v1", "revision": revision,
                       "at": "2026-01-01T00:00:00+00:00",
                       "model": "test/test-frames", "snapshot": {},
                       "measured": {}, "suggested_tests": []}
    creative_mod.save_annotation(conn, key, ann, video_id=video_id)
    drafts.set_video_transcript(conn, video_id, transcript)


def _two_video_setup(tmp_path):
    """Two drafts/owners, different videos, one creative name.

    Video A (emp-A): approved, hook question. Video B (emp-B):
    analysed, hook bold_claim, confirmed match. Returns
    (conn, key, vidA, vidB, didB)."""
    conn, _store, didA = bound_db(tmp_path)
    key = "video-upload-sample"
    media_id = conn.execute(
        "SELECT media_id FROM videos WHERE draft_id=?",
        (didA,)).fetchone()[0]
    vidA = conn.execute(
        "SELECT id FROM videos WHERE draft_id=?", (didA,)).fetchone()[0]
    # bound_db's draft belongs to emp-1: reassign as emp-A's draft.
    conn.execute("UPDATE drafts SET owner_employee_id=? WHERE id=?",
                 ("emp-A", didA))
    conn.execute("UPDATE videos SET creative_key=? WHERE id=?",
                 (key, vidA))
    _seed_versioned(conn, key, vidA, "question", "human_verified",
                    "A exact words", "rev-A")
    didB = drafts.create_draft(conn, "emp-B")
    drafts.update_draft(conn, didB, spec={"client": "Client B",
                                          "campaign": "Campaign B",
                                          "clientConfirmed": True})
    vidB = drafts.add_video(conn, didB, key, media_id=media_id,
                            duration_s=15.0, width=1280, height=720,
                            sha256="other-sha-B",
                            validation={"status": "valid"})
    drafts.add_dataset(conn, didB, "b.csv", rows=1, version="imp-B")
    drafts.update_draft(conn, didB, dataset_version="imp-B")
    _seed_versioned(conn, key, vidB, "bold_claim", "auto",
                    "B exact words", "rev-B")
    conn.execute("INSERT INTO creatives (creative_key, transcript)"
                 " VALUES (?, ?) ON CONFLICT (creative_key) DO UPDATE"
                 " SET transcript = excluded.transcript",
                 (key, "stale shared words"))
    conn.commit()
    return conn, key, vidA, vidB, didB


def test_report_annotation_prefers_confirming_video(tmp_path):
    """Round-6 recheck 1: B's confirmed performance must pair with
    B's own annotation — never A's approved findings."""
    conn, key, _vidA, vidB, didB = _two_video_setup(tmp_path)
    rec = {"id": 7, "import_id": "imp-B", "platform": "meta",
           "campaign": "Campaign B", "impressions": 6000,
           "creative_key": "report_asset"}
    drafts.confirm_match(conn, didB, key, "emp-B", method="manual",
                         records=[rec], video_id=vidB)
    ann = creative_mod.annotation_for_report(conn, key, owner="emp-B")
    assert ann["hook_type"] == "bold_claim"
    assert ann["analysis"]["revision"] == "rev-B"
    # A viewer with no applicable confirmation keeps the legacy
    # approved-or-latest row (documented fallback, no confirmed
    # performance shown alongside it either).
    legacy = creative_mod.annotation_for_report(conn, key,
                                                owner="emp-A")
    assert legacy["hook_type"] == "question"
    conn.close()


def test_export_uses_single_result_identity(tmp_path):
    """Round-6 recheck 1 (export): approval, hook, and transcript
    come from the same video version. A's approval must not
    authorise B's unreviewed content, and an approved B exports
    B's own words — never the shared copy."""
    from creative_intel import export_gate
    conn, key, _vidA, vidB, didB = _two_video_setup(tmp_path)
    rec = {"id": 7, "import_id": "imp-B", "platform": "meta",
           "campaign": "Campaign B", "impressions": 6000,
           "creative_key": "report_asset"}
    drafts.confirm_match(conn, didB, key, "emp-B", method="manual",
                         records=[rec], video_id=vidB)
    # B is unreviewed: export is blocked even though A is approved
    # (the old code exported A's hook with the shared transcript).
    with pytest.raises(export_gate.ExportBlocked):
        export_gate.build_one_pager(conn, [key], {}, owner="emp-B")
    creative_mod.mark_verified(conn, key, video_id=vidB)
    out = export_gate.build_one_pager(conn, [key], {}, owner="emp-B")
    assert out["cards"][0]["hook_type"] == "bold_claim"
    assert out["cards"][0]["transcript"] == "B exact words"
    conn.close()


def test_confirmed_rows_keep_full_fields_and_destination(tmp_path):
    """Round-6 recheck 2: complete snapshots preserve revenue,
    reach, market, and conversion event; client-less rows inherit
    the confirming draft's authorised destination."""
    conn, _store, _did = bound_db(tmp_path)
    key = "video-upload-sample"
    vid = conn.execute(
        "SELECT id FROM videos WHERE draft_id=?", (_did,)).fetchone()[0]
    rec = {"id": 9, "import_id": "imp", "platform": "meta",
           "campaign": "Sample Launch", "adset": "Prospecting",
           "ad_name": "B Story", "creative_key": "report_asset",
           "spend": 120.0, "impressions": 6000, "clicks": 150,
           "conversions": 7.0, "video_views": 3000,
           "client": "", "project": "", "vertical": "", "market": "MY",
           "objective": "", "funnel_stage": "", "date": "2026-09-01",
           "revenue": 240.0, "revenue_reported": 1, "reach": 4500,
           "currency": "USD", "link_clicks": 140,
           "conversion_event": "purchase", "missing_json": "[]"}
    drafts.confirm_match(conn, _did, key, "emp-1", method="manual",
                         records=[rec], video_id=vid)
    rows = drafts.performance_rows_for_key(conn, key, [], owner="emp-1")
    assert len(rows) == 1
    row = rows[0]
    assert row["impressions"] == 6000
    assert row["revenue"] == 240.0
    assert row["reach"] == 4500
    assert row["market"] == "MY"
    assert row["conversion_event"] == "purchase"
    assert row["client"] == "Foap"
    assert row["campaign"] == "Sample Launch"
    conn.close()


@NEEDS_FFMPEG
def test_publish_rejects_rival_commit_inside_transaction(tmp_path,
                                                         monkeypatch):
    """Round-6 recheck 3: a dataset change plus cleared match
    committed after the post-pipeline check must abort the publish.
    The in-transaction re-bind sees the rival commit and nothing is
    saved — no stale result, no ready_for_review."""
    db = str(tmp_path / "va.db")
    conn, store, did = bound_db(tmp_path)
    snap = va.bind_snapshot(conn, did)
    real_check = va.check_snapshot
    calls = {"n": 0}

    def spy(conn, snapshot):
        calls["n"] += 1
        try:
            return real_check(conn, snapshot)
        finally:
            if calls["n"] == 2:
                rival = sqlite3.connect(db)
                rival.execute("UPDATE drafts SET dataset_version='import-2'"
                              " WHERE id=?", (did,))
                rival.execute("DELETE FROM matches WHERE draft_id=?",
                              (did,))
                rival.commit()
                rival.close()

    monkeypatch.setattr(va, "check_snapshot", spy)
    with pytest.raises(va.AnalysisUnavailable):
        va.run(conn, snap, owner="emp-1", media_dir=store,
               providers=StubProviders(), queued_at="")
    assert calls["n"] == 3
    assert drafts.get_draft(conn, did)["status"] != "ready_for_review"
    assert conn.execute("SELECT COUNT(*) FROM annotations"
                        " WHERE creative_key=?",
                        ("video-upload-sample",)).fetchone()[0] == 0
    conn.close()


def test_no_analysis_means_none_and_blocked_export(tmp_path):
    """Round-7 recheck 1: B confirmed but never analysed → no
    annotation and a blocked export. A's approved result is not
    substituted, with or without a confirmation."""
    from creative_intel import export_gate
    conn, key, _vidA, vidB, didB = _two_video_setup(tmp_path)
    # No applicable confirmation and several versions: no
    # substitution for a stranger to the key.
    assert creative_mod.annotation_for_report(
        conn, key, owner="emp-C") is None
    # B matched but never analysed: no scoped analysis row.
    conn.execute("DELETE FROM annotations WHERE creative_key=?"
                 " AND video_id=?", (key, vidB))
    conn.commit()
    rec = {"id": 7, "import_id": "imp-B", "platform": "meta",
           "campaign": "Campaign B", "impressions": 6000,
           "creative_key": "report_asset"}
    drafts.confirm_match(conn, didB, key, "emp-B", method="manual",
                         records=[rec], video_id=vidB)
    assert creative_mod.annotation_for_report(
        conn, key, owner="emp-B") is None
    with pytest.raises(export_gate.ExportBlocked):
        export_gate.build_one_pager(conn, [key], {}, owner="emp-B")
    conn.close()


def test_silent_video_exports_empty_transcript(tmp_path):
    """Round-7 recheck 2: an approved silent video exports with an
    empty transcript — A's speech from the shared copy is not
    borrowed, and the card renders '(no transcript)' downstream."""
    from creative_intel import export_gate
    conn, key, _vidA, vidB, didB = _two_video_setup(tmp_path)
    rec = {"id": 7, "import_id": "imp-B", "platform": "meta",
           "campaign": "Campaign B", "impressions": 6000,
           "creative_key": "report_asset"}
    drafts.confirm_match(conn, didB, key, "emp-B", method="manual",
                         records=[rec], video_id=vidB)
    creative_mod.mark_verified(conn, key, video_id=vidB)
    drafts.set_video_transcript(conn, vidB, "")
    out = export_gate.build_one_pager(conn, [key], {}, owner="emp-B")
    assert out["cards"][0]["hook_type"] == "bold_claim"
    assert out["cards"][0]["transcript"] == ""
    assert "(no transcript)" in out["markdown"]
    conn.close()


def test_creatives_card_uses_scoped_identity(tmp_path):
    """Round-7 recheck 3: the Creatives card's annotation,
    transcript, and status come from B's version — never the
    shared last-writer copies."""
    from ci_backend import actions as actions_mod
    conn, key, _vidA, vidB, didB = _two_video_setup(tmp_path)
    rec = {"id": 7, "import_id": "imp-B", "platform": "meta",
           "campaign": "Campaign B", "impressions": 6000,
           "creative_key": "report_asset"}
    drafts.confirm_match(conn, didB, key, "emp-B", method="manual",
                         records=[rec], video_id=vidB)
    cards = actions_mod.build_creatives_list(conn, {}, owner="emp-B")
    card = [c for c in cards if c["creative_key"] == key][0]
    assert card["annotation"]["hook_type"] == "bold_claim"
    assert card["transcript"] == "B exact words"
    assert card["status"] == "auto"
    conn.close()


@NEEDS_FFMPEG
def test_late_cancel_aborts_publish_inside_transaction(tmp_path,
                                                       monkeypatch):
    """Round-7 recheck 4: a cancel landing after the final
    checkpoint — after the last pre-transaction check — still stops
    the publish via the in-transaction recheck. Nothing is saved."""
    conn, store, did = bound_db(tmp_path)
    snap = va.bind_snapshot(conn, did)
    real_check = va.check_snapshot
    calls = {"n": 0}
    flag = {"off": False}

    def spy(conn, snapshot):
        calls["n"] += 1
        try:
            return real_check(conn, snapshot)
        finally:
            if calls["n"] == 3:
                flag["off"] = True

    monkeypatch.setattr(va, "check_snapshot", spy)
    with pytest.raises(jobs_mod.JobCancelled):
        va.run(conn, snap, owner="emp-1", media_dir=store,
               providers=StubProviders(), queued_at="",
               cancelled=lambda: flag["off"])
    assert calls["n"] == 3
    assert drafts.get_draft(conn, did)["status"] != "ready_for_review"
    assert conn.execute("SELECT COUNT(*) FROM annotations"
                        " WHERE creative_key=?",
                        ("video-upload-sample",)).fetchone()[0] == 0
    conn.close()


def test_single_row_fallback_needs_owner(tmp_path):
    """Round-8 recheck 1: one stored analysis is not an access
    permission. A stranger with no confirmation gets nothing and
    export blocks; the owning employee and admins keep access."""
    from creative_intel import export_gate
    conn, key, _vidA, vidB, _didB = _two_video_setup(tmp_path)
    # Only A analysed: one stored row (B's video exists, unanalysed).
    conn.execute("DELETE FROM annotations WHERE creative_key=?"
                 " AND video_id=?", (key, vidB))
    conn.commit()
    # Stranger C: no confirmation, not admin.
    assert creative_mod.annotation_for_report(
        conn, key, owner="emp-C") is None
    assert creative_mod.annotation_scope_for_report(
        conn, key, owner="emp-C") == ""
    with pytest.raises(export_gate.ExportBlocked):
        export_gate.build_one_pager(conn, [key], {}, owner="emp-C")
    # Owner A and admins still read A's lone approved row.
    assert creative_mod.annotation_for_report(
        conn, key, owner="emp-A")["analysis"]["revision"] == "rev-A"
    assert creative_mod.annotation_for_report(
        conn, key, owner="emp-C",
        admin=True)["analysis"]["revision"] == "rev-A"
    conn.close()


def test_unavailable_card_hides_shared_fields(tmp_path):
    """Round-8 recheck 2: B confirmed but unanalysed → the card
    carries B's own duration with empty transcript/status, never
    A's shared words, approval, or length."""
    from ci_backend import actions as actions_mod
    conn, key, _vidA, vidB, didB = _two_video_setup(tmp_path)
    conn.execute("DELETE FROM annotations WHERE creative_key=?"
                 " AND video_id=?", (key, vidB))
    conn.execute("UPDATE videos SET duration_s=? WHERE id=?",
                 (15.0, vidB))
    conn.execute("UPDATE creatives SET transcript=?, status=?,"
                 " duration_s=? WHERE creative_key=?",
                 ("PRIVATE A shared words", "human_verified", 99.0,
                  key))
    conn.commit()
    rec = {"id": 7, "import_id": "imp-B", "platform": "meta",
           "campaign": "Campaign B", "impressions": 6000,
           "creative_key": "report_asset"}
    drafts.confirm_match(conn, didB, key, "emp-B", method="manual",
                         records=[rec], video_id=vidB)
    cards = actions_mod.build_creatives_list(conn, {}, owner="emp-B")
    card = [c for c in cards if c["creative_key"] == key][0]
    assert card["annotation"] is None
    assert card["transcript"] == ""
    assert card["status"] == ""
    assert card["duration_s"] == 15.0
    conn.close()


def test_job_read_keeps_publish_transaction(tmp_path):
    """Round-8 recheck 3 (unit): a job-state read inside an open
    transaction performs no writes and no commit — the same
    transaction stays active for the save."""
    from creative_intel import jobs as jobs_mod
    conn, _store, _did = bound_db(tmp_path)
    job = jobs_mod.enqueue(conn, "video_analysis", {}, owner="emp-1")
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = jobs_mod.get(conn, job["id"])
        assert row["status"] != "cancelled"
        assert conn.in_transaction
    finally:
        conn.rollback()
    conn.close()


@NEEDS_FFMPEG
def test_worker_chain_cancel_aborts_publish(tmp_path, monkeypatch):
    """Round-8 recheck 3 (integration): the real worker-style
    cancellation callback (jobs.get-based, as built in
    worker_handlers._control) observes a rival connection's cancel
    and stops the job. Nothing is saved. The in-transaction
    half is covered by test_late_cancel_aborts_publish_inside_transaction;
    the no-release half by test_job_read_keeps_publish_transaction
    (which fails against the old committing ensure)."""
    from creative_intel import jobs as jobs_mod
    db = str(tmp_path / "va.db")
    conn, store, did = bound_db(tmp_path)
    snap = va.bind_snapshot(conn, did)
    job = jobs_mod.enqueue(conn, "video_analysis", {}, owner="emp-1")
    real_check = va.check_snapshot
    calls = {"n": 0}

    def worker_cancelled():
        try:
            row = jobs_mod.get(conn, job["id"])
        except Exception:
            return False
        return row is None or row["status"] == "cancelled"

    def spy(conn, snapshot):
        calls["n"] += 1
        try:
            return real_check(conn, snapshot)
        finally:
            if calls["n"] == 2:
                rival = sqlite3.connect(db)
                jobs_mod.cancel(rival, job["id"])
                rival.commit()
                rival.close()

    monkeypatch.setattr(va, "check_snapshot", spy)
    with pytest.raises(jobs_mod.JobCancelled):
        va.run(conn, snap, owner="emp-1", media_dir=store,
               providers=StubProviders(), queued_at="",
               cancelled=worker_cancelled)
    assert drafts.get_draft(conn, did)["status"] != "ready_for_review"
    assert conn.execute("SELECT COUNT(*) FROM annotations"
                        " WHERE creative_key=?",
                        ("video-upload-sample",)).fetchone()[0] == 0
    conn.close()


def test_scoped_helpers_withhold_stranger_findings(tmp_path):
    """Round-9: analyst and QA helpers use the authorised selection —
    a stranger gets nothing, the owner keeps access, and legacy
    viewer-less callers behave exactly as before."""
    from creative_intel import analyst as analyst_mod
    from creative_intel import qa as qa_mod
    conn, key, _vidA, _vidB, _didB = _two_video_setup(tmp_path)
    assert analyst_mod.annotations_for(conn, [key],
                                       owner="emp-C") == {key: (None, "none")}
    assert qa_mod._annotations(conn, owner="emp-C") == {key: {}}
    ann, status = analyst_mod.annotations_for(
        conn, [key], owner="emp-A")[key]
    assert ann["analysis"]["revision"] == "rev-A"
    assert status == "human_verified"
    legacy, _ = analyst_mod.annotations_for(conn, [key])[key]
    assert legacy["analysis"]["revision"] == "rev-A"
    conn.close()


def test_export_blocked_on_pending_qa(tmp_path):
    """Round-9: the review-to-zero gate lives inside build_one_pager,
    so no caller can export past pending QA answers."""
    from creative_intel import export_gate
    from creative_intel import qa as qa_mod
    conn, _store, _did = bound_db(tmp_path)
    got = qa_mod.answer(conn, "what is spend?")
    assert got["review_id"] is not None
    assert qa_mod.pending_count(conn) == 1
    with pytest.raises(export_gate.ExportBlocked) as exc:
        export_gate.build_one_pager(conn, ["video-upload-sample"], {})
    assert "review-to-zero" in str(exc.value)
    conn.close()


def test_nan_never_reaches_rows_or_render(tmp_path):
    """Round-9: non-finite numerics degrade to safe defaults at
    ingest, snapshot shaping, and export rendering — never nan."""
    from creative_intel import export_gate
    from creative_intel import ingest as ingest_mod
    assert ingest_mod._to_number("NaN", float) == 0.0
    assert ingest_mod._to_number("-inf", float) == 0.0
    assert ingest_mod._to_number("1,000.5", float) == 1000.5
    conn, _store, _did = bound_db(tmp_path)
    key = "video-upload-sample"
    vid = conn.execute(
        "SELECT id FROM videos WHERE draft_id=?", (_did,)).fetchone()[0]
    rec = {"id": 11, "import_id": "imp", "platform": "meta",
           "campaign": "Sample Launch", "spend": float("nan"),
           "impressions": 6000, "clicks": 150, "creative_key": "x"}
    drafts.confirm_match(conn, _did, key, "emp-1", method="manual",
                         records=[rec], video_id=vid)
    rows = drafts.performance_rows_for_key(conn, key, [], owner="emp-1")
    assert rows[0]["spend"] == 0
    assert rows[0]["impressions"] == 6000
    assert export_gate._finite_or_na(float("nan")) == "n/a"
    assert export_gate._finite_or_na(float("inf")) == "n/a"
    assert export_gate._finite_or_na(12.5) == 12.5
    conn.close()


def test_validate_rejects_nonfinite(tmp_path):
    """Round-9: validate() treats NaN/inf numerics as invalid, not
    merely out of range."""
    conn, _store, _did = bound_db(tmp_path)
    ann = creative_mod.blank_annotation()
    assert isinstance(ann, dict)
    bad = creative_mod.blank_annotation()
    bad["structure"] = {"hook": {"start_s": float("nan"), "end_s": 1.0,
                                 "confidence": 0.5}}
    bad["hook_confidence"] = float("inf")
    errors = creative_mod.validate(bad)
    assert any("not numeric" in e for e in errors)
    assert any("hook_confidence" in e for e in errors)
    conn.close()


def test_correction_rejects_nonfinite_moment(tmp_path):
    """Round-6 validation: NaN/inf timestamps are rejected before
    range checks (both comparisons pass NaN silently)."""
    conn, _store, _did = bound_db(tmp_path)
    key = "video-upload-sample"
    seed = creative_mod.blank_annotation()
    seed["analysis"] = {"version": "v1", "revision": "rev-0",
                        "at": "2026-01-01T00:00:00+00:00",
                        "model": "test/test-frames",
                        "snapshot": {}, "measured": {},
                        "suggested_tests": []}
    creative_mod.save_annotation(conn, key, seed)
    conn.commit()
    with pytest.raises(ValueError):
        va.apply_corrections(
            conn, key,
            {"frame_labels": [{"t_sec": "NaN", "label": "opening"}]},
            by="emp-1", duration_s=15.0, expected_revision="rev-0")
    with pytest.raises(ValueError):
        va.apply_corrections(
            conn, key,
            {"frame_labels": [{"t_sec": "inf", "label": "opening"}]},
            by="emp-1", duration_s=15.0, expected_revision="rev-0")
    conn.close()
