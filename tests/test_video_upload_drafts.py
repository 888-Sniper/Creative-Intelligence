"""WP1: drafts/videos/datasets/matches persistence (schema + module)."""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from creative_intel import drafts, schema

TABLES = ("drafts", "videos", "datasets", "matches")


def fresh_db(tmp_path):
    path = str(tmp_path / "drafts.db")
    conn = sqlite3.connect(path)
    schema.init_db(conn)
    return conn


def test_init_creates_upload_tables(tmp_path):
    conn = fresh_db(tmp_path)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(TABLES) <= names
    conn.close()


def test_migrate_upgrades_legacy_database(tmp_path):
    """An old file (pre-upload tables, with real rows) gains empty
    tables and keeps its data: no rewrite, no seeded rows."""
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    schema.init_db(conn)
    # Simulate a file written by the old code: full schema, real
    # rows, but none of the upload tables.
    conn.execute("INSERT INTO ads (platform, creative_key)"
                 " VALUES ('meta', 'hook-question-v1')")
    for table in TABLES:
        conn.execute("DROP TABLE %s" % table)
    conn.commit()
    schema.init_db(conn)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(TABLES) <= names
    assert conn.execute("SELECT creative_key FROM ads").fetchone() == (
        "hook-question-v1",)
    for table in TABLES:
        assert conn.execute("SELECT COUNT(*) FROM %s" % table).fetchone() == (0,)
    # Second open is a no-op upgrade (idempotent).
    schema.init_db(conn)
    conn.close()


def test_draft_roundtrip_and_owner_scope(tmp_path):
    conn = fresh_db(tmp_path)
    mine = drafts.create_draft(conn, "emp-1", spec={"client": "Foap"})
    assert drafts.get_draft(conn, mine)["status"] == "draft"
    assert drafts.get_draft(conn, mine)["owner_employee_id"] == "emp-1"
    other = drafts.create_draft(conn, "emp-2")
    assert [d["id"] for d in drafts.list_drafts(conn, "emp-1")] == [mine]
    assert [d["id"] for d in drafts.list_drafts(conn, "emp-2")] == [other]
    assert drafts.get_draft(conn, "nope") is None
    conn.close()


def test_create_draft_id_collision_across_owners(tmp_path):
    """A colliding client id from another owner is rejected, never
    served as the foreign draft (M11)."""
    conn = fresh_db(tmp_path)
    drafts.create_draft(conn, "emp-1", draft_id="shared")
    with pytest.raises(ValueError):
        drafts.create_draft(conn, "emp-2", draft_id="shared")
    assert drafts.get_draft(conn, "shared")["owner_employee_id"] == "emp-1"
    conn.close()


def test_create_draft_idempotent_on_retry(tmp_path):
    """Repeated POSTs (double click, network retry) return the same
    row untouched instead of duplicating drafts."""
    conn = fresh_db(tmp_path)
    first = drafts.create_draft(conn, "emp-1", draft_id="fixed",
                                spec={"v": 1})
    second = drafts.create_draft(conn, "emp-1", draft_id="fixed",
                                 spec={"v": 2})
    assert first == second == "fixed"
    assert conn.execute("SELECT COUNT(*) FROM drafts").fetchone() == (1,)
    import json
    assert json.loads(
        drafts.get_draft(conn, "fixed")["spec_json"]) == {"v": 1}
    conn.close()


def test_update_draft_status_rejects_unknown(tmp_path):
    conn = fresh_db(tmp_path)
    did = drafts.create_draft(conn, "emp-1")
    assert drafts.update_draft(conn, did, status="needs_confirmation")
    assert drafts.get_draft(conn, did)["status"] == "needs_confirmation"
    with pytest.raises(ValueError):
        drafts.update_draft(conn, did, status="teleporting")
    assert drafts.get_draft(conn, did)["status"] == "needs_confirmation"
    assert drafts.update_draft(conn, "missing", status="draft") is False
    with pytest.raises(ValueError):
        drafts.create_draft(conn, "  ")
    conn.close()


def test_video_and_dataset_links(tmp_path):
    conn = fresh_db(tmp_path)
    did = drafts.create_draft(conn, "emp-1")
    vid = drafts.add_video(conn, did, "video-upload-sample", media_id=7,
                           duration_s=15.0, width=1280, height=720,
                           sha256="abc",
                           validation={"status": "valid"})
    assert drafts.list_videos(conn, did)[0]["id"] == vid
    dsid = drafts.add_dataset(conn, did, "Video Upload Sample Dataset.csv",
                              rows=3, sha256="def")
    ds = drafts.list_datasets(conn, did)[0]
    assert ds["id"] == dsid and ds["rows"] == 3
    assert drafts.list_videos(conn, "other") == []
    conn.close()


def test_match_propose_confirm_and_invalidate(tmp_path):
    """Fuzzy proposals never confirm; only explicit confirmation
    sets confirmed; input changes clear it."""
    conn = fresh_db(tmp_path)
    did = drafts.create_draft(conn, "emp-1")
    records = [{"ad": "Sample Story V1", "impressions": 6000}]
    drafts.propose_match(conn, did, "video-upload-sample",
                         "fuzzy_filename", records)
    assert drafts.get_match(conn, did, "video-upload-sample")[
        "confirmed"] == 0
    drafts.confirm_match(conn, did, "video-upload-sample", "emp-1",
                         method="platform_id", records=records)
    match = drafts.get_match(conn, did, "video-upload-sample")
    assert (match["confirmed"], match["confirmed_by"]) == (1, "emp-1")
    drafts.clear_matches(conn, did)
    assert drafts.get_match(conn, did, "video-upload-sample") is None
    with pytest.raises(ValueError):
        drafts.propose_match(conn, did, "k", "telepathy", [])
    conn.close()
