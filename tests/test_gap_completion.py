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


def test_export_includes_seeded_conversation_history(conn):
    conn.execute(
        "INSERT INTO analyst_conversations (id, owner_employee_id, title,"
        " objective, language, scope_json, dataset_version, created_at,"
        " updated_at) VALUES ('c1', 'emp-1', 'T', 'reach', 'en', '{}', '',"
        " '2026-01-01', '2026-01-01')")
    conn.execute(
        "INSERT INTO analyst_messages (id, conversation_id, role, kind,"
        " body_text, payload_json, created_at) VALUES (1, 'c1', 'user',"
        " 'question', 'hello history', '{}', '2026-01-01')")
    conn.commit()
    blob, _name = data_export.build_export(
        conn, {"id": "emp-1", "email": "a@b.c", "status": "active"})
    zf = zipfile.ZipFile(io.BytesIO(blob))
    convs = json.loads(zf.read("conversations.json"))
    msgs = json.loads(zf.read("messages.json"))
    assert [c["id"] for c in convs] == ["c1"]
    assert msgs and msgs[0]["body_text"] == "hello history"


def test_ga4_pagination_and_owner_rows(conn, tmp_path, monkeypatch):
    import creative_intel.ga4 as ga4_mod

    def row(date, src):
        return {"dimensionValues": [{"value": date}, {"value": src},
                                    {"value": "cpc"}, {"value": ""}],
                "metricValues": [{"value": "3"}, {"value": "2"},
                                 {"value": "1"}]}

    big = [row("20260101", "s%d" % i) for i in range(10000)]
    small = [row("20260102", "tail")]
    pages = iter([
        {"rows": big, "rowCount": 10001,
         "metadata": {"timeZone": "Europe/Warsaw"}},
        {"rows": small, "rowCount": 10001,
         "metadata": {"timeZone": "Europe/Warsaw"}}])
    monkeypatch.setattr(ga4_mod, "_post", lambda u, t, p: next(pages))
    rows = ga4_mod.fetch_rows("tok", "123", "2026-01-01", "2026-01-02")
    assert len(rows) == 10001
    assert rows[-1]["session_source"] == "tail"
    assert rows[0]["timezone"] == "Europe/Warsaw"

    http = _authed_client(tmp_path)
    seeded = http.get("/api/integrations/ga4/rows")
    assert seeded.status_code == 200
    assert seeded.json()["rows"] == []


def test_notification_dedup_claimed_before_send(conn):
    # A pre-claimed queued slot (concurrent winner) must block sending.
    conn.execute(
        "INSERT INTO notification_outbox (id, employee_id, kind, subject,"
        " body, status, detail, dedup_key, created_at, sent_at) VALUES"
        " ('n0', 'emp-1', 'analysis_ready', 's', 'b', 'queued', '',"
        " 'dup-1', '2026-01-01', '')")
    conn.commit()
    sent = []
    out = notifications.enqueue(
        conn, "emp-1", "analysis_ready", "s", "b", dedup_key="dup-1",
        recipient="a@b.c", sender=lambda to, s, b: sent.append(to))
    assert out.get("duplicate") is True
    assert sent == []


def test_spanish_language_accepted_by_analyst_body(tmp_path):
    http = _authed_client(tmp_path)
    res = http.post("/api/analyst/conversations", json={
        "objective": "reach", "language": "es"})
    assert res.status_code == 200, res.text
    cid = res.json()["id"]
    got = http.get("/api/analyst/conversations/%s" % cid)
    assert got.status_code == 200, got.text
    assert got.json()["language"] == "es"


def test_ga4_same_property_two_employees_keep_own_rows(conn, monkeypatch):
    import creative_intel.ga4 as ga4_mod
    fake = [{"date": "2026-01-01", "session_source": "google",
             "session_medium": "cpc", "session_campaign": "x",
             "sessions": 5, "total_users": 4, "conversions": 1.0,
             "timezone": "UTC"}]
    monkeypatch.setattr(ga4_mod, "fetch_rows",
                        lambda *a, **k: list(fake))
    ga4_mod.import_rows(conn, "tok", "123", "2026-01-01", "2026-01-01",
                        imported_by="emp-A")
    ga4_mod.import_rows(conn, "tok", "123", "2026-01-01", "2026-01-01",
                        imported_by="emp-B")
    owners = {r[0] for r in conn.execute(
        "SELECT imported_by FROM ga4_rows WHERE property_id='123'")}
    assert owners == {"emp-A", "emp-B"}


def test_notification_concurrent_dedup_sends_once(tmp_path):
    import threading
    db = str(tmp_path / "race.db")
    c0 = sqlite3.connect(db)
    schema_mod.init_db(c0)
    c0.close()
    sent = []
    barrier = threading.Barrier(2)

    def worker():
        c = sqlite3.connect(db, timeout=30)
        barrier.wait(timeout=10)
        notifications.enqueue(
            c, "emp-1", "analysis_ready", "s", "b", dedup_key="race-1",
            recipient="a@b.c",
            sender=lambda to, s, b: sent.append(to))
        c.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sent == ["a@b.c"]


def test_gemini_stt_uses_managed_secret(monkeypatch):
    captured = {}

    def fake_init(self, model, secret=None, base_url=None):
        captured["secret"] = secret
        captured["base_url"] = base_url
        self.model = model

    monkeypatch.setattr(prov_mod.GeminiChat, "__init__", fake_init)
    monkeypatch.setattr(
        prov_mod.GeminiChat, "chat",
        lambda self, messages, max_tokens=2048:
            json.dumps({"transcript": "ok", "confidence": 0.5}))
    text, _conf = prov_mod.GeminiStt(
        secret="managed-key", base_url="http://127.0.0.1:9").transcribe(
            "ck", audio_bytes=b"RIFFx", mime="audio/wav")
    assert text == "ok"
    assert captured["secret"] == "managed-key"
    assert captured["base_url"] == "http://127.0.0.1:9"


def test_ga4_migration_recovers_stranded_rows(tmp_path):
    db = str(tmp_path / "mig.db")
    c = sqlite3.connect(db)
    # Pre-fix schema (owner-less UNIQUE) with live data, plus a
    # stranded ga4_rows_new from an interrupted earlier migration.
    c.executescript(
        "CREATE TABLE ga4_rows (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " property_id TEXT NOT NULL DEFAULT '', date TEXT NOT NULL"
        " DEFAULT '', session_source TEXT NOT NULL DEFAULT '',"
        " session_medium TEXT NOT NULL DEFAULT '', session_campaign"
        " TEXT NOT NULL DEFAULT '', sessions INTEGER NOT NULL DEFAULT 0,"
        " total_users INTEGER NOT NULL DEFAULT 0, conversions REAL"
        " NOT NULL DEFAULT 0, timezone TEXT NOT NULL DEFAULT '',"
        " imported_by TEXT NOT NULL DEFAULT '', imported_at TEXT NOT"
        " NULL DEFAULT '', UNIQUE (property_id, date, session_source,"
        " session_medium, session_campaign));"
        "CREATE TABLE ga4_rows_new (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " property_id TEXT NOT NULL DEFAULT '', date TEXT NOT NULL"
        " DEFAULT '', session_source TEXT NOT NULL DEFAULT '',"
        " session_medium TEXT NOT NULL DEFAULT '', session_campaign"
        " TEXT NOT NULL DEFAULT '', sessions INTEGER NOT NULL DEFAULT 0,"
        " total_users INTEGER NOT NULL DEFAULT 0, conversions REAL"
        " NOT NULL DEFAULT 0, timezone TEXT NOT NULL DEFAULT '',"
        " imported_by TEXT NOT NULL DEFAULT '', imported_at TEXT NOT"
        " NULL DEFAULT '', UNIQUE (property_id, date, session_source,"
        " session_medium, session_campaign, imported_by));")
    c.execute("INSERT INTO ga4_rows (property_id, date, session_source,"
              " imported_by) VALUES ('123', '2026-01-01', 'a', 'emp-A')")
    c.execute("INSERT INTO ga4_rows_new (property_id, date,"
              " session_source, imported_by) VALUES"
              " ('123', '2026-01-02', 'b', 'emp-B')")
    c.commit()
    schema_mod.init_db(c)
    rows = sorted(r[0] for r in c.execute(
        "SELECT session_source FROM ga4_rows WHERE property_id='123'"))
    assert rows == ["a", "b"]
    names = {r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "ga4_rows_new" not in names and "ga4_rows_stash" not in names
    # Idempotent second open.
    schema_mod.init_db(c)
    assert c.execute("SELECT COUNT(*) FROM ga4_rows").fetchone()[0] == 2
    c.close()


def test_notification_forced_overlap_sends_once(tmp_path):
    import threading
    db = str(tmp_path / "race2.db")
    c0 = sqlite3.connect(db)
    schema_mod.init_db(c0)
    c0.close()
    sent = []
    in_send = threading.Event()
    release = threading.Event()

    def slow_sender(to, s, b):
        # Signal mid-delivery, then BLOCK until released. Raise a
        # distinctive error on timeout (not assert): enqueue would
        # swallow AssertionError as a delivery failure and could
        # mask a broken test as a pass.
        in_send.set()
        if not release.wait(timeout=30):
            raise RuntimeError("test harness: release never set")
        sent.append(to)

    outcomes = []

    def worker():
        c = sqlite3.connect(db, timeout=30)
        outcomes.append(notifications.enqueue(
            c, "emp-1", "analysis_ready", "s", "b",
            dedup_key="race-2", recipient="a@b.c", sender=slow_sender))
        c.close()

    first = threading.Thread(target=worker)
    first.start()
    # Deterministic overlap: thread two starts only once thread
    # one is provably inside the sender, then releases it after
    # thread two's enqueue attempt has completed (duplicate) —
    # under claim-after-send both would deliver.
    assert in_send.wait(timeout=30)
    second = threading.Thread(target=worker)
    second.start()
    second.join(timeout=30)
    # The second worker must have COMPLETED (as duplicate) while
    # the first delivery was still blocked — under claim-after-
    # send it would instead be inside its own sender here.
    assert len(outcomes) == 1
    assert outcomes[0].get("duplicate") is True
    assert sent == []
    release.set()
    first.join(timeout=30)
    assert sent == ["a@b.c"]
    assert len(outcomes) == 2
    assert sum(1 for o in outcomes if o.get("duplicate")) == 1
    # The first (real) delivery must have SUCCEEDED — a sender
    # timeout swallowed as "failed" must not satisfy this test.
    assert sum(1 for o in outcomes if o.get("status") == "sent") == 1


def test_analyst_narrative_mock_mode_is_labelled(conn, monkeypatch):
    monkeypatch.delenv("CREATIVE_INTEL_PROVIDER_MODE", raising=False)
    from ci_backend import worker_handlers
    narrative, source, _detail = worker_handlers._analyst_narrative(
        conn, {}, {"language": "en", "text": "facts"}, "q")
    assert narrative == ""
    assert source == "deterministic"
