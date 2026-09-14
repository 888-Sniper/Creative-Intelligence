"""Deploy-script regression tests (A10/A13/A18).

Guards the exact production journeys: the `alembic` CLI migration
command the Oracle scripts run (from the repo root, twice — the
second run must be a clean no-op), and executable deployment
helpers surviving an rsync-style update.
"""

import os
import re
import sqlite3
import stat
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORACLE = os.path.join(ROOT, "deploy", "oracle")


def test_oracle_helpers_are_executable():
    # A18: direct script calls and service ExecStarts fail without
    # the exec bit; the bit is committed in git (100755).
    scripts = sorted(f for f in os.listdir(ORACLE) if f.endswith(".sh"))
    assert scripts, "expected oracle helper scripts"
    dead = [f for f in scripts
            if not os.access(os.path.join(ORACLE, f), os.X_OK)]
    assert not dead, "non-executable deploy helpers: %r" % (dead,)
    for name in scripts:
        mode = stat.S_IMODE(os.stat(os.path.join(ORACLE, name)).st_mode)
        assert mode & 0o111, "%s missing exec bit (%o)" % (name, mode)


def test_restore_validates_before_downtime():
    # A11: hash/decrypt/stage/validate must all precede any
    # systemctl stop; both writers (web + worker) must stop; a
    # rollback path must restore the DB and prior unit states.
    with open(os.path.join(ORACLE, "restore.sh")) as handle:
        text = handle.read()
    stops = [m.start() for m in re.finditer(r"systemctl stop", text)]
    assert stops, "restore must stop writers"
    for marker in ("sha256sum -c", "openssl enc -d",
                   "integrity_check", "creative-intelligence-worker"):
        pos = text.find(marker)
        assert pos != -1, "restore.sh missing %r" % marker
        assert pos < stops[0], \
            "%r must precede the first service stop" % marker
    assert "ROLLBACK" in text and "rollback" in text


def test_update_restores_helper_modes_after_rsync():
    # A18: rsync -a preserves source modes, so update.sh must
    # re-assert them (install.sh already does at install time).
    # A13: the mode is 755 so the unprivileged DuckDNS unit can
    # still read and execute the root-owned helpers.
    with open(os.path.join(ORACLE, "update.sh")) as handle:
        text = handle.read()
    rsync_at = text.find("rsync -a")
    chmod_at = text.find("chmod 755")
    assert rsync_at != -1 and chmod_at != -1
    assert chmod_at > rsync_at, \
        "update.sh must chmod helpers after the rsync"


def _service_text(name):
    with open(os.path.join(ORACLE, name)) as handle:
        return handle.read()


def test_duckdns_unit_drops_root():
    # A13: the updater is app-tree code — it must not execute as root.
    text = _service_text("creative-intelligence-duckdns.service")
    user = re.search(r"^User=(\S+)", text, re.M)
    assert user, "duckdns unit must set User="
    assert user.group(1) != "root", "duckdns unit must not run as root"
    assert "NoNewPrivileges=true" in text


def test_deploy_helpers_root_owned_after_chown():
    # A13: install.sh/update.sh blanket-chown the tree to the service
    # account but must then re-own deploy/ to root so the
    # unprivileged DuckDNS unit executes non-app-writable code.
    for name in ("install.sh", "update.sh"):
        with open(os.path.join(ORACLE, name)) as handle:
            text = handle.read()
        chown_at = text.find("chown -R \"${APP_USER}:${APP_GROUP}\"")
        if chown_at == -1:  # update.sh spells the account literally
            chown_at = text.find(
                "chown -R creative-intel:creative-intel")
        root_at = text.find("chown -R root:root \"${APP_DIR}/deploy\"")
        assert chown_at != -1 and root_at != -1, \
            "%s must root-own deploy/" % name
        assert root_at > chown_at, \
            "%s must root-own deploy/ after the app chown" % name


def test_duckdns_token_not_world_readable():
    # A13: the token readable by the unprivileged unit must stay
    # group-scoped — never world-readable.
    with open(os.path.join(ORACLE, "install.sh")) as handle:
        text = handle.read()
    assert "chmod 640" in text and "duckdns.env" in text
    world_readable = [line for line in text.splitlines()
                      if "duckdns.env" in line
                      and re.search(r"chmod\s+[0-7]*[4567]\b", line)]
    assert not world_readable, \
        "duckdns token must stay group-scoped: %r" % (world_readable,)


def test_deploy_migration_command_from_repo_root(tmp_path):
    # A10: the exact command install.sh/update.sh run — from the repo
    # root, against a scratch database, twice. Before the fix the
    # first run exited 0 while leaving the DB half-migrated and
    # unstamped, and the second run crashed on existing tables.
    db = str(tmp_path / "deploy.db")
    env = dict(os.environ,
               CREATIVE_INTEL_DB_URL="sqlite:///%s" % db,
               PYTHONDONTWRITEBYTECODE="1")
    for run in (1, 2):
        proc = subprocess.run(
            [sys.executable, "-m", "alembic", "-c",
             "Backend/alembic.ini", "upgrade", "head"],
            cwd=ROOT, env=env, capture_output=True, text=True,
            timeout=120)
        assert proc.returncode == 0, \
            "run %d failed: %s" % (run, proc.stderr[-2000:])
    conn = sqlite3.connect(db)
    try:
        version = [r[0] for r in conn.execute(
            "SELECT version_num FROM alembic_version")]
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert version == ["0012"], version
    assert {"employees", "auth_sessions", "oauth_tokens"} <= tables
    assert {"provider_configs", "provider_model_cache",
            "active_provider_selection"} <= tables
