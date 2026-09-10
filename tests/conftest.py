"""Shared pytest fixtures for FastAPI TestClient tests (Nextly conftest.py pattern)."""

import contextlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import employees as emp_store
from ci_backend.app import create_app
from ci_backend.config import Settings
from ci_backend.db import (
    dispose_all_engines,
    init_db,
    make_engine,
    make_session_factory,
)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item):
    """Close pooled SQLite handles after every test (both styles).

    Implemented as a wrapper hook — not an autouse fixture — because
    fixtures do not apply to unittest.TestCase methods, which most of
    this suite uses. The wrapper form matters: Engine.dispose()
    replaces the pool, so disposing while a fixture-owned session still
    holds a checked-out connection orphans that connection into the old
    pool, which is then garbage-collected unclosed (ResourceWarning).
    Running after ``yield`` lets fixture finalizers return their
    connections first. dispose() only closes pooled connections;
    engines held by class-scoped clients transparently reconnect, so
    this is safe mid-class too. Without it, dropped engines surface
    pooled handles as ResourceWarnings at garbage collection.
    """
    _ = item
    outcome = yield
    dispose_all_engines()
    return outcome


@contextlib.contextmanager
def employee_session(db_path):
    """Yield an employee DB session; dispose the engine afterwards.

    Seeding helpers must not drop engines with pooled SQLite handles
    checked out (ResourceWarnings at GC). The engine lives exactly as
    long as the session block. Tables are ensured, so callers need no
    separate init step.
    """
    engine = make_engine(db_path)
    init_db(engine)
    try:
        with make_session_factory(engine)() as sess:
            yield sess
    finally:
        engine.dispose()


def temp_db_path(suffix=".db"):
    """Named temp-file path with the handle already closed.

    Bare ``NamedTemporaryFile(...).name`` drops the open handle, which
    surfaces as a ResourceWarning at garbage collection.
    """
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
        return fh.name


def make_client(db_path, admin_email="", workos=True):
    """TestClient bound to db_path, optionally with an active admin session."""
    settings = Settings(workos_client_id="client_test" if workos else "",
                        key_workos="sk-test-key" if workos else "",
                        admin_email=admin_email)
    app = create_app(str(db_path), settings)
    return TestClient(app, raise_server_exceptions=False)


def mint_admin(db_path, email="staff@example.com", role="admin"):
    """Create an active employee + session directly; return the cookie."""
    with employee_session(db_path) as sess:
        try:
            employee = emp_store.admin_create(sess, "test-helper", email,
                                              role=role)
        except emp_store.StoreError:
            employee = emp_store.find_employee(sess, "", email)
        token = emp_store.create_session(sess, employee.id,
                                         employee.workos_user_id or "")
    return {"Cookie": "ci_session=%s" % token}


@pytest.fixture()
def tmp_db(tmp_path):
    return str(tmp_path / "t.db")


@pytest.fixture()
def anon_client(tmp_db):
    return make_client(tmp_db)


@pytest.fixture()
def admin_client(tmp_db):
    client = make_client(tmp_db)
    client.headers.update(mint_admin(tmp_db))
    return client
