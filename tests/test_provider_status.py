"""GET /api/providers/status: safe AI readiness, no secret leakage."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from conftest import make_client, mint_admin  # noqa: E402


def test_anonymous_is_denied(tmp_db):
    r = make_client(tmp_db).get("/api/providers/status")
    assert r.status_code == 401


def test_reports_capabilities_without_secrets(tmp_db, monkeypatch):
    monkeypatch.setenv("CREATIVE_INTEL_KEY_DEEPGRAM", "dummy-secret-xyz")
    client = make_client(tmp_db)
    client.headers.update(mint_admin(tmp_db))
    r = client.get("/api/providers/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] in ("live", "mock")
    for cap in ("stt", "vision", "llm"):
        assert body["capabilities"][cap]["status"] in (
            "configured", "missing")
        assert isinstance(body["capabilities"][cap]["adapters"], list)
    assert "dummy-secret-xyz" not in r.text
