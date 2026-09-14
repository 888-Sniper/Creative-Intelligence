"""Readable employee numbers (EMP-001…): assignment, stability, backfill."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError

from ci_backend import employees as emp
from ci_backend.db import ensure_migrated, make_engine, make_session_factory


def _session(db_path):
    engine = make_engine(db_path)
    ensure_migrated(engine)
    factory = make_session_factory(engine)
    return engine, factory()


def test_admin_create_assigns_sequential_numbers(tmp_path):
    engine, sess = _session(str(tmp_path / "n.db"))
    try:
        a = emp.admin_create(sess, "root", "a@foap.test")
        b = emp.admin_create(sess, "root", "b@foap.test")
        assert a.emp_no == "EMP-001"
        assert b.emp_no == "EMP-002"
    finally:
        sess.close()
        engine.dispose()


def test_number_survives_status_changes(tmp_path):
    engine, sess = _session(str(tmp_path / "n.db"))
    try:
        e = emp.admin_create(sess, "root", "a@foap.test")
        no = e.emp_no
        emp.admin_set_status(sess, e.id, e.id, "suspended", "EMPLOYEE_SUSPENDED")
        assert emp.get_employee(sess, e.id).emp_no == no
        emp.admin_set_status(sess, e.id, e.id, "active", "EMPLOYEE_REACTIVATED")
        assert emp.get_employee(sess, e.id).emp_no == no
    finally:
        sess.close()
        engine.dispose()


def test_number_not_derived_from_count(tmp_path):
    engine, sess = _session(str(tmp_path / "n.db"))
    try:
        emp.admin_create(sess, "root", "a@foap.test")
        mid = emp.admin_create(sess, "root", "b@foap.test")
        emp.admin_create(sess, "root", "c@foap.test")
        # Revoking keeps the row (and its number); the next creation
        # continues past the maximum instead of reusing the gap.
        emp.admin_set_status(sess, mid.id, mid.id, "revoked", "EMPLOYEE_REVOKED")
        d = emp.admin_create(sess, "root", "d@foap.test")
        assert d.emp_no == "EMP-004"
        assert emp.get_employee(sess, mid.id).emp_no == "EMP-002"
    finally:
        sess.close()
        engine.dispose()


def test_duplicate_number_rejected(tmp_path):
    engine, sess = _session(str(tmp_path / "n.db"))
    try:
        a = emp.admin_create(sess, "root", "a@foap.test")
        a.emp_no = "EMP-009"
        sess.flush()
        b = emp.admin_create(sess, "root", "b@foap.test")
        assert b.emp_no == "EMP-010"
        c = emp.Employee(id="x", email="x@foap.test", emp_no="EMP-009")
        sess.add(c)
        try:
            sess.flush()
        except IntegrityError:
            sess.rollback()
        else:
            raise AssertionError("duplicate emp_no must fail")
    finally:
        sess.close()
        engine.dispose()


def test_ensure_identity_assigns_number(tmp_path):
    engine, sess = _session(str(tmp_path / "n.db"))
    try:
        e, created = emp.ensure_identity(sess, {
            "email": "n@foap.test", "verified": True,
            "workos_user_id": "w1", "provider": "email",
        })
        assert created is True
        assert e.emp_no == "EMP-001"
        assert emp.public_employee(e).employee_no == "EMP-001"
    finally:
        sess.close()
        engine.dispose()


def test_backfill_numbers_deterministically(tmp_path):
    from ci_backend.db import ensure_migrated, migrate
    engine = make_engine(str(tmp_path / "n.db"))
    try:
        ensure_migrated(engine)
        factory = make_session_factory(engine)
        with factory() as sess:
            # Newest first on purpose: backfill must follow created_at.
            for i, mail in enumerate(["c@foap.test", "a@foap.test", "b@foap.test"]):
                e = emp.admin_create(sess, "root", mail)
                e.created_at = "2026-01-%02dT00:00:00+00:00" % (3 - i)
            sess.commit()
        # Drop back to before 0011 (column gone: legacy shape), then
        # upgrade: numbers follow created_at order.
        migrate(engine, "0010")
        with factory() as sess:
            cols = [c["name"] for c in
                    sa_inspect(sess.connection()).get_columns("employees")]
            assert "emp_no" not in cols
        ensure_migrated(engine)
        with factory() as sess:
            got = {e.email: e.emp_no for e in
                   sess.query(emp.Employee).all()}  # noqa: E731
            assert got == {"b@foap.test": "EMP-001",
                           "a@foap.test": "EMP-002",
                           "c@foap.test": "EMP-003"}, got
    finally:
        engine.dispose()
