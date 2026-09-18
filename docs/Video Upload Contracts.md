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

- `POST /api/media/upload` (auth) -> `{media_id, creative_key, sha256, bytes, mime}`
- `POST /api/videos/validate` (auth) -> `{video_id, duration_s, width, height, validation_json}`
- `POST /api/datasets/import` (auth) -> `{dataset_id, rows, version}`
- `POST /api/drafts` (auth, `{creative_key, media_id?, dataset_id?, spec}`) -> `{id, status}`
- `POST /api/jobs/pipeline` (auth, `{draft_id, model_id}`) -> `{job_id, status}`
- `GET /api/drafts/:id` -> `{id, status, progress, spec_json, result_json, error}`
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

- `draft.status`: `queued -> running -> completed | failed | cancelled`
  (cancel is owner-or-admin; worker restart requeues interrupted).
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
