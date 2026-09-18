# Video Upload Walkthrough (Dayana's One-Video Test)

Branch: `feat/dashboard-video-upload-analysis` (off `eac90ae`, unmerged).
Fixtures: `fixtures/Video Upload Sample 720p.mp4` (15s, 1280x720)
+ `fixtures/Video Upload Sample Dataset.csv` (hand-checkable totals:
3 rows, 6,000 impressions, 150 link clicks, pooled CTR 2.50%).

## Setup

1. Backend: `python3 Backend/ci_backend/main.py --db <path>` (ffmpeg +
   ffprobe must be on PATH for validation and frame/audio prep).
2. Worker (analysis runs outside the request): in a second terminal,
   `python3 Backend/ci_backend/worker.py --db <same path>`.
   Without it, analysis jobs wait in `queued` (visible, never silent).
3. Frontend dev: `npm run dev` inside `apps/creative-intelligence-ui`
   (or serve a fresh `npm run build` dist/ next to the backend).
4. Live-provider smoke additionally needs `CREATIVE_INTEL_PROVIDER_MODE=live`
   plus a configured frame-eligible vision key (Stage D names the exact
   model, what is sent, and storage before anything is charged).

## Upload limits (server-enforced, shown in Stage A)

- Containers MP4/MOV only; max 100 MB; max 600 s; dimensions capped.
- The server revalidates extension, content type, file signature,
  decoder compatibility, size, duration, and corrupt/empty content —
  the browser checks are convenience only.

## The journey (about 5 minutes with your assets)

1. Dashboard: the **Analyze a video** card sits below the greeting.
   Click **Upload video** (or drop the file onto the card).
2. Stage Video: pick the MP4, set the creative key
   (e.g. `video-upload-sample`), Upload, wait for
   "Video valid — 1280x720, 15s." Continue.
3. Stage Client and campaign: choose client + campaign, Confirm
   selection. "All clients" is refused; changing either clears the
   match (said out loud, not silently).
4. Stage Dataset: paste the CSV (or choose the CSV/XLSX file; a
   multi-sheet workbook asks you to pick the sheet) and Import.
   Expect "3 rows · 3 new · 0 updated". Save draft works with or
   without data; closing the panel keeps the draft (Recent uploads
   offers Resume).
5. Stage Review: tick the record rows, Find matches, **Confirm match**,
   then **Analyze** (enabled only with a valid video + confirmation;
   otherwise the reason is printed, not just greyed out).
6. Wait for `ready_for_review` (Recent uploads shows live status;
   Cancel analysis works while it runs), reopen the draft at Review:
   Findings shows measured totals with pooled CTR, the transcript,
   and suggested tests labelled as hypotheses.
7. Correct anything on the Creatives page (transcript text,
   classifications); only a human verification flips the export gate.

## Limitations in this release

- One video per flow; campaigns accumulate creatives over time.
- Analyze refuses honestly without a live frame-eligible provider —
  no mock results ever stand in (prove readiness on Stage D).
- No bulk upload, no cross-client benchmarking, no billing changes
  (all deferred on purpose).
- Render Free wipes non-seeded rows each redeploy; seeded admins
  survive, drafts do not.
