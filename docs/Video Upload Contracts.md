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
  -> `{video_id, media_id, draft_id, creative_key, duration_s, width,
  height, validation}` (`validation` verdict object; `video_id` is ""
  when invalid and no row is stored; without a draft_id a
  caller-owned draft is minted so every video row is owned; the
  draft check runs before any media/ffprobe work). Media entitlement
  (uploader, draft-bound owner, or admin) is established BEFORE any
  byte is decoded or bound: attaching a known media id to one's own
  draft never launders access to another employee's upload (403).
  A re-upload of identical bytes earns its own attributable row over
  the shared stored file — never an alias of the other's record.
- `GET /media/{id}` serves the raw file only to the uploader, to an
  admin, or to the owner of a draft whose videos bind that media row.
  Board thumbnails are served as preview bytes by the thumbnail route
  and stay tenant-visible like the analytics surface around them.
- `POST /api/datasets/import` (auth,
  `{draft_id, platform, filename?, csv?|xlsx_b64?, sheet?}`)
  -> `{dataset_id, draft_id, rows, version(import_id), inserted,
  updated, quarantined, quarantine, sheet, sheets}`
  (multi-sheet workbooks without `sheet` get 409 + `sheets` catalogue)
- `POST /api/drafts` (auth, `{draft_id?, spec?}`)
  -> `{draft: view}` (idempotent on client-supplied `draft_id`;
  a colliding id owned by someone else is rejected, never served)
- `GET /api/drafts` (auth) -> `{drafts: view[]}` (owner-scoped)
- `GET /api/drafts/{id}` (owner-or-admin) -> `{draft: view}` where
  view = `{id, owner_employee_id, status, dataset_version,
  created_at, updated_at, spec, videos[], datasets[], matches[],
  live_job_id, review}` (`live_job_id` is "" when no job runs;
  `review` is the recorded human review or {}). Reads are
  owner-or-admin like writes: views carry matched records and
  analysis. Raw media bytes are entitlement-gated separately; only
  derived board thumbnails stay tenant-visible.
- `PATCH /api/drafts/{id}` (owner-or-admin, `{status?, spec?,
  dataset_version?}`) -> `{draft: view}`; spec/dataset edits clear
  matches server-side
- `DELETE /api/drafts/{id}` (owner-or-admin) removes the draft and
  its videos/datasets/matches rows, cancels bound jobs, and erases
  content no other draft references (media row + stored file,
  annotation, generated transcript and pipeline record). Replace and
  Remove reap displaced assets the same way at drop time. Shared
  assets are kept (the creatives row itself stays as reporting
  identity); the stored file goes only when its last referencing
  media row does. Media erase removes the file first so a
  failed filesystem delete keeps the row as the recovery record.
- `DELETE /api/drafts/{id}/videos` (owner-or-admin) removes the
  draft's bound video row(s) so removal is explicit, never form-only.
- `POST /api/videos/validate` with a draft replaces prior video rows:
  a draft has exactly one active video version (newest valid wins).
- `GET /api/drafts/{id}/candidates` (owner-or-admin)
  -> `{candidates[], version}` (rows of the draft's dataset_version
  only, capped at 200; [] before any import; snapshots carry
  `missing_json`)
- `POST /api/drafts/{id}/matches/propose|confirm` (owner-or-admin,
  `{creative_key, method, ad_rowids[]}`) -> `{match}`; confirm
  requires a valid video and row ids from the draft's dataset version,
  and the key must be one of the draft's validated videos. With a
  confirmed client/campaign selection, records must belong to that
  campaign (the report carries no client grain, so client scoping is
  documented, not faked).
  Validating a replacement video clears matches like any other
  material input change.
- `POST /api/drafts/{id}/review` (owner-or-admin,
  `{analysis_version, revision?, note?}`) records a human review of
  one unique analysis result (reviewer + timestamp + note); 409
  unless ready_for_review, the revision matches the stored block,
  and the block's frozen input snapshot still matches live inputs.
  Success marks the annotation human_verified so the export gate
  recognises the approval. PATCH can never set `reviewed`. Material
  input changes — including a fresh propose or confirm — invalidate
  the review (status back to needs_confirmation, bound keys back to
  auto). Campaign comparison is case-insensitive; client is enforced
  only when both the selection and the record carry one.
- PATCH `dataset_version` only accepts this draft's own import
  versions (arbitrary import ids 409).
- `POST /api/drafts/{id}/analyze` (auth, `{brand_terms?}`, AI-rate-limited)
  -> `{job_id, status, model, provider, sends, storage, poll}`
  (`poll` is the existing `/api/pipeline/jobs/{job_id}` status route —
  no second job API; 409 when preconditions, readiness, or a live job
  for the draft fail, with an honest reason). Preconditions in guided
  order: validated video, then the authorised confirmed client/campaign
  destination on the draft's own spec (an incomplete draft may be
  saved, but combined analysis needs the confirmed destination; the
  snapshot inherits it for reports without a client column), then
  dataset, then confirmed match;
- `POST /api/drafts/{id}/corrections` (owner-or-admin, any subset of
  `{transcript, hook_type, hook_confidence, hook_modality,
  opening_delivery, narrative, message_class, promotion_kind,
  format_kind, creator_vs_branded, edit_style, frame_labels, tests}`)
  -> `{draft, annotation, revision}`. Corrects the stored finding
  itself (a review note never rewrites it): transcript text,
  hook/category values and confidence, frame timestamps/labels, and
  per-test accept/reject verdicts. Dimension corrections lock like
  analyst confirmations. Unknown fields, illegal enums, and unknown
  test ids 409. Every call mints a fresh analysis revision with a
  {by, at, fields} log entry and invalidates any recorded review, so
  corrected content must be re-reviewed;
- `GET /api/drafts/{id}/analysis` (owner-or-admin)
  -> `{draft_id, status, creative_key, annotation|null, transcript}`
- `GET /media/by-creative/:key`, `GET /api/campaigns/meta`, `POST /api/reviews/mark`

## DB tables (in `Backend/creative_intel/schema.py` DDL + `migrate()` only;
alembic stays auth-only by design)

- Reuse `media`, `worker_jobs`.
- New: `drafts(id PK, owner_employee_id, status, spec_json, dataset_version,
  review_json, created_at, updated_at)`,
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
  over comparable records with the same click definition (only records
  with BOTH sides known enter the pool).
- Link clicks stay distinct from all clicks. Missing is not zero: every
  known total accumulates independently — a missing CTR denominator
  withholds only the rate, never erases known spend, conversions, or
  views. Metrics listed in a record's `missing_json` — or explicitly
  null — contribute nothing to their own total (unknown clicks can
  never drag a CTR to 0%), while each known side is still preserved;
  a missing CTR pair produces no rate. An unavailable total is never a
  genuine zero. Mixed-currency spend is kept per-currency and
  the combined total is unavailable (never a genuine zero); an
  unspecified currency is its own bucket, never assumed. Campaign-only
  totals are labelled as such and never presented as creative-level
  metrics. Findings surface coverage and measurement warnings.

## Analysis pipeline

- Never send raw video: `video.prepare()` (ffmpeg -> JPEG frames + 16kHz WAV).
- Provider gating by `VIDEO_MODEL_SUPPORT`: native-video, image, audio,
  text-only (fail-fast). Unverified IDs render unverified, never capable.
- Findings split: Observed in the video / Measured from the dataset /
  Suggested test-hypothesis. Schema-validated before persistence, with
  sampling method, coverage, provider/model, analysis version, timestamp.
- Snapshot binding: Analyse freezes video id/media/key/sha + dataset
  version + match confirmation time + confirmed client/campaign. The
  worker re-binds before provider work AND after the pipeline (inputs
  may change mid-run); a newer stamped analysis aborts the late
  result instead of being overwritten. Deferred publish: the pipeline
  generates the full report WITHOUT writing to the published creative
  record, so an in-flight job can never clobber a concurrent
  finisher's rows — not even briefly. Freshness (inputs, job,
  cancellation) is verified first; only then is the complete result
  (transcript, pipeline record, annotation with a fresh unique
  revision, draft status) published in one step. A job that aborts
  before publish leaves no trace and needs no repair: stale aborts,
  cancellations (at any checkpoint, including after the pipeline),
  and provider failures write nothing.
- Worker startup: the web process runs the queue worker in-process on
  hosted single-service deploys (PORT set) or CREATIVE_INTEL_RUN_WORKER=true;
  standalone `worker.py` (Oracle systemd, local dev) is unchanged.
  Residual note: freshness is re-checked immediately before the
  single publish step, so the only remaining window is two jobs on
  the same creative passing the final gate simultaneously — prevented
  in practice by the per-draft live-job guard; cross-draft same-key
  concurrency is out of scope for this release.
