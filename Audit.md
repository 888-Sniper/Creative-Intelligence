# Creative Intelligence — audit of the branding/configured-state push

You are the second, independent reviewer. Your job is to find what is
still missing, wrong, or unsafe in the change below. Be adversarial:
assume every "should now be true" claim is unproven until you have
opened the cited code and tried to falsify it. Do not call the
product perfect, and do not repeat the implementer's summary as if
it were your own finding.

## Exact review target

- Repository: https://github.com/888-Sniper/Creative-Intelligence
- Parent on `main` (previous push):
  `b2566028c588e82fb0713d3843b16b0c63cfd147`
  (code `43bc721` + Audit.md-only commit; see git history)
- Under review in THIS push: code commit
  `e8f5639c5eb081920326aa9a073802cb5728b965`
  (`Remove workspace subtitle under logo; surface integration configured state`)
- After `git fetch`, the commit under review is `origin/main`.
  Commits after `e8f5639` on this push touch only this `Audit.md`;
  review the code at `e8f5639` regardless of branch head. Render
  auto-deploys from `main` (`render.yaml autoDeploy: true`), but
  deployment was not verified by the implementer — do not claim
  the live site shows this push without checking it, and do not
  treat Render state as a source defect.

Confirm the change with both ends named (never a one-revision diff;
a behind checkout invents changes that are not in this push):

```
git diff --stat b2566028c588e82fb0713d3843b16b0c63cfd147 e8f5639c5eb081920326aa9a073802cb5728b965
git diff b2566028c588e82fb0713d3843b16b0c63cfd147 e8f5639c5eb081920326aa9a073802cb5728b965
git rev-parse e8f5639c5eb081920326aa9a073802cb5728b965    # must resolve
git diff --stat e8f5639c5eb081920326aa9a073802cb5728b965 HEAD  # must touch Audit.md only
git rev-parse origin/main     # the commit under review, after fetch
git status                    # stop only if the worktree is dirty
```

Expected shape for the code diff: 8 files, 40 insertions, 17
deletions. If yours disagrees, stop and say so. A behind local
checkout, or no local `main` branch, is not a reason to stop.
Read files at the reviewed commit (`git show e8f5639:PATH` if
needed); if a later edit moves a line, follow the symbol, not the
stale number. Earlier audits live in git history (most recently
`git show b256602:Audit.md`, parent `a36bc3d`, code `43bc721`).
This push is an owner-requested change (not a review round):
(1) remove the workspace-name subtitle under the sidebar logo;
(2) surface each integration's deployment-configured state up
front. Check those first, then hunt wider.

## Hard rules for this audit

- Do NOT edit, commit, push, build, install, start the server, or
  activate a provider. Read-only inspection only.
- Report ONLY defects still true at `e8f5639`, each with: severity
  (P1/P2/P3), observed behavior, exact file and line at `e8f5639`,
  and the evidence. No evidence, no defect — use "Unverified".
- Do NOT treat any of these as a source defect: an unrun live
  Gemini call, an unrun live browser/Render click-through, a
  previously stored analysis, missing SMTP/Meta/TikTok/GA4 console
  credentials, or the five pre-existing test failures named at
  the end. In particular: Meta/TikTok/GA4 OAuth cannot complete
  anywhere until the `docs/RENDER.md` credentials and provider
  console apps exist — that is a configuration blocker, and this
  push's claim is only that the UI now SAYS so up front.
- Check the tests as skeptically as the code.
- Secrets: never print a credential value (file/line only, redacted).

## Required output format

1. `Claims check` — one verdict line per claim below with evidence.
2. `Defects still true` — numbered, severity-ordered.
3. `Requirements missing or only partly done`.
4. `Areas checked, no defect found`.
5. `Unverified` — what reading cannot settle, and what would.
6. One verdict sentence: ship / ship after fixes / do not ship.

## What the implementer claims — falsify each one

### 1. The workspace subtitle under the logo is gone, nothing else changed

Claim. Only the `<p className="side-workspace">` block was
removed (`AppShell.tsx`); the Workspace Name setting, its
persistence, and every other consumer are untouched. Check
for other renders of the workspace name (any layout, incl.
`AppLayout.tsx` if reachable), orphaned CSS (`.side-workspace`),
and layout spacing regressions (collapsed sidebar included).

### 2. Unconfigured integrations say so instead of offering a dead Connect

Claim. `GET /api/auth/integrations/{provider}/status` now also
returns `configured` (deployment credentials present), and the
row renders a disabled "Not Configured" button when
`configured === false` (`IntegrationCards.tsx`, new locale key
in en/es/pl). Try: connected-but-now-unconfigured deployments
(credentials removed after connect — Disconnect still offered?
`forget` behavior without settings); `configured()` per
provider vs the exact env/secret inputs `start` requires
(any input checked in one place but not the other, e.g.
secret-store vs env fallbacks); status responses from an older
backend during rolling deploy (missing field ⇒ treated as
configured — deliberate; judge it); GA4 sharing the Google
client with Drive (configured logic overlap).

### 3. Tests

Claims. Backend status assertions updated to the new shape and
the unconfigured fixture now asserts `configured: False` for all
three providers. The Settings test mock now models Meta as
unconfigured: it asserts a disabled "Meta Ads Not Configured"
button and no Connect button, TikTok/GA4 unchanged. Judge
whether changing the exact-shape backend assertions hides any
contract break for other status consumers (grep them).

## Evidence (implementer's machine; check plausibility, do not re-run)

- `pnpm test`: 361 passed. `pnpm exec tsc --noEmit`: clean.
  `pnpm build`: passed.
- `pytest tests/test_integrations_oauth.py
  tests/test_gap_completion.py`: 31 passed. Full backend suite
  not repeated (round-eight run: 911 passed / 5 named failures).
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
  and outcomes are memory-only.
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
