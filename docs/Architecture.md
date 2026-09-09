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
