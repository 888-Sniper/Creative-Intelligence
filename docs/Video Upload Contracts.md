# Video Upload and Analysis — Frozen Contracts (WP0)

Feature branch: `feat/dashboard-video-upload-analysis` off `eac90ae` (main).
Fixtures: `fixtures/Video Upload Sample 720p.mp4` + `fixtures/Video Upload Sample Dataset.csv`.

## Fixture identity (hand-verifiable)

- Video: 15.000s, 1280x720, h264 + aac, 356,681 bytes,
  sha256 `041fd928e6a146997dc44482e9291b65a21e2efb3945540f583661fc85ebda9b`.
- Creative key: `video-upload-sample` (matches `Creative Name` in the CSV).
- Dataset totals: 3 rows, 6,000 impressions, 150 link clicks,
  pooled CTR = 150 / 6,000 x 100 = **2.50%** (never average row CTRs),
  spend 60.00, conversions 12, views 2400 / 1800 / 1200 / 600 / 300.

## Upload limits (configurable, documented)

- Containers: MP4 / MOV only, codecs subject to ffprobe decode check.
- Max file size and max duration are server settings surfaced to the
  Stage A UI; frontend checks are convenience only, the server revalidates
  extension, content type, file signature, decoder compatibility, size,
  duration, and corrupt/empty content.

## API shapes (backend is source of truth; TS types must mirror these)

- `POST /api/media/upload` (auth, multipart) -> media record
  `{id, creative_key, filename, mime, bytes, sha256, url}`
- `POST /api/videos/validate` (auth, `{media_id, draft_id?}`)
  -> `{video_id, media_id, creative_key, duration_s, width, height,
  validation}` (`validation` verdict object; `video_id` is "" when
  invalid and no row is stored; a draft link is required for a row)
- `POST /api/datasets/import` (auth,
  `{draft_id, platform, filename?, csv?|xlsx_b64?, sheet?}`)
  -> `{dataset_id, draft_id, rows, version(import_id), inserted,
  updated, quarantined, quarantine, sheet, sheets}`
  (multi-sheet workbooks without `sheet` get 409 + `sheets` catalogue)
- `POST /api/drafts` (auth, `{draft_id?, spec?}`)
  -> `{draft: view}` (idempotent on client-supplied `draft_id`;
  a colliding id owned by someone else is rejected, never served)
- `GET /api/drafts` (auth) -> `{drafts: view[]}` (owner-scoped)
- `GET /api/drafts/{id}` (auth) -> `{draft: view}` where view =
  `{id, owner_employee_id, status, dataset_version, created_at,
  updated_at, spec, videos[], datasets[], matches[],
  live_job_id}` (`live_job_id` is "" when no job runs)
- `PATCH /api/drafts/{id}` (owner-or-admin, `{status?, spec?,
  dataset_version?}`) -> `{draft: view}`; spec/dataset edits clear
  matches server-side
- `DELETE /api/drafts/{id}` (owner-or-admin) removes the draft and
  its videos/datasets/matches rows
- `GET /api/drafts/{id}/candidates` (auth)
  -> `{candidates[], version}` (rows of the draft's dataset_version
  only, capped at 200; [] before any import)
- `POST /api/drafts/{id}/matches/propose|confirm` (owner-or-admin,
  `{creative_key, method, ad_rowids[]}`) -> `{match}`; confirm
  requires a valid video and row ids from the draft's dataset version,
  and the key must be one of the draft's validated videos.
  Validating a replacement video clears matches like any other
  material input change.
- `POST /api/drafts/{id}/analyze` (auth, `{brand_terms?}`, AI-rate-limited)
  -> `{job_id, status, model, provider, sends, storage, poll}`
  (`poll` is the existing `/api/pipeline/jobs/{job_id}` status route —
  no second job API; 409 when preconditions, readiness, or a live job
  for the draft fail, with an honest reason);
- `GET /api/drafts/{id}/analysis` (auth)
  -> `{draft_id, status, creative_key, annotation|null, transcript}`
- `GET /media/by-creative/:key`, `GET /api/campaigns/meta`, `POST /api/reviews/mark`

## DB tables (in `Backend/creative_intel/schema.py` DDL + `migrate()` only;
alembic stays auth-only by design)

- Reuse `media`, `worker_jobs`.
- New: `drafts(id PK, owner_employee_id, status, spec_json, dataset_version,
  created_at, updated_at)`,
  `videos(id PK, draft_id FK, creative_key, media_id FK, duration_s, width,
  height, sha256, validation_json, created_at)`,
  `datasets(id PK, draft_id FK, filename, rows, version, sha256, created_at)`
  (+ `matches(draft_id, creative_key, score_json)` only if needed).

## State machines

- `draft.status` (`DRAFT_STATUSES` in `creative_intel/drafts.py`):
  `draft -> validating -> needs_confirmation -> queued -> analyzing ->`
  `ready_for_review -> reviewed`, with `failed | cancelled | expired`
  off-ramps. The endpoint submits as `queued`; the worker owns the
  `queued -> analyzing` flip at start and every exit path
  (`ready_for_review` / `failed` / `cancelled`), so no failure,
  cancel, or timeout strands a draft in `queued`/`analyzing`.
  Worker restart requeues only expired-lease running jobs, never live
  ones. CSV imports are capped at 20M chars like xlsx at 20MB.
- `video.validation`: `pending -> valid | invalid`
  (reasons: mime / size / duration / dims / sha-mismatch).
- `job.status` mirrors the draft while running, progress 0-1 measured only.
- Review: `Ready for review` (processing finished) vs `Reviewed`
  (authorised human checked that version). Material input changes invalidate
  approval. The AI never approves its own output.

## Metric rules

- Pooled CTR = total clicks / total impressions x 100 for display only,
  over comparable records with the same click definition.
- Link clicks stay distinct from all clicks. Missing is not zero; a zero
  denominator produces no rate. Campaign-only totals are labelled as such
  and never presented as creative-level metrics.

## Analysis pipeline

- Never send raw video: `video.prepare()` (ffmpeg -> JPEG frames + 16kHz WAV).
- Provider gating by `VIDEO_MODEL_SUPPORT`: native-video, image, audio,
  text-only (fail-fast). Unverified IDs render unverified, never capable.
- Findings split: Observed in the video / Measured from the dataset /
  Suggested test-hypothesis. Schema-validated before persistence, with
  sampling method, coverage, provider/model, analysis version, timestamp.
- Snapshot binding: Analyse freezes video sha + dataset version +
  match confirmation time. The worker re-binds before provider work
  AND after the pipeline (inputs may change mid-run); a newer
  stamped analysis aborts the late result instead of being
  overwritten (the intermediate save preserves the prior stamp).
  Residual note: two jobs on the same creative started in the same
  second could still interleave at commit time — prevented in
  practice by the per-draft live-job guard; cross-draft same-key
  concurrency is out of scope for this release.
