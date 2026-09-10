# Backup and restore

Everything Creative Intelligence stores locally lives under one data
directory, so a backup is a consistent copy of three paths. Stop the
server first (or accept a SQLite-wal-tolerant copy); never back up a
database while a migration is running.

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

```sh
# 1. Stop the server.
# 2. Restore the database and media from a backup stamp:
cp "$BACKUP/creative_intel.db" "<data>/creative_intel.db"
rm -rf "<data>/media"
cp -r "$BACKUP/media" "<data>/media"
# 3. Restart the server and confirm /readiness returns {"ready": true}.
```

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
