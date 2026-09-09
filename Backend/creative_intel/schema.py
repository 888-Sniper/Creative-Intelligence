"""Canonical SQLite dataset DDL.

Store-unification dimensions (client, project, vertical, market,
objective, funnel_stage, date, revenue) live on ads with defaults so
pre-existing rows and fixtures keep passing without a backfill.
"""

# Backfill-friendly migration notes:
# - New columns all carry NOT NULL + DEFAULT, so ALTER TABLE on an old
#   database fills existing rows automatically ('' for text, 0 revenue).
# - No data rewrite is needed: open the old file with the new code and
#   init_db()/migrate() adds whatever is missing (idempotent).
# - Optional backfill: re-ingest CSVs that carry the new header aliases,
#   or UPDATE ads SET client=... WHERE client='' per cohort.
# - Downgrade-safe: old code ignores the extra columns (it names its
#   INSERT columns explicitly).

# (column name, ADD COLUMN DDL fragment). Text dims default to '' and
# revenue defaults to 0 so old rows/tests keep passing.
NEW_DIMENSIONS = (
    ("client", "TEXT NOT NULL DEFAULT ''"),
    ("project", "TEXT NOT NULL DEFAULT ''"),
    ("vertical", "TEXT NOT NULL DEFAULT ''"),
    ("market", "TEXT NOT NULL DEFAULT ''"),
    ("objective", "TEXT NOT NULL DEFAULT ''"),
    ("funnel_stage", "TEXT NOT NULL DEFAULT ''"),
    ("date", "TEXT NOT NULL DEFAULT ''"),
    ("revenue", "REAL NOT NULL DEFAULT 0"),
)

DDL = """
CREATE TABLE IF NOT EXISTS ads (
    id INTEGER PRIMARY KEY,
    platform TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'upload',
    campaign TEXT NOT NULL DEFAULT '',
    adset TEXT NOT NULL DEFAULT '',
    ad_name TEXT NOT NULL DEFAULT '',
    creative_key TEXT NOT NULL DEFAULT '',
    spend REAL NOT NULL DEFAULT 0,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks INTEGER NOT NULL DEFAULT 0,
    conversions REAL NOT NULL DEFAULT 0,
    video_views INTEGER NOT NULL DEFAULT 0,
    views_25 INTEGER NOT NULL DEFAULT 0,
    views_50 INTEGER NOT NULL DEFAULT 0,
    views_75 INTEGER NOT NULL DEFAULT 0,
    views_100 INTEGER NOT NULL DEFAULT 0,
    client TEXT NOT NULL DEFAULT '',
    project TEXT NOT NULL DEFAULT '',
    vertical TEXT NOT NULL DEFAULT '',
    market TEXT NOT NULL DEFAULT '',
    objective TEXT NOT NULL DEFAULT '',
    funnel_stage TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL DEFAULT '',
    revenue REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS creatives (
    creative_key TEXT PRIMARY KEY,
    platform TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    duration_s REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'auto',
    transcript TEXT NOT NULL DEFAULT '',
    pipeline_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS annotations (
    creative_key TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL DEFAULT 'v0',
    annotation_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS retention (
    creative_key TEXT NOT NULL,
    t_sec REAL NOT NULL,
    retention_pct REAL NOT NULL,
    PRIMARY KEY (creative_key, t_sec)
);
CREATE TABLE IF NOT EXISTS replay_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
);
"""


def migrate(conn):
    """Add unification columns missing from an old ads table.

    Idempotent: existing columns are left untouched, so opening an
    old database with the new code is a safe no-rewrite upgrade.
    Returns the list of columns added.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(ads)")}
    added = []
    for name, ddl in NEW_DIMENSIONS:
        if name not in existing:
            conn.execute("ALTER TABLE ads ADD COLUMN %s %s" % (name, ddl))
            added.append(name)
    if added:
        conn.commit()
    return added


def init_db(conn):
    conn.executescript(DDL)
    migrate(conn)
    conn.commit()
