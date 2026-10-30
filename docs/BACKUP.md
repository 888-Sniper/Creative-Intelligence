# Backup and restore

> **local backup ≠ disaster recovery.** An on-VM archive does not
> survive a lost VM. For the public demo, configure the off-host copy
> below; until then, treat every backup as convenience, not safety.

Everything Creative Intelligence stores locally lives under one data
directory, so a backup is a consistent copy of three paths. Stop the
server first (or accept a SQLite-wal-tolerant copy); never back up a
database while a migration is running.

## Off-host copy (Oracle VM, free)

On the VM, nightly snapshots run automatically. Point them off-host
with one setting in `/etc/creative-intelligence/creative-intelligence.env`:

```text
BACKUP_OFFHOST_DEST=<rsync destination or mounted path>
```

Free options that need no paid infrastructure:

- **OCI Object Storage (Always Free allowance):** create a private
  bucket, mount it on the VM (e.g. via s3fs with an OCI S3-compatible
  key), and set `BACKUP_OFFHOST_DEST` to the mount path. Bucket
  versioning or lifecycle rules handle remote retention; the script
  prunes local-path destinations to `BACKUP_OFFHOST_KEEP` archives.
- **rsync/SSH to any host you control:**
  `BACKUP_OFFHOST_DEST=backup@vault.example:/srv/creative-intelligence`
  (key-based SSH, no passwords).

Verify with `ls` at the destination after the next timer run
(`systemctl list-timers 'creative-intelligence-*'`).

## Encryption

Set a passphrase in `/etc/creative-intelligence/creative-intelligence.env`
(generate: `openssl rand -base64 32`):

```text
BACKUP_ENCRYPTION_PASSPHRASE=<secret>
```

`backup.sh` then writes `<stamp>.tar.gz.enc` (AES-256-CBC, PBKDF2) and
removes the plaintext. Once the passphrase is configured,
`offhost_backup.sh` refuses to transfer plaintext archives, so client
data never leaves the VM unencrypted. When
`CREATIVE_INTEL_ENVIRONMENT=production`, both scripts fail closed
without a passphrase — no plaintext client data at rest or in
transit. The passphrase itself is never logged and never enters the
repo — it lives only in the 600-permission env file and the operator
shell.

## Integrity + retention

Every archive ships a `<archive>.sha256` sidecar, verified by the
backup run itself (`sha256sum -c`) and re-checked by every restore
test. On-host retention keeps the newest `BACKUP_KEEP_DAILY` archives
(default 14) plus their hashes; older ones are pruned automatically.

## Weekly restore self-test

`creative-intelligence-restorecheck.timer` runs
`deploy/oracle/verify-restore.sh` weekly against the newest backup:
hash check, manifest + database presence, SQLite `integrity_check` —
all in a temp dir, never touching live data. A failure exits non-zero
(a failed systemd unit — check `systemctl status
creative-intelligence-restorecheck` and the journal). Run it manually
any time:

```sh
sudo -u creative-intel deploy/oracle/verify-restore.sh
# RESTORE_OK /var/backups/creative-intelligence/<stamp>.tar.gz[.enc]
```

## Locations

| What              | Default location (override)                          |
| ----------------- | ---------------------------------------------------- |
| SQLite database   | `<data>/creative_intel.db` (`CREATIVE_INTEL_DATA_DIR`, `CREATIVE_INTEL_DB_FILENAME` via `--db`) |
| Creative media    | `<data>/media/` (`CREATIVE_INTEL_MEDIA_DIR`)         |
| Avatars           | `<data>/media/avatars/` (inside the media directory) |

`<data>` defaults to `<repo>/Data/` (`Settings.data_dir`).

## Backup

```sh
# 1. Stop the server.
# 2. Copy all three paths with one timestamp:
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP=~/creative-intelligence-backups/$STAMP
mkdir -p "$BACKUP"
cp "<data>/creative_intel.db" "$BACKUP/"
cp -r "<data>/media" "$BACKUP/"
# 3. Restart the server and confirm /readiness returns {"ready": true}.
```

For a hot copy without stopping, use the SQLite backup API instead of
`cp` for the `.db` file, then copy `media/`:

```sh
sqlite3 "<data>/creative_intel.db" ".backup '$BACKUP/creative_intel.db'"
```

## Restore

Stop every writer first, including the server. Do not copy onto the
live database, and do not delete the live media directory, until a
staged copy of both has been checked.

The selected backup directory must exist and must not be empty. It
must contain a readable `creative_intel.db`. It must also contain a
readable `media` directory. An intentionally empty `media` directory
is valid. A missing or unreadable database, or a missing or unreadable
`media` directory, stops the restore before any live path changes.

```sh
# Preconditions: writers are stopped, BACKUP is the selected stamp,
# and <data> is the live data directory. This block only stages.
test -n "$BACKUP" && test -d "$BACKUP"
test -s "$BACKUP/creative_intel.db" && test -r "$BACKUP/creative_intel.db"
test -d "$BACKUP/media" && test -r "$BACKUP/media"
mkdir -p "<data>/.restore-staging"
rm -rf "<data>/.restore-staging/creative_intel.db" "<data>/.restore-staging/media"
cp "$BACKUP/creative_intel.db" "<data>/.restore-staging/creative_intel.db"
cp -r "$BACKUP/media" "<data>/.restore-staging/media"
test -s "<data>/.restore-staging/creative_intel.db"
test -d "<data>/.restore-staging/media"
```

Keep the current database and the current media directory as rollback
copies, then switch the staged pair into place. If either switch fails,
put both rollback copies back before starting the server again. Remove
the rollback copies only after the restored pair is in place and
`/readiness` returns `{"ready": true}`.

```sh
mkdir -p "<data>/.restore-rollback"
rm -rf "<data>/.restore-rollback/creative_intel.db" "<data>/.restore-rollback/media"
cp "<data>/creative_intel.db" "<data>/.restore-rollback/creative_intel.db"
cp -r "<data>/media" "<data>/.restore-rollback/media"
cp "<data>/.restore-staging/creative_intel.db" "<data>/creative_intel.db" \
  && cp -r "<data>/.restore-staging/media" "<data>/media.new" \
  && rm -rf "<data>/media" \
  && mv "<data>/media.new" "<data>/media"
# If that chain stops early, put both rollback copies back:
# cp "<data>/.restore-rollback/creative_intel.db" "<data>/creative_intel.db"
# rm -rf "<data>/media"
# cp -r "<data>/.restore-rollback/media" "<data>/media"
```

Restart the server and confirm `/readiness` returns `{"ready": true}`.
Only then remove `<data>/.restore-rollback` and `<data>/.restore-staging`.
This procedure is documentation. Do not run it against a live host
from a review.

## Before migrations

1. Take a backup as above and note its stamp.
2. Apply the migration (app startup runs `migrate()`; Alembic
   upgrades run via the documented upgrade path once adopted).
3. Re-run the backend suite and `Source/self_check.py`.
4. If anything fails, stop the server, restore the stamp, and
   investigate before retrying. Destructive migrations (table
   rebuilds such as the `sync_jobs` id-keying) must never run without
   a recovery backup.

## What is NOT in the backup

Provider/API secrets live in the OS keychain or environment, never in
the database or media tree — reconfigure them on a new machine via
`docs/PROVIDERS.md` instead of copying them.
