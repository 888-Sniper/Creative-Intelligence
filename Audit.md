# Creative Intelligence audit for 2026-10-08

Review `origin/main` after `git fetch`. Confirm that `origin/main` and GitHub `main` name the same SHA. A behind local checkout or a missing local `main` branch is not a reason to stop; use `git show origin/main:PATH`. Stop only if the remote identities differ or the worktree is dirty.

This is the product repo https://github.com/888-Sniper/Creative-Intelligence. The parent of this push is `bf93c9503c346b604d0303d6ea4595a584b5df1d` (`Localize the wizard duration and current dataset labels`). This push replaces `Audit.md` only. It records a source check of every routed screen, button, and setting. It does not change product code. Do not call the product perfect. Do not edit, commit, push, build, install, start the server, or activate a provider. Do not treat an unrun live model, live browser, or a previously stored analysis as a source defect. Report only defects still present at the reviewed SHA, with severity, observed behavior, file and line, and the evidence that reproduces them. State checks not performed.

Confirm the push with both ends named:

```
git diff --stat bf93c9503c346b604d0303d6ea4595a584b5df1d origin/main
```

The diff is `Audit.md` only. Re-read the files named below at `origin/main`. A green unit test that mocks a missing route is not evidence the route exists.

## How this check was made

The live router is `apps/creative-intelligence-ui/src/app/router.tsx`. It mounts `AppShell`, not `AppLayout`. These files are not on a route: `OverviewPage.tsx`, `layouts/AppLayout.tsx`, `components/FilterBar.tsx`, `components/AskBar.tsx`, `components/SyncJobs.tsx`. Do not treat their buttons as live controls.

`FilterProvider` wraps the shell, so filter values survive navigation. `SampleScopeBanner` is mounted on every page from `AppShell.tsx`. Compare has no filter panel of its own.

On this machine the UI suite was 302 passed (`cd apps/creative-intelligence-ui && pnpm exec vitest run`). The backend suite was 861 passed, 1 skipped, 4 failed (`uv run --extra dev pytest -q --tb=line`). Playwright was not run. The live Render site, live providers, and the five Notino clips were not used. Do not upload the clips.

The four backend failures:

- `tests/test_ci_app.py::test_security_headers_health_readiness` passes the `/health` header checks, then raises `ModuleNotFoundError: No module named 'tests'` on `from tests.conftest import make_client`.
- `tests/test_ci_app.py::test_no_licensing_concepts` walks the repo, including `.venv`, and finds `grace_period` in the installed `watchfiles` package. Product source does not contain that word.
- `tests/test_web_shell.py` expects `200` for `/assets/favicon.png` and `/assets/foap-logo.png`. Both 404. See the asset defect below.

## Shell

`AppShell.tsx` wires the menu button, the collapse button (`localStorage` key `ci-shell-collapsed`), search, the bell, and the account menu. The bell is a link to `/insights`, not a notification inbox. Search results navigate. The account menu links to Settings, can switch a saved account, and logs out.

Nav targets that render: `/`, `/campaigns`, `/creatives`, `/compare`, `/benchmarks`, `/insights`, `/reports`, `/workbook`, `/ask`, `/analyst`, `/settings`. `/providers` and `/admin` render only when `me.is_admin` is true. The backend still authorizes those APIs.

## Dashboard

`DashboardPage.tsx` refetches KPIs, daily points, campaigns, creatives, and benchmarks when the filter scope changes (`useScopedApi` / `useDaily`). Apply bumps a refresh key. Clear resets the shared filters. With no date chosen, one effect writes `date_from` and `date_to` from the daily series once (`rangeBooted`). Money formatting in `formatBench` uses USD.

The retention, hooks, length, and format tabs render empty states when their rows are missing. Retry is wired on the error state.

Analyze Video on this page opens `VideoUploadCard` / `VideoUploadPanel`. Upload, Back, Save Draft, Continue, Analyze, delete, replace, remove, import, and confirm-match call their handlers. The duration detail and the active dataset option use `durationValue` and `datasetCurrent`. English stays `{duration} Seconds` and `{name} (Current)`. Spanish and Polish stay `{duration} s`, `{name} (actual)`, and `{name} (bieżący)`.

## Campaigns

The table, search, status, spend bands, attribute selects, clear, and CSV export are wired. The list comes from `GET /api/campaigns` and follows the shared scope.

The details button is not wired to a real route. `CampaignsPage.tsx` line 361 requests `GET /api/campaigns/${name}`. `Backend/ci_backend/routers/product.py` exposes `/api/campaigns`, `/api/campaigns/meta`, and `/api/campaigns/recommendations`, and no `/{name}` route. The drawer at lines 682–724 then shows the client’s “Request failed (404)”. `CampaignsPage.test.tsx` mocks `/api/campaigns/Alpha`, so that test stays green. `top_creatives` exists only in that test fixture.

## Creatives

Sort, length filter, reset, list/grid, export, and the detail disclosure are wired. The list follows the shared scope. Retention is fetched per creative key. A duration of `0` is treated as missing by `secondsOf(datum) ? ... : "—"` at `CreativesPage.tsx` line 119, because `secondsOf` returns a number and `0` is falsy.

## Compare

Apply, remove, add, Rank By, and Compare Periods are wired. Apply is required before Rank By changes the result. Fewer than two names does not call the API.

Compare does not redraw when the shared filter changes while the page stays mounted. The automatic run sets `booted` at `ComparePage.tsx` lines 377–409 and never reads `scope` again. The daily series effect at lines 411–434 also omits `scope`. `SampleScopeBanner.tsx` can write `date_from` and `date_to` while Compare is open, including the Return action at lines 74–82. The campaign dropdown refetches. The cards and the trend chart keep the previous result until Apply, or until the page unmounts and mounts again. There is no filter panel on Compare.

The trend chart aligns days by index. `daily_series` in `Backend/creative_intel/benchmarks.py` lines 194–232 returns only dates that have rows. `ComparePage.tsx` lines 517–531 and `charts.tsx` lines 51–58 plot those arrays on one shared x scale. Two campaigns with different flight dates land on each other’s days.

Suggested tests and the percent sentences are English literals at `ComparePage.tsx` lines 247–253 and 551 (`higher` / `lower`). Period validation at line 355 is the English sentence `Fill All Four Period Dates.`

## Benchmarks, Insights, Reports, Workbook, Ask, Analyst

Benchmarks: group-by, attribute selects, clear, save, apply-view, delete-view, export, and clear-selection are wired. The table refetches with the scope. The first two rows are preselected when the selection is empty.

Insights: save, apply-view, and the local search/date chips are wired. Creative cards follow `/api/analyst/creatives`. Saved conversations load once per mount.

Reports: template save, date range, generate, and history actions are wired. The catalog refetches with the scope. Generate stays disabled until that catalog returns. Unchecking every campaign sends `campaigns: null` from `ReportsPage.tsx` line 447. `expert2_report_route` in `Backend/ci_backend/actions.py` line 1217 turns null into every campaign, and `campaign_kpis` in `benchmarks.py` line 839 keeps every group when `campaigns is None`.

Workbook: module, template, KPI chips, cancel, and create are wired. Preview data uses `useScopedApi`.

Ask: submit and suggestion chips call `POST /api/ask` with the filter scope captured at send time. A production workspace does not auto-send. A demo workspace sends the default question once.

Analyst: the page remounts when the employee id changes (`AnalystRoute` in `router.tsx`). Run, ask, clear, new conversation, one-pager, spreadsheet, workbook download, and the filter controls are wired. Clear also clears the shared filters.

## Settings

These controls change live behavior, through `applyLive` in `SettingsPage.tsx` lines 232–237:

- Theme, accent, and density.
- Language (`en`, `es`, `pl`) and time zone. Dates elsewhere use that zone. Language falls back to English for a missing key.
- Workspace name autosaves to `localStorage` (`ci-settings-prefs:<employeeId>`). A blank name is rejected. The name is not read by any other screen.
- Save Profile, upload photo, remove photo, and the avatar URL field call the account API.
- Change Password, Log Out Everywhere, and Log Out call the session API. Log Out Everywhere asks for confirmation.
- Reset Defaults restores the preference document and reapplies the live fields above. Retry repeats the last local save.

These controls save and restore on the Settings page only. No other screen reads them:

- Default View, Default Currency, Default Date Range, Default Campaign View (`SettingsPage.tsx` lines 834–870). Dashboard money stays USD (`DashboardPage.tsx` `formatBench`). The dashboard date window is chosen by the dashboard effect, not by Default Date Range.
- Email Reports, Campaign Updates, AI Insights, Product Updates (lines 762–769).
- Data Usage, Share Analytics, and the retention select (lines 971–979).

`src/state/notificationPrefs.ts` is not imported anywhere.

Two-Factor Authentication and the Meta, TikTok, and GA4 rows render an unavailable pill. They have no action button. That is the coded state, not a missed click handler.

## Admin

Employees: refresh, export, create team, invite, and the per-row actions call the admin API. Non-admins see the admin-required line. The backend still returns 403.

Providers: refresh, save key, remove key, save base URL, test, cancel test, refresh catalogue, activate, and deactivate are wired. Activate and deactivate confirm. A 409 keeps the previous selection and offers retry. Do not activate a provider during review.

Demo pack controls live on the providers admin surface: import, migrate, remove, rename, and per-file delete. They are admin API calls.

## Assets

`/assets/{name}` in `product.py` lines 2849–2858 treats `.png` as a built frontend file and looks only in `dist/assets`. `Web/assets/favicon.png`, `foap-logo.png`, and `foap-mark.png` are never consulted for that path, so `/assets/favicon.png` and `/assets/foap-logo.png` 404. The React shell uses `/favicon.png`, `/foap-logo.png`, and `/foap-mark.png` (lines 2880–2893), which read `Web/assets`.

## Wizard copy still in English

Match methods are the English map at `VideoUploadPanel.tsx` lines 74–84, used for the method dropdown and the matched sentence. Moment flags are the English words Brand, Product, Logo, CTA, and End at lines 177–181. Spanish and Polish do not translate them.

## Checks not performed

No Playwright run, no production UI build, no server start, no live Render click-through, no live model call, no provider activation, and no upload of the five Notino clips. An unrun live page is not a source defect. This push does not change video analysis or the audio cache.
