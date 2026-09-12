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
    _ = monkeypatch
    http, headers = _demo_client(tmp_path)
    r = http.post("/api/admin/demo/seed", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["inserted"] > 0
    assert body["campaigns"] == 10
    assert body["creatives"] == 10
    # Demo-namespaced proof: the ten synthetic examples specifically.
    assert body["demo_campaigns"] == 10
    assert body["demo_creatives"] == 10
    # Second call is a verified no-op: counts hold, nothing duplicated.
    r = http.post("/api/admin/demo/seed", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["inserted"] == 0
    assert r.json()["campaigns"] == 10
    assert r.json()["creatives"] == 10
    assert r.json()["demo_campaigns"] == 10
    assert r.json()["demo_creatives"] == 10


def test_admin_seed_refused_outside_demo(tmp_path, monkeypatch):
    db = str(tmp_path / "local.db")
    http = _authed_client(tmp_path, db, monkeypatch)
    r = http.post("/api/admin/demo/seed")
    assert r.status_code == 403, r.text
