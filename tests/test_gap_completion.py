"""Regression tests for the 2026-10-18 gap-completion work.

Covers: Gemini-only video readiness (no separate STT key), the
Gemini key never travelling in a URL, video-only snapshots and
reports, owner-scoped report templates, server preferences +
notification opt-outs/dedup, secret-free data export, GA4 input
validation, and the Analyst narrative source labelling.
"""

import io
import json
import os
import sqlite3
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import data_export, drafts, ga4, notifications
from creative_intel import providers as prov_mod
from creative_intel import report_templates as rt_mod
from creative_intel import schema as schema_mod
from creative_intel import video_analysis as va


@pytest.fixture()
def conn(tmp_path):
    c = sqlite3.connect(str(tmp_path / "t.db"))
    schema_mod.init_db(c)
    yield c
    c.close()


# --- video / Gemini ----------------------------------------------------

def test_gemini_only_roster_needs_no_stt_key(monkeypatch):
    monkeypatch.setenv("CREATIVE_INTEL_PROVIDER_MODE", "live")
    monkeypatch.setenv("CREATIVE_INTEL_KEY_GEMINI", "test-key")
    for var in ("CREATIVE_INTEL_KEY_DEEPGRAM", "CREATIVE_INTEL_KEY_GROQ_STT",
                "CREATIVE_INTEL_KEY_OPENAI", "CREATIVE_INTEL_KEY_ANTHROPIC",
                "CREATIVE_INTEL_KEY_NVIDIA", "CREATIVE_INTEL_KEY_ZAI"):
        monkeypatch.delenv(var, raising=False)
    roster = va.eligible_vision_roster()
    assert ("gemini", "gemini-2.5-flash", "active") in roster
    ready = va.readiness()
    assert ready["ready"] is True
    assert ready["provider"] == "gemini"
    assert ready["model"] == "gemini-2.5-flash"


def test_gemini_key_never_in_url(monkeypatch):
    monkeypatch.setenv("CREATIVE_INTEL_KEY_GEMINI", "sekrit-value")
    client = prov_mod.GeminiChat("gemini-2.5-flash")
    assert "sekrit-value" not in client.url
    assert "key=" not in client.url


def test_gemini_stt_parses_transcript(monkeypatch):
    monkeypatch.setenv("CREATIVE_INTEL_KEY_GEMINI", "k")
    seen = {}

    def fake_chat(self, messages, max_tokens=2048):
        seen["messages"] = messages
        return json.dumps({"transcript": "hello world",
                           "language": "en", "confidence": 0.8})

    monkeypatch.setattr(prov_mod.GeminiChat, "chat", fake_chat)
    text, conf = prov_mod.GeminiStt().transcribe(
        "ck", audio_bytes=b"RIFFfake", mime="audio/wav")
    assert text == "hello world"
    assert conf == 0.8
    parts = seen["messages"][0]["content"]
    assert any(p.get("type") == "audio" for p in parts)


def test_video_only_snapshot_and_report(conn):
    did = drafts.create_draft(conn, "emp-1")
    drafts.add_video(conn, did, "ck-1", media_id=0, duration_s=15.8,
                     width=1080, height=1920, sha256="abc",
                     validation={"status": "valid"})
    snap = va.bind_snapshot(conn, did, video_only=True)
    assert snap["video_only"] is True
    assert snap["records"] == []
    # Combined mode still refuses without a confirmed destination.
    with pytest.raises(va.AnalysisUnavailable):
        va.bind_snapshot(conn, did)
    ann = {"hook_type": "question", "hook_modality": "visual",
           "hook_confidence": 0.7,
           "frame_labels": [{"t_sec": 1.0, "label": "opening",
                             "cta_visible": True,
                             "text_overlay": "Shop now"}],
           "analysis": {"version": "v1", "at": "2026-10-18T00:00:00Z",
                        "model": "gemini/gemini-2.5-flash",
                        "snapshot": {"video_only": True},
                        "measured": {"available": False,
                                     "video_only": True,
                                     "note": "Performance metrics "
                                             "unavailable: video only."},
                        "coverage": {"frames": 1, "clip_s": 15.8},
                        "suggested_tests": []}}
    report = va.build_creative_report(ann, transcript="hi",
                                      creative_key="ck-1",
                                      duration_s=15.8)
    assert "Video-only creative report" in report
    assert "Performance metrics unavailable" in report
    assert "Shop now" in report
    assert "ROAS" not in report.split("## Performance")[1] \
        or "unavailable" in report.split("## Performance")[1]


# --- templates / prefs / notifications ---------------------------------

def test_templates_are_owner_scoped(conn):
    cfg = {"campaigns": ["A"], "kpis": ["ctr"], "benchmark": "industry",
           "format": "xlsx"}
    saved = rt_mod.save(conn, "emp-1", "Mine", cfg)
    assert rt_mod.get(conn, "emp-1", saved["id"])["name"] == "Mine"
    assert rt_mod.get(conn, "emp-2", saved["id"]) is None
    assert rt_mod.list_mine(conn, "emp-2") == []
    assert rt_mod.delete(conn, "emp-2", saved["id"]) is False
    assert rt_mod.delete(conn, "emp-1", saved["id"]) is True
    with pytest.raises(ValueError):
        rt_mod.save(conn, "emp-1", "Bad", {"format": "exe"})


def test_notification_opt_out_dedup_and_blocker(conn, monkeypatch):
    monkeypatch.delenv("CREATIVE_INTEL_SMTP_HOST", raising=False)
    notifications.save_prefs(conn, "emp-1", {"ai_insights": False})
    out = notifications.enqueue(conn, "emp-1", "analysis_ready",
                                "s", "b", recipient="a@b.c")
    assert out["status"] == "skipped"
    notifications.save_prefs(conn, "emp-1", {"ai_insights": True})
    out = notifications.enqueue(conn, "emp-1", "analysis_ready",
                                "s", "b", dedup_key="k1",
                                recipient="a@b.c")
    assert out["status"] == "blocked"
    assert "CREATIVE_INTEL_SMTP_HOST" in out["detail"]
    again = notifications.enqueue(conn, "emp-1", "analysis_ready",
                                  "s", "b", dedup_key="k1",
                                  recipient="a@b.c")
    assert again.get("duplicate") is True
    sent = []
    ok = notifications.enqueue(
        conn, "emp-1", "analysis_ready", "s", "b", recipient="a@b.c",
        sender=lambda to, s, b: sent.append(to))
    assert ok["status"] == "sent" and sent == ["a@b.c"]


def test_export_zip_has_no_secrets(conn):
    notifications.save_prefs(conn, "emp-1", {"workspace": "W"})
    blob, name = data_export.build_export(conn, {
        "id": "emp-1", "email": "a@b.c", "first_name": "A",
        "last_name": "B", "status": "active",
        "api_key": "should-never-appear", "session_token": "nope"})
    assert name.endswith(".zip")
    zf = zipfile.ZipFile(io.BytesIO(blob))
    assert "profile.json" in zf.namelist()
    assert "preferences.json" in zf.namelist()
    everything = b"".join(zf.read(n) for n in zf.namelist())
    assert b"should-never-appear" not in everything
    assert b"nope" not in everything


# --- GA4 + analyst narrative -------------------------------------------

def test_ga4_validates_inputs():
    with pytest.raises(ga4.Ga4Unavailable):
        ga4.fetch_rows("", "123", "2026-01-01", "2026-01-02")
    with pytest.raises(ga4.Ga4Unavailable):
        ga4.fetch_rows("tok", "not-a-number", "2026-01-01", "2026-01-02")
    with pytest.raises(ga4.Ga4Unavailable):
        ga4.fetch_rows("tok", "123", "2026-02-01", "2026-01-02")


def _authed_client(tmp_path, email="boss@foap.test"):
    from fastapi.testclient import TestClient
    sys.path.insert(0, os.path.dirname(__file__))
    from ci_backend import employees as emp_store
    from ci_backend.app import create_app
    from ci_backend.config import Settings
    from conftest import employee_session
    db = str(tmp_path / "app.db")
    settings = Settings(workos_client_id="client_test",
                        key_workos="[REDACTED]", admin_email=email)
    app = create_app(db, settings)
    with employee_session(db) as sess:
        boss = emp_store.admin_create(sess, "root", email, role="admin")
        cookie = "ci_session=" + emp_store.create_session(sess, boss.id, "")
    http = TestClient(app, raise_server_exceptions=False)
    http.headers.update({"Cookie": cookie})
    return http


def test_export_endpoint_downloads_zip(tmp_path):
    http = _authed_client(tmp_path)
    res = http.post("/api/auth/export", json={})
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    assert "README.txt" in zf.namelist()
    anon = http.post("/api/auth/export", json={},
                     headers={"Cookie": ""})
    assert anon.status_code in (401, 403)


def test_templates_and_prefs_endpoints(tmp_path):
    http = _authed_client(tmp_path)
    made = http.post("/api/report-templates", json={
        "name": "Weekly",
        "config": {"campaigns": ["A"], "kpis": ["ctr"],
                   "benchmark": "industry", "format": "xlsx"}})
    assert made.status_code == 200, made.text
    tid = made.json()["id"]
    listed = http.get("/api/report-templates").json()["templates"]
    assert [t["id"] for t in listed] == [tid]
    updated = http.put(f"/api/report-templates/{tid}", json={
        "name": "Weekly v2",
        "config": {"campaigns": [], "kpis": [], "format": "pptx"}})
    assert updated.json()["name"] == "Weekly v2"
    assert http.delete(f"/api/report-templates/{tid}").status_code == 200
    assert http.get("/api/report-templates").json()["templates"] == []
    put = http.put("/api/preferences",
                   json={"prefs": {"workspace": "Acme",
                                   "email_reports": False}})
    assert put.status_code == 200
    prefs = http.get("/api/preferences").json()["prefs"]
    assert prefs["workspace"] == "Acme"
    assert prefs["email_reports"] is False


def test_analyst_narrative_mock_mode_is_labelled(conn, monkeypatch):
    monkeypatch.delenv("CREATIVE_INTEL_PROVIDER_MODE", raising=False)
    from ci_backend import worker_handlers
    narrative, source, _detail = worker_handlers._analyst_narrative(
        conn, {}, {"language": "en", "text": "facts"}, "q")
    assert narrative == ""
    assert source == "deterministic"
