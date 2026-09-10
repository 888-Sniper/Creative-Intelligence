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
    ("revenue_reported", "INTEGER NOT NULL DEFAULT 0"),
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
    revenue REAL NOT NULL DEFAULT 0,
    revenue_reported INTEGER NOT NULL DEFAULT 0
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
    -- Curve provenance: 'manual' rows are never touched by the
    -- quartile synthesizer; 'quartile_synthesized' rows are rebuilt
    -- on every import. Old rows default to 'manual' (protect first:
    -- a pre-existing synthetic curve freezes rather than risk
    -- overwriting a hand-supplied one).
    source TEXT NOT NULL DEFAULT 'manual',
    PRIMARY KEY (creative_key, t_sec)
);
CREATE TABLE IF NOT EXISTS replay_log (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS saved_views (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    state_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    inserted INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    quarantined INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    job_id TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS sync_jobs (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    params_json TEXT NOT NULL DEFAULT '{}',
    owner_employee_id TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS sync_jobs_source ON sync_jobs (source);

-- NOTE: ads_sync_key lives in migrate(), not here: the static script
-- must stay runnable against pre-dimension databases, and migrate()
-- dedupes existing rows before creating the index. A copy here would
-- 500 every request on older files with "no such column: date".
-- WorkOS authentication + admin-controlled employee access (auth.py).
-- WorkOS proves identity; these tables decide access (default deny).
CREATE TABLE IF NOT EXISTS employees (
    id TEXT PRIMARY KEY,
    -- NULL until first login: SQLite UNIQUE permits many NULLs, so any
    -- number of pre-added staff can coexist before they authenticate.
    workos_user_id TEXT DEFAULT NULL,
    email TEXT NOT NULL DEFAULT '',
    first_name TEXT NOT NULL DEFAULT '',
    last_name TEXT NOT NULL DEFAULT '',
    avatar_url TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'employee',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT '',
    approved_at TEXT NOT NULL DEFAULT '',
    approved_by TEXT NOT NULL DEFAULT '',
    last_login_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS employees_workos_uid
    ON employees (workos_user_id);
CREATE UNIQUE INDEX IF NOT EXISTS employees_email ON employees (email);
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    employee_id TEXT NOT NULL DEFAULT '',
    workos_user_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '',
    last_seen_at TEXT NOT NULL DEFAULT '',
    expires_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS auth_pending (
    state TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT '',
    verifier TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS employee_audit (
    id TEXT PRIMARY KEY,
    target_id TEXT NOT NULL DEFAULT '',
    admin_id TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    prev_value TEXT NOT NULL DEFAULT '',
    new_value TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);
"""

# Natural dedup key for re-imports: the same fact from the same origin
# (same source feed, platform, campaign/adset/ad row and reporting date)
# is one row. Every product import surface (uploads, connectors,
# scheduler) stores via ingest.upsert_rows(), so re-imports update
# metrics instead of duplicating rows; insert_rows() stays the raw
# append primitive and refuses exact-duplicate facts.
SYNC_KEY_COLUMNS = ("source", "platform", "campaign", "adset",
                    "ad_name", "date")


def migrate(conn):
    """Add unification columns missing from an old ads table.

    Idempotent: existing columns are left untouched, so opening an
    old database with the new code is a safe no-rewrite upgrade.
    Also brings old databases onto the sync contract: exact duplicate
    facts under the sync key collapse (last write wins, mirroring
    ingest.upsert_rows) before the uniqueness index is created, and
    the sync_runs/sync_jobs tables are added when missing.
    Returns the list of columns added.
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(ads)")}
    added = []
    for name, ddl in NEW_DIMENSIONS:
        if name not in existing:
            conn.execute("ALTER TABLE ads ADD COLUMN %s %s" % (name, ddl))
            added.append(name)
    retention_cols = {row[1] for row in
                      conn.execute("PRAGMA table_info(retention)")}
    if "source" not in retention_cols:
        conn.execute("ALTER TABLE retention ADD COLUMN"
                     " source TEXT NOT NULL DEFAULT 'manual'")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS employees ("
        "id TEXT PRIMARY KEY, workos_user_id TEXT DEFAULT NULL,"
        " email TEXT NOT NULL DEFAULT '',"
        " first_name TEXT NOT NULL DEFAULT '',"
        " last_name TEXT NOT NULL DEFAULT '',"
        " avatar_url TEXT NOT NULL DEFAULT '',"
        " role TEXT NOT NULL DEFAULT 'employee',"
        " status TEXT NOT NULL DEFAULT 'pending',"
        " created_at TEXT NOT NULL DEFAULT '',"
        " approved_at TEXT NOT NULL DEFAULT '',"
        " approved_by TEXT NOT NULL DEFAULT '',"
        " last_login_at TEXT NOT NULL DEFAULT '',"
        " updated_at TEXT NOT NULL DEFAULT '')")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS employees_workos_uid"
                 " ON employees (workos_user_id)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS employees_email"
                 " ON employees (email)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS auth_sessions ("
        "token_hash TEXT PRIMARY KEY,"
        " employee_id TEXT NOT NULL DEFAULT '',"
        " workos_user_id TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL DEFAULT '',"
        " last_seen_at TEXT NOT NULL DEFAULT '',"
        " expires_at TEXT NOT NULL DEFAULT '')")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS auth_pending ("
        "state TEXT PRIMARY KEY, provider TEXT NOT NULL DEFAULT '',"
        " verifier TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL DEFAULT '')")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS employee_audit ("
        "id TEXT PRIMARY KEY, target_id TEXT NOT NULL DEFAULT '',"
        " admin_id TEXT NOT NULL DEFAULT '',"
        " action TEXT NOT NULL DEFAULT '',"
        " prev_value TEXT NOT NULL DEFAULT '',"
        " new_value TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL DEFAULT '')")
    key_cols = ", ".join(SYNC_KEY_COLUMNS)
    conn.execute(
        "DELETE FROM ads WHERE rowid NOT IN"
        " (SELECT MAX(rowid) FROM ads GROUP BY %s)" % key_cols)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ads_sync_key ON ads (%s)"
        % key_cols)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sync_runs ("
        "id INTEGER PRIMARY KEY, source TEXT NOT NULL DEFAULT '',"
        " started_at TEXT NOT NULL DEFAULT '',"
        " finished_at TEXT NOT NULL DEFAULT '',"
        " status TEXT NOT NULL DEFAULT '',"
        " inserted INTEGER NOT NULL DEFAULT 0,"
        " updated INTEGER NOT NULL DEFAULT 0,"
        " quarantined INTEGER NOT NULL DEFAULT 0,"
        " attempts INTEGER NOT NULL DEFAULT 0,"
        " error TEXT NOT NULL DEFAULT '',"
        " job_id TEXT NOT NULL DEFAULT '')")
    run_cols = {row[1] for row in
                conn.execute("PRAGMA table_info(sync_runs)")}
    if "job_id" not in run_cols:
        conn.execute("ALTER TABLE sync_runs ADD COLUMN"
                     " job_id TEXT NOT NULL DEFAULT ''")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sync_jobs ("
        "id TEXT PRIMARY KEY, source TEXT NOT NULL DEFAULT '',"
        " name TEXT NOT NULL DEFAULT '',"
        " params_json TEXT NOT NULL DEFAULT '{}',"
        " owner_employee_id TEXT NOT NULL DEFAULT '',"
        " enabled INTEGER NOT NULL DEFAULT 1,"
        " created_at TEXT NOT NULL DEFAULT '',"
        " updated_at TEXT NOT NULL DEFAULT '')")
    conn.execute("CREATE INDEX IF NOT EXISTS sync_jobs_source"
                 " ON sync_jobs (source)")
    job_cols = {row[1] for row in
                conn.execute("PRAGMA table_info(sync_jobs)")}
    if "id" not in job_cols:
        # Legacy single-job-per-source shape (source PRIMARY KEY):
        # rebuild with one job per source, preserving params/owner.
        has_owner = "owner_employee_id" in job_cols
        conn.execute(
            "CREATE TABLE sync_jobs_new ("
            "id TEXT PRIMARY KEY, source TEXT NOT NULL DEFAULT '',"
            " name TEXT NOT NULL DEFAULT '',"
            " params_json TEXT NOT NULL DEFAULT '{}',"
            " owner_employee_id TEXT NOT NULL DEFAULT '',"
            " enabled INTEGER NOT NULL DEFAULT 1,"
            " created_at TEXT NOT NULL DEFAULT '',"
            " updated_at TEXT NOT NULL DEFAULT '')")
        conn.execute(
            "INSERT INTO sync_jobs_new (id, source, name, params_json,"
            " owner_employee_id, enabled, created_at, updated_at)"
            " SELECT hex(randomblob(16)), source, source, params_json,"
            " %s, 1, updated_at, updated_at FROM sync_jobs"
            % ("owner_employee_id" if has_owner else "''"))
        conn.execute("DROP TABLE sync_jobs")
        conn.execute("ALTER TABLE sync_jobs_new RENAME TO sync_jobs")
        conn.execute("CREATE INDEX IF NOT EXISTS sync_jobs_source"
                     " ON sync_jobs (source)")
    elif "owner_employee_id" not in job_cols:
        conn.execute("ALTER TABLE sync_jobs ADD COLUMN"
                     " owner_employee_id TEXT NOT NULL DEFAULT ''")
    conn.commit()
    return added


def init_db(conn):
    conn.executescript(DDL)
    migrate(conn)
    conn.commit()
