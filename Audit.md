# Creative Intelligence — audit of the fifth-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `f41c7598646c393e0a2c4aab6e0aa51694af1559`
  (code `3d9e4d8` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `965158f28bc1cd5e85e77b6e85fb3dddb1878975`
  (`Fix the fifth-round audit defects (dashboard basis, per-account touch, reset)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `965158f` on this push touch only this `Audit.md`;
  review the code at `965158f` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat f41c7598646c393e0a2c4aab6e0aa51694af1559 965158f28bc1cd5e85e77b6e85fb3dddb1878975
git diff f41c7598646c393e0a2c4aab6e0aa51694af1559 965158f28bc1cd5e85e77b6e85fb3dddb1878975
git rev-parse 965158f28bc1cd5e85e77b6e85fb3dddb1878975    # must resolve
git diff --stat 965158f28bc1cd5e85e77b6e85fb3dddb1878975 HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 7 files, 119 insertions, 29
deletions (includes new `src/state/prefs.test.ts`). If yours
disagrees, stop and say so. A behind local checkout, or no local
`main` branch, is not a reason to stop. Read files at the reviewed
commit (`git show 965158f:PATH` if needed); if a later edit moves
a line, follow the symbol, not the stale number. Earlier audits
live in git history (most recently `git show f41c759:Audit.md`,
parent `12a816e`, code `6a610fb`). This push answers the fifth
review of `3d9e4d8` (defects 1–5); re-verify those first, then
hunt wider. Earlier rounds' fixed items should be
regression-checked, not re-reported unless broken again.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `965158f`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `965158f`,
  and the evidence. No evidence, no defect — use "Unverified".
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at the
  end.
- For each of the fifth review's 5 defects, state explicitly:
  fixed / partly fixed / still open, with line evidence.
- Check the tests as skeptically as the code.
- Secrets: never print a credential value (file/line only, redacted).

## Required output format

1. `Fifth-review 5 defects` — one verdict line each with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per section below.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

### 1. Dashboard range uses an unrestricted basis; late All Time clears

Claim. `DashboardPage.tsx` fetches `/api/kpis/daily?days=366`
UNSCOPED once into `basisDates`; `applyRangeBoot` slices that
basis (falling back to scoped `daily` only before the basis
arrives). A late All Time preference clears `date_from`/`date_to`
when a booted window is active, still guarded by "visible dates
equal booted dates" in the prefs-updated handler. Try: basis
request itself scoped by `scopedPath` sample-batch or server-side
defaults; 366-day cap vs datasets longer than a year; basis
 arriving after prefs (boot used scoped data — does anything
recompute?); All Time clearing dates the user set to exactly the
booted values by hand; `days=366` server validation limits.

### 2. Campaign status memory is per-account

Claim. `markCampaignStatusTouched`/`campaignStatusTouched`
(`state/prefs.ts`) key sessionStorage + an in-memory set by
employee id; Campaigns reads/writes only its own account's flag.
Try: anonymous/empty id collisions (`""` key shared across
signed-out states), account switch A→B→A in one tab, sessionStorage
unavailable (memory-only correctness), flag never expiring within
a tab session after the user resets prefs.

### 3. Analyst-restored status is protected

Claim. Restoring a conversation whose scope contains `status`
calls `markCampaignStatusTouched(accountKey)`
(`AnalystPage.tsx`), so Campaigns' default cannot overwrite it.
Try: `accountKey` empty in some mount paths (router passes
employee id — verify); restore with status present but empty;
restore in account A then Campaigns as account B; workbook/other
scope writers that still bypass the flag.

### 4. Reset Defaults persists like a normal edit

Claim. `resetDefaults` (`SettingsPage.tsx`) now calls `commit(next)`
— local save, revision bump, server PUT, live apply — instead of
savePrefs-only. Try: commit's failure path still showing
"Defaults Restored" toast on a failed PUT; name-draft debounce
racing the reset; theme/language applied twice or not at all
(applyLive coverage vs the removed explicit calls).

### 5. Dedup race test cannot pass spuriously; new prefs tests

Claims. The overlap test now asserts mid-flight state (second
worker completed as duplicate and `sent == []` BEFORE release)
and final state (exactly one `sent` outcome), and the sender
raises `RuntimeError` instead of asserting on timeout.
`src/state/prefs.test.ts` covers per-account touch scoping and
revision bumping on revert-to-original; `savePrefs` bumps the
revision even when storage fails. Try: outcomes ordering
assumptions, SQLite busy errors surfacing as test flakes, jsdom
storage absence masking a real browser-only failure in the new
frontend test. Frontend regression coverage for Dashboard late
prefs / reset-across-reload is still only partial — say exactly
what is missing if you agree.

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pytest tests/test_gap_completion.py`: 20 passed.
- `pnpm test`: 330 passed (328 previous + 2 new prefs tests).
  `pnpm exec tsc --noEmit`: clean. `pnpm build`: passed.
- No backend production code changed in this push (frontend +
  tests only). Full 899-test backend run remains unrepeated
  since the first push.
- Gemini key re-probed: still absent; user previously chose
  "skip live run". Live workflow remains unverified.

## Blocked / unverified — do not report as source defects

- **Live Gemini run: BLOCKED** on `CREATIVE_INTEL_KEY_GEMINI`
  (env or Keychain `creative-intel-gemini`) + live mode + an
  activated Gemini model. No live call, job id, browser session,
  FPS figure, or screenshot exists for any push.
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
