"""Cohort delete + saved-view open/delete + dispatcher/video-eligibility tests.

Covers item 15 (admin-guarded audited DELETE /api/cohorts/{id} with
refresh persistence), item 28 (saved views: what Create Benchmark
persists, open support via GET, delete persisting after refresh) and
item 32 (dispatcher exact-model-only with no silent fallback; vision
frame-path refusal for text-only models).
"""

import os
import sqlite3
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import employees as emp_store  # noqa: E402
from ci_backend.app import create_app  # noqa: E402
from ci_backend.config import Settings  # noqa: E402
from conftest import employee_session  # noqa: E402
from creative_intel import dispatcher as dispatcher_mod  # noqa: E402
from creative_intel import provider_inventory as inv_mod  # noqa: E402
from creative_intel import providers as providers_mod  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _client(tmp_path, role="admin"):
    db = str(tmp_path / ("app-%s.db" % role))
    settings = Settings(workos_client_id="client_test",
                        key_workos="[REDACTED]")
    app = create_app(db, settings)
    with employee_session(db) as sess:
        who = emp_store.admin_create(sess, "root-%s" % role,
                                     "%s@foap.test" % role, role=role)
        cookie = "ci_session=" + emp_store.create_session(sess, who.id, "")
    http = TestClient(app, raise_server_exceptions=False)
    http.headers.update({"Cookie": cookie})
    return http


# ---------------------------------------------------------------------------
# Item 15: cohort DELETE
# ---------------------------------------------------------------------------

def test_cohort_delete_admin_roundtrip(tmp_path):
    http = _client(tmp_path, "admin")
    created = http.post("/api/cohorts", json={
        "name": "Beauty", "filters": {"platform": ["tiktok"]}})
    assert created.status_code == 200, created.text
    cohort_id = created.json()["id"]
    assert [c["name"] for c in http.get("/api/cohorts").json()] == ["Beauty"]
    deleted = http.delete("/api/cohorts/%d" % cohort_id)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == "Beauty"
    # Refresh persistence: a re-fetched list stays empty.
    assert http.get("/api/cohorts").json() == []
    # Deleting twice is a clean 404, not a crash.
    again = http.delete("/api/cohorts/%d" % cohort_id)
    assert again.status_code == 404, again.text


def test_cohort_delete_unknown_id_is_404(tmp_path):
    http = _client(tmp_path, "admin")
    resp = http.delete("/api/cohorts/424242")
    assert resp.status_code == 404, resp.text


def test_cohort_delete_forbidden_for_non_admin(tmp_path):
    http = _client(tmp_path, "employee")
    created = http.post("/api/cohorts", json={"name": "Beauty"})
    assert created.status_code == 200, created.text
    resp = http.delete("/api/cohorts/%d" % created.json()["id"])
    assert resp.status_code == 403, resp.text
    # Nothing was removed.
    assert len(http.get("/api/cohorts").json()) == 1


def test_cohort_delete_anonymous_is_denied(tmp_path):
    admin = _client(tmp_path, "admin")
    created = admin.post("/api/cohorts", json={"name": "Beauty"})
    assert created.status_code == 200, created.text
    # Same app, no session cookie.
    anon = TestClient(admin.app, raise_server_exceptions=False)
    resp = anon.delete("/api/cohorts/%d" % created.json()["id"])
    assert resp.status_code in (401, 403), resp.text


# ---------------------------------------------------------------------------
# Item 28: saved views open/delete
# ---------------------------------------------------------------------------

def test_saved_view_create_open_delete_roundtrip(tmp_path):
    http = _client(tmp_path, "admin")
    # What Create Benchmark persists: grouping + filters + kpi.
    saved = http.post("/api/views", json={
        "name": "Benchmark X",
        "state": {"filters": {"platform": ["meta"]}, "kpi": "roas",
                  "view": "benchmark", "benchmark": "platform",
                  "benchmark_scope": "filters"}})
    assert saved.status_code == 200, saved.text
    view_id = saved.json()["id"]
    # Open support: GET lists the exact persisted state back.
    listed = http.get("/api/views").json()
    hit = next(v for v in listed if v["id"] == view_id)
    assert hit["state"]["benchmark"] == "platform"
    assert hit["state"]["filters"] == {"platform": ["meta"]}
    assert hit["state"]["view"] == "benchmark"
    # Delete persists after refresh.
    deleted = http.post("/api/views/delete", json={"id": view_id})
    assert deleted.status_code == 200, deleted.text
    assert all(v["id"] != view_id for v in http.get("/api/views").json())
    # Unknown id is a clean 409 (existing contract), not a crash.
    assert http.post("/api/views/delete",
                     json={"id": 424242}).status_code == 409


# ---------------------------------------------------------------------------
# Item 32: dispatcher never substitutes; vision refuses text-only
# ---------------------------------------------------------------------------

def _selection_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE active_provider_selection (id INTEGER PRIMARY KEY,"
        " provider_id TEXT, model_id TEXT, revision INTEGER,"
        " updated_by TEXT, updated_at TEXT)")
    conn.execute(
        "CREATE TABLE provider_configs (provider_id TEXT PRIMARY KEY,"
        " display TEXT, kind TEXT, base_url TEXT, secret_enc TEXT,"
        " secret_updated_at TEXT, created_at TEXT, updated_at TEXT)")
    conn.execute(
        "CREATE TABLE provider_model_cache (provider_id TEXT,"
        " model_id TEXT, display TEXT, offered INTEGER, fetched_at TEXT)")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO active_provider_selection (id, provider_id,"
        " model_id, revision, updated_by, updated_at)"
        " VALUES (1, 'openai', 'gpt-9.9-fictional', 1, 'admin', ?)", (now,))
    conn.execute(
        "INSERT INTO provider_model_cache (provider_id, model_id,"
        " display, offered, fetched_at) VALUES"
        " ('openai', 'gpt-5.6-luna', 'GPT 5.6 Luna', 1, ?)", (now,))
    conn.commit()
    return conn


def test_dispatcher_never_substitutes_unlisted_model(tmp_path):
    conn = _selection_db(str(tmp_path / "sel.db"))
    try:
        with pytest.raises(providers_mod.ProviderUnavailable) as exc:
            dispatcher_mod._resolve(conn)
    finally:
        conn.close()
    text = str(exc.value)
    # Fails closed naming the requested id …
    assert "gpt-9.9-fictional" in text
    # … and never names (let alone dials) the cached alternative.
    assert "gpt-5.6-luna" not in text
    assert "[provider=openai]" in text


def test_vision_refuses_text_only_model_without_fallback(tmp_path):
    _ = tmp_path
    vision = providers_mod.LiveVision([("deepseek", "deepseek-v4-flash",
                                        "active")])
    with pytest.raises(providers_mod.ProviderUnavailable) as exc:
        vision.annotate([{"t_sec": 0.0}], images=[b"\xff\xd8\xfffake"])
    assert "deepseek-v4-flash" in str(exc.value)


def test_frame_support_levels():
    assert inv_mod.video_eligible("gemini", "gemini-2.5-flash") is True
    assert inv_mod.video_eligible("anthropic", "claude-haiku-4-5") is False
    level, doc = inv_mod.frame_support("anthropic", "claude-haiku-4-5")
    assert level == "image" and doc.startswith("https://")
    # Fictional/future ids are never presented as capable.
    assert inv_mod.frame_support("openai", "gpt-5.6-luna") == (
        "unverified", "")
    assert inv_mod.video_eligible("openai", "gpt-5.6-luna") is False


def test_frame_eligible_covers_ffmpeg_outputs():
    # Native-video ids qualify, and so do image-level ids: ffmpeg
    # emits timed JPEG frames, which any image-input model can read
    # (the WAV track goes to the STT roster).
    assert inv_mod.frame_eligible("gemini", "gemini-2.5-flash") is True
    assert inv_mod.frame_eligible("anthropic", "claude-haiku-4-5") is True
    assert inv_mod.frame_eligible("openrouter", "openai/gpt-4o-mini") is True
    assert inv_mod.frame_eligible("deepseek", "deepseek-chat") is False
    assert inv_mod.frame_eligible("kimi", "kimi-k3") is False
    assert inv_mod.frame_eligible("openai", "gpt-5.6-luna") is False


# ---------------------------------------------------------------------------
# Item 30: max_points retasks analysis-shaped questions to condense
# ---------------------------------------------------------------------------

_JOURNEY_CSV = (
    "Campaign,Ad,Impressions,2s views,3s views,25% views,"
    "50% views,Completions,Watch time,Video views,Spend,"
    "Link clicks,Message\n"
    "C,A,5000,1500,1200,900,500,300,5900,5000,50,40,promotional\n"
    "C,B,5000,500,400,300,150,80,5100,5000,50,10,neutral\n"
    "C,C,5000,200,150,120,60,30,3000,5000,50,5,neutral\n")


def _seeded_conn():
    from creative_intel import ingest as ingest_mod
    from creative_intel import schema as schema_mod
    conn = sqlite3.connect(":memory:")
    schema_mod.init_db(conn)
    ingest_mod.import_report(conn, _JOURNEY_CSV, "tiktok")
    return conn


def test_max_points_retasks_analysis_question_to_condense():
    from creative_intel import analyst_chat as chat_mod
    conn = _seeded_conn()
    try:
        # Plain analysis wording: without max_points this is a full
        # table; with max_points the 3 Points button must visibly
        # condense instead of silently ignoring the cap.
        out = chat_mod.answer_turn(
            conn, "e1", "Which hook types drive the highest CTR?",
            scope={"campaign": ["C"]}, max_points=3)
        assert out["task"] == "condense", out["task"]
        assert out["payload"]["condensed_to"] == 3
        assert out["text"].startswith("In 3 points")
        points = [ln for ln in out["text"].splitlines()
                  if len(ln) > 2 and ln[0].isdigit()]
        assert len(points) == 3
    finally:
        conn.close()


def test_condense_empty_scope_explains_instead_of_zero_points():
    from creative_intel import analyst_chat as chat_mod
    conn = _seeded_conn()
    try:
        # No matching rows: the honest empty-scope message stands,
        # never a hollow points header.
        out = chat_mod.answer_turn(
            conn, "e1", "Which hook types drive the highest CTR?",
            scope={"campaign": ["ZZZ"]}, max_points=3)
        assert "In 0 points" not in out["text"]
        assert "No rows match this scope" in out["text"]
    finally:
        conn.close()


def test_route_task_spanish_condense_phrase():
    from creative_intel import analyst_chat as chat_mod
    # The UI's es 3 Points override must route to condense, like the
    # en/pl equivalents (route_task matches wording, not max_points).
    task, _args = chat_mod.route_task(
        "Condensa la última respuesta en 3 puntos.", [])
    assert task == "condense"
    task, _args = chat_mod.route_task(
        "Condense the last answer to 3 points.", [])
    assert task == "condense"
    task, _args = chat_mod.route_task(
        "Skróć ostatnią odpowiedź do 3 punktów.", [])
    assert task == "condense"


def test_condense_without_findings_explains_instead_of_zero_points():
    from creative_intel import ingest as ingest_mod
    from creative_intel import schema as schema_mod
    from creative_intel import analyst_chat as chat_mod
    # One strong creative: analysis succeeds but fires no findings,
    # so there is nothing to condense.
    conn = sqlite3.connect(":memory:")
    schema_mod.init_db(conn)
    ingest_mod.import_report(
        conn,
        "Campaign,Ad,Impressions,2s views,3s views,25% views,"
        "50% views,Completions,Watch time,Video views,Spend,"
        "Link clicks,Message\n"
        "C,A,5000,4800,4700,4600,4500,4400,59000,5000,50,4000,"
        "promotional\n",
        "tiktok")
    try:
        out = chat_mod.answer_turn(
            conn, "e1", "Condense the last answer to 3 points.",
            scope={"campaign": ["C"]}, max_points=3)
        assert out["task"] == "condense"
        assert "In 0 points" not in out["text"]
        assert "No recommendations to condense" in out["text"]
    finally:
        conn.close()


import pytest  # noqa: E402
