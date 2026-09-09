"""Canonical SQLite dataset DDL."""

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
    views_100 INTEGER NOT NULL DEFAULT 0
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


def init_db(conn):
    conn.executescript(DDL)
    conn.commit()
