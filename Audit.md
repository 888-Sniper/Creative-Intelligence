# Creative Intelligence audit — gap-completion branch (2026-10-18)

Review branch `feature/complete-gaps-2026-10-18` against reviewed
`main` SHA `5dcb3a0a0d68a15bf3bd67174402944a0cdf2c55`. This branch
is NOT pushed to `main` and NOT deployed; the Render site is
unchanged. Do not edit, commit, push, build, install, start the
server, or activate a provider. Report only defects still present
on this branch, with severity, observed behavior, file and line,
and reproducing evidence. Do not treat an unrun live Gemini call,
live browser, or missing deployment credentials as a source defect;
they are recorded below as blockers/unverified.

Confirm the change with both ends named:

```
git diff --stat 5dcb3a0a0d68a15bf3bd67174402944a0cdf2c55 feature/complete-gaps-2026-10-18
```

## What should now be true

1. **Video → Gemini (Gemini-only works).**
   `eligible_vision_roster()` no longer constructs `LiveBundle`
   (`video_analysis.py`), so a Gemini key without Deepgram/Groq
   keys reports ready. `VISION_ROSTER` leads with real ids
   `gemini-2.5-flash` / `gemini-2.5-flash-lite` (native-video in
   `VIDEO_MODEL_SUPPORT`). `GeminiStt` transcribes via inline audio;
   `LiveBundle` falls back to it. The Gemini key rides the
   `x-goog-api-key` header, never the URL (`providers.py`); the old
   test asserting `?key=` was replaced. A paused/absent managed LLM
   aborts the job before the vision call. `/api/providers/status`
   reports the worker's frame-eligible roster plus
   `analysis.ready/model/llm_ready`. Video-only analysis
   (`video_only: true`) binds without dataset/match, stamps
   performance `available: false`, and
   `GET /api/drafts/{id}/report` downloads the saved findings as
   Markdown. Combined analysis still requires a confirmed match.

2. **AI Analyst uses the managed provider for narrative.**
   Numbers stay deterministic (`analyst_chat.answer_turn`).
   `worker_handlers._analyst_narrative` calls the active managed
   model over computed facts only, labels
   `narrative_source: "managed_provider"` solely on a real answer,
   and returns `deterministic` + the not-configured sentence when
   paused. Spanish is accepted end to end (narrative language).

3. **Saved conversations restore.** Opening a previous analysis or
   `/analyst?conversation=<id>` loads stored messages in order
   (`AnalystPage.openConversation`) with a generation + account
   guard, loading/error/retry states, and account-switch clearing
   (first mount no longer cancels the deep-link restore). Insights
   conversation cards deep-link with the id. All Time reflects the
   shared date filter (`custom` range); Reset clears
   Objective/Language; Clear clears chat + shared filters.

4. **Report templates are real.** Owner-scoped CRUD at
   `/api/report-templates` (`report_templates` table). Reports page
   saves (named), lists, applies (dropping vanished campaigns with
   a status note) and deletes. No global `ci-report-template`
   browser key remains.

5. **Export Data downloads.** `POST /api/auth/export` returns a ZIP
   (profile/preferences/conversations/messages/templates/drafts/
   notifications + README). Credential-shaped keys are stripped
   recursively. The UI reports success only on a real attachment
   (`apiBlob`, which also re-gates expired sessions for workbook,
   report XLSX and draft-report downloads).

6. **Settings preferences take effect.** Server copy at
   `/api/preferences` (per employee). Default View routes the first
   landing (`DefaultLanding`), Default Date Range drives the
   Dashboard boot window, Default Currency keeps USD source values
   with an explicit no-conversion note (never a symbol swap),
   workspace name shows in the shell, theme/accent/density follow
   the account via the server copy, and the debounced workspace
   autosave flushes on unmount. Retention copy stays a browser
   preference, not server enforcement.

7. **Notifications are truthful.** Opt-ins persist server-side;
   every send attempt lands in `notification_outbox` as
   sent/skipped/blocked/failed with dedup. Without
   `CREATIVE_INTEL_SMTP_HOST`/`_FROM` the status is `blocked`
   naming the variable. No production email was sent.

8. **Integrations.** Google Drive OAuth now binds the starting
   employee into the pending verifier (same packing as
   Meta/TikTok/GA4); a foreign callback exchanges nothing. GA4
   gains property discovery + read-only `runReport` import into
   `ga4_rows` (separate from ad facts, no attribution claimed).
   `docs/RENDER.md` documents Meta/TikTok/GA4 env vars, console
   permissions and Render-domain callbacks.

9. **Controls.** Campaign "vs. Benchmark" is per-row vs the pooled
   scope benchmark. Insights surfaces load errors with Retry.
   Workbook preview shows an error + Retry (sheets contract
   unchanged; modules recorded on the cover). Provider cards name
   the actual in-flight action. Cohort Create is double-submit
   locked. Benchmark Select-All respects the 3-chart cap with a
   status. Creatives learnings include measured 0s durations.
   New strings exist in en/es/pl (`parity.test.ts`).

## Evidence (this branch)

- Backend: `pytest tests/test_gap_completion.py` 11 passed;
  focused suites (video, analyst, providers, oauth, workbook)
  passed after two contract fixes. Full-suite comparison vs the
  887-pass/5-fail baseline is recorded in the delivery report.
- Frontend: `pnpm exec tsc --noEmit` clean; `pnpm test` 327+
  passed (incl. a new deep-link restore test); `pnpm build` ok.
- Real attached video `04-quentin-retargeting-si.mp4`
  (15.8s, 1080×1920, h264+aac) ran through media save → ffmpeg
  frame/audio prepare (9 JPEG frames) → pipeline → persisted
  `ready_for_review` → Markdown report with stub providers
  (`/tmp/live_stub_run.py`, `/tmp/stub-creative-report.md`).

## Blocked / unverified (not source defects)

- **Live Gemini run: BLOCKED.** `CREATIVE_INTEL_KEY_GEMINI` is
  empty in env, login shell, launchctl and macOS Keychain
  (`creative-intel-gemini` not found). No live model call, UI
  click-through, or screenshot evidence exists. Supplying the key
  (env or Keychain) plus an admin-activated Gemini model unblocks
  the exact live test in the task (§12).
- **Email delivery: BLOCKED** on `CREATIVE_INTEL_SMTP_*` (see §7).
  Implementation + fake-transport tests pass; delivery unverified.
- **Meta/TikTok/GA4 live OAuth + imports: BLOCKED** on console app
  credentials listed in `docs/RENDER.md`. Code paths and owner
  binding are unit-covered; no live provider was contacted.
- **Production:** nothing was pushed to `main` or deployed.
  Render still serves `5dcb3a0`.

## Still open (known, not addressed here)

- Compare page hardcoded English copy (pre-existing, untouched).
- Full es/pl rendering of deterministic Analyst tables (templates
  remain en/pl; Spanish narrative comes from the provider).
- Browser-local admin teams have no per-employee team backend;
  created teams list as "Local" only (documented in-file).
- Five pre-existing backend failures on `main`
  (`test_no_licensing_concepts` .venv walker, 3× migrations,
  deploy migration head) — unchanged by this branch.
