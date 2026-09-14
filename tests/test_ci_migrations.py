"""Alembic authority tests (pytest, Nextly migration-test pattern).

Identity tables evolve through Backend/alembic versions only:
fresh upgrade, downgrade, re-upgrade, legacy create_all databases,
and live enforcement of the 0002 constraints.
"""

import os
import sys

import pytest
from sqlalchemy import inspect, text

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import employees as emp
from ci_backend.db import ensure_migrated, init_db, make_engine, make_session_factory


def _upgrade(engine, revision):
    from ci_backend.db import migrate
    migrate(engine, revision)


def _downgrade(engine, revision):
    from ci_backend.db import migrate
    migrate(engine, revision)


def _version(engine):
    with engine.connect() as conn:
        return [r[0] for r in
                conn.execute(text("SELECT version_num FROM alembic_version"))]
def test_fresh_upgrade_downgrade_upgrade(tmp_path):
    engine = make_engine(str(tmp_path / "mig.db"))
    ensure_migrated(engine)
    assert _version(engine) == ["0012"]
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
    assert {"employees", "auth_sessions", "auth_pending",
            "employee_audit"} <= tables
    # Managed-provider tables exist, configs seeded secretless, and
    # no selection is pre-activated (paused by default).
    assert {"provider_configs", "provider_model_cache",
            "active_provider_selection"} <= tables
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM provider_configs")
                         ).fetchone()[0]
        secrets = conn.execute(text("SELECT COUNT(*) FROM provider_configs"
                                    " WHERE secret_enc IS NOT NULL")
                               ).fetchone()[0]
        sel = conn.execute(text("SELECT COUNT(*) FROM"
                                " active_provider_selection")).fetchone()[0]
    assert n == 17 and secrets == 0 and sel == 0
    _downgrade(engine, "0001")
    assert _version(engine) == ["0001"]
    with engine.connect() as conn:
        cols = {c["name"] for c in inspect(conn).get_columns("auth_sessions")}
    assert "container_id" not in cols
    _upgrade(engine, "head")
    assert _version(engine) == ["0012"]
    with engine.connect() as conn:
        cols = {c["name"] for c in inspect(conn).get_columns("auth_sessions")}
    assert "container_id" in cols
    # Full teardown to base drops identity tables, and a fresh boot
    # re-creates them at head (downgrade-base re-upgrade path).
    _downgrade(engine, "base")
    assert _version(engine) == []
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
    assert not ({"employees", "auth_sessions", "auth_pending",
                 "employee_audit"} & tables)
    ensure_migrated(engine)
    assert _version(engine) == ["0012"]
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
    assert {"employees", "auth_sessions", "auth_pending",
            "employee_audit"} <= tables
    # App boot stays on head and is idempotent.
    ensure_migrated(engine)
    assert _version(engine) == ["0012"]
    engine.dispose()

def test_ensure_upgrades_behind_database_forward(tmp_path):
    from ci_backend.db import script_head
    assert script_head() == "0012"
    engine = make_engine(str(tmp_path / "behind.db"))
    ensure_migrated(engine)
    _downgrade(engine, "0003")
    assert _version(engine) == ["0003"]
    # Boot no longer sits stale on an old revision: it upgrades.
    ensure_migrated(engine)
    assert _version(engine) == ["0012"]
    with engine.connect() as conn:
        cols = {c["name"] for c in inspect(conn).get_columns("oauth_tokens")}
    assert "refresh_token_enc" in cols
    engine.dispose()

def test_legacy_create_all_db_migrates_with_data(tmp_path):
    engine = make_engine(str(tmp_path / "legacy.db"))
    init_db(engine)  # pre-Alembic path: tables, no version stamp
    with make_session_factory(engine)() as sess:
        admin = emp.admin_create(sess, "root", "ada@foap.test", role="admin")
        emp.create_session(sess, admin.id, "")
    ensure_migrated(engine)
    assert _version(engine) == ["0012"]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM employees")
                            ).fetchone()[0] == 1
        assert conn.execute(text("SELECT count(*) FROM auth_sessions")
                            ).fetchone()[0] == 1
    engine.dispose()

def test_constraints_enforced_live(tmp_path):
    from sqlalchemy.exc import IntegrityError
    engine = make_engine(str(tmp_path / "con.db"))
    ensure_migrated(engine)
    with make_session_factory(engine)() as sess:
        admin = emp.admin_create(sess, "root", "ada@foap.test", role="admin")
        with pytest.raises(IntegrityError):
            sess.execute(text("INSERT INTO employees (id, role, status)"
                              " VALUES ('x', 'superuser', 'active')"))
        sess.rollback()
        with pytest.raises(IntegrityError):
            sess.execute(text("INSERT INTO employees (id, role, status)"
                              " VALUES ('y', 'employee', 'ghost')"))
        sess.rollback()
        with pytest.raises(IntegrityError):
            sess.execute(text("INSERT INTO auth_sessions (token_hash,"
                              " employee_id) VALUES ('t', 'nobody')"))
        sess.rollback()
        with pytest.raises(IntegrityError):
            sess.execute(text("INSERT INTO employee_audit (id, target_id,"
                              " admin_id, action) VALUES ('a', 'nobody',"
                              " 'root', 'ROLE_CHANGED')"))
        sess.rollback()
        # Real references still work.
        sess.execute(text("INSERT INTO employee_audit (id, target_id,"
                          " admin_id, action) VALUES ('b', '%s', 'root',"
                          " 'ROLE_CHANGED')" % admin.id))
        sess.commit()
    engine.dispose()
