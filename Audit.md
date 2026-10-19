# Creative Intelligence — audit of the fourteenth-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `d97fd3b24bb9b8cec6e6f63c684e10b7df16e55c`
  (code `6f779bf` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `01102eabcb584e04e284405705502deb776204b2`
  (`Fix the fourteenth-round audit defect (settle outcomes vs keystrokes)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `01102ea` on this push touch only this `Audit.md`;
  review the code at `01102ea` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat d97fd3b24bb9b8cec6e6f63c684e10b7df16e55c 01102eabcb584e04e284405705502deb776204b2
git diff d97fd3b24bb9b8cec6e6f63c684e10b7df16e55c 01102eabcb584e04e284405705502deb776204b2
git rev-parse 01102eabcb584e04e284405705502deb776204b2    # must resolve
git diff --stat 01102eabcb584e04e284405705502deb776204b2 HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 2 files, 69 insertions, 3
deletions, frontend only. If yours disagrees, stop and say so. A
behind local checkout, or no local `main` branch, is not a
reason to stop. Read files at the reviewed commit
(`git show 01102ea:PATH` if needed); if a later edit moves a
line, follow the symbol, not the stale number. Earlier audits
live in git history (most recently `git show d97fd3b:Audit.md`,
parent `c25fa1f`, code `6f779bf`). This push answers the
fourteenth review of `6f779bf` (one P2 defect); re-verify it
first, then hunt wider. Earlier rounds' fixed items should be
regression-checked, not re-reported unless broken.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `01102ea`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `01102ea`,
  and the evidence. No evidence, no defect — use "Unverified".
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at
  the end.
- For the P2 defect, state explicitly: fixed / partly fixed /
  still open, with line evidence.
- Check the tests as skeptically as the code.
- Secrets: never print a credential value (file/line only, redacted).

## Required output format

1. `Fourteenth-review defect` — verdict with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per section below.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

### 1. Keystrokes can no longer suppress a save outcome

Claim. Settle handlers record `saveFailedRef` unconditionally
(settles arrive in flush order), and their UI updates are gated
by a COMMIT-only generation (`commitGenRef`) instead of the
shared revision that keystrokes also bump (`SettingsPage.tsx`).
`revRef` still guards GET merges (keystrokes count as newer
there). Try: the reviewer's sequence in both outcomes
(failure recorded → validation restores error + Retry; success
after validation settles to saved); a stale settle recording
over a NEWER synchronous local-storage failure (commit2
throws locally while commit1's flush later succeeds — trace
what `saveFailedRef`, the visible state, and a subsequent
validation each do); reconcile now running on settles that a
keystroke intervened on (typing-guard inside
`reconcileLocal`); the theme catch-up effect as the
"intervening commit"; rapid double-commit where the first
settle's UI skip must still hold.

### 2. Tests

Claims. Two new tests drive the reviewer's exact ordering
(density PUT held → clear name → release): failure keeps
Retry + error after validation; success released after
validation settles to saved with the name error still shown.
Judge the held-PUT timing (`advanceTimersByTimeAsync(0)` to
reach the PUT before clearing the name). Flake disclosure:
during this round's development the Settings file showed two
transient failures in ONE intermediate run (`storage throws`,
`blank-name validation…`), then 1, then 0; both pass in
isolation and in the final full runs, and the storage test has
a documented flake history since round seven. Decide whether
you can find a timing dependency by reading, and say so
plainly if you cannot. Still missing (admitted): legacy-GET
remount at page level; fresh-module new-tab tests;
Analyst→Campaigns navigation; three-tab double-409.

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pnpm test`: 355 passed (final run; see flake disclosure
  above). `pnpm exec tsc --noEmit`: clean. `pnpm build`: passed.
- Backend untouched this round (round-eight full run on
  near-identical backend: 911 passed / 5 named failures).
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
