# Architecture

Local-first MVP. One SQLite file, one stdlib Python backend, one static
page. Mirrors Nextly AI trust boundaries: loopback only, Keychain-only
secrets, mock-first.

```text
CSV/XLSX/Sheets upload
  │  Backend/creative_intel/ingest.py  (Meta/TikTok/Excel/Sheets-normalize)
  ▼
SQLite (canonical dataset: ads, creatives, annotations, retention, replay_log)
  │  benchmarks.py (spend-weighted)   retention.py (drop-off ⨝ timestamps)
  ▼
Creative pipeline: ingest → transcribe → frame-sample → vision-annotate
                   → LLM-structure → confidence + HUMAN-VERIFIED gate
  │  creative.py + providers.py (Keychain or mock)
  ▼
Static UI (Web/Index.html, 5 views, light+dark tokens)
Gated one-pager export (export_gate.py) + fixture/replay (replay.py)
```

## Tables

- `ads` — one row per ad/row of an upload: platform, campaign, adset,
  ad name, creative key, spend, impressions, clicks, conversions,
  video views + quartile views (for retention).
- `creatives` — one row per creative key: platform, name, duration,
  status (`auto` | `human_verified`), transcript, pipeline JSON.
- `annotations` — schema v0 JSON per creative + per-field confidence.
- `retention` — `(creative_key, t_sec, retention_pct)` curve points.
- `replay_log` — every mutating API call, in order, for fixture replay.

## Views

Main (upload + KPIs), Campaign (spend-weighted table), Creative
(library + annotate + verify), Compare (A/B deltas), Benchmark
(spend-weighted bars by hook type / creator-vs-branded).

## Production database (SQLite now, PostgreSQL path later)

SQLite + WAL is the deliberate choice for the controlled demo and
early pilot: one file, zero services, `sqlite3 .backup` snapshots,
and the whole suite runs against it. Do NOT treat the single-VM
SQLite design as long-term production once Foap has concurrent
employees, many scheduled jobs and simultaneous analyses (single-file
write contention, no role separation, backups are file copies).

Migration path (kept viable, not yet built):

1. Identity layer first: `ci_backend` already talks SQLAlchemy and
   every schema change ships as an Alembic version — point the engine
   at a `postgresql+psycopg://` URL and run the same versions. (Adds
   the `psycopg` driver to `uv.lock`/`requirements.lock` plus a
   `CREATIVE_INTEL_DATABASE_URL` setting; nothing else in
   `ci_backend` is SQLite-specific.)
2. Analytics layer second: `creative_intel` uses raw `sqlite3` SQL
   with a handful of SQLite-isms to port (`PRAGMA` introspection,
   two `strftime` calls, one `randomblob`, one `INSERT OR REPLACE`;
   `ON CONFLICT` already ports as-is). Port each statement, then use
   `replay_log` as the deterministic before/after check: replay the
   log on both backends and compare totals.
3. Data move: one offline load (SQLite dump → PostgreSQL, or
   `pgloader`), cut over with the app stopped, and keep the last
   SQLite backup until the first successful PostgreSQL backup plus
   restore test (`verify-restore.sh` grows a `--db-url` mode then).
