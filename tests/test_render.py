"""Render Free deployment regression tests.

Covers the additive Render support: PORT/host binding in
ci_backend.main, first-boot demo seeding without duplication, and the
/health + /readiness endpoints the Render health check relies on.
Oracle deployment behaviour is asserted unchanged (defaults kept).
"""

import os
import sqlite3
import sys
import types

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Backend"))

from ci_backend.app import create_app
from ci_backend.config import Settings
from ci_backend.main import maybe_seed_demo, resolve_bind


def _args(**kw):
    base = {"port": None, "host": None}
    base.update(kw)
    return types.SimpleNamespace(**base)


def _local_settings(tmp_path, **kw):
    # Local environment: public-safety gates stay out of the way and
    # the database lands in an isolated tmp dir, never the repo Data/.
    params = {"data_dir": str(tmp_path), "environment": "local"}
    params.update(kw)
    return Settings(**params)


def test_bind_defaults_preserve_local_oracle_behavior(monkeypatch):
    # No PORT, no flags: historical 127.0.0.1:4321 (Oracle units pass
    # no flags, so this is their path too).
    monkeypatch.delenv("PORT", raising=False)
    assert resolve_bind(_args()) == ("127.0.0.1", 4321)


def test_bind_uses_port_env_for_render(monkeypatch):
    monkeypatch.setenv("PORT", "10000")
    assert resolve_bind(_args()) == ("0.0.0.0", 10000)


def test_bind_cli_flags_win_over_port_env(monkeypatch):
    monkeypatch.setenv("PORT", "10000")
    assert resolve_bind(_args(port=4321)) == ("0.0.0.0", 4321)
    assert resolve_bind(_args(host="127.0.0.1")) == ("127.0.0.1", 10000)


def test_bind_blank_port_env_keeps_defaults(monkeypatch):
    monkeypatch.setenv("PORT", "   ")
    assert resolve_bind(_args()) == ("127.0.0.1", 4321)


def test_bind_malformed_port_fails_closed(monkeypatch, capsys):
    monkeypatch.setenv("PORT", "not-a-port")
    with pytest.raises(SystemExit) as exc:
        resolve_bind(_args())
    assert exc.value.code == 2
    assert "PORT" in capsys.readouterr().err


def test_demo_seed_disabled_by_default(tmp_path):
    db = str(tmp_path / "demo.db")
    assert maybe_seed_demo(db, _local_settings(tmp_path), fresh=True) == 0
    assert not os.path.exists(db)


def test_demo_seed_loads_once_on_fresh_database(tmp_path):
    db = str(tmp_path / "demo.db")
    settings = _local_settings(tmp_path, demo_seed=True)
    first = maybe_seed_demo(db, settings, fresh=True)
    assert first > 0, "expected the bundled fixtures to insert rows"
    with sqlite3.connect(db) as conn:
        creatives = conn.execute("SELECT COUNT(*) FROM creatives").fetchone()[0]
    assert creatives > 0
    # Same running instance, existing database: never touched again.
    assert maybe_seed_demo(db, settings, fresh=False) == 0
    with sqlite3.connect(db) as conn:
        again = conn.execute("SELECT COUNT(*) FROM creatives").fetchone()[0]
    assert again == creatives


def test_demo_seed_never_overwrites_existing_rows(tmp_path):
    from ci_backend.actions import load_demo_dataset

    db = str(tmp_path / "demo.db")
    settings = _local_settings(tmp_path, demo_seed=True)
    assert maybe_seed_demo(db, settings, fresh=True) > 0
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO creatives (creative_key, platform, name)"
            " VALUES ('sentinel', 'meta', 'Sentinel')"
        )
        conn.commit()
    # A second first-boot-style load inserts nothing new (ingest
    # upserts) and the sentinel row survives: no duplication, no wipe.
    assert load_demo_dataset(db) == 0
    with sqlite3.connect(db) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM creatives WHERE creative_key='sentinel'"
            ).fetchone()[0]
            == 1
        )


def _seeded_client(tmp_path):
    db = str(tmp_path / "demo.db")
    settings = _local_settings(tmp_path, demo_seed=True)
    assert maybe_seed_demo(db, settings, fresh=True) > 0
    app = create_app(db, settings)
    return TestClient(app, raise_server_exceptions=False)


def test_health_liveness_on_seeded_demo(tmp_path):
    http = _seeded_client(tmp_path)
    r = http.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_readiness_after_demo_bootstrap(tmp_path):
    http = _seeded_client(tmp_path)
    r = http.get("/readiness")
    assert r.status_code == 200
    assert r.json() == {"ready": True}
