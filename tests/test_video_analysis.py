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
    # Preconditions enforced in order before provider readiness.
    resp = http.post("/api/drafts/%s/analyze" % did, json={})
    assert resp.status_code == 409
    assert "validate the video" in resp.json()["error"]
    http.post("/api/videos/validate",
              json={"media_id": rec["id"], "draft_id": did})
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
    real_at = va._analysis_at
    calls = {"n": 0}

    def fake_at(conn, key):
        calls["n"] += 1
        if calls["n"] > 1:
            return "2999-01-01T00:00:00"  # B finished mid-run
        return real_at(conn, key)

    monkeypatch.setattr(va, "_analysis_at", fake_at)
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
    # Record 2's unknown clicks are excluded: 190/8000 = 2.38%.
    assert measured["pooled_link_ctr_pct"] == 2.38
    assert measured["totals"]["impressions"] == 8000
    assert measured["totals"]["link_clicks"] == 190
    # Incompatible spend is not combined.
    assert measured["totals"]["spend"] == 0.0
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
                 " annotation_json, updated_at) VALUES (?, 'v0', ?, '')"
                 " ON CONFLICT (creative_key) DO UPDATE SET"
                 " annotation_json = excluded.annotation_json",
                 (key, json.dumps({"status": "auto",
                                   "analysis": {"version": "v0"}})))
    conn.commit()
    real_at = va._analysis_at
    calls = {"n": 0}

    def fake_at(conn, key):
        calls["n"] += 1
        if calls["n"] > 1:
            return "2999-01-01T00:00:00"  # B finished mid-run
        return real_at(conn, key)

    monkeypatch.setattr(va, "_analysis_at", fake_at)
    with pytest.raises(va.AnalysisUnavailable):
        va.run(conn, snap, owner="emp-1", media_dir=store,
               providers=StubProviders(), queued_at="2000-01-01T00:00:00")
    assert conn.execute("SELECT transcript FROM creatives"
                        " WHERE creative_key=?", (key,)).fetchone()[0] \
        == "prior words"
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
