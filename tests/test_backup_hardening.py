"""Backup hardening tests (pytest driving the Oracle shell scripts).

backup.sh / offhost_backup.sh / verify-restore.sh run against temp
dirs (DATA_DIR/BACKUP_DIR overrides), so no root or VM is needed:
encryption round-trips, SHA-256 sidecars, retention pruning, the
plaintext-transfer refusal and restore verification incl. tamper.
"""

import hashlib
import os
import sqlite3
import subprocess
import tarfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
ORACLE = os.path.join(ROOT, "deploy", "oracle")


def run_script(name, env):
    proc = subprocess.run(
        ["bash", os.path.join(ORACLE, name)],
        env={**os.environ, **env},
        capture_output=True, text=True, timeout=120)
    return proc


def seed_data(data_dir):
    os.makedirs(os.path.join(data_dir, "media"), exist_ok=True)
    db = os.path.join(data_dir, "creative_intel.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ads (id INTEGER PRIMARY KEY, x TEXT)")
    conn.execute("INSERT INTO ads (x) VALUES ('row')")
    conn.commit()
    conn.close()
    with open(os.path.join(data_dir, "media", "spot.txt"), "w") as fh:
        fh.write("creative-bytes")
    return db


def newest(backup_dir, suffix):
    names = sorted(f for f in os.listdir(backup_dir)
                   if f.endswith(suffix))
    assert names, "no %s archive produced" % suffix
    return os.path.join(backup_dir, names[-1])


def test_plaintext_backup_with_hash_and_manifest(tmp_path):
    data = tmp_path / "data"
    dest = tmp_path / "backups"
    dest.mkdir()
    seed_data(str(data))
    env = {"CREATIVE_INTEL_DATA_DIR": str(data),
           "BACKUP_DIR": str(dest)}
    proc = run_script("backup.sh", env)
    assert proc.returncode == 0, proc.stderr
    archive = newest(str(dest), ".tar.gz")
    assert archive.endswith(".tar.gz") and not archive.endswith(".enc")
    sidecar = archive + ".sha256"
    assert os.path.isfile(sidecar)
    digest = hashlib.sha256(open(archive, "rb").read()).hexdigest()
    assert digest in open(sidecar).read()
    check = subprocess.run(["sha256sum", "-c", sidecar],
                           capture_output=True, text=True)
    assert check.returncode == 0
    with tarfile.open(archive) as tar:
        manifest = tar.extractfile(
            next(m for m in tar.getnames()
                 if m.endswith("/MANIFEST.txt")
                 and "/._" not in m)).read().decode()
    assert "encrypted=false" in manifest
    assert "unencrypted" in proc.stderr


def test_encrypted_backup_roundtrip(tmp_path):
    data = tmp_path / "data"
    dest = tmp_path / "backups"
    dest.mkdir()
    seed_data(str(data))
    env = {"CREATIVE_INTEL_DATA_DIR": str(data),
           "BACKUP_DIR": str(dest),
           "BACKUP_ENCRYPTION_PASSPHRASE": "test-passphrase-123"}
    proc = run_script("backup.sh", env)
    assert proc.returncode == 0, proc.stderr
    archive = newest(str(dest), ".tar.gz.enc")
    assert not [f for f in os.listdir(str(dest))
                if f.endswith(".tar.gz") and not f.endswith(".enc")]
    assert os.path.isfile(archive + ".sha256")
    out = run_script("verify-restore.sh",
                     {"BACKUP_DIR": str(dest),
                      "BACKUP_ENCRYPTION_PASSPHRASE":
                      "test-passphrase-123"})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().startswith("RESTORE_OK")


def test_local_retention_prunes_old_archives(tmp_path):
    data = tmp_path / "data"
    dest = tmp_path / "backups"
    dest.mkdir()
    seed_data(str(data))
    for day in range(1, 8):
        name = "202001%02dT000000Z.tar.gz" % day
        path = dest / name
        path.write_bytes(b"old-%d" % day)
        (dest / (name + ".sha256")).write_bytes(b"hash")
    env = {"CREATIVE_INTEL_DATA_DIR": str(data),
           "BACKUP_DIR": str(dest), "BACKUP_KEEP_DAILY": "3"}
    proc = run_script("backup.sh", env)
    assert proc.returncode == 0, proc.stderr
    kept = sorted(f for f in os.listdir(str(dest))
                  if f.endswith(".tar.gz"))
    # Retention keeps the newest KEEP_DAILY archives in total.
    assert len(kept) == 3
    assert "20200107T000000Z.tar.gz" in kept
    assert "20200106T000000Z.tar.gz" in kept
    assert "20200105T000000Z.tar.gz" not in kept
    assert not os.path.exists(
        str(dest / "20200101T000000Z.tar.gz.sha256"))


def test_offhost_refuses_plaintext_when_encrypted(tmp_path):
    dest = tmp_path / "backups"
    vault = tmp_path / "vault"
    dest.mkdir()
    vault.mkdir()
    plain = dest / "20200101T000000Z.tar.gz"
    plain.write_bytes(b"plaintext-client-data")
    env = {"BACKUP_DIR": str(dest),
           "BACKUP_OFFHOST_DEST": str(vault),
           "BACKUP_ENCRYPTION_PASSPHRASE": "test-passphrase-123"}
    proc = run_script("offhost_backup.sh", env)
    assert proc.returncode != 0
    assert list(vault.iterdir()) == []


def test_offhost_copies_newest_with_hash_and_prunes(tmp_path):
    dest = tmp_path / "backups"
    vault = tmp_path / "vault"
    dest.mkdir()
    vault.mkdir()
    for day in range(1, 5):
        (dest / ("202001%02dT000000Z.tar.gz" % day)).write_bytes(b"x")
    (vault / "20200101T000000Z.tar.gz").write_bytes(b"old")
    env = {"BACKUP_DIR": str(dest),
           "BACKUP_OFFHOST_DEST": str(vault),
           "BACKUP_OFFHOST_KEEP": "2"}
    data = tmp_path / "data"
    seed_data(str(data))
    run_script("backup.sh", {**env,
                             "CREATIVE_INTEL_DATA_DIR": str(data),
                             "BACKUP_KEEP_DAILY": "30"})
    proc = run_script("offhost_backup.sh", env)
    assert proc.returncode == 0, proc.stderr
    copied = sorted(f.name for f in vault.iterdir()
                    if f.suffix == ".gz")
    assert len(copied) == 2
    fresh = newest(str(dest), ".tar.gz")
    assert os.path.basename(fresh) in copied
    assert os.path.isfile(
        os.path.join(str(vault), os.path.basename(fresh) + ".sha256"))


def test_verify_restore_rejects_tampered_archive(tmp_path):
    data = tmp_path / "data"
    dest = tmp_path / "backups"
    dest.mkdir()
    seed_data(str(data))
    env = {"CREATIVE_INTEL_DATA_DIR": str(data),
           "BACKUP_DIR": str(dest)}
    assert run_script("backup.sh", env).returncode == 0
    archive = newest(str(dest), ".tar.gz")
    good = run_script("verify-restore.sh", {"BACKUP_DIR": str(dest)})
    assert good.returncode == 0, good.stderr
    assert good.stdout.strip().startswith("RESTORE_OK")
    with open(archive, "ab") as fh:
        fh.write(b"tampered")
    bad = run_script("verify-restore.sh", {"BACKUP_DIR": str(dest)})
    assert bad.returncode != 0
