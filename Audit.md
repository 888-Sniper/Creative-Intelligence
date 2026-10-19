# Creative Intelligence — audit of the seventeenth-round fix push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `9c7f051b7e3ac03110290c100ef5de1b09457bcc`
  (code `35179f5` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `e25d38ad0764fe8fdb61bac4548e2ee8a00a8a27`
  (`Fix the seventeenth-round audit defect (stale account callbacks)`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `e25d38a` on this push touch only this `Audit.md`;
  review the code at `e25d38a` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat 9c7f051b7e3ac03110290c100ef5de1b09457bcc e25d38ad0764fe8fdb61bac4548e2ee8a00a8a27
git diff 9c7f051b7e3ac03110290c100ef5de1b09457bcc e25d38ad0764fe8fdb61bac4548e2ee8a00a8a27
git rev-parse e25d38ad0764fe8fdb61bac4548e2ee8a00a8a27    # must resolve
git diff --stat e25d38ad0764fe8fdb61bac4548e2ee8a00a8a27 HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 2 files, 56 insertions, 5
deletions, frontend only. If yours disagrees, stop and say so. A
behind local checkout, or no local `main` branch, is not a
reason to stop. Read files at the reviewed commit
(`git show e25d38a:PATH` if needed); if a later edit moves a
line, follow the symbol, not the stale number. Earlier audits
live in git history (most recently `git show 9c7f051:Audit.md`,
parent `0cb6082`, code `35179f5`). This push answers the
seventeenth review of `35179f5` (one P2 defect); re-verify it
first, then hunt wider. Earlier rounds' fixed items should be
regression-checked, not re-reported unless broken.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `e25d38a`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `e25d38a`,
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

1. `Seventeenth-review defect` — verdict with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found` — one line per section below.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

### 1. Stale async callbacks cannot repaint a newer account/session

Claim. Every async preference applier in Settings is guarded by
mount + account currency (`mountedRef`/`accountRef`/
`stillCurrent`, plus a cleanup `live` flag on the GET-merge
effect): both GET-merge callbacks, commit settle handlers, and
the mount-recovery settle (`SettingsPage.tsx`). Outcome
recording itself stays unconditional (module state is
per-account by construction). Try: the reviewer's sequence
in-place (identity swap WITHOUT unmount — effect deps are
`[employee?.id]`; trace `me.employee.id`-only changes and the
identity-adopt branch's synchronous `setPrefOwner` path);
AppShell's equivalent callback (pre-existing `live` flag —
verify it also covers the account dimension, since its effect
deps are `[employeeId]`); Analyst/AppShell or any other caller
of `applyLive`-equivalents (theme/language/timezone setters)
with unguarded async paths; the unmount name-flush effect
(module flush on unmount — account-stamped, but trace it);
`accountRef` assigned during render vs callbacks firing
between renders of an identity swap.

### 2. Tests

Claim. New test: account A's GET held → unmount → account B
loads (Comfortable/Teal) → A's response released → B's density
control, body density dataset, and accent CSS variable are
unchanged. Admitted limits: the test remounts a fresh tree
(new providers) rather than swapping identity in place, so
the shared-locale-provider aspect is asserted only through
document-level side effects (`applyAccent`); judge whether
the in-place swap is equivalently guarded from source. Still
missing (admitted): legacy-GET remount at page level;
fresh-module new-tab tests; Analyst→Campaigns navigation;
three-tab double-409.

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pnpm test`: 359 passed. `pnpm exec tsc --noEmit`: clean.
  `pnpm build`: passed.
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

- No durable recovery across a full page reload: pending edits
  and outcomes are memory-only (noted by the sixteenth review
  as a separate limitation, not a classified defect).
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
