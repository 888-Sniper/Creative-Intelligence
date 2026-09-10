"""Shared pytest fixtures for FastAPI TestClient tests (Nextly conftest.py pattern)."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend import employees as emp_store
from ci_backend.app import create_app
from ci_backend.config import Settings
from ci_backend.db import make_engine, make_session_factory


def make_client(db_path, admin_email="", workos=True):
    """TestClient bound to db_path, optionally with an active admin session."""
    settings = Settings(workos_client_id="client_test" if workos else "",
                        key_workos="sk-test-key" if workos else "",
                        admin_email=admin_email)
    app = create_app(str(db_path), settings)
    return TestClient(app, raise_server_exceptions=False)


def mint_admin(db_path, email="staff@example.com", role="admin"):
    """Create an active employee + session directly; return the cookie."""
    engine = make_engine(db_path)
    with make_session_factory(engine)() as sess:
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
