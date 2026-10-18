# Creative Intelligence — audit of the findings-fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `fbb9a65f1c576279cebeec3149ff0db71c283964`
  (code `d6a8ae7` + Audit.md-only commits; see git history)
- Under review in THIS push: code commit
  `8d6045171a369f0bd0516bc13f7c6604b9c0504e`
  (`Fix the independent audit findings (GA4 access, export, Analyst, notifications)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `8d60451` on this push touch only this `Audit.md`;
  review the code at `8d60451` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat fbb9a65f1c576279cebeec3149ff0db71c283964 8d6045171a369f0bd0516bc13f7c6604b9c0504e
git diff fbb9a65f1c576279cebeec3149ff0db71c283964 8d6045171a369f0bd0516bc13f7c6604b9c0504e
git rev-parse 8d6045171a369f0bd0516bc13f7c6604b9c0504e    # must resolve
git diff --stat 8d6045171a369f0bd0516bc13f7c6604b9c0504e HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 22 files, 620 insertions, 80
deletions. If yours disagrees, stop and say so. A behind local
checkout, or no local `main` branch, is not a reason to stop.
Read files at the reviewed commit (`git show 8d60451:PATH` if
needed); if a later edit moves a line, follow the symbol, not the
stale number. For full context of the feature set this push fixes,
also read the previous audit in history:
`git show fbb9a65:Audit.md` (base `5dcb3a0`, code `d6a8ae7`). This
push answers that review's 12 numbered defects plus its
"Requirements missing" list; re-verify those first, then hunt wider.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `8d60451`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `8d60451`,
  and the evidence (quoted code or a minimal reproduction by
  reasoning over the code). No evidence, no defect — list it under
  "Unverified" instead.
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at the
  end. They are blockers/unverified, recorded below.
- Do NOT report an item as open when the cited lines do what the
  matching section says. Conversely, do NOT mark an item fixed from
  a summary, a comment, or a test name — open the implementation.
  For each of the previous review's items 1–12, state explicitly:
  fixed / partly fixed / still open, with the line evidence.
- Check the tests as skeptically as the code: a test that encodes
  the same wrong assumption as the fix proves nothing. Say so when
  you find one.
- Secrets: never print a credential value. If you find one in the
  diff, report file and line only, redacted.

## Required output format

1. `Previous 12 findings` — one verdict line each (fixed /
   partly fixed / still open) with file:line evidence at `8d60451`.
2. `Defects still true` — numbered, severity-ordered (above format).
3. `Requirements missing or only partly done` — anything the
   original task asked for that the code still does not deliver.
4. `Areas checked, no defect found` — one line per numbered section
   below, naming what you actually opened. Silence is not a pass.
5. `Unverified` — anything you could not confirm by reading, and
   exactly what run/access would settle it.
6. End with one verdict sentence: ship / ship after fixes / do not
   ship, naming the blocking items by number.

## What the implementer claims — falsify each one

### 1. Previous finding 1 (P1): GA4 rows are owner-scoped

Claim. `GET /api/integrations/ga4/rows` (`product.py`, `ga4_rows`)
filters `WHERE imported_by=?` with the authenticated employee id;
the discarded `who` is gone. Try: employee B (never connected
Google) requesting rows for A's property id; admin accounts;
`property_id` variants (`properties/123` vs `123`); any other route
that reads `ga4_rows`.

### 2. Previous finding 2: export includes conversation history

Claim. `data_export.py` queries `owner_employee_id` (the real
column) for both conversations and the messages join.
`test_export_includes_seeded_conversation_history` seeds both
tables and asserts the ZIP contents. Try: other tables in
`build_export` with wrong columns that `_rows()` still swallows
into empty success (templates, drafts); should `_rows` fail loudly
for core tables instead? Secret-shaped keys in nested JSON strings
(`config_json`, payloads) that evade `_safe`.

### 3. Previous finding 3: server preferences load on normal visits

Claim. `SettingsPage.tsx` merges the server copy once per identity
even when `id === prefOwner` (`serverMergedFor` ref), unless a save
or name edit is in flight. Try: fresh browser, account switch A→B→A,
offline failure then first edit (does it clobber richer server
prefs?), StrictMode double-effect double-merge, theme select and
merged theme disagreeing.

### 4. Previous finding 4: Spanish Analyst requests work

Claim. `AnalystBody._check_language` accepts `pl|en|es`
(`product.py`); `detect_language` already accepted `es`.
`test_spanish_language_accepted_by_analyst_body` creates and reads
back an `es` conversation. Try: every other language validator
(Ask, report, conversation create), uppercase `ES`, explicit `es`
with Polish text, deterministic table language honesty in the UI.

### 5. Previous finding 5: GA4 refresh gets real settings

Claim. Both GA4 endpoints pass `request.app.state.ci_settings` to
`access_token_for` (matching the sync resolver pattern). Try: app
instances where `ci_settings` is absent (tests, alternate
factories); expired-token refresh end to end by reading
`integrations_oauth._refresh_google`; error still reported as
"not connected" when refresh genuinely fails vs when unset.

### 6. Previous finding 6: GA4 imports paginate

Claim. `ga4.fetch_rows` pages `runReport` with `offset` until a
short page or `rowCount` is covered, hard-stops at 250000 rows
with an explicit error. `test_ga4_pagination_and_owner_rows`
fakes a 10000+1 two-page result. Try: `rowCount` absent/string/0,
exact-multiple-of-page-size results, offset drift duplications,
quota errors mid-pagination leaving a partial "successful" import.

### 7. Previous findings 7–9: Analyst restore, late answers, honest failures

Claims. `openConversation` (`AnalystPage.tsx`) restores the
conversation scope into FilterContext (`clearFilters` + per-key
`setFilter`). `send()` captures `sentIn` and drops the append when
`data.conversation_id !== activeIdRef.current` (list refresh only).
Deterministic fallbacks render `analyst.narrativeFallback` with the
server `narrative_detail`. Try: scope keys that are not
`FilterValues` members; multi-value scope entries (only first is
applied — lossy?); new-conversation sends (`sentIn === null`)
raced with opening an old one; narrative detail containing
provider error text that should not reach the UI; mock-mode detail
noise on every answer.

### 8. Previous findings 10–11: notification triggers + dedup-before-send

Claims. Real triggers call `notifications.notify_employee`:
report generation (`product.py` report route,
`report_generated`), dataset import (`campaign_import`, dedup
`import:<import_id>`), video analysis success
(`worker_handlers.run_video_analysis`, `analysis_ready`, dedup
`analysis:<job_id>`). `enqueue()` inserts the `queued` outbox row
first — the unique dedup index is the lock — then sends and
updates status. `test_notification_dedup_claimed_before_send`
pre-claims a slot and asserts no send. Try: triggers firing for
the wrong employee (worker owner vs requester), notification
failure failing the underlying job/report/import, dedup keys that
collide across employees or never collide when they should
(report_generated has none — intentional?), `queued` rows stranded
forever if the process dies between claim and update, opt-out
checked after the claim (visible `skipped` rows — intended?).

### 9. Previous finding 12: 90-day default covers 90 dates

Claim. `DashboardPage.tsx` fetches `useDaily(90, ...)`. Try: other
consumers still assuming 30 points (charts, boot logic, tests);
datasets with sparse dates; the boot window vs `applyPresetDays`
consistency.

### 10. Previous "missing" list

Claims.
- Video roster aligns with AI Providers: `_managed_vision_entry`
  leads `eligible_vision_roster(conn)` when the admin selection is
  frame-eligible, `LiveVision(secret_for=...)` resolves the managed
  secret via `dispatcher._resolve`, `_gemini_live_models()` (5-min
  cache) filters Gemini ids against `gemini_available_models()`,
  and `_vision_model()` reports `LiveVision.last_winner`.
- GA4 has a UI: `Ga4Tools` (`IntegrationCards.tsx`) — property
  select, dates, import, own-rows table. Scheduled GA4 sync is
  still NOT implemented (`sync.py` sources unchanged) — check no
  copy claims it is.
- Template update exists in the UI (`ReportsPage.tsx`
  `updateTemplate`, PUT with current config).
- Default Campaign View is consumed on Campaigns mount
  (`Active Only` → status filter, `By Platform` → more filters);
  appearance (theme/accent/density) applies at shell init
  (`AppShell.tsx` + `applyAccent` in `state/prefs.ts`).
  Privacy switches remain persisted preferences with no telemetry
  consumer — check the copy does not claim enforcement.
- Expired-session handling: standalone Workbook download uses
  `apiBlob`; avatar upload uses new `apiForm` (`client.ts`), both
  re-gating like `api()`. Search for remaining raw `fetch(`.
- Tests added for: seeded export history, GA4 pagination, GA4 rows
  endpoint scoping smoke, dedup-before-send, Spanish acceptance.

Try to break the video claims hardest: managed entry when the
selection's provider differs from legacy keys; `_resolve` raising
the not-configured sentinel inside `_managed_secret` (swallowed?);
discovery cache poisoning across keys/accounts; discovery network
failure latencies on every readiness poll; `last_winner` races
across concurrent batches; test doubles still forcing the
`_roster()` TypeError fallback to hide a real signature bug.

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pytest tests/test_gap_completion.py`: 15 passed (11 previous +
  4 new: seeded export history, GA4 pagination, dedup-before-send,
  Spanish acceptance).
- `pytest` on video/analyst/provider suites
  (`test_video_analysis.py`, `test_analyst_api.py`,
  `test_provider_status.py`, `test_live_providers.py`,
  `test_admin_providers.py`, `test_gap_completion.py`): passed
  (64 + 73 across two runs). The full 899-test run from the
  previous push was NOT repeated for this fix push — flag any area
  below whose risk makes that omission matter.
- `pnpm test`: 328 passed (38 files). `pnpm exec tsc --noEmit`:
  clean. `pnpm build`: passed. Ruff on changed Python: clean.
- Two regressions were caught and fixed during this push:
  no-arg `eligible_vision_roster` test doubles (`_roster` fallback)
  and `CampaignsPage` requiring AuthProvider (`useOptionalAuth`).
  Judge whether either accommodation hides a real defect.

## Blocked / unverified — do not report as source defects

- **Live Gemini run: BLOCKED.** `CREATIVE_INTEL_KEY_GEMINI` empty
  in env, login shell, launchctl, and macOS Keychain on the
  implementer's machine. No live model call, job id, browser
  click-through, or screenshot exists for either push.
- **Email delivery: BLOCKED** on `CREATIVE_INTEL_SMTP_HOST`,
  `_PORT`, `_USER`, `_PASSWORD`, `_FROM`. Triggers + outbox are
  code-complete; real delivery unverified. Do not send test mail.
- **Meta/TikTok/GA4 live OAuth/imports: BLOCKED** on the console
  credentials in `docs/RENDER.md`.
- **Production:** Render auto-deploys `main`; neither push's
  deployment was verified.

## Known still-open items (already admitted — only re-report if worse)

- Scheduled GA4 sync not implemented (manual import only).
- Compare page hardcoded English copy (pre-existing).
- Deterministic Analyst tables render en/pl only; Spanish is the
  provider narrative.
- Admin "teams" are browser-local; no per-employee team backend.
- Privacy toggles (data usage / share analytics / retention) are
  persisted preferences; there is no telemetry or server retention
  engine behind them.
- Five pre-existing backend failures on the original base,
  unchanged here: `test_ci_app.py::test_no_licensing_concepts`
  (walker enters `.venv`), three `test_ci_migrations.py` tests,
  `test_deploy.py::test_deploy_migration_command_from_repo_root`
  (expects head `0012`, tree has `0013`).
