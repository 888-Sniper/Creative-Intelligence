# Creative Intelligence — audit of the seventh-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `55b4c9671f5a5d2ecdb3865410d95ea8e1940868`
  (code `b33cc7a` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `06a8fa71196a244e36e8ca124e9877255e70785f`
  (`Fix the seventh-round audit defects (account-bound preference writes)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `06a8fa7` on this push touch only this `Audit.md`;
  review the code at `06a8fa7` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat 55b4c9671f5a5d2ecdb3865410d95ea8e1940868 06a8fa71196a244e36e8ca124e9877255e70785f
git diff 55b4c9671f5a5d2ecdb3865410d95ea8e1940868 06a8fa71196a244e36e8ca124e9877255e70785f
git rev-parse 06a8fa71196a244e36e8ca124e9877255e70785f    # must resolve
git diff --stat 06a8fa71196a244e36e8ca124e9877255e70785f HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 8 files, 117 insertions, 37
deletions. If yours disagrees, stop and say so. A behind local
checkout, or no local `main` branch, is not a reason to stop.
Read files at the reviewed commit (`git show 06a8fa7:PATH` if
needed); if a later edit moves a line, follow the symbol, not the
stale number. Earlier audits live in git history (most recently
`git show 55b4c96:Audit.md`, parent `422f8db`, code `b33cc7a`).
This push answers the seventh review of `b33cc7a` (defects 1–4);
re-verify those first, then hunt wider. Earlier rounds' fixed
items should be regression-checked, not re-reported unless broken.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `06a8fa7`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `06a8fa7`,
  and the evidence. No evidence, no defect — use "Unverified".
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at the
  end.
- For each of the seventh review's 4 defects, state explicitly:
  fixed / partly fixed / still open, with line evidence.
- Check the tests as skeptically as the code.
- Secrets: never print a credential value (file/line only, redacted).

## Required output format

1. `Seventh-review 4 defects` — one verdict line each with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per section below.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

### 1. Queued preference writes cannot land on the wrong account (was P1)

Claim. `putServerPrefs(next, employeeId)` stamps the originating
employee at enqueue time; `PUT /api/preferences` rejects (409) any
body whose `employee_id` differs from the authenticated employee
(`product.py`, `preferences_put`). The serialized queue therefore
drops cross-account writes instead of re-attributing them. Try:
writes with no `employee_id` (older clients/other callers — still
accepted for the signed-in account; is that safe?); the unmount
flush path's owner id; account switch implemented as session swap
vs full reload (does the queue survive either?); 409 surfacing as
a Settings save error on the NEW account's screen.

### 2. Server-issued preference version survives reloads and tabs

Claim. `save_prefs(..., base_revision=…)` (`notifications.py`):
server owns `_rev`, increments on every accepted save, drops
writes whose base is older. Clients persist the last seen server
version per account in localStorage (`serverPrefsRevision` /
`noteServerPrefsRevision`, updated on every GET merge and PUT
response) and echo it as base. Unknown base (`None`) accepts.
Try: two tabs interleaving (tab2's stale base rejected — does its
UI recover or loop?); first-ever save before any GET (base null
accepts — can that resurrect stale data?); `_rev` leaking into
client merges or exports; AppShell merge-save bumping local state
without noting the new server rev from its GET (order of
note-vs-merge); Settings' separate in-memory `revRef` guards vs
the server version disagreeing.

### 3. Dashboard respects dates chosen before entry

Claim. Boot now marks pre-existing shared dates user-owned
(`userDateTouched`, `bootedMode = null`) before any basis/prefs
recompute can run (`DashboardPage.tsx`). Try: dates arriving via
saved-view apply AFTER Dashboard mounts; Analyst restore setting
dates then navigating to Dashboard; basis effect deps
(`applyRangeBoot` identity) re-firing recomputes; the
`rangeBooted` gate vs `userDateTouched` ordering on first render.

### 4. Campaign Reset records the explicit All choice

Claim. `resetAll` calls `markCampaignStatusTouched(id, "")`
before `clearFilters()` (`CampaignsPage.tsx`), so remounts restore
touched-with-no-value (All) instead of the pre-reset status. Try:
reset with no status ever touched; reset as account A then view
as B; legacy `"1"` session entries; Reset buttons on other pages
that clear shared filters without marking (Analyst Clear,
Dashboard Reset) — same resurrection via Campaigns remount?

### 5. Tests

Claims. Backend: rewritten `test_stale_preference_revision_cannot_overwrite`
(server increments, stale base loses, GET-then-save reload
lifecycle succeeds) and new
`test_preferences_write_for_another_account_is_rejected` (409 +
own prefs untouched). Frontend: 330 passed; one Settings storage
test flaked once in the full suite this session, then passed
isolated and in the rerun — hunt for the timing dependency if you
can find it by reading. Still missing (admitted): page-level UI
tests for queued cross-account saves, Dashboard entry with
pre-set dates, and Reset-then-navigate. Name exact tests you
would require.

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pytest tests/test_gap_completion.py`: 22 passed.
- `pnpm test`: 330 passed (after one flaky Settings failure that
  passed isolated and on rerun). `pnpm exec tsc --noEmit`: clean
  (one unused-import fix). `pnpm build`: passed.
- Full 899-test backend run remains unrepeated since round one.
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
