"""Five-campaign v2 pack: strict verification, retry-safe identity,
ownership safety, review-only migration, recoverable finalisation.

Isolated temp DBs, never the live team database.
"""

import json
import os
import sqlite3
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

import pytest
from ci_backend.actions import save_view
from creative_intel import demo_pack, schema as S


@pytest.fixture(autouse=True)
def _isolated_media_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_INTEL_MEDIA_DIR",
                       str(tmp_path / "media"))


def _db(tmp_path, name="packv2.db"):
    db = str(tmp_path / name)
    conn = sqlite3.connect(db)
    S.init_db(conn)
    return db, conn


def _import_v2(conn, md, by="admin1"):
    core = demo_pack.import_pack_v2(conn, imported_by=by,
                                    workspace="test", media_dir=md)
    assert core.get("phase") == "core", core
    fin = demo_pack.finalize_pack_v2(conn, core["batch_id"],
                                     imported_by=by, media_dir=md,
                                     core_counts=core["counts"])
    return core["batch_id"], fin


def test_full_import_passes_strict_verify(tmp_path):
    _, conn = _db(tmp_path)
    md = os.path.join(str(tmp_path), "media")
    bid, fin = _import_v2(conn, md)
    assert fin["created"] is True
    ok, detail = demo_pack.verify_pack_v2(conn, bid, md)
    assert ok, detail
    assert detail["db"]["campaigns"] == 5
    assert detail["db"]["creatives"] == 15
    assert detail["db"]["media_rows"] == 15
    assert detail["db"]["sample_files"] == 9
    assert detail["db"]["saved_views"] == 10
    assert detail["db"]["conversations"] == 6
    assert demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)["status"] \
        == "added"


def test_workbooks_prefilled_with_pack_figures(tmp_path):
    _, conn = _db(tmp_path)
    md = os.path.join(str(tmp_path), "media")
    bid, fin = _import_v2(conn, md)
    assert fin["created"] is True
    keys = [r[0] for r in conn.execute(
        "SELECT file_key FROM sample_files WHERE batch_id=? AND format=?",
        (bid, "workbook"))]
    assert len(keys) == 3
    for fk in keys:
        name = conn.execute(
            "SELECT name FROM sample_files WHERE file_key=?",
            (fk,)).fetchone()[0]
        path = os.path.join(md, "sample", bid, name)
        with zipfile.ZipFile(path) as z:
            blob = z.read("xl/sharedStrings.xml").decode("utf-8")
        assert "smp-" in blob, name  # Input rows carry creative keys
        assert "Prefilled Sample" in blob, name  # honestly labelled


def test_view_retry_reuses_sample2_never_mints_sample3(tmp_path):
    _, conn = _db(tmp_path)
    bid = "batch-retry-1"
    user = save_view(conn, "Sample \u2014 Benchmark: Foo",
                     {"filters": {}, "kpi": "roas"})
    first, created = demo_pack._v2_claim_view(
        conn, bid, "Sample \u2014 Benchmark: Foo",
        {"filters": {}, "kpi": "roas"})
    assert created is True
    row = conn.execute("SELECT name FROM saved_views WHERE id=?",
                       (first,)).fetchone()
    assert row[0] == "Sample \u2014 Benchmark: Foo (Sample 2)"
    second, created2 = demo_pack._v2_claim_view(
        conn, bid, "Sample \u2014 Benchmark: Foo",
        {"filters": {}, "kpi": "roas"})
    assert (second, created2) == (first, False)
    names = [r[0] for r in conn.execute(
        "SELECT name FROM saved_views WHERE name LIKE ?",
        ("Sample \u2014 Benchmark: Foo%",))]
    assert sorted(names) == ["Sample \u2014 Benchmark: Foo",
                             "Sample \u2014 Benchmark: Foo (Sample 2)"]
    # The user's own row was never adopted or tracked.
    assert str(user["id"]) not in demo_pack._member_keys(
        conn, bid, "saved_views")


def test_conversation_retry_never_adopts_user_row(tmp_path):
    _, conn = _db(tmp_path)
    md = os.path.join(str(tmp_path), "media")
    bid, fin = _import_v2(conn, md)
    assert fin["created"] is True
    question, scope, _, _ = demo_pack.SAMPLE_QUESTIONS_V2[0]
    scoped = dict(scope or {})
    scoped["sample_batch"] = [bid]
    title = question[:60]
    # A genuine user conversation sharing owner/title/scope/timing.
    user_id = "user-conv-during-import"
    conn.execute(
        "INSERT INTO analyst_conversations (id, owner_employee_id, title,"
        " scope_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, "admin1", title, json.dumps(scoped),
         demo_pack._utcnow()))
    conn.execute("INSERT INTO analyst_messages (conversation_id, role,"
                 " body_text, created_at) VALUES (?, 'user', 'my own q', ?)",
                 (user_id, demo_pack._utcnow()))
    conn.commit()
    # Simulate a crash that lost tracking for this title.
    tracked = [c for c in demo_pack._member_keys(
        conn, bid, "analyst_conversations")
        if (conn.execute("SELECT title FROM analyst_conversations"
                         " WHERE id=?", (c,)).fetchone() or [""])[0]
        == title]
    assert len(tracked) == 1
    conn.execute("DELETE FROM demo_batch_members WHERE batch_id=?"
                 " AND table_name='analyst_conversations' AND record_key=?",
                 (bid, str(tracked[0])))
    conn.commit()
    new_id, created = demo_pack._v2_claim_conversation(
        conn, bid, "admin1", question, scoped, None, None)
    assert created is True
    assert new_id != user_id
    assert str(user_id) not in demo_pack._member_keys(
        conn, bid, "analyst_conversations")
    assert str(new_id) in demo_pack._member_keys(
        conn, bid, "analyst_conversations")


def test_verify_rejects_pack_without_media_or_files(tmp_path):
    _, conn = _db(tmp_path)
    bid = "batch-bare-1"
    for ci in range(5):
        for ki in range(3):
            key = "bare-c%d-k%d" % (ci, ki)
            conn.execute(
                "INSERT INTO ads (platform, source, campaign, ad_name,"
                " creative_key, date, campaign_id, spend, import_id)"
                " VALUES ('meta','sample','Bare %d','Ad %d','%s',"
                " '2026-02-%02d','BARE-%d', 1.0, ?)"
                % (ci, ki, key, ki + 1, ci), (bid,))
            conn.execute("INSERT INTO creatives (creative_key, name)"
                         " VALUES (?, ?)", (key, key))
            demo_pack._track(conn, bid, "creatives", key)
    conn.commit()
    ok, detail = demo_pack.verify_pack_v2(conn, bid, str(tmp_path))
    assert ok is False
    assert detail["db"]["campaigns"] == 5
    assert detail["db"]["creatives"] == 15
    assert detail["db"]["media_rows"] == 0
    assert detail["db"]["sample_files"] == 0
    assert detail["db"]["sample_files_expected"] == 9
    assert detail["db"]["saved_views"] == 0
    assert detail["db"]["conversations"] == 0


def test_finalize_failure_recorded_and_retry_recovers(
        tmp_path, monkeypatch):
    from creative_intel import analyst_chat as chat
    _, conn = _db(tmp_path)
    md = os.path.join(str(tmp_path), "media")
    core = demo_pack.import_pack_v2(conn, imported_by="admin1",
                                    workspace="test", media_dir=md)
    bid = core["batch_id"]

    def _boom(*a, **k):
        raise RuntimeError("simulated analyst outage")
    monkeypatch.setattr(chat, "answer_turn", _boom)
    with pytest.raises(RuntimeError):
        demo_pack.finalize_pack_v2(conn, bid, imported_by="admin1",
                                   media_dir=md,
                                   core_counts=core["counts"])
    st = demo_pack.pack_status(conn, demo_pack.PACK_KEY_V2)
    assert st["status"] == "failed"
    assert "finalize:" in (st["receipt"]["counts_json"] or "")
    # Retry after the outage resumes without duplicating tracked rows.
    monkeypatch.undo()
    fin = demo_pack.finalize_pack_v2(conn, bid, imported_by="admin1",
                                     media_dir=md,
                                     core_counts=core["counts"])
    assert fin["created"] is True
    ok, detail = demo_pack.verify_pack_v2(conn, bid, md)
    assert ok, detail


def test_migration_keeps_review_views_and_verifies(tmp_path):
    _, conn = _db(tmp_path)
    md = os.path.join(str(tmp_path), "media")
    core = demo_pack.import_pack(conn, imported_by="admin1",
                                 workspace="test", media_dir=md)
    fin = demo_pack.finalize_pack(conn, core["batch_id"], media_dir=md,
                                  core_counts=core["counts"])
    assert fin["counts"]["campaigns"] == 10
    batch = core["batch_id"]
    views_before = len(demo_pack._member_keys(conn, batch, "saved_views"))
    assert views_before == 10
    out = demo_pack.migrate_to_v2(conn, imported_by="admin1",
                                  authorize=True, media_dir=md)
    assert out["authorized"] is True
    assert len(out["deleted"]) == 5
    assert out.get("verified") is True, out.get("verify")
    # Review-only v1 views survive the nested campaign deletes.
    alive_views = conn.execute(
        "SELECT COUNT(*) FROM saved_views WHERE id IN (%s)" % ",".join(
            "?" * views_before),
        demo_pack._member_keys(conn, batch, "saved_views")).fetchone()[0]
    assert alive_views == 10
    assert demo_pack.pack_status(
        conn, demo_pack.PACK_KEY_V2)["status"] == "added"
    assert demo_pack.pack_status(
        conn, demo_pack.PACK_KEY)["status"] == "migrated"
