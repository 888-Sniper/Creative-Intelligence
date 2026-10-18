# Creative Intelligence — audit of the fourth-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `12a816e2feab32980dafd6048e9b559430151801`
  (code `6a610fb` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `3d9e4d8570bb95eb11bf213b4ffb722d4bbed500`
  (`Fix the fourth-round audit defects (selection, revision and boot races)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `3d9e4d8` on this push touch only this `Audit.md`;
  review the code at `3d9e4d8` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat 12a816e2feab32980dafd6048e9b559430151801 3d9e4d8570bb95eb11bf213b4ffb722d4bbed500
git diff 12a816e2feab32980dafd6048e9b559430151801 3d9e4d8570bb95eb11bf213b4ffb722d4bbed500
git rev-parse 3d9e4d8570bb95eb11bf213b4ffb722d4bbed500    # must resolve
git diff --stat 3d9e4d8570bb95eb11bf213b4ffb722d4bbed500 HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 6 files, 92 insertions, 37
deletions. If yours disagrees, stop and say so. A behind local
checkout, or no local `main` branch, is not a reason to stop.
Read files at the reviewed commit (`git show 3d9e4d8:PATH` if
needed); if a later edit moves a line, follow the symbol, not the
stale number. Earlier audits live in git history (most recently
`git show 12a816e:Audit.md`, parent `f86be61`, code `6a610fb`).
This push answers the fourth review of `6a610fb` (defects 1–4 plus
the test-synchronization note); re-verify those first, then hunt
wider. Earlier rounds' fixed items should be regression-checked,
not re-reported unless broken again.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `3d9e4d8`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `3d9e4d8`,
  and the evidence. No evidence, no defect — use "Unverified".
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at the
  end.
- For each of the fourth review's 4 defects, state explicitly:
  fixed / partly fixed / still open, with line evidence.
- Check the tests as skeptically as the code.
- Secrets: never print a credential value (file/line only, redacted).

## Required output format

1. `Fourth-review 4 defects` — one verdict line each with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per section below.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

### 1. GA4 import completion cannot overwrite the selected property

Claim. `selectedRef` mirrors the selector via an effect on
`propertyId` and is never written by `loadRows`;
`loadRows(pid)` drops responses when `pid` is non-empty and differs
from the current selection; import completion reloads
`selectedRef.current`, not the imported property
(`IntegrationCards.tsx`, `Ga4Tools`). Try: import A → select B →
A completes (rows must stay B's or empty, never A's); initial
all-properties load (`pid=""`) landing after a selection; rapid
A→B→A switching; import for the still-selected property (must
refresh); unmount mid-flight.

### 2. Explicit Campaigns status survives remounts

Claim. `statusTouchedAcrossMounts` is module-scoped in
`CampaignsPage.tsx`; the status select sets it (and the ref);
`applyCampaignView` and the prefs-updated re-apply both bail when
set. Try: Completed → navigate away → return (must stay
Completed); status set via saved view / deep link / shared-filter
change on another page (module flag unset — can the default still
override?); account switch in the same SPA session (flag leaks
across employees?); full page reload (module state resets — is
re-applying the default then correct?).

### 3. AppShell merge uses an edit revision, not values

Claim. `savePrefs` bumps module-scoped `prefsRevision`
(`state/prefs.ts`); AppShell captures `currentPrefsRevision()` at
fetch start and drops the response on any bump — including
edit-then-revert-to-original. Try: edits that do NOT go through
`savePrefs` (theme toggle via `useTheme`, language switcher,
direct localStorage writers — grep `ci-settings-prefs`); AppShell's
own merge-save bumping the revision and starving a second legit
merge; Settings' separate `revRef` vs this counter disagreeing;
multi-tab edits (revision is per-tab — state the limit honestly).

### 4. Dashboard range follows late-arriving server prefs

Claim. Boot records `bootedWindow`; on `ci-prefs-updated` the
window is recomputed only while visible dates still equal the
booted ones (`DashboardPage.tsx`, `applyRangeBoot`). Try: daily
data arriving after the prefs event (boot never applied — does
the late path still fire?); All Time (`days === null`) arriving
late (booted dates must clear or stay? check what actually
happens); user picks exactly the booted dates manually, then prefs
land (override — acceptable?); date preset buttons vs booted
window equality.

### 5. Notification race test is synchronized, not timed

Claim. `test_notification_forced_overlap_sends_once` blocks the
sender on events: thread two starts only after thread one is
provably inside `sender`, completes as duplicate, then releases
thread one; asserts exactly one send and one duplicate outcome.
Judge whether it would fail under claim-after-send, and whether
SQLite busy-timeout behavior could make it pass for the wrong
reason on a slow machine.

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pytest tests/test_gap_completion.py`: 20 passed (unchanged
  count; the overlap test was rewritten in place).
- `pnpm test`: 328 passed. `pnpm exec tsc --noEmit`: clean.
  `pnpm build`: passed.
- No backend code changed in this push except tests; the full
  899-test backend run remains unrepeated since the first push.
- Gemini key re-probed before this push: still absent (env,
  login shell, launchctl, Keychain). The user previously chose
  "skip live run" over credential handoff; live verification
  remains blocked, not forgotten.

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
