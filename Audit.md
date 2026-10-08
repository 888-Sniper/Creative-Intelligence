# Creative Intelligence audit for 2026-10-08

Review `origin/main` after `git fetch`. Confirm that `origin/main` and GitHub `main` name the same SHA. A behind local checkout or a missing local `main` branch is not a reason to stop. Use `git show origin/main:PATH`. Stop only if the remote identities differ or the worktree is dirty.

This is the product repo https://github.com/888-Sniper/Creative-Intelligence. The parent of this push is `6cdf4380f56e43edecc9e35748e1be0a6efd2a1c` (`Resume the video upload wizard on the step it left`). This push replaces `Audit.md` only. It does not change product code. Do not call the product perfect. Do not edit, commit, push, build, install, start the server, or activate a provider. Do not treat an unrun live model, live browser, Playwright run, Render click-through, or the five Notino clips as a source defect. Report only defects still present at the reviewed SHA, with severity, observed behavior, file and line, and the evidence that reproduces them.

Confirm the push with both ends named:

```
git diff --stat 6cdf4380f56e43edecc9e35748e1be0a6efd2a1c origin/main
```

The diff is this file. Re-read the cited files at `origin/main`. Line numbers below were opened at the parent SHA. If a later commit moves a line, follow the symbol, not the stale number.

Four source reads covered the routed app: shell, sign-in, Dashboard, Campaigns, and Creatives; Compare, Benchmarks, Insights, Reports, and Workbook; Ask, Analyst, Settings, Admin, and the Providers screen; the model path and the Analyze Video wizard, including resume. Unrouted files are not live tabs: `OverviewPage.tsx`, `layouts/AppLayout.tsx`, `components/FilterBar.tsx`, `components/AskBar.tsx`, `components/SyncJobs.tsx`. `router.tsx` does not mount them.

The UI suite was not re-run for this file. On the parent, `pnpm exec vitest run` from `apps/creative-intelligence-ui` passed 306 tests across 38 files, `pnpm exec tsc --noEmit` exited 0, and `VideoUpload.test.tsx` passed 28. The backend suite was last run before the resume commit, which did not change Python: 861 passed, 1 skipped, 4 failed. Those four are named under Checks not performed. Playwright, the live Render site, live providers, and the five Notino clips were not used.

## Resume

The Resume button in `VideoUploadCard.tsx` line 294 still opens `{ draftId }` and does not pass a stage. That is the restore path. Do not report the missing `stage` argument as a defect.

Stages are `video`, `client`, `dataset`, and `review` (`VideoUploadPanel.tsx` lines 44 and 59, `videoUploadApi.ts` line 41).

On open, `VideoUploadPanel.tsx` lines 778–781 choose the step in this order:

1. `open.stage`, when the caller passed one. Recent Uploads View passes `review` and Retry passes `video` (`VideoUploadCard.tsx` lines 327–330). Those win.
2. The step stored for that draft id in `localStorage` key `ci-video-draft-stage:<employeeId>`. The value is a map of draft id to a stage (`readDraftStage` in `videoUploadApi.ts` lines 48–89).
3. `spec.wizardStage` (`storedStage` at `VideoUploadPanel.tsx` lines 71–72, field at `videoUploadApi.ts` line 196).
4. `stageForSpec` (`VideoUploadPanel.tsx` lines 61–66). Missing or invalid video returns `video`. Otherwise an unconfirmed client returns `client`. Otherwise no dataset returns `dataset`. Otherwise `review`. This is only the fallback.

Continue does not require those gates. The Continue button (`VideoUploadPanel.tsx` lines 1912–1914) is not disabled on them. Continue and Back call `goStage` (lines 1001–1007), which writes the stage map and then `persistLeaveFields`. Closing the dialog, the overlay, or Escape calls `leaveAndClose` (lines 1010–1019, overlay at 1387, close button at 1400, Escape at 851–852 through `closeRef` at 1021). Analyze calls `forgetDraftStage` and then `onClose` (lines 1365–1370). It does not use `leaveAndClose`.

The chosen stage is written in the same synchronous block as `setDraft` (lines 775–795), before `await loadRows` (line 812). A render cannot record the default `video` step over a stored later step.

A step-only leave does not PATCH. `persistLeaveFields` (lines 960–998) patches only when the client, campaign, creative key, or platform differs from the last saved spec. A confirmed match returns first unless the client, campaign, or creative key changed (lines 975–976), because any spec PATCH clears matches (`product.py` lines 1893–1896). `fieldSnap` treats a missing platform as `meta` on both sides (lines 75–86), so the default does not count as a change. Closing an unchanged wizard sends no PATCH and leaves a confirmed match in place.

Typed client, campaign, creative key, and platform are included when they differ, so Resume can show them again. `wizardStage` is stamped on `persistSpec` (line 907), upload (line 1082), import (line 1218), and the leave body (line 985). A video file that was chosen and never uploaded is not restored. CSV or XLSX text that was never imported is not restored. Boot clears that staged file and text (lines 728–740). An uploaded video and an imported dataset come back from the draft.

The same browser keeps one step per draft id. Opening a second draft does not erase the first. Delete forgets only that id (`VideoUploadCard.tsx` line 185). A successful Analyze forgets only that id. Switching accounts clears the previous account's map (lines 130–136). A dead pin forgets only that pinned id (line 120). The pin key `ci-video-draft:<employeeId>` is separate from the stage map.

In-progress Recent Uploads Continue also passes only `{ draftId }` (lines 383–384) and therefore uses the same stored step. View and Retry pass a stage and win over it.

## Shell and sign-in

Signed-in employees get `AppShell`. Nav labels come from `en.ts` `nav.*`: Dashboard, Campaigns, Creatives, Compare, Benchmarks, Saved Insights, Generated Reports, Blank Workbook, Ask The Data, AI Analyst, then AI Providers and Admin only when `me.is_admin`, then Settings (`AppShell.tsx` lines 10–27). Collapse is stored as `ci-shell-collapsed`. The brand mark goes to `/`. Open Menu, Close Menu, and Collapse Sidebar are local. The search box is `GlobalSearch.tsx`: after the first query it loads campaigns meta, creatives, and analyst creatives, and a submit goes to `/campaigns?find=`. Suggestion rows go to campaigns, creatives, or insights. The bell (`AppShell.tsx` line 117) goes to `/insights`. It is not an inbox. The dot at line 119 is always painted.

`/` is the dashboard. `/dashboard` replaces to `/`. `/profile` replaces to `/settings`. Admin and Providers are wrapped in `AdminOnly`. A non-admin sees “Admin Access Required.” `get_current_admin` in `deps.py` lines 90–98 returns 403, and `/api/admin` and `/api/admin/providers` use that guard.

`SampleScopeBanner` is mounted from `AppShell` and renders only while `ci-sample-scope` is valid. Return To My Scope restores the saved filters and removes that key.

Sign-in is email password, email code, or Google.

- Refresh Access (`AuthScreens.tsx` line 65) calls `GET /api/auth/me`.
- Log Out (`AuthScreens.tsx` line 68 and `AccountMenu.tsx` line 141) calls `POST /api/auth/logout`.
- Work Email, password, Remember Me, and Show/Hide Password are local. Remember Me writes `ci-remember-email`. The password-mode label “Work Email” is a literal at `EmailSignIn.tsx` line 146, not `auth.login.workEmail`.
- Sign In posts `/api/auth/email/signin`. Forgot Password posts `/api/auth/email/reset`. The success sentence is the English string at `AuthProvider.tsx` line 205.
- Use A Sign-In Code Instead is local. Send Sign-In Code posts `/api/auth/email/code`. Success copy is hardcoded at `AuthProvider.tsx` line 181. Verify & Sign In posts `/api/auth/email/code/signin`.
- Continue With Google posts `/api/auth/oauth/start` and then assigns `location`. Microsoft, Apple, and GitHub exist on `OAuthButtons`, but the login screen renders `EmployeeOAuthButtons`, which is Google only.
- The account menu loads `GET /api/auth/accounts`. Settings navigates to `/settings`. Switch To posts `/api/auth/switch` and then `/api/auth/me`. A failed account load leaves “Loading Accounts…” up (`AccountMenu.tsx` lines 116–117) and also shows the error (line 140).

`useSessionCount` calls `GET /api/auth/sessions`. `useGoogleStatus` calls `GET /api/auth/google/status`. They have no controls of their own on this shell.

## Shared filters

`FilterContext` holds the shared scope. `scopeParams` (`FilterContext.tsx` lines 52–66) drops `kpi` and appends `sample_batch` from local storage. Exact `date` and a `date_from`/`date_to` pair clear each other. `useScopedApi` (`product.tsx` lines 208–223) refetches when the path, scope key, or refresh key changes, and clears `data` first.

`FilterPanel` (`product.tsx` line 534) writes `FilterContext` as soon as a select changes. On Dashboard and Creatives the panel is passed `actions="none"`, so its own Apply and Reset are hidden. The page headers show Apply and Reset instead. Apply bumps a refetch. It is not the first commit of the select. Date Range, From, To, Clear, and Done are local to the popover (`product.tsx` lines 501–525).

Dashboard’s block (`showTeam={false}`) is Client, Project, Campaign, Platform, Vertical, Market, Funnel Stage, Campaign Objective, KPI, and Date Range. Team is hidden. KPI is stored and not sent. Creatives’ block is Client, Campaign, Hook Type, Format, Creator vs Branded, Platform, Funnel Stage, and Date Range.

`useDaily` turns any error into `[]` (`product.tsx` line 190). Trend panels then show the empty state.

## Dashboard

Dashboard loads `/api/campaigns`, `/api/creatives`, `/api/benchmarks` grouped by platform, hook, and creator-versus-branded, `/api/kpis/compare`, `/api/kpis/daily?days=30`, and the top creative’s `/api/retention/curve`. On first mount, if no dates are set and the daily series has at least two days, it writes that series’ first and last dates into the shared scope (`DashboardPage.tsx` lines 222–232). It does not read Settings’ Default Date Range or Default Currency. `formatBench` hardcodes `currency: "USD"` (lines 167–168). Shared `fmtMoney` does the same (`product.tsx` lines 39–41).

Controls:

- Apply Filters and Reset Filters (lines 537 and 540). Reset calls `clearFilters`. The bootstrapped date window does not return, because `rangeBooted` stays true.
- Clear team filter (line 554), only when a team is already in scope.
- Left Trend Metric and Right Trend Metric (lines 596 and 600): Impressions, Clicks, Spend, Conversions. Local, over the daily series.
- Benchmark Metric and Benchmark Baseline (lines 623 and 627): CTR, ROAS, CPA, CPC, versus Scope Average or Top Performer. Local.
- See All (line 663) goes to `/creatives`.
- Open {name} in Creatives (line 707) goes to `/creatives` with no `?find=` and no creative key. Creatives already honors `?find=` (`CreativesPage.tsx` lines 199–206).
- Insight Type (line 725): Audience Retention, Hook Analysis, Video Length, Format Comparison. Local.
- Recommendation links in `InsightList` (`product.tsx` line 721) are plain `<a href>`: View Creatives and Explore Creatives go to `/creatives`, View Campaigns to `/campaigns`, See Recommendations to `/insights`.
- See All on recommendations (line 801) goes to `/insights`.
- Upload Video, Resume, Discard, and the Recent Uploads row are the wizard card. See Resume and the wizard section.

Video Length sets `bench` equal to `yours` (`DashboardPage.tsx` lines 345–347), so the bars compare each bucket with itself. Duration `0` is dropped before bucketing (line 322, `if (!seconds) continue`).

Top Creatives, the benchmark chart, and the recommendation rail stay on `Skeleton` when `data` is null (lines 634–654, 665–718, 803–807), including after an error. Hook and format tabs treat a failed fetch as the empty copy.

## Campaigns

Campaigns loads the campaign list, benchmarks, meta, compare, and daily endpoints. Status and spend bands are real scope axes. The backend resolves them into a campaign allowlist. The name search is local.

Controls:

- Apply Filters and Reset Filters (lines 400 and 403). Reset also clears the name search.
- Client, Spend Range, KPI Focus, Campaign Objective, Team, Market, Campaign Status, Platform (lines 416–490). KPI Focus is not sent. Objective options are raw meta strings, not `filters.objectives.*`.
- How Campaign Status Is Determined is an `InfoTip` (line 473). Local.
- More Filters / Fewer Filters (line 494) reveals Project, Vertical, and Funnel Stage. Those selects write the shared scope.
- Platform Metric (line 574): Spend, Impressions, or Clicks. Local.
- Search Campaigns (line 595). `?find=` is copied only into the initial state (lines 107–108). A later navigation to the same route does not update the box. Global search uses that query (`GlobalSearch.tsx` lines 130–132).
- Compare Selected (line 602) goes to `/compare` with the selected names. One campaign is enough. An empty selection only sets a status line. The compare page asks for two to four.
- Export (line 605) posts `/api/exports/campaigns` (line 335) and surfaces “Export Failed”. That path is not registered. The action table (`product.py` lines 891–902) does not contain it, so `POST /api/{action:path}` returns 404 (lines 2502–2503). The only export route is `POST /api/export` (line 1411), which builds a one-pager from creative keys.
- Select All and the row checkbox are the compare selection.
- Details (line 658) opens the drawer, which calls `GET /api/campaigns/${name}` (line 361). The backend exposes `/api/campaigns` (line 146), `/api/campaigns/meta` (line 157), and `/api/campaigns/recommendations` (line 171). No per-name route. The client turns a body without `error` into `Request failed (${status})` (`client.ts` lines 32–33). The drawer prints that in `EmptyState` (lines 723–724). A stock 404 is “Request failed (404)”. The recommendations route is never called.
- Delete Sample, Confirm Delete, and Cancel (`SampleDelete.tsx` lines 105–123) are admin-only and sample-campaign-only. They call the demo-pack impact and campaign-delete routes.
- Retry (line 675) refetches a failed campaign list.
- See All (line 731) goes to `/insights`.
- Rail links (lines 229–266) are `<a href>`: View Campaigns reloads `/campaigns`, View Recommendations goes to `/creatives`, See Insights to `/insights`, View Details to `/compare` with no campaign state.

“vs. Benchmark” is one shared number. `benchVal` comes from `focus.metrics[kpiKey].current` (lines 372–376). `focus` is filled only from `location.state` (lines 127–140). Every row prints that same value (line 655). With no navigation state the cell is Unavailable.

A failed daily series becomes the empty state (lines 560–569). Platform bars stay on `Skeleton` when data is null (lines 580–588).

## Creatives

Creatives loads `/api/creatives`, compare KPIs, and a retention curve for the open row.

Controls:

- Apply Filters and Reset Filters (lines 430 and 433). Reset also clears sort, view, length, benchmark, selection, and the open detail.
- Video Length and Benchmark (lines 457 and 466) are local. Length filters the rows already returned. Benchmark only changes the badge.
- See All on Top Creatives (line 526) navigates to `/creatives`, the current page.
- List View and Grid View (lines 563 and 568). Grid cards are not buttons and do not open the detail (lines 648–668).
- Sort By (line 575): Top Performing, Highest CTR, Highest ROAS, Most Impressions. Local.
- Export (line 578) posts `/api/exports/creatives` (line 399) with every visible key. The checkboxes are ignored. The route is not registered. Same 404 path as the campaign export.
- Select All and the row checkbox write `selected` (lines 187 and 616). `selected` is only read to paint the checkbox (line 388). `creatives.compareSelected` exists in `en.ts` and is not rendered.
- The creative name (line 622) toggles the detail panel and loads `GET /api/retention/curve`.
- See All on Top Learnings and on Next Tests (lines 684 and 705) go to `/insights`. Next Tests are three fixed sentences (lines 375–379) whenever any creative is in scope.

`secondsOf` returns a real zero (`CreativesPage.tsx` lines 71–72). The detail then uses a truthiness check: `secondsOf(datum) ? ... : "—"` (line 119). The length column does the same (`s ? \`${s}s\` : "—"` at line 635). The short, sweet, and long filters require `s > 0` (lines 218–220). A zero-length creative looks unmeasured and is excluded from every length bucket.

A failed creatives table has no Retry (lines 671–672). The campaign table does.

## Compare

Compare has no `FilterPanel`. It loads catalogs through scoped `GET /api/campaigns` and `GET /api/creatives`, then compares with scoped `GET /api/compare/campaigns` or `GET /api/compare`, at most four. The first boot picks the top four campaigns by spend, or a `?mode=&campaigns=|creatives=` link, and runs only when at least two ids validate (`ComparePage.tsx` lines 377–409). `booted` makes that effect return on later scope changes. Option lists still refresh, because they use `useScopedApi` (lines 289–290). Leaving the route remounts the page, so the next visit boots again. While it stays mounted, including when Return To My Scope writes the shared filter, cards, ranking, and the trend stay on the last run until Apply.

Controls:

- Compare By (line 670) sets the mode and clears the selection and both results.
- Add and remove chips (lines 682–694). At most four. Local until Apply.
- Rank By (lines 698–701) stores the metric. Apply (line 708) sends it (lines 626–628). Apply is disabled while loading or when fewer than two are picked.
- Trend metric (line 749), comparison metric (line 780), and baseline (line 795) are local.
- Period disclosure (line 895), A/B From and To (lines 907–919), and Compare Periods (line 923). Compare Periods calls scoped `GET /api/compare/periods`. It does not send `label_a` or `label_b`, so the API default is Period A / Period B (`product.py` lines 275–278). Empty dates set an error and do not call the API.

Campaign trends call scoped `GET /api/kpis/daily?days=30` per ranked campaign. The daily effect depends on `[mode, campaignData]` (line 434) and reads `scope` inside (line 420). Creative curves call unscoped `GET /api/retention/curve`. Creative mode replaces the attribute table with backend rows whose labels are English (`actions.py` lines 647–670, used at lines 593–596).

`daily_series` (`benchmarks.py` lines 208–231) keeps only dates that have rows, then the last `days` of those dates. Compare does not join series on the date. Each campaign’s points are its own day order (`ComparePage.tsx` lines 517–523). `trendLabels` come from the first non-empty series (lines 527–530). `TrendChart` plots point `i` at `x(i)` (`charts.tsx` lines 51–52) and places a label with `labels.indexOf` (lines 85–86). Different date sets, or a repeated `MM-DD` after `date.slice(5)`, misalign the lines. A missing daily response becomes `[]` (lines 426–428) and then `compare.noDaily`, with no error. The trend chart draws an uncomputable ROAS, CTR, CPA, or CPM as `0` (lines 518–521).

These strings are hardcoded English, not `t()`: the five suggested tests and their bodies (lines 247–253); `is …% higher` / `lower` (line 551); `Fill All Four Period Dates.` (line 355); `Select at least two campaigns to compare.` (line 301); `Select at least two creatives to compare.` (line 329); `Request Failed` (lines 318, 347, and 368); `Top Creative` and `Last 30 Days` (lines 486–487); `Unassigned` and `Video` (lines 501–502). A creative deep link runs `ctr` (line 396) while Rank By still shows the default `roas` (line 269) until Apply. A creative test can still be suggested from the default `ctr` idea when every compared KPI is missing (lines 576–588). The first takeaway can be a raw winner id because `why.top` is pushed as text (lines 560–561).

## Benchmarks

Benchmarks groups with scoped `GET /api/benchmarks?group_by=`. Saved cards are `GET`/`POST /api/views` and `POST /api/views/delete`. Opening one calls `applySavedView`, which writes global filters and navigates. Create Benchmark stores the live scope, KPI, and axis. The page’s own client, vertical, platform, market, objective, and funnel controls call `setFilter` immediately (lines 283–310), so they change the shared scope for every page before Apply. Apply (line 314) only increments `applied`. Reset (line 317) calls `clearFilters()` on the shared scope.

Controls:

- Create Benchmark (line 276). It calls an unscoped `GET /api/benchmarks` and discards the result (line 209), then `POST /api/views`.
- Platform options are only Meta and TikTok (lines 291–295).
- View All (line 329) goes to `/insights`.
- Open Benchmark (line 341) and Delete (line 344).
- Group By (lines 375–378). The select offers `platform`, `hook_type`, `format`, and `creator_vs_branded` (`AXES` at lines 31–33). `GROUPABLE` is only `platform`, `campaign`, `hook_type`, `creator_vs_branded`, and `edit_style` (`benchmarks.py` lines 10–11). `format` raises `ValueError` (lines 236–237). The panel then renders `benchmarks.error` (line 428) instead of rows. The same invalid call with `group_by=vertical` (line 112) never fills the vertical count, so lines 474–476 stay `0` even when verticals exist.
- Export, desktop (line 380) and overflow (line 371), posts `{}` to `/api/exports/benchmarks` (lines 236–246). No backend route registers that path. The unit test mocks the missing URL.
- Select All (lines 393–395) checks every row. The three-benchmark cap and `benchmarks.maxCompare` exist only in `toggle` (lines 159–165). Charts still use `compared.slice(0, 3)` (lines 134–137), so extra checked rows are omitted with no status. Clear All (line 434) clears the local selection.
- Open AI Analyst (line 498) and Open Reports (line 499).

Coverage and Platform cells are canned `filters.allVerticals` or `filters.allPlatforms` (lines 414–415), not the row’s coverage. `MiniBars` turns a null CPM, CPA, or ROAS into `0` (line 442). CPM ignores the API value and recomputes `spend / impressions * 1000` (lines 262–267), including when the API nulled CPM for mixed currency (`summarize`, `benchmarks.py` lines 153–154).

## Insights

Insights loads reach-objective cards from scoped `GET /api/analyst/creatives?objective=reach`. The backend treats that `objective` as the analysis objective and does not use it as a campaign filter (`product.py` lines 1048–1056). Page search, client, platform, market, type, and date are local state. Save Insight posts the global `scopeBody(scope)` plus `filters.kpi` and `view: "main"` (`InsightsPage.tsx` lines 213–215). It ignores the page’s own client, platform, and market. Conversations and views load once (lines 94–103, deps `[]`).

Controls:

- Save Insight (line 235), search (line 245), client (line 248), platform (lines 252–256, Meta and TikTok only), market (line 258), Insight Type (line 262), Date Saved (line 268).
- Open and Delete on a saved view (lines 312 and 315). Delete posts `/api/views/delete`.
- Open Insight on a conversation (line 323) goes to `/analyst` with no conversation id.
- Open AI Analyst on the empty states (lines 295 and 334).
- Open in Analyst on a finding (line 348) goes to `/analyst` with no creative key.

Insight Type does not hide Pinned Learnings. Search and date do not filter findings. Date does not filter saved views. A failed card request never reads `cards.error`. Lines 277 and 375 fall through to `Skeleton`. A failed conversation or view fetch becomes `[]` (lines 98 and 101), the same UI as an empty account. The empty Pinned and empty Saved panels share `pageInsights.noPinnedTitle` (lines 293 and 332), whose English text is `No saved insights yet`.

## Reports

Reports builds `POST /api/report` for PPTX, XLSX, or a one-pager. The catalog is scoped `GET /api/campaigns` in its own effect (`ReportsPage.tsx` lines 419–437), so it does refetch when the scope changes. It does not use `useScopedApi`. Generate is `disabled={busy || campaigns === null}` (line 667). A catalog error leaves `campaigns` null, so Generate stays disabled. Any scope change sets `campaigns` back to null and then checks every returned name (lines 421–429), which clears a partial selection.

Controls:

- Save as Template (line 610) writes `ci-report-template`. Nothing reads that key.
- Campaign checklist (line 617). The empty label is All Campaigns. Generate then sends `campaigns: null` (line 447). `expert2_report_route` (`actions.py` line 1217) turns a missing or empty list into `None`. `campaign_kpis` (`benchmarks.py` lines 839–841) then keeps every campaign still in the filter scope.
- KPI checklist (line 626). An empty selection still sends `["cpa", "ctr"]` (line 448) while the control reads Select KPIs.
- Benchmarks (line 637). The id `industry` is sent as `hook_type` (line 449). The English label is Scope Average (`en.ts` line 241). `rank_by` is always `cpa`.
- Date range, From, To, Clear, and Done (lines 265–286) are the report’s own range. They are sent inside `filters` on top of the global scope (lines 454–458). `match_filters` applies an exact day and a range together (`benchmarks.py` lines 553–571).
- PPTX, XLSX, and One-Pager (lines 648–663). The titles are the English literals `PPTX`, `XLSX`, and `One-Pager`.
- Generate Report (line 667).
- Search, status, format, and time (lines 688–704). Status values stay `Completed`, `Generating`, and `Failed`.
- Delete sample file (line 749) is admin-only and calls `DELETE /api/admin/demo/pack/files/{key}`.
- Download (line 757) uses `r.href` when a blob or sample URL exists.
- The retry icon (line 765) posts `POST /api/report` with the stored body. After a refresh, stored rows have `href: null`, so this is a new generation.
- View All (line 827) clears the list filters. It does not navigate.

History is local storage plus sample files and, in a demo workspace, synthetic rows. Time windows parse the display string with `new Date(r.created)` (lines 580–582). New rows store `fmtDate` output (line 513). Demo rows store English strings such as `Mar 31, 2024 10:42 AM` (lines 144–148). A string `Date` cannot parse is treated as outside the window, so Last 7 Days and Last 30 Days drop those rows. The report list always adds a `+2` chip (line 542). The campaign and KPI popovers do not close on outside click or Escape. The demo history row whose status is Generating never finishes (`demoHistory`, lines 158–164).

## Workbook

The nav label is Blank Workbook. Preview uses scoped creatives and `/api/kpis/compare` through `useCompare`, which refetches on the whole filters object, including `kpi`. Create downloads `GET /api/analyst/workbook` with name, description, modules, and KPIs only. The handler builds a cover plus seven blank sheets (`product.py` lines 1114–1133). The about copy says that on purpose (`en.ts` lines 1550 and 1576). Module cards other than summary and breakdown do not change the file.

Controls:

- About (line 300) toggles the panel. Hover and focus also open it.
- Seven module cards (line 330). Preview only reacts to `summary` and `breakdown`.
- Name (line 357) and description (line 361).
- Remove KPI and Add KPI (lines 375 and 379).
- Full screen (line 389), exit (line 448), overlay (line 441), and Escape (lines 182–191).
- Five templates (line 408). A non-custom template sets the name to `Q1 2024 Creative Performance Report` (line 210).
- Duplicate from Template (line 432) reapplies the current template. It does not copy a file.
- Cancel (line 435) resets, including that English name.
- Create Workbook (line 436) is disabled while busy.

There is no error branch. `previewFailedTitle` exists in `en.ts` (line 1563) and is unused. If compare or `/api/creatives` fails, the preview stays a `Skeleton` (lines 400–403 and 458–461).

## Ask

Ask submits `POST /api/ask` with the filter scope captured at send time (`scopeRef` in `AskPage.tsx` lines 101–102 and 130–133). Prompt chips, suggested questions, and follow-ups call the same `ask()`. Production does not auto-send. A demo workspace, `useCampaignMeta().data?.demo === true`, sends the current composer text once (lines 110–153).

When the managed LLM is paused, the ask job fails with `AI is not configured. Contact your administrator.` (`provider_inventory.py` lines 43–44, `providers.py` lines 1105–1106, `qa.py` lines 490–500). `product.py` lines 923–930 return that string as `detail.error` through `_conflict`, because the paused text has no `[provider=` marker. Ask shows `ApiError.message` (lines 135–136 and 244–245). A chosen-model transport failure marked `[provider=` becomes 502 through `_provider_failure` (`product.py` lines 74–88).

Controls: the composer and Ask button (lines 220–227); prompt chips `ask.prompts.p0`–`p3` (lines 231–239); suggested questions `s0`–`s5` (lines 332–344); follow-ups `f0`–`f2` after an answer (lines 304–313); recent chats (lines 346–363) from `GET /api/analyst/conversations`, linking to `/analyst?conversation=`. The destination does not load the transcript. See Analyst. KPI, trend, and source blocks render the answer plus scoped compare, daily, and benchmark calls (lines 249–302). Ask money uses the USD formatter in `product.tsx`.

## Analyst

Analyst Run, Ask, 3 Points, try-asking chips, and follow-ups all `POST /api/analyst/ask` with `scopeBody(scope)` (`AnalystPage.tsx` lines 419–438). The handler is deterministic. `run_analyst` calls `analyst_chat.answer_turn` and does not consult the provider (`worker_handlers.py` lines 147–173). `answer_turn` uses templates (`analyst_chat.py` lines 705–784). There is no `NOT_CONFIGURED` check on this path. A paused model does not stop Analyst.

`AnalystRoute` passes the employee id (`router.tsx` lines 34–37 and 64). The page clears chat state when that key changes (`AnalystPage.tsx` lines 386–396).

Controls:

- Clear (`clearAll`, lines 459–465, button at 930) clears the transcript, composer, error, scope text, and active id. It does not call `clearFilters`.
- Reset (line 998) calls `clearFilters()` and sets the local range to `"all"`. It does not reset Objective or Language. The next ask still sends the previous objective and language (lines 1038–1054).
- Run Analysis (lines 933–935), Ask (lines 942–957), 3 Points (lines 959–969). An empty 3 Points uses `analyst.condenseLast` when a thread exists. `max_points` is 3.
- Try asking (lines 980–987).
- Campaign, platform, client, and project (lines 1004–1069) write the shared filters.
- Date range (lines 1022–1036) is local state, initial `"all"` (line 347). Charts use `FilterContext` through `useScopedApi`. A range chosen on another page stays in effect while this select says All Time, until the user changes it.
- Objective (lines 1038–1047) is page-local and is sent on the ask body. It is not written back to the shared filters.
- Language (lines 1050–1054). `auto` omits language. The options are the hardcoded strings Auto, Polski, and English. The backend rejects anything else (`product.py` lines 1260–1267). Spanish is not offered.
- New Conversation (lines 1072–1075) posts `/api/analyst/conversations`.
- Report (lines 1077–1080) posts `/api/analyst/report` through the API client.
- Report XLSX (lines 1082–1085) fetches the same route with a raw `fetch` (lines 150–161). A 401 does not run the API client’s login gate.
- Blank Workbook (lines 1087–1090) is `GET /api/analyst/workbook` through a raw `fetch` (lines 513–541). The comment at lines 514–516 claims session re-gating that this fetch does not do. The server builds a blank workbook (`product.py` lines 1114–1139).
- Previous analyses (lines 1093–1110) set `activeId` and `setMessages([])` (lines 1101–1104). The Ask deep link only calls `setActiveId` (lines 375–378). Nothing calls `GET /api/analyst/conversations/{id}` (`product.py` lines 1016–1030 returns messages). The next ask still sends `conversation_id`, so the server thread continues while the screen stays empty.
- Save To Next-Flight Plan and Dismiss (lines 903–913) post accepted or rejected while the finding is proposed.
- Follow-up chips (lines 1179–1186) send the returned follow-up text.

Charts on this page use `/api/benchmarks`, `/api/campaigns`, and `/api/creatives`. The page does not call `GET /api/analyst/creatives`.

## Settings

`applyLive` (`SettingsPage.tsx` lines 232–237) applies theme, accent, density, language, and timezone on each autosave commit. Language and timezone are also restored for the signed-in employee by `LocalePrefsSync` (`i18n/index.tsx` lines 160–162). Accent and density CSS variables are rewritten when Settings is mounted (lines 314–316) and then left on `documentElement`.

The prefs key is `ci-settings-prefs:<employeeId>` (`prefs.ts` lines 106–147), with a one-time read of the legacy global key. `src/state/notificationPrefs.ts` is unused. Nothing imports it.

Live on commit: theme, accent, density, language, timezone.

Saved on this page and not read by Dashboard, the router, or Ask: workspace name, Default View, Default Currency, Default Date Range, Default Campaign View, Email Reports, Campaign Updates, AI Insights, Product Updates, Data Usage, Share Analytics, and the retention select. Workspace name autosaves after 450 ms, trims, caps at 80, and rejects a blank (lines 270–288). No other page reads `prefs.workspace`. Unmount clears the debounce without flushing (lines 291–293), so a name typed and left within 450 ms is dropped. Default View, currency, date-range, and campaign-view option labels are English arrays (lines 66–69 and 840–878). The retention hint says the browser preference is not workspace retention (`en.ts` line 1783).

Theme is saved per employee, but the painted mode is the global `ci-theme` key (`useTheme.ts` lines 6–18 and 45–51). The live tree mounts `useTheme` only from Settings. Account switch applies language and timezone and does not call `setThemeMode` for the new employee. Accent and density update only when Settings mounts.

Backend actions, not prefs:

- Retry (lines 516–519) re-saves the prefs already on screen, and only after a local save failed.
- Reset Defaults (lines 521–523) writes `DEFAULTS` and applies them. No confirm.
- Edit Profile focuses the first-name field.
- Upload Photo posts `/api/auth/me/avatar` with a raw `fetch` (lines 387–414).
- Save Profile patches `/api/auth/me` (lines 345–367). The avatar URL is included only if it changed.
- Remove Avatar patches `avatar_url: ""` (lines 370–384). The fallback error is the English sentence “Could not remove avatar.” (line 381).
- Change Password posts `/api/auth/email/reset` (lines 417–429). It sends a reset email. The form does not set a new password.
- Log Out (lines 742–746) posts `/api/auth/logout` and is shown only when the session count is under 2.
- Log Out Everywhere (lines 735–740) confirms, then posts `/api/auth/sessions/revoke-all`. The handler destroys every session and clears the cookie (`auth.py` lines 378–391). It is shown only when the count is at least 2, in place of Log Out.
- Export Data posts `/api/auth/export` (lines 462–473).
- Google Drive Connect and Disconnect live on `GoogleDriveCard.tsx` lines 35–89.

The only `status` output requires `op !== null` (line 619). Save Profile, avatar upload and remove, Change Password, Log Out Everywhere, and Export Data set `status` in `catch` and clear `op` or `sessionOp` in `finally` (lines 363–366, 381–383, 410–413, 425–428, 455–458, 469–472). Those updates land in one paint, so the error never shows. A rejected photo sets `status` without setting `op` (lines 389–391). Success still uses the toast.

The Google SSO row shows Connected unless the check is still loading or `connected === false` (lines 694–700). `useGoogleStatus` sets `connected` to null and `error` to true on failure (`useGoogleStatus.ts` lines 54–57). The Drive card shows a retry for that state (`GoogleDriveCard.tsx` lines 76–81). The SSO row does not.

Unavailable, with no connect button: two-factor (lines 750–757), Meta Ads, TikTok Ads, and Google Analytics 4 (lines 937–967). Not-connected and those integration pills use `pill-ok` (lines 697, 946, 955, 964). Two-factor uses `pill-info` (line 754). `theme.css` line 916 paints both classes as the brand teal. The words still differ.

Data tools on this page: retention patterns call `GET /api/retention/patterns`. Create Cohort posts `/api/cohorts` with the current filter scope (`DataTools.tsx` lines 272–346) and has no in-flight lock. Build calls `GET /api/cohorts/build`. Delete confirms and is rendered only for admins.

No key this slice calls is missing in `es.ts` or `pl.ts`. Extra keys in Spanish and Polish are allowed. English button labels in this slice stay title case.

## Admin

`/admin` renders only for `me.is_admin`.

Controls on `AdminEmployeesPage.tsx`:

- Export report (line 449) builds a client CSV of the loaded rows and audit events.
- Create Team (line 452) writes `localStorage` key `ci-local-teams`. The team column stays “—” (line 569).
- Add Employee (line 455) posts `/api/admin/employees`. It creates an active employee and sends no invite. The loading label is the English literal `Adding…` (line 850).
- Search, status, role, and Refresh (lines 479–515) load `GET /api/admin/employees` and `GET /api/admin/audit?limit=20`. Status and role are also filtered locally.
- Approve, Suspend, and Reactivate (lines 582–621). Suspending an admin confirms. The backend refuses to remove the last active admin (`employees.py` lines 876–895).
- Revoke, Make Admin, Make Employee, and Invalidate Sessions (lines 623–637). Revoke and demotion confirm.
- The add dialog (lines 790–852) and the team dialog (lines 859–901). The team dialog saves a local name.
- The demo-tools disclosure (lines 779–787) mounts `DemoPackPanel`.

Demo pack (`DemoPackPanel.tsx`): Add once posts import (lines 357–360). Review migration and the second click posts `/migration/apply` with `authorize: true` (lines 334–351). Open Demo Dashboard stores the sample scope and goes to `/` (line 279). Remove all requires a second click with `confirm` and `batch_id` (lines 368–386). Per-campaign delete loads impact, then deletes (lines 404–419). Rename posts `/rename` (lines 429–445). A file row can download or delete (lines 456–462). File delete has no confirm.

## Providers and the model path

`/providers` renders only for an admin.

`GET /api/health` returns `ok` and `provider_mode` only (`product.py` lines 113–117). It does not report a model.

`GET /api/providers/status` (lines 120–143) marks `stt`, `vision`, and `llm` configured when any name in `LiveBundle`’s hardcoded roster has a legacy key. It does not read the admin selection, `readiness().ready`, or `frame_eligible`. The `analysis` object copies the sends and storage strings.

`LiveBundle` (`providers.py` lines 997–1044) keeps fixed STT, vision, and LLM lists and keeps entries whose provider is `_configured` (lines 978–985). That probe is env or Keychain through `live_secret` (lines 313–330), not the encrypted admin secret. Ollama’s key is `None` (lines 433–434), so `_configured("ollama")` is true and the legacy LLM list is not emptied by a missing chat key. Construction still raises if STT or vision has no configured entry (lines 1035–1040).

The managed model and frame analysis are separate. `Providers.__init__` (lines 1059–1083) builds the legacy bundle, then `_attach_managed_llm` (lines 1089–1106) replaces only `self.llm`. A selection becomes `ManagedLlm`. No selection becomes `_Unavailable` with `AI is not configured. Contact your administrator.` STT and vision stay on the legacy race. `get_providers` passes `ci_db_path` (`deps.py` lines 59–69). The worker does the same (`worker_handlers.py` lines 53–55). Activating the managed model does not enable frame analysis. A paused selection fail-closes later LLM calls (`dispatcher.py` lines 514–525, `ManagedLlm.ask_facts` at 477–485). It does not stop the STT or vision race when `LiveBundle()` can construct.

`eligible_vision_roster` (`video_analysis.py` lines 37–57) constructs `LiveBundle()` and keeps `VISION_ROSTER` entries that are both `_configured` and `frame_eligible`. The worker overwrites `prov.vision` with `LiveVision` of that filtered list (lines 514–525). `LiveVision._annotate_batch` calls `make_chat(provider, model)` with no admin secret (`providers.py` lines 870–872). If `LiveBundle()` raises because no STT adapter is configured (lines 1031–1040), the roster returns `[]` even when a frame-eligible vision key exists. `run` then aborts at lines 519–522, after ffmpeg prepare and before the pipeline, so a silent clip never reaches the STT skip. The 409 reason is the STT bundle error.

Frame-eligible entries from `VIDEO_MODEL_SUPPORT` (`provider_inventory.py` lines 628–669) that also sit on `VISION_ROSTER` (`providers.py` lines 1003–1013) are `gemini` / `gemini-3.5-flash-lite`, `gemini` / `gemini-3.7-flash`, and `anthropic` / `claude-haiku-4-5`. These roster ids are absent, so `frame_eligible` is false: `nvidia` / `meta/muse-glimmer-30b`, `openai` / `gpt-5.6-luna`, `openai` / `gpt-5.6-sol`, `anthropic` / `claude-opus-5`, `zai` / `glm-5v-turbo`, `zai` / `glm-5.2`. `providers_status` still lists a provider with a key as vision configured (`product.py` lines 127–134). The wizard repeats that (`VideoUploadPanel.tsx` lines 1717–1722). If the bundle constructs and the frame filter then empties the roster, `readiness` keeps the reason `provider mode is 'live': switch on a live provider` (`video_analysis.py` lines 63–70).

The catalog cache TTL is 24 hours (`provider_inventory.py` line 48). Activate requires an exact offered cache row fresher than 24 hours (`admin_providers.py` lines 214–230). Deactivate clears the singleton. A revision mismatch returns 409 and does not write (lines 195–199 and 265–268). Adopt copies a legacy secret once and does not activate.

Provider screen controls (`ProvidersPage.tsx`):

- Reload Provider List (lines 307–309) calls `GET /api/admin/providers`.
- The active and paused banner (lines 327–359). The paused body says AI Analyst is paused (`en.ts` lines 778–779). Analyst does not check the provider. Ask does fail closed.
- Use as active (lines 605–655) confirms, then posts activate or deactivate with `current_revision`.
- Save Key and Replace Key (lines 481–503 and 700–709). The input is cleared and never prefilled. Any HTTP 409 calls `onConflict` with `kind: "deactivate"` (line 499).
- Show Key and Hide Key (lines 690–698).
- Remove Key (lines 529–553) confirms, then PUTs `secret: ""` and `confirm: true`. The backend deactivates if that provider is active (lines 337–364). A 409 is also sent to deactivate-retry (line 549).
- Save Base URL (lines 506–526). A 409 is sent to deactivate-retry (line 523). The backend uses 409 for an unsafe base URL (lines 322–324) and for a failed validation of a new active key (lines 386–392).
- Test Connection and Cancel Test (lines 556–583 and 757–774). The test does not change activation.
- Search models (lines 784–796) filters the offered list. Refresh Models (lines 586–602) posts `.../refresh` and does not activate. A 409, including “no secret stored” (`admin_providers.py` lines 488–491), is sent to deactivate-retry (line 598).
- The model select (lines 837–863) uses the exact offered id.
- Conflict Retry (lines 246–259). Activate and deactivate retry the same action with the fresh revision. Every other 409 stored a `deactivate` action, so Retry calls `runDeactivate` (lines 255–258) with no second confirm. `isConflict` is any `ApiError` with status 409 (lines 108–109). A secret over 4096 characters is also 409 (`admin_providers.py` lines 331–334).

Any in-flight provider action shows “Activating…” on every card. The shared `busy` flag is rendered inside each card, and only the exact string `"deactivate"` selects the other label (lines 668–671).

`POST /api/drafts/{id}/analyze` (`product.py` lines 2381–2432) calls `bind_snapshot`, then `readiness()`, and returns 409 when not ready. The job payload stores that snapshot. The draft becomes `queued`.

One Analyse press binds the snapshot in `bind_snapshot` (`video_analysis.py` lines 88–135). The worker re-checks in `check_snapshot` (lines 145–158) at the start of `run` (line 485), after the pipeline (line 546), and again inside the publish transaction (line 585). A changed input raises and does not publish. Metrics come from `measured_from_records` (line 553, function at 245–378) using the confirmed match records, not the LLM. A total with no known contributor becomes `None` (lines 367–371). A zero impression pool leaves CTR null and adds `missing is not zero` (lines 354–359). Silent clips set `audio` to `None` in `prepare_media` (lines 189–200). `run_pipeline` then skips STT (`creative.py` lines 1106–1113) and still calls `llm.structure` (line 1130). That skip is reached only if the vision-roster gate has already passed. Draft success status is `ready_for_review` (`video_analysis.py` lines 627–628). `jobs.complete` sets the job row to `completed` (`jobs.py` lines 203–217), and the worker applies that after the handler returns (`worker.py` lines 110–119). The worker sets `analyzing` at start and `failed` or `cancelled` on the way out (`worker_handlers.py` lines 233–270). The provider receives JPEG bytes and WAV bytes, not the file path (`video_analysis.py` lines 526–539). Frames require a JPEG magic header (`video.py` lines 256–268). Audio is 16 kHz mono PCM (`video.py` lines 19 and 200–218). `readiness` labels the send as `sampled JPEG frames + 16kHz mono WAV` (lines 73–74).

Annotate runs before `llm.structure` (`creative.py` line 1086, then 1130). With no managed selection, the LLM slot is already the not-configured error. Publish does not happen. The draft is marked `failed` (`worker_handlers.py` lines 261–270). The vision call still ran.

`POST /api/ask` is the model call on the ask surface (`product.py` lines 905–936). `run_ask` passes `prov.llm` only in live mode (`worker_handlers.py` lines 125–138). Analyst ask, analyst creatives, and the analyst report do not call the model.

## Analyze Video wizard

Besides resume, these controls are wired:

- Card Upload opens a new panel (`VideoUploadCard.tsx` line 279). A dropped mp4 or mov opens the panel with that file (lines 166–173 and 265–269).
- Resume, Discard, Continue, View, Retry, Cancel Analysis, and Delete behave as in the Resume section. Cancel Analysis is shown only with `live_job_id` (lines 355–361) and posts cancel, then patches the draft. Delete asks, then deletes and forgets the stage.
- Choose file, Upload, Replace, and Remove (`VideoUploadPanel.tsx` lines 1440–1504). Upload calls media upload, validate, and a spec PATCH. Remove deletes draft videos first (lines 1105–1123).
- Creative key (lines 1431–1434). The placeholder `video-upload-sample` (line 1434) is hardcoded English.
- Client and campaign, catalogue or custom (lines 1515–1573), and confirm selection (lines 1547–1551).
- Platform (lines 1584–1587).
- Dataset file, CSV text, sheet picker, and Import (lines 1590–1628). Import posts the dataset and stamps `wizardStage`.
- Dataset version switch patches `dataset_version` (lines 1634–1638). The current option uses `datasetCurrent` (line 1646). Duration uses `durationValue` (line 1485). English is `{duration} Seconds` and `{name} (Current)`. Spanish is `{duration} s` and `{name} (actual)`. Polish is `{duration} s` and `{name} (bieżący)`.
- Match method, Propose, Confirm, and row checkboxes (lines 1777–1798 and 1865–1887). Changing the selection or the creative key drops a confirmed match locally.
- Back and Continue call `goStage` (lines 1902 and 1913). Save Draft calls `persistSpec` and re-confirms a held match (lines 1906–1910 and 930–952).
- Analyze posts `/api/drafts/{id}/analyze` (lines 1349–1370). `canAnalyze` (lines 1321–1322) requires a valid video, a confirmed client and campaign, a confirmed match, and a draft that is not `queued` or `analyzing`. It does not read `providerStatus`. The comment at lines 1317–1320 says the readiness block is display-only and the server 409 is the gate. The client comment in `videoUploadApi.ts` lines 290–294 says the submit stays disabled until vision is configured. The button does not do that.
- Findings seek, correct, accept, reject, and Mark reviewed call the correction and review endpoints (lines 1813–1858).
- The provider line (lines 1711–1729) is display-only, from `GET /api/providers/status`.

The step chips (lines 1404–1417) are text, not buttons.

`METHOD_LABELS` is fixed English (lines 98–104): Platform ID, Exact Filename, Explicit Tag, Fuzzy Filename, Manual. Moment flags are fixed English (lines 201–205): Brand, Product, Logo, CTA, End.

## Assets

`GET /assets/{name}` (`product.py` lines 2849–2870) serves `.png` from `REACT_ASSETS_DIR` first, because `.png` is in `_ALLOWED_DIST_EXTS` (lines 2796–2797). A missing dist file raises 404 (lines 2856–2858) and does not fall through to `ASSETS_DIR`. Brand files live in `Web/assets` and are served by `/foap-logo.png`, `/foap-mark.png`, and `/favicon.png` (lines 2880–2900). The React shell uses those dedicated paths. `GET /assets/favicon.png` and `GET /assets/foap-logo.png` 404 unless a hashed build has copied those exact names into the dist assets directory.

## Defects still true

P1. The campaign drawer calls `GET /api/campaigns/${name}` (`CampaignsPage.tsx` line 361). No such route exists. The drawer shows the client’s “Request failed (404)”.

P1. Campaign Export, Creative Export, and Benchmark Export post to `/api/exports/campaigns`, `/api/exports/creatives`, and `/api/exports/benchmarks`. Those routes are not registered. The only export route is `POST /api/export`.

P1. Group By Format asks for `group_by=format` (`BenchmarksPage.tsx` lines 31–33). `GROUPABLE` does not include `format` (`benchmarks.py` lines 10–11). The results panel shows the benchmark error.

P1. On Providers, a 409 from Save Key, Save Base URL, Remove Key, or Refresh Models is stored as a deactivate retry (`ProvidersPage.tsx` lines 499, 523, 549, and 598). Retry then calls `runDeactivate` (lines 246–259) with no second confirm. The backend uses 409 for a long secret, an unsafe base URL, a failed validation of the active key, and a refresh with no stored secret, not only for a revision conflict.

P2. Compare does not redraw results when the shared scope changes while the page stays mounted (`ComparePage.tsx` lines 377–409 and 411–434). The trend chart aligns days by index (`ComparePage.tsx` lines 517–531, `charts.tsx` lines 51–58 and 85–86).

P2. Compare copy listed in that section stays English in Spanish and Polish.

P2. Reports with every campaign unchecked send `campaigns: null` (`ReportsPage.tsx` line 447), and the report then includes every campaign still in scope (`actions.py` line 1217, `benchmarks.py` lines 839–841).

P2. Creative checkboxes do not change Export or open a compare. Grid view cannot open a creative. Dashboard “Open in Creatives” drops the creative key. Campaign “vs. Benchmark” is one shared number, or Unavailable. Campaign search ignores a later `?find=` while the page stays mounted.

P2. Dashboard length bars compare each bucket with itself, and duration `0` is dropped. Creatives shows duration `0` as “—” (`CreativesPage.tsx` line 119). Money on Dashboard, Campaigns, and Ask is USD. The dashboard date window is the first and last day of the latest 30 dates with rows, written into the shared scope, not Settings’ Default Date Range.

P2. Several failures render as a skeleton or as an empty state: dashboard charts and recommendations, campaign platform bars, daily series, Insights cards, and the Workbook preview. Insights filters do not filter the panels their labels name. Saved Analyst conversations and the Ask deep link do not load messages.

P2. The Analyst date select can read All Time while the shared date filter is still applied. Reset does not clear Objective or Language. Clear does not clear shared filters.

P2. Settings action failures are stored and then not rendered (`SettingsPage.tsx` line 619). A failed Google status check paints the SSO row as Connected. Theme follows the global `ci-theme` key, not the employee whose prefs stored it. Workspace name, default view, currency, date range, campaign view, notification toggles, and privacy toggles stay on Settings.

P2. The paused-provider banner says AI Analyst is paused. Analyst does not check the provider. Ask does fail closed with the administrator sentence.

P2. Vision readiness is not “a configured vision key.” `eligible_vision_roster` returns empty when `LiveBundle()` cannot construct an STT adapter. Unverified vision roster ids are still advertised as configured, and the not-ready reason can be the generic live-mode sentence. Activating the managed model does not enable frame analysis.

P2. `GET /assets/favicon.png` and `GET /assets/foap-logo.png` 404 through the dist-only `.png` branch. The shell uses `/favicon.png` and `/foap-logo.png`.

P3. Analyze is offered when the status line says vision is missing (`VideoUploadPanel.tsx` lines 1321–1322). The server 409 is the real gate. A paused managed LLM is discovered at structuring, after vision has been called.

P3. Wizard method labels (`VideoUploadPanel.tsx` lines 98–104) and moment flags (lines 201–205) stay English. The creative-key placeholder `video-upload-sample` (line 1434) stays English. Duration and the current-dataset label are localized.

P3. Provider cards show “Activating…” for every in-flight action. Workbook and spreadsheet downloads, and avatar upload, bypass the API client’s 401 gate. Add Employee’s loading label, several Settings option lists, and the Analyst language options are hardcoded English. A workspace name left within 450 ms is dropped. Cohort Create has no in-flight lock. Create Team does not appear in the employee table. Unavailable pills share the Connected color. The Insights empty titles share one string. Reports’ Save as Template is never read. Benchmark Select All exceeds the three-row chart cap without a status.

## Checks not performed

No server, browser, Playwright, Render click-through, live provider, ffmpeg run, or the five Notino clips. The UI suite and the backend suite were not re-run for this file. The four backend failures from the last full run, on Python that this push does not change, were `tests/test_ci_app.py::test_security_headers_health_readiness` (`ModuleNotFoundError: No module named 'tests'`), `tests/test_ci_app.py::test_no_licensing_concepts` (the walker does not skip `.venv`), and `tests/test_web_shell.py` `test_favicon_asset_serves` plus `test_logo_and_mark_assets_serve` (404 on `/assets/favicon.png` and `/assets/foap-logo.png`). The 404 string for the campaign drawer is what `client.ts` produces for a non-OK response whose JSON has no `error` field. It was not observed on a running API. Export failure is from the missing route, not from a captured HTTP response. Spanish and Polish catalogs were checked for missing keys on the Ask, Analyst, Settings, Admin, and Providers slice only. They were not opened line by line for Compare.
