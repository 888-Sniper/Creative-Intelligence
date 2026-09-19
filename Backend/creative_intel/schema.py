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
    ("team", "TEXT NOT NULL DEFAULT ''"),
    ("vertical", "TEXT NOT NULL DEFAULT ''"),
    ("market", "TEXT NOT NULL DEFAULT ''"),
    ("objective", "TEXT NOT NULL DEFAULT ''"),
    ("funnel_stage", "TEXT NOT NULL DEFAULT ''"),
    ("date", "TEXT NOT NULL DEFAULT ''"),
    ("revenue", "REAL NOT NULL DEFAULT 0"),
    ("revenue_reported", "INTEGER NOT NULL DEFAULT 0"),
)

# Foap Analyst measurement families (spec section 4). Same
# backfill-friendly contract as NEW_DIMENSIONS: every column carries
# NOT NULL + DEFAULT so old databases upgrade with no rewrite.
# Zero-vs-missing is NOT encoded in these columns — see missing_json
# below: a stored 0 for a field listed in missing_json means
# "not supplied", never a measured zero.
NEW_MEASURES = (
    # Stable source identity (never creative names alone).
    ("account_id", "TEXT NOT NULL DEFAULT ''"),
    ("campaign_id", "TEXT NOT NULL DEFAULT ''"),
    ("ad_id", "TEXT NOT NULL DEFAULT ''"),
    ("import_id", "TEXT NOT NULL DEFAULT ''"),
    # Delivery.
    ("reach", "INTEGER NOT NULL DEFAULT 0"),
    ("frequency", "REAL NOT NULL DEFAULT 0"),
    ("currency", "TEXT NOT NULL DEFAULT ''"),
    # Early attention.
    ("video_starts", "INTEGER NOT NULL DEFAULT 0"),
    ("views_2s", "INTEGER NOT NULL DEFAULT 0"),
    ("views_3s", "INTEGER NOT NULL DEFAULT 0"),
    ("views_6s", "INTEGER NOT NULL DEFAULT 0"),
    # Watch time (basis recorded per row in watch_time_basis).
    ("watch_time_total_s", "REAL NOT NULL DEFAULT 0"),
    ("watch_time_basis", "TEXT NOT NULL DEFAULT ''"),
    ("avg_watch_per_view_s", "REAL NOT NULL DEFAULT 0"),
    ("avg_watch_per_user_s", "REAL NOT NULL DEFAULT 0"),
    # Response (link clicks kept separate from all clicks).
    ("link_clicks", "INTEGER NOT NULL DEFAULT 0"),
    ("conversion_event", "TEXT NOT NULL DEFAULT ''"),
    ("attribution", "TEXT NOT NULL DEFAULT ''"),
    # Engagement.
    ("likes", "INTEGER NOT NULL DEFAULT 0"),
    ("comments", "INTEGER NOT NULL DEFAULT 0"),
    ("shares", "INTEGER NOT NULL DEFAULT 0"),
    ("saves", "INTEGER NOT NULL DEFAULT 0"),
    # Creative context.
    ("creator", "TEXT NOT NULL DEFAULT ''"),
    ("concept", "TEXT NOT NULL DEFAULT ''"),
    ("format", "TEXT NOT NULL DEFAULT ''"),
    ("message_class", "TEXT NOT NULL DEFAULT ''"),
    ("promotion", "TEXT NOT NULL DEFAULT ''"),
    # Campaign context.
    ("placement", "TEXT NOT NULL DEFAULT ''"),
    ("audience", "TEXT NOT NULL DEFAULT ''"),
    # Row-level missing-data record: JSON list of canonical fields
    # that were blank or unsupported for this row. A stored 0 for a
    # listed field means missing, never a measured zero.
    ("missing_json", "TEXT NOT NULL DEFAULT '[]'"),
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
    team TEXT NOT NULL DEFAULT '',
    vertical TEXT NOT NULL DEFAULT '',
    market TEXT NOT NULL DEFAULT '',
    objective TEXT NOT NULL DEFAULT '',
    funnel_stage TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL DEFAULT '',
    revenue REAL NOT NULL DEFAULT 0,
    revenue_reported INTEGER NOT NULL DEFAULT 0,
    account_id TEXT NOT NULL DEFAULT '',
    campaign_id TEXT NOT NULL DEFAULT '',
    ad_id TEXT NOT NULL DEFAULT '',
    import_id TEXT NOT NULL DEFAULT '',
    reach INTEGER NOT NULL DEFAULT 0,
    frequency REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT '',
    video_starts INTEGER NOT NULL DEFAULT 0,
    views_2s INTEGER NOT NULL DEFAULT 0,
    views_3s INTEGER NOT NULL DEFAULT 0,
    views_6s INTEGER NOT NULL DEFAULT 0,
    watch_time_total_s REAL NOT NULL DEFAULT 0,
    watch_time_basis TEXT NOT NULL DEFAULT '',
    avg_watch_per_view_s REAL NOT NULL DEFAULT 0,
    avg_watch_per_user_s REAL NOT NULL DEFAULT 0,
    link_clicks INTEGER NOT NULL DEFAULT 0,
    conversion_event TEXT NOT NULL DEFAULT '',
    attribution TEXT NOT NULL DEFAULT '',
    likes INTEGER NOT NULL DEFAULT 0,
    comments INTEGER NOT NULL DEFAULT 0,
    shares INTEGER NOT NULL DEFAULT 0,
    saves INTEGER NOT NULL DEFAULT 0,
    creator TEXT NOT NULL DEFAULT '',
    concept TEXT NOT NULL DEFAULT '',
    format TEXT NOT NULL DEFAULT '',
    message_class TEXT NOT NULL DEFAULT '',
    promotion TEXT NOT NULL DEFAULT '',
    placement TEXT NOT NULL DEFAULT '',
    audience TEXT NOT NULL DEFAULT '',
    missing_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS analyst_imports (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'upload',
    locale TEXT NOT NULL DEFAULT '',
    delimiter TEXT NOT NULL DEFAULT '',
    mapping_json TEXT NOT NULL DEFAULT '{}',
    unmapped_json TEXT NOT NULL DEFAULT '[]',
    rows_imported INTEGER NOT NULL DEFAULT 0,
    rows_quarantined INTEGER NOT NULL DEFAULT 0,
    imported_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS analyst_conversations (
    id TEXT PRIMARY KEY,
    owner_employee_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    scope_json TEXT NOT NULL DEFAULT '{}',
    objective TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'en',
    dataset_version TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS analyst_messages (
    id INTEGER PRIMARY KEY,
    conversation_id TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT '',
    body_text TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS analyst_messages_conv
    ON analyst_messages (conversation_id);
CREATE TABLE IF NOT EXISTS analyst_findings (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL DEFAULT '',
    scope_json TEXT NOT NULL DEFAULT '{}',
    dataset_version TEXT NOT NULL DEFAULT '',
    finding_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
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
    creative_key TEXT NOT NULL DEFAULT '',
    schema_version TEXT NOT NULL DEFAULT 'v0',
    annotation_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT '',
    -- Immutable asset-version identity (videos.id): each uploaded
    -- video version carries its own analysis row, so two uploads
    -- sharing one editable creative name can never read, correct,
    -- approve, or export each other's findings. '' is the legacy
    -- pre-scoped row.
    video_id TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (creative_key, video_id)
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
CREATE TABLE IF NOT EXISTS product_audit (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL DEFAULT '',
    employee_id TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_product_audit_created
    ON product_audit (created_at);
CREATE INDEX IF NOT EXISTS idx_product_audit_employee
    ON product_audit (employee_id);
-- One-time sample-data import ledger (demo_pack version of the
-- "persistent receipt"). One row per pack_key, never deleted:
-- normal record deletes and Remove All Demo Data keep the receipt
-- so deleted samples can never be mistaken for "never imported".
-- Batch membership (which rows belong to the pack) lives in
-- demo_batch_members, keyed by stable record identity — never by
-- display name, so renames keep their cleanup provenance.
CREATE TABLE IF NOT EXISTS demo_packs (
    pack_key TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL DEFAULT '',
    workspace TEXT NOT NULL DEFAULT '',
    imported_by TEXT NOT NULL DEFAULT '',
    imported_at TEXT NOT NULL DEFAULT '',
    data_start TEXT NOT NULL DEFAULT '',
    data_end TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'added',
    counts_json TEXT NOT NULL DEFAULT '{}',
    removed_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS demo_batch_members (
    batch_id TEXT NOT NULL DEFAULT '',
    table_name TEXT NOT NULL DEFAULT '',
    record_key TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (batch_id, table_name, record_key)
);
CREATE INDEX IF NOT EXISTS demo_batch_members_batch
    ON demo_batch_members (batch_id);
-- Generated sample files (reports, workbooks) with real bytes on
-- disk under the media store. file_key is "<batch_id>/<name>".
CREATE TABLE IF NOT EXISTS sample_files (
    file_key TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    format TEXT NOT NULL DEFAULT '',
    mime TEXT NOT NULL DEFAULT '',
    bytes INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS sample_files_batch
    ON sample_files (batch_id);
-- Guided video-upload flow: owner-scoped drafts, validated videos,
-- imported datasets, and confirmed video-to-record matches. The API
-- layer enforces owner-or-admin writes; reads follow the media
-- convention (any active employee). Draft status lifecycle lives in
-- creative_intel.drafts (DRAFT_STATUSES); job execution lifecycle
-- stays in worker_jobs.
CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    owner_employee_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    spec_json TEXT NOT NULL DEFAULT '{}',
    dataset_version TEXT NOT NULL DEFAULT '',
    review_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS drafts_owner
    ON drafts (owner_employee_id);
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL DEFAULT '',
    creative_key TEXT NOT NULL DEFAULT '',
    media_id INTEGER NOT NULL DEFAULT 0,
    duration_s REAL NOT NULL DEFAULT 0,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT NOT NULL DEFAULT '',
    validation_json TEXT NOT NULL DEFAULT '{}',
    transcript TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS videos_draft ON videos (draft_id);
CREATE INDEX IF NOT EXISTS videos_creative ON videos (creative_key);
CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    draft_id TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL DEFAULT '',
    rows INTEGER NOT NULL DEFAULT 0,
    version TEXT NOT NULL DEFAULT '',
    sha256 TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS datasets_draft ON datasets (draft_id);
CREATE TABLE IF NOT EXISTS matches (
    draft_id TEXT NOT NULL DEFAULT '',
    creative_key TEXT NOT NULL DEFAULT '',
    method TEXT NOT NULL DEFAULT '',
    record_json TEXT NOT NULL DEFAULT '[]',
    confirmed INTEGER NOT NULL DEFAULT 0,
    confirmed_by TEXT NOT NULL DEFAULT '',
    confirmed_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (draft_id, creative_key)
);
"""

# Natural dedup key for re-imports: the same fact from the same origin
# (same source feed, platform, campaign/adset/ad row and reporting date)
# is one row. Every product import surface (uploads, connectors,
# scheduler) stores via ingest.upsert_rows(), so re-imports update
# metrics instead of duplicating rows; insert_rows() stays the raw
# append primitive and refuses exact-duplicate facts.
#
# Identity includes the tenant/account grain: two unrelated clients
# using the same campaign/ad names on the same date must never
# collapse into one fact (client B's re-import used to overwrite
# client A's record). Rows without identifiers carry "" there, which
# preserves the legacy dedup behavior exactly.
SYNC_KEY_COLUMNS = ("source", "platform", "campaign", "adset",
                    "ad_name", "date", "client", "account_id",
                    "campaign_id", "ad_id")


def _sync_key_sql():
    return ("CREATE UNIQUE INDEX ads_sync_key ON ads (%s)"
            % ", ".join(SYNC_KEY_COLUMNS))


def ensure_sync_key(conn):
    """Idempotent, concurrency-safe sync-key index.

    Steady state is a read-only check: when ads_sync_key already
    exists with the current definition this performs zero writes, so
    per-request init_db() calls and parallel imports can no longer
    race "index already exists" or wedge each other with full-table
    DDL on every call (that race crashed the seeded E2E backend under
    parallel Playwright workers).

    DROP + dedup + CREATE runs only when the index is missing or
    stale. A stale narrow index from before account/client columns
    joined the key is still replaced — IF NOT EXISTS alone would
    keep it and silently re-allow cross-client overwrites. A lost
    create-if-missing race tolerates "already exists" by re-verifying
    the index definition instead of crashing.
    Returns True when the index was (re)built.
    """
    import sqlite3
    want = _sync_key_sql()
    got = conn.execute(
        "SELECT sql FROM sqlite_master"
        " WHERE type='index' AND name='ads_sync_key'").fetchone()
    if got and (got[0] or "") == want:
        return False
    conn.execute("DROP INDEX IF EXISTS ads_sync_key")
    key_cols = ", ".join(SYNC_KEY_COLUMNS)
    conn.execute(
        "DELETE FROM ads WHERE rowid NOT IN"
        " (SELECT MAX(rowid) FROM ads GROUP BY %s)" % key_cols)
    try:
        conn.execute(want)
    except sqlite3.OperationalError as exc:
        if "already exists" not in str(exc):
            raise
        got = conn.execute(
            "SELECT sql FROM sqlite_master"
            " WHERE type='index' AND name='ads_sync_key'").fetchone()
        if not got or (got[0] or "") != want:
            raise
    return True


def _migrate_annotations(conn):
    """Rebuild pre-scoped annotations to the (creative_key, video_id)
    identity.

    Idempotent: fresh databases already match the static DDL, and the
    rebuild runs once — when video_id is missing — preserving every
    existing row under the legacy '' video scope.
    """
    cols = [row[1] for row in conn.execute("PRAGMA table_info(annotations)")]
    if not cols:
        conn.execute(
            "CREATE TABLE annotations ("
            "creative_key TEXT NOT NULL DEFAULT '',"
            " schema_version TEXT NOT NULL DEFAULT 'v0',"
            " annotation_json TEXT NOT NULL DEFAULT '{}',"
            " updated_at TEXT NOT NULL DEFAULT '',"
            " video_id TEXT NOT NULL DEFAULT '',"
            " PRIMARY KEY (creative_key, video_id))")
        return
    if "video_id" in cols:
        return
    conn.execute(
        "CREATE TABLE annotations_new ("
        "creative_key TEXT NOT NULL DEFAULT '',"
        " schema_version TEXT NOT NULL DEFAULT 'v0',"
        " annotation_json TEXT NOT NULL DEFAULT '{}',"
        " updated_at TEXT NOT NULL DEFAULT '',"
        " video_id TEXT NOT NULL DEFAULT '',"
        " PRIMARY KEY (creative_key, video_id))")
    conn.execute(
        "INSERT INTO annotations_new (creative_key, schema_version,"
        " annotation_json, updated_at, video_id)"
        " SELECT creative_key, schema_version, annotation_json,"
        " updated_at, '' FROM annotations")
    conn.execute("DROP TABLE annotations")
    conn.execute("ALTER TABLE annotations_new RENAME TO annotations")


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
    for name, ddl in NEW_DIMENSIONS + NEW_MEASURES:
        if name not in existing:
            conn.execute("ALTER TABLE ads ADD COLUMN %s %s" % (name, ddl))
            added.append(name)
    # Analyst workflow tables (conversations, findings, import
    # provenance). CREATE IF NOT EXISTS: safe on every open.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS analyst_imports ("
        "id TEXT PRIMARY KEY,"
        " filename TEXT NOT NULL DEFAULT '',"
        " platform TEXT NOT NULL DEFAULT '',"
        " source TEXT NOT NULL DEFAULT 'upload',"
        " locale TEXT NOT NULL DEFAULT '',"
        " delimiter TEXT NOT NULL DEFAULT '',"
        " mapping_json TEXT NOT NULL DEFAULT '{}',"
        " unmapped_json TEXT NOT NULL DEFAULT '[]',"
        " rows_imported INTEGER NOT NULL DEFAULT 0,"
        " rows_quarantined INTEGER NOT NULL DEFAULT 0,"
        " imported_by TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL DEFAULT '')")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS analyst_conversations ("
        "id TEXT PRIMARY KEY,"
        " owner_employee_id TEXT NOT NULL DEFAULT '',"
        " title TEXT NOT NULL DEFAULT '',"
        " scope_json TEXT NOT NULL DEFAULT '{}',"
        " objective TEXT NOT NULL DEFAULT '',"
        " language TEXT NOT NULL DEFAULT 'en',"
        " dataset_version TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL DEFAULT '',"
        " updated_at TEXT NOT NULL DEFAULT '')")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS analyst_messages ("
        "id INTEGER PRIMARY KEY,"
        " conversation_id TEXT NOT NULL DEFAULT '',"
        " role TEXT NOT NULL DEFAULT '',"
        " kind TEXT NOT NULL DEFAULT '',"
        " body_text TEXT NOT NULL DEFAULT '',"
        " payload_json TEXT NOT NULL DEFAULT '{}',"
        " created_at TEXT NOT NULL DEFAULT '')")
    conn.execute("CREATE INDEX IF NOT EXISTS analyst_messages_conv"
                 " ON analyst_messages (conversation_id)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS analyst_findings ("
        "id TEXT PRIMARY KEY,"
        " conversation_id TEXT NOT NULL DEFAULT '',"
        " scope_json TEXT NOT NULL DEFAULT '{}',"
        " dataset_version TEXT NOT NULL DEFAULT '',"
        " finding_json TEXT NOT NULL DEFAULT '{}',"
        " status TEXT NOT NULL DEFAULT 'proposed',"
        " created_at TEXT NOT NULL DEFAULT '',"
        " updated_at TEXT NOT NULL DEFAULT '')")
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
    conn.execute(
        "CREATE TABLE IF NOT EXISTS product_audit ("
        "id TEXT PRIMARY KEY, request_id TEXT NOT NULL DEFAULT '',"
        " employee_id TEXT NOT NULL DEFAULT '',"
        " action TEXT NOT NULL DEFAULT '',"
        " target TEXT NOT NULL DEFAULT '',"
        " result TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL DEFAULT '')")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_product_audit_created"
                 " ON product_audit (created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_product_audit_employee"
                 " ON product_audit (employee_id)")
    # One-time sample-import ledger + batch membership + sample
    # files (see DDL above). CREATE IF NOT EXISTS: safe on every
    # open, and a migration never inserts presentation data.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS demo_packs ("
        "pack_key TEXT PRIMARY KEY,"
        " batch_id TEXT NOT NULL DEFAULT '',"
        " workspace TEXT NOT NULL DEFAULT '',"
        " imported_by TEXT NOT NULL DEFAULT '',"
        " imported_at TEXT NOT NULL DEFAULT '',"
        " data_start TEXT NOT NULL DEFAULT '',"
        " data_end TEXT NOT NULL DEFAULT '',"
        " status TEXT NOT NULL DEFAULT 'added',"
        " counts_json TEXT NOT NULL DEFAULT '{}',"
        " removed_at TEXT NOT NULL DEFAULT '')")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS demo_batch_members ("
        "batch_id TEXT NOT NULL DEFAULT '',"
        " table_name TEXT NOT NULL DEFAULT '',"
        " record_key TEXT NOT NULL DEFAULT '',"
        " PRIMARY KEY (batch_id, table_name, record_key))")
    conn.execute("CREATE INDEX IF NOT EXISTS demo_batch_members_batch"
                 " ON demo_batch_members (batch_id)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sample_files ("
        "file_key TEXT PRIMARY KEY,"
        " batch_id TEXT NOT NULL DEFAULT '',"
        " name TEXT NOT NULL DEFAULT '',"
        " format TEXT NOT NULL DEFAULT '',"
        " mime TEXT NOT NULL DEFAULT '',"
        " bytes INTEGER NOT NULL DEFAULT 0,"
        " sha256 TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL DEFAULT '')")
    conn.execute("CREATE INDEX IF NOT EXISTS sample_files_batch"
                 " ON sample_files (batch_id)")
    # Guided video-upload flow (see DDL above). CREATE IF NOT EXISTS:
    # safe on every open; old databases gain empty tables, never rows.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS drafts ("
        "id TEXT PRIMARY KEY,"
        " owner_employee_id TEXT NOT NULL DEFAULT '',"
        " status TEXT NOT NULL DEFAULT 'draft',"
        " spec_json TEXT NOT NULL DEFAULT '{}',"
        " dataset_version TEXT NOT NULL DEFAULT '',"
        " review_json TEXT NOT NULL DEFAULT '{}',"
        " created_at TEXT NOT NULL DEFAULT '',"
        " updated_at TEXT NOT NULL DEFAULT '')")
    conn.execute("CREATE INDEX IF NOT EXISTS drafts_owner"
                 " ON drafts (owner_employee_id)")
    draft_cols = {row[1] for row in
                  conn.execute("PRAGMA table_info(drafts)")}
    if "review_json" not in draft_cols:
        conn.execute("ALTER TABLE drafts ADD COLUMN"
                     " review_json TEXT NOT NULL DEFAULT '{}'")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS videos ("
        "id TEXT PRIMARY KEY,"
        " draft_id TEXT NOT NULL DEFAULT '',"
        " creative_key TEXT NOT NULL DEFAULT '',"
        " media_id INTEGER NOT NULL DEFAULT 0,"
        " duration_s REAL NOT NULL DEFAULT 0,"
        " width INTEGER NOT NULL DEFAULT 0,"
        " height INTEGER NOT NULL DEFAULT 0,"
        " sha256 TEXT NOT NULL DEFAULT '',"
        " validation_json TEXT NOT NULL DEFAULT '{}',"
        " transcript TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL DEFAULT '')")
    video_cols = {row[1] for row in
                  conn.execute("PRAGMA table_info(videos)")}
    if "transcript" not in video_cols:
        conn.execute("ALTER TABLE videos ADD COLUMN"
                     " transcript TEXT NOT NULL DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS videos_draft"
                 " ON videos (draft_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS videos_creative"
                 " ON videos (creative_key)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS datasets ("
        "id TEXT PRIMARY KEY,"
        " draft_id TEXT NOT NULL DEFAULT '',"
        " filename TEXT NOT NULL DEFAULT '',"
        " rows INTEGER NOT NULL DEFAULT 0,"
        " version TEXT NOT NULL DEFAULT '',"
        " sha256 TEXT NOT NULL DEFAULT '',"
        " created_at TEXT NOT NULL DEFAULT '')")
    conn.execute("CREATE INDEX IF NOT EXISTS datasets_draft"
                 " ON datasets (draft_id)")
    _migrate_annotations(conn)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS matches ("
        "draft_id TEXT NOT NULL DEFAULT '',"
        " creative_key TEXT NOT NULL DEFAULT '',"
        " method TEXT NOT NULL DEFAULT '',"
        " record_json TEXT NOT NULL DEFAULT '[]',"
        " confirmed INTEGER NOT NULL DEFAULT 0,"
        " confirmed_by TEXT NOT NULL DEFAULT '',"
        " confirmed_at TEXT NOT NULL DEFAULT '',"
        " PRIMARY KEY (draft_id, creative_key))")
    ensure_sync_key(conn)
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
