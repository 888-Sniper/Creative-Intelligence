# Creative Intelligence — independent audit of the gap-completion branch

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Base (reviewed `main`): `5dcb3a0a0d68a15bf3bd67174402944a0cdf2c55`
  (`Fix the frontend typecheck and ignore a stale Compare response`)
- Under review: branch `feature/complete-gaps-2026-10-18`, code
  commit `d6a8ae7b220507c2346a93ed3fc809e60d621061`
  (`Complete the video-to-report, Analyst, templates, export and settings gaps`).
  Commits after it on this branch touch only this `Audit.md`;
  review the code at `d6a8ae7` regardless of branch head.
- This push lands the branch on `main` by fast-forward. After
  `git fetch`, the commit under review is `origin/main`; the code
  commit is `d6a8ae7` (commits after it touch only this file).
  Render auto-deploys from `main` (`render.yaml autoDeploy: true`),
  but deployment was not verified by the implementer — do not
  claim the live site shows this push without checking it, and do
  not treat Render state as a source defect. If your checkout has
  only `5dcb3a0` (no `d6a8ae7`), stop and say so — fetch first.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this commit):

```
git diff --stat 5dcb3a0a0d68a15bf3bd67174402944a0cdf2c55 d6a8ae7b220507c2346a93ed3fc809e60d621061
git diff 5dcb3a0a0d68a15bf3bd67174402944a0cdf2c55 d6a8ae7b220507c2346a93ed3fc809e60d621061
```

Expected shape: 40 files, 2318 insertions, 691 deletions (most
deletions are this file replacing the 2026-10-09 audit). If your
diff disagrees, stop and say so. Also confirm:

```
git rev-parse d6a8ae7b220507c2346a93ed3fc809e60d621061   # must resolve (the code under review)
git diff --stat d6a8ae7b220507c2346a93ed3fc809e60d621061 HEAD   # must touch Audit.md only
git rev-parse origin/main     # must be 5dcb3a0a0d68a15bf3bd67174402944a0cdf2c55
git status                    # stop only if the worktree is dirty
```

A behind local `main` or a missing local `main` branch is not a
reason to stop. Stop only if the two SHAs above do not resolve, or
the worktree is dirty. Read files at the reviewed commit
(`git show d6a8ae7:PATH` if needed); if a later edit moves a line,
follow the symbol, not the stale number.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `d6a8ae7`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `d6a8ae7`,
  and the evidence (quoted code or a minimal reproduction by
  reasoning over the code). No evidence, no defect — list it under
  "Unverified" instead.
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing `main` test failures named
  at the end. They are blockers/unverified, recorded below.
- Do NOT report an item as open when the cited lines do what the
  matching section says. Conversely, do NOT mark an item fixed from
  a summary, a comment, or a test name — open the implementation.
- Check the tests as skeptically as the code: a test that encodes
  the same wrong assumption as the fix proves nothing. Say so when
  you find one.
- Secrets: never print a credential value. If you find one in the
  diff, report file and line only, redacted.

## Required output format

1. `Defects still true` — numbered, severity-ordered (above format).
2. `Requirements missing or only partly done` — anything the
   original task asked for (summarized in the sections below) that
   the code does not actually deliver, with file/line evidence.
3. `Areas checked, no defect found` — one line per numbered section
   below, naming what you actually opened. Silence is not a pass.
4. `Unverified` — anything you could not confirm by reading, and
   exactly what run/access would settle it.
5. End with one verdict sentence: ship / ship after fixes / do not
   ship, naming the blocking items by number.

## What the implementer claims — falsify each one

### 1. Video → Gemini analysis → saved report (highest risk)

Claims. `eligible_vision_roster()` (`Backend/creative_intel/video_analysis.py:37`)
no longer constructs `LiveBundle`, so Gemini-only (no
Deepgram/Groq key) reports ready. `VISION_ROSTER`
(`Backend/creative_intel/providers.py`, `LiveBundle`) leads with
`gemini-2.5-flash` / `gemini-2.5-flash-lite`, both native-video in
`VIDEO_MODEL_SUPPORT` (`provider_inventory.py`). `GeminiStt`
(`providers.py:992`) transcribes via inline audio and `LiveBundle`
falls back to it. `GeminiChat` (`providers.py:555`) sends the key
in the `x-goog-api-key` header, never the URL.
`gemini_available_models()` (`providers.py:1045`) lists real model
ids via `GET /v1beta/models`. `readiness(conn=None)`
(`video_analysis.py:60`) also reports `llm_ready`;
`/api/providers/status` (`Backend/ci_backend/routers/product.py`,
`providers_status`) shows the worker's frame-eligible roster, not
mere key presence. A paused/absent managed LLM aborts `run()`
before the vision call. `bind_snapshot(..., video_only)`
(`video_analysis.py:120`) binds a labelled video-only analysis
with `records: []`; combined mode still demands confirmed
client/campaign + dataset + match. `build_creative_report()`
(`video_analysis.py:978`) renders only saved findings;
`GET /api/drafts/{id}/report` (`product.py`, `draft_report`)
downloads them owner-scoped. The wizard
(`VideoUploadPanel.tsx`, `canAnalyze`) gates on readiness and
offers a video-only toggle; `analyzeDraft(..., videoOnly)` is in
`videoUploadApi.ts`.

Try to break it:
- Can `video_only` bypass draft ownership, video validation, or the
  immutable-snapshot/stale-result guards (`check_snapshot`,
  `_guard_not_stale`, publish transaction)? Trace every
  `check_snapshot` call in `run()`.
- Does any path still require a non-Gemini STT/vision key (bundle
  construction in `Providers`, wizard gating, dispatcher)?
- Is a genuinely silent clip still distinguishable from failed
  audio extraction after the GeminiStt fallback? What does
  `GeminiStt` do on malformed/empty/error responses — can it turn a
  failure into an empty "silent" transcript, or invent speech?
- Can instructions inside frames/transcript reach the structurer as
  instructions rather than data? Check the prompts.
- Does the report ever state spend/CTR/ROAS/conversions without
  confirmed records? Check `measured_from_records` zero/missing
  handling and the video-only measured block end to end (API →
  saved annotation → review screen → download must agree).
- Duplicate Analyze, cancel mid-run, retry, timeout, and a second
  newer job finishing first: can a stale/duplicate result publish?
- Is `gemini-2.5-flash` actually frame-eligible in
  `VIDEO_MODEL_SUPPORT`, and does discovery (`gemini_available_models`)
  ever gate anything, or can readiness still name a model the key
  cannot call? Is that acceptable or a defect?
- The two `readiness(conn)` call sites in `product.py` swallow
  `TypeError` for test doubles — can that mask a real bug?
- Does any error/log/URL carry the Gemini key after the header move
  (including `_http_json` errors and job error strings)?

### 2. AI Analyst on the managed provider

Claims. Metrics/tables stay deterministic (`analyst_chat.answer_turn`).
`_analyst_narrative` (`Backend/ci_backend/worker_handlers.py:150`,
used at `:235`) calls the active managed model over computed facts
only; `narrative_source` is `"managed_provider"` only on a real
answer, otherwise `"deterministic"` with the not-configured detail.
No silent provider switch. Spanish (`es`) is accepted
(`analyst_chat.detect_language`). Narrative persists as a
`narrative` message row.

Try to break it:
- Can template text ever be labelled as a provider answer (mock
  mode, `_Unavailable`, malformed JSON, empty answer, exception)?
- Can the narrative prompt receive data outside the caller's scope
  or another employee's conversation? Does it respect
  pause/deactivation exactly like Ask (`run_ask`)?
- Does narrative failure fail the whole turn, duplicate messages,
  or break cancellation/progress? What happens on retry — two
  narrative rows?
- Deterministic tables in Spanish: is the UI honest that only the
  narrative is Spanish?

### 3. Saved conversations restore

Claims. `openConversation` (`AnalystPage.tsx:369`) loads
`GET /api/analyst/conversations/{id}` in stored order, attaches
narrative rows to the prior answer, restores objective/language/
scope, and is generation- + account-guarded. Deep link
`/analyst?conversation=<id>` works without the list; unknown or
foreign ids show error + Retry; first mount no longer cancels the
restore (previous-account ref). Insights cards deep-link with the
id (`InsightsPage.tsx`, `savedCards`). All Time vs shared dates
(`custom` range), Reset and Clear semantics updated in
`AnalystPage.tsx`.

Try to break it:
- Race two conversation clicks; switch accounts mid-fetch; refresh
  on a deep link; open a foreign/deleted id. Any cross-account
  render, wrong-transcript win, or endless loading state?
- Does restoring resurrect findings actions against findings that
  are not in the restored payload? Is anything order-dependent
  beyond message order (scope inheritance on the next ask)?
- Backend: does `get_conversation` still 404 (not leak) for owners
  mismatched ids on every route that takes a conversation id?

### 4. Report templates

Claims. Owner-scoped CRUD `/api/report-templates`
(`product.py`, `report_templates_*`; `Backend/creative_intel/report_templates.py`;
`report_templates` table in `schema.py`). Reports page saves
named templates, lists, applies visibly before generation
(dropping vanished campaigns with a status), and deletes
(`ReportsPage.tsx`, `saveTemplate/applyTemplate/deleteTemplate`).
The global `ci-report-template` browser key is gone.

Try to break it:
- Any cross-owner read/update/delete (including PUT with another
  owner's id, list leakage, id guessing)? Any unvalidated config
  (format, list sizes, non-string entries) reaching generation?
- Does applying a template with empty/partial fields silently
  change KPIs/format, or resurrect deleted campaigns into a
  generated report?

### 5. Settings Export Data

Claims. `POST /api/auth/export` (`Backend/ci_backend/routers/auth.py:485`)
returns a ZIP built by `Backend/creative_intel/data_export.py`
(profile, preferences, conversations, messages, templates, draft
metadata, notification log, README). Credential-shaped keys are
stripped recursively (`_safe`). UI succeeds only on a real
attachment via `apiBlob` (`client.ts:106`, `SettingsPage.tsx`
`exportData`).

Try to break it:
- The `_safe` marker list is name-based. Find a secret-bearing
  field whose name evades it (long/spelled-out forms, nested JSON
  strings, `config_json`, message payloads). Default-deny would be
  safer — is the allowlist approach actually applied to profile but
  not to the DB rows?
- Can an employee export another employee's rows through any query?
  What about admins? Empty account, huge history, expired session,
  mid-export DB error — honest status codes, no partial "success"?
- Does the ZIP include media bytes, tokens from `oauth_tokens`, or
  provider secrets via any joined table?

### 6. Settings preferences take effect

Claims. Server copy `GET/PUT /api/preferences` (`product.py`,
`preferences_get/put`; `employee_prefs` table; `notifications.py`
`get_prefs/save_prefs` with a fixed key allowlist). Settings saves
locally + server-side and merges server-first on account adopt
(`SettingsPage.tsx`, `commit`, `SERVER_PREF_MAP`); debounced
workspace name flushes on unmount. Default View →
`DefaultLanding` (`router.tsx:46`), once per session. Default Date
Range → Dashboard boot window (`DashboardPage.tsx`,
`rangeDays(loadPrefs(...))`). Default Currency never converts:
USD source values stay, with `dashboard.currencyNote` when the
preference differs. Workspace name shows in `AppShell.tsx`.
Helpers in `state/prefs.ts` (`defaultViewPath`, `currencyCode`,
`rangeDays`).

Try to break it:
- Preference key smuggling through `PUT /api/preferences`
  (unknown keys, wrong types, another employee's row)?
- Server merge clobbering a newer local edit; explicit in-session
  choices overridden by defaults; `DefaultLanding` redirect loops
  or trapping the Dashboard nav/brand link; Dashboard boot
  overriding user-picked dates; currency note shown/hidden wrongly.
- Theme/accent/density actually following an account switch, or
  only language/timezone (check `applyLive` on the merged prefs)?
- Is anything described as server-enforced retention/privacy that
  is still only a browser preference?

### 7. Notifications

Claims. `Backend/creative_intel/notifications.py`: opt-ins persist
server-side; `enqueue()` records every attempt in
`notification_outbox` (sent/skipped/blocked/failed), dedupes on
`dedup_key`, honors opt-out before any send, and names the exact
missing SMTP variable when blocked. `POST /api/notifications/test`
sends only to the requester. SMTP via stdlib `smtplib` + STARTTLS.

Try to break it:
- Any path that sends to a non-requester address, sends when
  opted out, double-sends under concurrent duplicate submits, or
  reports `sent` without a completed SMTP transaction?
- Are the advertised toggles (Email Reports, Campaign Updates, AI
  Insights, Product Updates) each wired to a real trigger, or is
  only the test endpoint reachable? Treat an unwired trigger
  presented as working as a defect; `product_update` is explicitly
  `blocked` — check the UI copy agrees.
- Header injection via subject/recipient; credential leakage in
  `detail`/logs.

### 8. Integrations (Meta, TikTok, GA4, Google Drive)

Claims. Drive OAuth binds the starter: `start_google(...,
employee_id)` packs owner+verifier (`google_oauth.py`), router
passes `employee.id` (`routers/google.py`), `finish_google`
refuses owner mismatch before token exchange — same pattern as
`integrations_oauth.finish`. GA4: `GET /api/integrations/ga4/properties`
and `POST /api/integrations/ga4/import` (`product.py:2756,2780`)
over `Backend/creative_intel/ga4.py` (numeric property id, ISO
dates, upsert into `ga4_rows`, timezone preserved, explicit
"not ad-level metrics" note). Callbacks/env documented in
`docs/RENDER.md` ("Ad And Analytics Integrations").

Try to break it:
- Drive: legacy pending rows without the owner prefix; verifier
  values containing spaces; suspended starter; state-cookie vs
  owner check ordering. Can any callback still attach tokens to a
  different employee than the starter — for Drive, Meta, TikTok,
  GA4 alike?
- GA4: is the token fetched for provider id `"ga4"` the id tokens
  are actually stored under? Token refresh/disconnect, quota/error
  shapes, pagination limit (10k cap silently truncating?),
  repeat-import duplication, date/timezone conversion, and any
  path that merges `ga4_rows` into campaign/creative metrics.
- Scheduled Meta/TikTok imports still using the job owner's token
  (`sync.py` resolver) — regression-check against `da25a6e`.
- Docs: do the documented redirect paths byte-match the registered
  routes (`/api/auth/integrations/{provider}/callback`)?

### 9. Remaining controls, downloads, localisation

Claims. Campaign "vs. Benchmark" is per-row vs the pooled scope
benchmark (`CampaignsPage.tsx:392`, `pooledBench`/`benchFor`).
Insights shows load errors + Retry and deep-links conversations.
Workbook preview shows error + Retry; the seven-sheet contract is
unchanged with modules/KPIs recorded on the cover
(`analyst_workbook.build_blank_workbook`). Provider cards name the
in-flight action (`ProvidersPage.tsx`, busy label). Cohort Create
is in-flight locked (`DataTools.tsx`, `creating`). Benchmark
Select-All caps at the 3-chart limit with a status
(`BenchmarksPage.tsx`). Creatives learnings include 0s
(`CreativesPage.tsx`, `s >= 0`). Draft-report/workbook/XLSX
downloads go through `apiBlob`. New UI strings exist in en/es/pl
(`src/i18n/locales/*`, `parity.test.ts`).

Try to break it:
- `benchFor` for every selectable KPI (missing keys → crash or
  silent "Unavailable"? pooled vs averaged rates? zero pools?).
- Any remaining skeleton-forever or fake-empty error path on
  Dashboard/Insights/Workbook; any download/avatar path still on
  raw `fetch` that saves 401 JSON as a file (search for `fetch(`).
- Select-All indeterminate state; cohort lock release on error;
  provider label for `save-base:` vs `save:` ordering.
- i18n: keys used in code but missing in any locale (runtime shows
  the key), keys added to en only, Title-Case/plural rules broken.
  Check wizard method labels/moment flags and Compare copy — known
  English leftovers are listed below; find any NEW ones.

### 10. Tests and evidence quality

Claims. New durable tests: `tests/test_gap_completion.py`
(11 tests: Gemini-only roster, key-out-of-URL, GeminiStt parsing,
video-only snapshot+report, template owner scoping, notification
opt-out/dedup/blocker, secret-free export, GA4 validation, export
endpoint ZIP, templates/prefs endpoints, narrative labelling) and
one Analyst deep-link restore test (`AnalystPage.test.tsx`). One
existing test changed: `test_gemini_chat_uses_key_param` →
`test_gemini_chat_keeps_key_out_of_url` (`tests/test_admin_providers.py`)
because the task forbids credentials in URLs — judge whether that
test change is justified or hides a regression. Two contract fixes
were made under test pressure: workbook sheet filtering was
reverted, and `readiness(conn)` call sites gained a `TypeError`
fallback for no-arg test doubles — judge both.

Reported runs (implementer's machine; you may not re-run under the
rules above — instead check the tests would actually catch the
bugs they claim to):
- `pytest tests/` minus `test_ci_migrations.py`, minus
  `test_no_licensing_concepts`, minus
  `test_deploy_migration_command_from_repo_root`:
  899 passed, 1 skipped, 2 deselected.
- `pnpm test`: 327 passed. `pnpm exec tsc --noEmit`: clean.
  `pnpm build`: passed. Ruff on changed Python: clean
  (pre-existing `product.py` I001 untouched — verify it is old).
- Stub end-to-end over the real clip (NOT live evidence):
  `/tmp/live_stub_run.py` drove `04-quentin-retargeting-si.mp4`
  (15.8s, 1080×1920) through ffmpeg (9 JPEG frames + WAV) to a
  persisted `ready_for_review` and `/tmp/stub-creative-report.md`
  with stub providers.

Hunt especially for: tests that mock the very layer under change,
assertions on status codes without body/ownership checks, missing
negative cases (foreign owner, paused provider, malformed provider
JSON, zero-vs-missing metrics, concurrent duplicate submit), and
any coverage the sections above imply but no test exercises. Name
the missing test, not just "needs more tests".

## Blocked / unverified — do not report as source defects

- **Live Gemini run: BLOCKED.** `CREATIVE_INTEL_KEY_GEMINI` was
  empty in env, login shell, launchctl, and macOS Keychain
  (`creative-intel-gemini` not found) on the implementer's machine.
  No live model call, draft/job id, browser click-through, or
  screenshot exists. Verify the code path by reading; list the
  live run under your "Unverified" with the exact unblock steps.
- **Email delivery: BLOCKED** on `CREATIVE_INTEL_SMTP_HOST`,
  `_PORT`, `_USER`, `_PASSWORD`, `_FROM`. Fake-transport tests
  pass; real delivery unverified. Do not send test mail.
- **Meta/TikTok/GA4 live OAuth/imports: BLOCKED** on the console
  credentials in `docs/RENDER.md`. No live provider was contacted.
- **Production:** this push fast-forwards `main`; Render
  auto-deploys from `main`, but no deploy verification was done.
  Any claim that the live site already shows this push, without
  checking Render, would itself be a defect.

## Known still-open items (already admitted — only re-report if worse)

- Compare page hardcoded English copy (pre-existing, untouched).
- Deterministic Analyst tables render en/pl only; Spanish is the
  provider narrative, not the tables.
- Admin "teams" are browser-local (`ci-local-teams`, labelled
  Local); there is no per-employee team backend, so created teams
  cannot appear in employee assignment controls that do not exist.
- Five pre-existing backend failures on `main`, unchanged here:
  `test_ci_app.py::test_no_licensing_concepts` (walker enters
  `.venv`), three `test_ci_migrations.py` tests, and
  `test_deploy.py::test_deploy_migration_command_from_repo_root`
  (expects head `0012`, tree has `0013`). Confirm by reading; do
  not attribute them to this branch unless the diff touches them.

## Original task, in one paragraph (for completeness checking)

Implement and test the incomplete features: complete
upload → validation → destination → Gemini analysis → review →
saved report → download (Gemini-only sufficient, honest states,
no invented metrics, video-only reports allowed); connect AI
Analyst narrative to the managed provider; restore saved
conversations incl. deep links; reusable report templates;
Settings Export Data; effective Settings preferences; real
notification delivery behavior; Meta/TikTok/GA4 integration
completion incl. callback owner safety; remaining visible-control
fixes; en/es/pl localisation; regression tests plus a controlled
live Gemini test on `04-quentin-retargeting-si.mp4`; deliver a
checklist, evidence, blockers, and this Audit.md — without pushing
to `main` or deploying. Anything in that paragraph with no code
behind it belongs in your "Requirements missing" section.
