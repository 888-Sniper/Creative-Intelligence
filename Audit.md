# Creative Intelligence — audit of the third-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `f86be61b62fab6a3a32e4d81dcb60b481fb97d9e`
  (code `6e7c003` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `6a610fb9265be3768473047def1cfb435a1d2c2d`
  (`Fix the third-round audit defects (migration recovery, scope and merge races)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `6a610fb` on this push touch only this `Audit.md`;
  review the code at `6a610fb` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat f86be61b62fab6a3a32e4d81dcb60b481fb97d9e 6a610fb9265be3768473047def1cfb435a1d2c2d
git diff f86be61b62fab6a3a32e4d81dcb60b481fb97d9e 6a610fb9265be3768473047def1cfb435a1d2c2d
git rev-parse 6a610fb9265be3768473047def1cfb435a1d2c2d    # must resolve
git diff --stat 6a610fb9265be3768473047def1cfb435a1d2c2d HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 9 files, 262 insertions, 54
deletions. If yours disagrees, stop and say so. A behind local
checkout, or no local `main` branch, is not a reason to stop.
Read files at the reviewed commit (`git show 6a610fb:PATH` if
needed); if a later edit moves a line, follow the symbol, not the
stale number. Earlier audits live in git history
(`git show fbb9a65:Audit.md`, `git show 5336e41:Audit.md`,
`git show f86be61:Audit.md`). This push answers the third review
of `6e7c003` (defects 1–7 + consumer-reactivity note); re-verify
those first, then hunt wider. Earlier rounds' fixed items should
be regression-checked, not re-reported unless broken again.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `6a610fb`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `6a610fb`,
  and the evidence. No evidence, no defect — use "Unverified".
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at the
  end.
- For each of the third review's 7 defects, state explicitly:
  fixed / partly fixed / still open, with line evidence.
- Check the tests as skeptically as the code.
- Secrets: never print a credential value (file/line only, redacted).

## Required output format

1. `Third-review 7 defects` — one verdict line each with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per section below.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

### 1. GA4 migration is transactional and recoverable (was P1)

Claim. `_migrate_ga4_owner_unique` (`schema.py`) first recovers a
stranded `ga4_rows_new` (rename if `ga4_rows` is gone; stash+merge
if both exist), then rebuilds inside one `BEGIN IMMEDIATE`
transaction (copy live + stash, drop, rename, index, COMMIT;
ROLLBACK on error). Try: crash points before BEGIN, mid-transaction,
and between COMMIT and `migrate()`; connections already inside a
transaction when `init_db` runs; `ga4_rows_stash` left by a crash
inside the transaction (does rollback really restore the rename?);
foreign keys/indexes lost; duplicate rows across live+stash with
different metrics (which copy wins, is that honest?).

### 2. AppShell cannot undo a newer edit; consumers react

Claim. AppShell snapshots local prefs JSON at fetch start and drops
the server response if local prefs changed meanwhile; on merge it
fires `ci-prefs-updated` (`state/prefs.ts` `notifyPrefsUpdated`).
`LocalePrefsSync` re-applies language/timezone on that event (tick
state + appliedFor reset). Campaigns re-applies Default Campaign
View on the event until the user touches the status select
(`statusTouched`). Try: edit-in-flight via theme toggle (does it
write prefs?), Settings and AppShell fetches racing each other,
event loops (merge → savePrefs → event → re-apply), campaign view
re-applying over a status set by saved-view/deep-link rather than
the select.

### 3. Analyst scope coherence and Clear-All race

Claims. Drift detection compares the ENTIRE filters object to the
exact snapshot the restore produced (`restoredFiltersRef`), so
adding any new filter ends the override. Downloads use
`restoredScope ?? scopeBody(scope)` like chat. `send()` captures
`convGenRef` and drops late answers after Clear All/selection
bumps. Try: key-order fragility of the JSON snapshot vs
`EMPTY_FILTERS` order; React batching (clear+sets landing in
separate renders killing the override instantly); date-range
preset buttons that set filters through other paths; workbook
download scope (separate path — still single-value?); Clear during
`loadConversations` await.

### 4. Discovery cache identity; managed STT precedence

Claims. Cache key hashes the actual secret + base URL (managed) or
the legacy secret — fingerprints only, secrets never stored.
Managed Gemini replaces a legacy `GeminiStt`/`_Unavailable` STT;
dedicated `LiveStt` (Deepgram/Groq) is untouched. Try: two managed
accounts alternating within 5 minutes; secret rotation to an
invalid key (discovery returns None → offline roster — honest?);
`live_secret` Keychain access cost/failure inside `_gemini_live_models`
on every readiness poll; providers whose bundle STT is `LiveStt`
wrapping a Gemini entry (does the precedence rule miss it?).

### 5. GA4 rows generation guard

Claim. `loadRows` captures a generation + selected property and
drops stale responses (`IntegrationCards.tsx`). Try: initial
all-properties load racing the first selection; import-triggered
reload racing a selector change; unmount during flight.

### 6. Tests

Claims. New in `tests/test_gap_completion.py` (20 total):
`test_ga4_migration_recovers_stranded_rows` (pre-fix table +
stranded `_new`, both rows survive, idempotent reopen) and
`test_notification_forced_overlap_sends_once` (slow sender holds
delivery open while the second thread arrives). Judge whether the
overlap test would fail against claim-after-send, and whether the
migration test covers the crash-after-DROP state (only `_new`
exists) — it seeds both tables; check the rename-only branch by
reading. Name still-missing UI race tests specifically.

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pytest tests/test_gap_completion.py`: 20 passed.
- `pytest tests/test_video_analysis.py tests/test_analyst_api.py`:
  82 passed. Ruff on changed Python: clean.
- `pnpm test`: 328 passed (one earlier run in this session failed
  with no named test, then passed twice consecutively — treat as
  an unexamined flake; hunt for timing-sensitive tests touched
  here). `pnpm exec tsc --noEmit`: clean. `pnpm build`: passed.
- Full 899-test backend run still not repeated since the first
  push. Gemini key re-probed: still absent everywhere checked.

## Blocked / unverified — do not report as source defects

- **Live Gemini run: BLOCKED.** `CREATIVE_INTEL_KEY_GEMINI` empty
  in env, login shell, launchctl, and macOS Keychain. No live
  model call, job id, browser click-through, FPS measurement, or
  screenshot exists for any push. Unblock steps as in prior audits.
- **Email delivery: BLOCKED** on `CREATIVE_INTEL_SMTP_*`.
- **Meta/TikTok/GA4 live OAuth/imports: BLOCKED** on console
  credentials in `docs/RENDER.md`.
- **Production:** Render auto-deploys `main`; unverified.

## Known still-open items (already admitted — only re-report if worse)

- Scheduled GA4 sync not implemented (manual import only).
- Privacy toggles are persisted preferences; no telemetry or
  server retention engine exists behind them.
- Admin "teams" are browser-local; no per-employee team backend.
- Deterministic Analyst tables render en/pl only; Spanish is the
  provider narrative. Compare page English copy (pre-existing).
- Five pre-existing backend failures on the original base:
  `test_no_licensing_concepts` (.venv walker), three
  `test_ci_migrations.py` tests,
  `test_deploy_migration_command_from_repo_root` (`0012` vs `0013`).
