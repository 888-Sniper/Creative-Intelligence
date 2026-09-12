"""Demo showcase seed: saved views + analyst chats pinned to demo rows.

Extends the synthetic demo dataset (Backend/ci_backend/actions.py
load_demo_dataset) with the API-backed content populated screens read:

- 7 saved views (4 benchmark cards with view="benchmark" + 3 compare
  views with view="compare") in saved_views, visible to every viewer
  through GET /api/views (the Benchmarks "Saved Benchmarks" cards and
  the Saved Insights grid both read that endpoint).
- 3 analyst conversations + messages + stored findings in
  analyst_conversations / analyst_messages / analyst_findings, built
  by running the REAL deterministic engine (analyst_chat.answer_turn)
  under the stable showcase owner "demo" — every message and finding
  is computed from the seeded rows, never invented.

Attribution + idempotency contract (mirrors the ads seed):

- Every row is demo-attributed: view names start with "Demo —",
  conversations carry owner_employee_id="demo" (a fixed showcase
  string, never an employee row — accounts/auth tables are untouched).
- Seeding skips what is present: each view inserts only when its
  name is missing; analyst turns run only when no demo-owned
  conversation exists. Reloads are verified no-ops and demo edits
  made during the session survive.
- Counts pinned elsewhere never move: 10 campaigns, 10 creatives,
  15 thumbnails — this module adds no ads/creatives/media rows.

Deliberately NOT seeded (no API-backed table/endpoint exists):

- Report generation history: ReportsPage history is localStorage plus
  client-side demo rows regenerated from the campaign catalog, so it
  is already populated from the 10 demo campaigns with zero backend
  rows. Seeding fake worker_jobs would forge per-owner job state the
  worker could pick up — dishonest and unsafe.
- Per-viewer recent chats: analyst conversations are strictly
  owner-scoped (cross-owner reads 404 by design). The showcase turns
  are seeded under the "demo" owner AND mirrored to every employee
  present at seed time (per-owner skip), so each seeded account opens
  with a populated Recent Chats; a fresh visitor's list fills in with
  their own first analyst turn. Pinned learnings and
  creative findings need no rows at all: they render live from
  /api/analyst/creatives over the seeded dataset.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

import sqlite3

from auth_help import authed
from ci_backend.actions import DEMO_ANALYST_OWNER, load_demo_dataset
from ci_backend.app import create_app
from ci_backend.config import Settings
from creative_intel import analyst_chat
from fastapi.testclient import TestClient


def _seeded_db(tmp_path):
    db = str(tmp_path / "demo-showcase.db")
    inserted = load_demo_dataset(db, media_dir=str(tmp_path / "media"))
    assert inserted > 0
    return db


def test_demo_saved_views_seeded(tmp_path):
    db = _seeded_db(tmp_path)
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT name, state_json FROM saved_views ORDER BY name"
        ).fetchall()
    import json

    assert len(rows) == 7
    names = [r[0] for r in rows]
    assert all(n.startswith("Demo — ") for n in names)
    by_name = {r[0]: json.loads(r[1]) for r in rows}
    benchmarks = [n for n in names
                  if by_name[n].get("view") == "benchmark"]
    compares = [n for n in names if by_name[n].get("view") == "compare"]
    assert len(benchmarks) == 4
    assert len(compares) == 3
    for name, state in by_name.items():
        assert set(state) <= {"filters", "kpi", "view", "benchmark",
                              "benchmark_scope", "rank_by"}, name
        assert state.get("benchmark_scope") in ("filters", "global"), name


def test_demo_saved_views_visible_through_api(tmp_path):
    db = _seeded_db(tmp_path)
    settings = Settings(workos_client_id="client_test",
                        key_workos="sk_test_demo",
                        admin_email="demo@foap.test",
                        data_dir=str(tmp_path))
    http = TestClient(create_app(db, settings),
                      raise_server_exceptions=False)
    cookie = authed(db, email="demo@foap.test", role="admin")
    r = http.get("/api/views", headers={"Cookie": cookie})
    assert r.status_code == 200, r.text
    views = r.json()
    assert len(views) == 7
    assert sum(1 for v in views
               if v["state"].get("view") == "benchmark") == 4
    # The Benchmarks page renders the first four rows as its saved
    # cards: benchmark cards sort before compare views, so all four
    # cards open benchmark states.
    assert [v["state"].get("view") for v in views[:4]] == \
        ["benchmark"] * 4


def test_demo_analyst_cards_yield_pinned_learnings(tmp_path):
    # Pinned Learnings need no seed rows: the Saved Insights page
    # derives them live from GET /api/analyst/creatives. Pin that the
    # seeded dataset actually yields them (high-priority first, else
    # the first three cards with a primary signal — the page's rule).
    db = _seeded_db(tmp_path)
    settings = Settings(workos_client_id="client_test",
                        key_workos="sk_test_demo",
                        admin_email="demo@foap.test",
                        data_dir=str(tmp_path))
    http = TestClient(create_app(db, settings),
                      raise_server_exceptions=False)
    cookie = authed(db, email="demo@foap.test", role="admin")
    r = http.get("/api/analyst/creatives?objective=reach",
                 headers={"Cookie": cookie})
    assert r.status_code == 200, r.text
    cards = r.json()["creatives"]
    assert len(cards) == 10
    with_signal = [c for c in cards
                   if (c.get("finding") or {}).get("primary_signal")]
    assert len(with_signal) >= 3
    pinned = [c for c in with_signal
              if (c.get("finding") or {}).get("priority") == "high"][:3]
    pinned = pinned or with_signal[:3]
    assert len(pinned) == 3


def test_demo_analyst_showcase_seeded(tmp_path):
    db = _seeded_db(tmp_path)
    with sqlite3.connect(db) as conn:
        convs = conn.execute(
            "SELECT id, owner_employee_id, title, objective"
            " FROM analyst_conversations"
            " WHERE owner_employee_id=?", (DEMO_ANALYST_OWNER,)).fetchall()
        assert len(convs) == 3
        owners = {c[1] for c in convs}
        assert owners == {DEMO_ANALYST_OWNER}
        assert all(c[2] for c in convs)  # every chat has a title
        conv_ids = [c[0] for c in convs]
        msgs = conn.execute(
            "SELECT COUNT(*) FROM analyst_messages"
            " WHERE conversation_id IN (%s)"
            % ",".join("?" * len(conv_ids)), conv_ids).fetchone()[0]
        assert msgs == 2 * len(convs)  # one user + one assistant turn each
        findings = conn.execute(
            "SELECT COUNT(*) FROM analyst_findings"
            " WHERE conversation_id IN (%s)"
            % ",".join("?" * len(conv_ids)), conv_ids).fetchone()[0]
        assert findings == 20  # two full-analysis turns x ten creatives
        # Library-level owner-scoped read sees the showcase chats.
        listed = analyst_chat.list_conversations(conn, DEMO_ANALYST_OWNER)
        assert len(listed) == 3
        # Stored findings are proposed, data-grounded, demo-scoped.
        import json as _json

        for (fid, fjson, status) in conn.execute(
                "SELECT id, finding_json, status FROM analyst_findings"
                " WHERE conversation_id IN (%s)"
                % ",".join("?" * len(conv_ids)), conv_ids).fetchall():
            assert status == "proposed"
            finding = _json.loads(fjson)
            assert finding.get("conversation_id") in conv_ids
            assert finding.get("primary_signal"), fid


def test_demo_showcase_reload_is_noop(tmp_path):
    db = _seeded_db(tmp_path)
    with sqlite3.connect(db) as conn:
        before = (
            conn.execute("SELECT COUNT(*) FROM saved_views").fetchone()[0],
            conn.execute(
                "SELECT COUNT(*) FROM analyst_conversations").fetchone()[0],
            conn.execute(
                "SELECT COUNT(*) FROM analyst_messages").fetchone()[0],
            conn.execute(
                "SELECT COUNT(*) FROM analyst_findings").fetchone()[0],
        )
    assert load_demo_dataset(db, media_dir=str(tmp_path / "media")) == 0
    with sqlite3.connect(db) as conn:
        after = (
            conn.execute("SELECT COUNT(*) FROM saved_views").fetchone()[0],
            conn.execute(
                "SELECT COUNT(*) FROM analyst_conversations").fetchone()[0],
            conn.execute(
                "SELECT COUNT(*) FROM analyst_messages").fetchone()[0],
            conn.execute(
                "SELECT COUNT(*) FROM analyst_findings").fetchone()[0],
        )
    assert after == before


def test_demo_seed_touches_no_auth_or_media_tables(tmp_path):
    db = _seeded_db(tmp_path)
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM employees").fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM auth_sessions").fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM media").fetchone()[0] == 10
        assert conn.execute(
            "SELECT COUNT(*) FROM creatives").fetchone()[0] == 10
