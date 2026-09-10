"""Deploy-configuration tests (pytest, file content only).

The Oracle systemd/setup/backup wiring cannot run in CI (no root, no
VM), so these tests assert the wiring deterministically from the
shipped files: sync env plumbing, fail-safe demo setup, backup
directory ordering, service users and timer cadence.
"""

import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(name):
    with open(os.path.join(ROOT, name)) as fh:
        return fh.read()


def test_service_consumes_sync_every_from_environment():
    service = _read("deploy/oracle/creative-intelligence.service")
    assert "EnvironmentFile=/etc/creative-intelligence/" in service
    # Env-driven cadence: a hardcoded flag would silently win over
    # CREATIVE_INTEL_SYNC_EVERY (explicit --sync-every wins in main).
    assert "--sync-every" not in service
    assert "ci_backend/main.py" in service
    example = _read("deploy/oracle/demo.env.example")
    cadence = re.search(r"^CREATIVE_INTEL_SYNC_EVERY=(\d+)\s*$",
                        example, re.M)
    assert cadence and int(cadence.group(1)) > 0


def test_settings_namespace_matches_deploy_env():
    config = _read("Backend/ci_backend/config.py")
    assert 'env_prefix="CREATIVE_INTEL_"' in config
    assert re.search(r"^\s+sync_every:\s*int", config, re.M)


def test_setup_demo_auto_installs_demo_config():
    setup = _read("deploy/oracle/setup-demo.sh")
    assert "demo.env.example" in setup
    assert re.search(r"cp .*demo\.env\.example", setup), \
        "clean demo setup must auto-install the demo configuration"
    assert "CREATIVE_INTEL_PROVIDER_MODE" in setup
    assert "'live'" in setup or '"live"' in setup
    assert "CREATIVE_INTEL_COOKIE_SECURE" in setup
    assert "CREATIVE_INTEL_WORKOS_CLIENT_ID" in setup
    assert "CREATIVE_INTEL_KEY_WORKOS" in setup
    assert "EXPECT_LIVE=1" in setup
    assert "verify.sh" in setup


def test_installer_creates_backup_dir_before_timer():
    install = _read("deploy/oracle/install.sh")
    mkdir_at = install.index('mkdir -p "${BACKUP_DIR}"')
    chown_at = install.index("chown creative-intel:creative-intel")
    timer_at = install.index('enable --now "${SERVICE_NAME}-backup.timer"')
    assert mkdir_at < chown_at < timer_at, \
        "backup dir with service ownership must precede timer enable"
    assert 'BACKUP_DIR="${BACKUP_DIR:-/var/backups/creative-intelligence}"' \
        in install
    assert 'chmod 700 "${BACKUP_DIR}"' in install


def test_backup_hardening_wiring():
    backup = _read("deploy/oracle/backup.sh")
    assert "BACKUP_ENCRYPTION_PASSPHRASE" in backup
    assert "openssl enc -aes-256-cbc -pbkdf2" in backup
    assert ".sha256" in backup
    assert "BACKUP_KEEP_DAILY" in backup
    offhost = _read("deploy/oracle/offhost_backup.sh")
    assert "Refusing to transfer unencrypted" in offhost
    restore = _read("deploy/oracle/verify-restore.sh")
    assert "RESTORE_OK" in restore
    assert "integrity_check" in restore
    timer = _read(
        "deploy/oracle/creative-intelligence-restorecheck.timer")
    assert re.search(r"^OnCalendar=weekly", timer, re.M)
    service = _read(
        "deploy/oracle/creative-intelligence-restorecheck.service")
    assert re.search(r"^User=creative-intel\s*$", service, re.M)
    assert "verify-restore.sh" in service
    install = _read("deploy/oracle/install.sh")
    assert "restorecheck.service" in install
    assert "restorecheck.timer" in install
    example = _read("deploy/oracle/env.example")
    assert "BACKUP_ENCRYPTION_PASSPHRASE" in example
    assert "BACKUP_KEEP_DAILY" in example


def test_backup_service_runs_unprivileged_with_offhost():
    service = _read("deploy/oracle/creative-intelligence-backup.service")
    assert re.search(r"^User=creative-intel\s*$", service, re.M)
    assert "backup.sh" in service
    assert "offhost_backup.sh" in service
    timer = _read("deploy/oracle/creative-intelligence-backup.timer")
    assert re.search(r"^OnCalendar=", timer, re.M)
    backup = _read("deploy/oracle/backup.sh")
    assert "/var/backups/creative-intelligence" in backup


def test_ci_runs_security_and_deploy_gates():
    ci = _read(".github/workflows/ci.yml")
    assert "pip_audit" in ci
    assert "shellcheck" in ci
    assert "gitleaks" in ci
    assert "audit --audit-level high" in ci
    assert "requirements.lock" in ci
    codeql = _read(".github/workflows/codeql.yml")
    assert "python" in codeql and "typescript" in codeql


def test_worker_service_bounded_and_enabled():
    service = _read("deploy/oracle/creative-intelligence-worker.service")
    assert re.search(r"^User=creative-intel\s*$", service, re.M)
    install = _read("deploy/oracle/install.sh")
    assert "creative-intelligence-worker" in install
