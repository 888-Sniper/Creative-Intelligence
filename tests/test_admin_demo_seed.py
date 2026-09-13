"""Admin on-demand demo seeding: safe population + verification counts.

POST /api/admin/demo/seed lets an administrator populate the demo
dataset without touching the Render dashboard or the database file:
it is refused outside demo environments (real deployments can never
gain synthetic rows this way), the loader upserts (existing rows are
never duplicated or deleted), and the response carries live
campaign/creative counts for verification.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

import pytest
from auth_help import authed
from ci_backend.app import create_app
from ci_backend.config import Settings
from fastapi.testclient import TestClient
from test_demo_dataset import _authed_client


@pytest.fixture(autouse=True)
def _isolated_media_dir(tmp_path, monkeypatch):
    # Seeded demo artwork must never land in the repo Data/ tree.
    monkeypatch.setenv("CREATIVE_INTEL_MEDIA_DIR",
                       str(tmp_path / "media"))


def _demo_settings(tmp_path):
    return Settings(workos_client_id="client_test",
                    key_workos="sk_test_demo",
                    workos_redirect_uri="https://demo.test/api/auth/callback",
                    admin_email="demo@foap.test",
                    provider_mode="live", cookie_secure=True,
                    environment="demo", data_dir=str(tmp_path))


def _demo_client(tmp_path):
    # Session cookie minted straight into the app database (OAuth
    # ceremony needs live WorkOS credentials; backend stub tests cover
    # that path, and cookie auth is the same gate the UI uses).
    db = str(tmp_path / "seed.db")
    http = TestClient(create_app(db, _demo_settings(tmp_path)),
                      raise_server_exceptions=False)
    cookie = authed(db, email="demo@foap.test", role="admin")
    return http, {"Cookie": cookie}


def test_admin_seed_populates_and_verifies(tmp_path, monkeypatch):
    # Legacy refill route is retired: it must fail loudly (410) and
    # insert nothing, so deleted samples can never be resurrected.
    # The one-time pack path is covered in test_demo_pack.py.
    _ = monkeypatch
    http, headers = _demo_client(tmp_path)
    r = http.post("/api/admin/demo/seed", headers=headers)
    assert r.status_code == 410, r.text
    assert "Add Demo Data Once" in r.text
    r = http.post("/api/admin/demo/seed", headers=headers)
    assert r.status_code == 410, r.text


def test_admin_seed_refused_outside_demo(tmp_path, monkeypatch):
    # Retired in every environment (410), so the env gate it used to
    # carry is irrelevant: nothing can repopulate through this route.
    db = str(tmp_path / "local.db")
    http = _authed_client(tmp_path, db, monkeypatch)
    r = http.post("/api/admin/demo/seed")
    assert r.status_code == 410, r.text
