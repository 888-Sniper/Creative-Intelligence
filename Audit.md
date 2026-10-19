# Creative Intelligence — audit of the eleventh-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `b97423545108a2354dd78fdacd121bee3db848b0`
  (code `7c7412b` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `6a9829c1edda9be3fda22b4af0195f7b742a2aa1`
  (`Fix the eleventh-round audit defects (name draft, stale GET merges)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `6a9829c` on this push touch only this `Audit.md`;
  review the code at `6a9829c` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat b97423545108a2354dd78fdacd121bee3db848b0 6a9829c1edda9be3fda22b4af0195f7b742a2aa1
git diff b97423545108a2354dd78fdacd121bee3db848b0 6a9829c1edda9be3fda22b4af0195f7b742a2aa1
git rev-parse 6a9829c1edda9be3fda22b4af0195f7b742a2aa1    # must resolve
git diff --stat 6a9829c1edda9be3fda22b4af0195f7b742a2aa1 HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 5 files, 183 insertions, 25
deletions, frontend only. If yours disagrees, stop and say so. A
behind local checkout, or no local `main` branch, is not a
reason to stop. Read files at the reviewed commit
(`git show 6a9829c:PATH` if needed); if a later edit moves a
line, follow the symbol, not the stale number. Earlier audits
live in git history (most recently `git show b974235:Audit.md`,
parent `3a371b0`, code `7c7412b`). This push answers the
eleventh review of `7c7412b` (defects 1–2); re-verify those
first, then hunt wider. Earlier rounds' fixed items should be
regression-checked, not re-reported unless broken.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `6a9829c`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `6a9829c`,
  and the evidence. No evidence, no defect — use "Unverified".
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at
  the end.
- For each of the eleventh review's 2 defects, state explicitly:
  fixed / partly fixed / still open, with line evidence.
- Check the tests as skeptically as the code.
- Secrets: never print a credential value (file/line only, redacted).

## Required output format

1. `Eleventh-review 2 defects` — one verdict line each with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per section below.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

### 1. A typed workspace name survives unrelated control changes

Claim. The debounce timer no longer keys on the shared commit
revision (only on the draft itself), and `commit` syncs the
name draft only when that commit changes the workspace
(`SettingsPage.tsx` `onWorkspaceInput`/`commit`). Try: typing,
then Reset Defaults inside the window (reset rewrites the
draft — does the timer stay dead?); typing, clearing the
field to empty, then an unrelated commit (the required-name
error path vs the timer's draft guard); two rapid unrelated
commits both landing before the timer (its commit builds from
then-current prefs — verify no key is reverted); the header
theme toggle commit path (`liveThemeMode` effect) as the
"unrelated commit"; "saved" appearing for the unrelated commit
while the name is still debounce-pending (judge whether that
claim is honest for autosave semantics).

### 2. Reopening Settings mid-save cannot undo the saved value

Claim. Two guards at every GET merge site (Settings ×2,
AppShell): `isStaleServerPrefs` drops responses older than the
newest confirmed revision (in-memory snapshot or persisted
note; `noteServerPrefsSnapshot` itself never moves backward),
and `withoutPendingPrefs` strips keys whose writes are still
in flight — pending state is module-level, so it covers saves
started by a previous mount. Try: the reviewer's exact order
and the immediate-GET order; a full page RELOAD mid-save
(module state dies — which guard still applies via the
persisted revision note, and what is honestly lost?); a GET
whose `_rev` is absent/non-integer (legacy rows) against a
high baseline; account switch where the OTHER account's
persisted revision is higher (baselines are per-employee —
verify every call passes the right id); AppShell's merge
writing local storage for keys Settings has pending.

### 3. Tests

Claims. New: type-name-then-change-density inside the debounce
(both edits reach the server, input never reverts); remount
during a held PUT (reopened page's GET cannot undo Compact,
before and after release); unit tests for staleness, snapshot
monotonicity, pending-exclusion. Test-isolation change to
judge: server-prefs tests now run under UNIQUE employee ids
(`mockFetch({employeeId})`) because module snapshot/pending
state is keyed per account and fixtures restart server
revisions per test — check no test silently relies on shared
`e1` state anymore, and whether any remaining `e1` test can
still be polluted by an earlier `e1` test's snapshot (the
appearance test failure mode from this round's development).
Still missing (admitted): true fresh-module "new tab" tests
(vitest isolates files, not tests within a file); page-level
Analyst→Campaigns navigation; three-tab double-409.

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pnpm test`: 350 passed. `pnpm exec tsc --noEmit`: clean.
  `pnpm build`: passed. (During development, six Settings
  tests failed from cross-test snapshot pollution under the
  new staleness guard; fixed by per-test employee isolation
  above, not by weakening assertions.)
- Backend untouched this round (full run from round eight on
  identical backend code: 911 passed / 5 named failures).
- Gemini key re-probed (env + Keychain): still absent; user
  previously chose "skip live run". Live workflow unverified.

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
