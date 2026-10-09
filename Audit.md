# Creative Intelligence audit for 2026-10-09

Review `origin/main` after `git fetch`. Confirm that `origin/main` and GitHub `main` name the same SHA. A behind local checkout or a missing local `main` branch is not a reason to stop. Use `git show origin/main:PATH`. Stop only if the remote identities differ or the worktree is dirty.

This is the product repo https://github.com/888-Sniper/Creative-Intelligence. The parent of this push is `dc02927d16d2353f059f61e88b6ce11c4d1e4a14` (`Fix the ready audit defects and name the Render site in the docs`). This push makes `pnpm exec tsc --noEmit` pass, drops a Compare response that is no longer the latest request, and replaces `Audit.md` in the same push. Do not call the product perfect. Do not edit, commit, push, build, install, start the server, or activate a provider. Do not treat an unrun live model, live browser, Playwright run, Render click-through, or the five Notino clips as a source defect. Report only defects still present at the reviewed SHA, with severity, observed behavior, file and line, and the evidence that reproduces them.

Confirm this push with both ends named:

```
git diff --stat dc02927d16d2353f059f61e88b6ce11c4d1e4a14 origin/main
```

The ready-audit commit and the day's earlier product commits are already inside that parent. The day starts after `a765cfc143a163fcafa679dfe327aad23c078fc1` (`Treat string creative export filters as one value`, 2026-10-08). Confirm them with:

```
git log --oneline a765cfc143a163fcafa679dfe327aad23c078fc1..dc02927d16d2353f059f61e88b6ce11c4d1e4a14
```

## This push

`Backend/creative_intelligence.egg-info/` stays untracked and is not in this push. Do not say Render, WorkOS, or Google Cloud already use the callback values saved in `render.yaml`. Saving that file does not change the running service or those consoles. A blueprint sync would apply the two redirect values. GitHub About is still https://www.foap.com. Render was not clicked. Do not say Render already shows this push.

Line numbers below were opened on this push. Do not report an item as open when the cited lines do what this section says.

1. `pnpm exec tsc --noEmit` passes. At the parent it failed six times: `CreativesPage.tsx` compared a numeric duration with `""` and then used a `number | null` as a number, and `DashboardPage.tsx` compared a numeric duration with `""`. `secondsOf` (`CreativesPage.tsx` lines 72–76) returns that finite number, including `0`, or `null`. The length filters require `s != null` before comparing (lines 221–223). The learnings loop skips `null` before the bucket test (line 343). Dashboard duration rows accept only a finite number that is at least `0` (`DashboardPage.tsx` line 322), so `0` stays in Under 15s. A missing duration is still skipped. The learnings short bucket still requires `s > 0` (`CreativesPage.tsx` line 337).

2. A Compare response is stored only when it is still the latest request. `compareGen` (`ComparePage.tsx` line 293) increments at the start of `runCampaigns` (line 302) and `runCreatives` (line 333). The campaign result is applied only while `gen` is current (lines 318, 323, and 327). The creative result uses the same check (lines 348, 356, and 360). A shared-scope change still starts a new comparison (lines 422–437). An older campaign response that finishes after that change does not replace the newer result. Period comparison was not given this check.

Checks for this push. `pnpm exec tsc --noEmit` passed. `ComparePage.test.tsx`, `CreativesPage.test.tsx`, and `DashboardPage.test.tsx` passed 24, including “keeps the newer filtered comparison when an older request finishes later”. The signed-in app was not opened. `vite build` was not run. The full UI suite and the full backend suite were not re-run. Render was not clicked.

Still open after this push: everything still listed under On the parent `dc02927`, apart from the TypeScript build and the late Compare response. The Creatives learnings length bucket still requires `s > 0` (`CreativesPage.tsx` line 337).

## On the parent `dc02927`

`Backend/creative_intelligence.egg-info/` stayed untracked and was not in that push. Do not say Render, WorkOS, or Google Cloud already use the new callback values. Saving `render.yaml` does not change the running service or those consoles. A blueprint sync would apply the two redirect values. GitHub About is still https://www.foap.com. Render was not clicked for that push. Do not say Render already shows it.

Line numbers below describe that parent. Where This push edits the same file, use the lines in This push. Do not report an item as open when the cited lines do what this section says.

1. Admin stat cards are Active Users, Total Admins, Total Employees, Pending Approvals, in that order (`AdminEmployeesPage.tsx` lines 393–399). The lock card title is `admin.stats.totalAdmins` (`en.ts` line 645, “Total Admins”). Spanish is “Administradores totales” (`es.ts` line 645). Polish is “Wszyscy administratorzy” (`pl.ts` line 659). The team-panel heading stays “Admins (n)” (`AdminEmployeesPage.tsx` line 661, `admin.stats.admins` at `en.ts` line 644). The role label stays Admin.

2. Google Drive body is “Read-only access to creatives.” (`en.ts` line 1647). Spanish is “Acceso de solo lectura a creatividades.” (`es.ts` line 1647). Polish is “Dostęp tylko do odczytu do kreacji.” (`pl.ts` line 1661). The card title and actions share one row. The body sits under the title (`GoogleDriveCard.tsx` lines 95–99).

3. Two-factor body is “Use an authenticator app for a second sign-in step after your password.” (`en.ts` line 1727). Spanish is “Usa una aplicación de autenticación para un segundo paso de inicio de sesión después de tu contraseña.” (`es.ts` line 1727). Polish is “Użyj aplikacji uwierzytelniającej jako drugiego kroku logowania po swoim haśle.” (`pl.ts` line 1741). The parent’s English sentence was the shorter “Use an authenticator app for a second sign-in step.”

4. Dark-mode service-logo tiles use `var(--shell-bg)` (`theme.css` line 939). Light mode stays `#E8EDF3` (line 938). A black mark uses `.svc-logo-ink` and inverts in dark mode (line 940, `IntegrationCards.tsx` lines 87–88). Provider-page tiles were not changed (`ProvidersPage.tsx` still notes the fixed light tile).

5. The Settings Theme select shows the painted mode, `liveThemeMode` (`SettingsPage.tsx` line 985). `adoptPrefs` (lines 89–93) uses that mode when it disagrees with a saved theme string. A later header change is written back (lines 262–268). `useTheme` publishes `ci-theme-change` so a second hook shares the mode (`useTheme.ts` lines 7–11 and 54–62). Choosing Light (Default) while the page is dark is a real change and clears `data-theme`. The selected sidebar item uses `#0B1F2A` for the label and the icon, at weight 700 (`theme.css` lines 871–872 and 906–907). Unselected items stay on `--shell-navy`.

6. An empty report campaign list does not mean every campaign. The page sends `campaigns: checkedCampaigns` (`ReportsPage.tsx` line 449). Generate returns and the button stays disabled when that list is empty (lines 537–539 and 673). `expert2_report_route` (`actions.py` lines 1406–1413) keeps omitted or null as every campaign in scope, and an explicit empty list raises `Select at least one campaign.` Compare still uses `campaigns or None` (`actions.py` line 1365) and was not changed. English labels are “No Campaigns Selected” and “Select At Least One Campaign.” (`en.ts` lines 230–231). Spanish and Polish have the matching report keys.

7. `GET /assets/{name}` serves a dist file when it exists (`product.py` lines 3014–3021). A missing dist file with extension `.png`, `.svg`, `.ico`, or `.webp` is served from `ASSETS_DIR` with `max-age=86400` (lines 3025–3031). `.js`, `.css`, and `.woff2` still 404 when missing from dist. `/favicon.png`, `/foap-logo.png`, and `/foap-mark.png` are unchanged.

8. A failed profile save stays on screen after the button is enabled again. `saveProfile` clears status first (`SettingsPage.tsx` line 355) and the status span renders whenever `status` is non-empty (lines 712–714). A failed Google check on a Google account shows “Could not check status.” and Retry (`en.ts` line 1655, `SettingsPage.tsx` lines 789–794). It does not show Connected. Not Connected uses `pill-bad` (line 799). A non-Google provider still shows Connected with `pill-ok` (line 801).

9. Compare redraws the open comparison when the shared scope changes after the first boot (`ComparePage.tsx` lines 422–437). Trend points use the sorted union of campaign dates (lines 538–562). A missing day or an uncomputable ROAS, CTR, CPA, or CPM is `null`. `TrendChart` breaks the stroke at null (`charts.tsx` lines 32 and 59–76). Compare’s hardcoded English strings were not translated. At this parent the redraw could still be overwritten by an older response. This push drops that response.

10. Creative export sends the checked keys when any row is checked, and otherwise every visible row (`CreativesPage.tsx` lines 394–408). A grid card is a `div` with `role="button"` (lines 658–669) because the card contains a paragraph. `secondsOf` returns `0` for a measured zero and `null` when duration is missing (lines 72–76). The short length filter includes `0` (line 221). The duration label uses `0s` rather than “—”. The learnings length bucket still requires `s > 0` (line 337), so a zero duration is still left out of that bucket. Whether a creative link drops a selection was not rechecked after this edit.

11. Dashboard length bars use the combined click rate across buckets as the benchmark (`DashboardPage.tsx` lines 352–360). A duration of `0` stays in Under 15s (lines 316 and 322). A missing duration is still skipped. Open in Creatives includes `?find=` for the creative key (line 720). Currency on Dashboard stays USD. The dashboard date window still ignores Settings’ Default Date Range.

12. Campaign search fills from a later `?find=` while the page is mounted (`CampaignsPage.tsx` lines 110–114). Campaign “vs. Benchmark” was not changed.

13. README, `docs/RENDER.md`, and `render.yaml` name https://creative-intelligence-0t0c.onrender.com as the live site. `render.yaml` lines 50–53 set `CREATIVE_INTEL_WORKOS_REDIRECT_URI` and `CREATIVE_INTEL_GOOGLE_REDIRECT_URI` to the Render callbacks. `docs/ORACLE_ALWAYS_FREE.md` says that document is the separate Oracle VM. DuckDNS stays in the Oracle files. The running Render service, the WorkOS dashboard, and Google Cloud were not edited.

Checks on that parent, each aimed at the edit it names. They were not one suite, and they were not re-run as a group at the end. `tests/test_deploy_config.py::test_live_site_is_render_and_oracle_keeps_duckdns` passed. `tests/test_request_schemas.py::test_report_empty_campaign_list_is_not_every_campaign` and `tests/test_web_shell.py` `ShellLiveTest` `test_favicon_asset_serves` and `test_logo_and_mark_assets_serve` passed together (3). `ReportsPage.test.tsx` passed 14, and `src/i18n/parity.test.ts` passed 2 after the report strings and again after the two-factor sentence. `SettingsPage.test.tsx` passed 36, including the dark `ci-theme` with a saved light preference, and a second theme hook. `CreativesPage.test.tsx` and `CampaignsPage.test.tsx` passed 17. An earlier Compare, Dashboard, and Campaigns run passed 21, before the creative edits, and was not repeated after them. A browser render of `theme.css` measured the selected nav link as `rgb(11, 31, 42)`, weight 700, with the icon the same color, on `rgb(0, 199, 178)`, at desktop width, at 390px, and with `data-theme="dark"`. The signed-in app was not opened for the theme menu, the two-factor sentence, the report checklist, compare, creatives, or the admin cards. Ruff was not run on these edits. The full UI suite and the full backend suite were not re-run. `pnpm build` was not run for them.

Still open after that parent: Compare Spanish and Polish copy. A recheck of `dc02927` also found the six TypeScript errors and the late Compare response. This push fixes those two. Campaign “vs. Benchmark”. Dashboard currency and the Settings date window. Failed requests that look like a skeleton or an empty state, and Insights filters that do not control the panels their labels name. Analyst saved conversations, All Time against a date filter, reset, and the provider pause. Settings Export Data, preferences outside Settings, and notification email. Vision readiness, the Analyze button when vision is missing, and a paused model found late. The lower-priority copy, loading text, and incomplete controls in Defects still true. Google Drive owner binding and a GA4 row import were not started. The Creatives learnings length bucket still requires `s > 0` (`CreativesPage.tsx` line 337). A creative link dropping its selection was not rechecked.

## Fixed on the parent

These four were fixed at `da25a6e`. Do not report them as open unless the cited lines no longer do what this file says. Render was not clicked for them. Do not say Render already shows them.

1. A same-domain email edit no longer lets another WorkOS identity sign into that account. `update_profile` still stores the new address and leaves the WorkOS id unchanged (`employees.py` lines 713–726). `ensure_identity` (lines 278–285) signs an identity in only when the stored WorkOS id matches, or when the row has no WorkOS id and the address was not rewritten by a profile edit (`_profile_changed_email`, lines 242–255). A mismatch raises `That email is already registered.` and does not open a session. A pre-added employee whose address was never edited still links on first verified sign-in. The same WorkOS user can still sign in after the edit.

2. One recovery code opens one session when two checks overlap. `take_challenge` deletes the challenge in the same transaction as the compare-and-swap (`totp.py` lines 380–386). The hash removal is `_claim_recovery` (lines 199–216). The second check changes no row, returns 409 `That code is not valid.`, and does not create a session. A fresh authenticator step uses the same kind of update on `last_step` (`_claim_step`). Confirm and Turn Off still use `_accept_code`. Wrong-code attempts are counted on the parent. `_spend_attempt` (`totp.py` lines 332–350) adds one with a single `UPDATE` while `attempts` is below four. The attempt that finds the row already at four deletes the challenge. Five overlapping wrong codes, and five in a row, leave no challenge. Four failures leave it. `tests/test_two_factor.py` passed 7 on that parent. Ruff passed on `totp.py` and that test.

3. An integration callback stores tokens only for the employee who started it. `integration_start` passes that employee into `start` (`integrations.py` line 47). The pending verifier is bound to that id (`integrations_oauth.py` `_bind_owner`, lines 59–66). `finish` (lines 307–309) refuses a different signed-in employee, does not exchange the code, and does not write `oauth_tokens`. The callback redirects to `/settings?integration={provider}&result=failed`. The state cookie alone is not the owner.

4. A scheduled Meta or TikTok import uses the job owner's connected token. `_job_bearer` (`sync.py` lines 434–451) asks the resolver for `meta` and `tiktok`, and for sheets or drive jobs that set `google_auth`. `_google_bearer_resolver` (`main.py` lines 31–39) returns `integrations_oauth.access_token_for` when that owner is connected, and `None` when they are not, so the workspace `CREATIVE_INTEL_KEY_META` / `CREATIVE_INTEL_KEY_TIKTOK` path still runs. A connected token that cannot be read raises, and `tick` records that error on the job. The token is not saved in job params. GA4 still has no import route.

Checks for that parent: `tests/test_ci_auth.py`, `tests/test_two_factor.py`, and `tests/test_integrations_oauth.py` passed, including the overlapping recovery-code case, the foreign OAuth callback, and the scheduler resolver. `tests/test_sync.py` TickBearerTest, JobsTest, and the connect-meta upsert passed. The connect-meta fake accepts `bearer`. `tests/test_google_oauth.py::test_scheduler_resolver_refreshes_expired_token` passed. Ruff passed on the edited Python files. That run was 51 tests. The full UI suite and the full backend suite were not re-run. UI files were not edited. `pnpm build` was not run.

## Adjustments on main for 2026-10-09

These seven commits are already on the parent. Do not report them as missing unless the cited lines no longer do what this file says. Email sign-in, recovery consumption, the integration owner, and scheduled ad tokens were amended at `da25a6e`. Overlapping wrong-code attempts are on the parent `7a9440a`. Render was not clicked for any of them. Do not say Render already shows them.

1. `0be9464e99ca9e4c23185240f900390e7af89adc` — Let earlier analyze video steps open from the step chips. A step chip earlier than the open step is a button and calls `goStage` (`VideoUploadPanel.tsx` lines 1406–1415). The current step and later steps are text (lines 1418–1429). From Review, Video, Client & Campaign, and Dataset open those steps. Continue still moves one step forward.

2. `fb2b75beeb5d88c2685c170528b1e9b6ad1e60d6` — Hide the standing analyze video notes. The wizard does not render “Changing The Client Or Campaign Clears The Confirmed Match.”, “No Dataset Yet.”, or “Add And Validate A Video To Enable Analysis.” (`VideoUpload.test.tsx` lines 444, 447, and 451). Analyze stays disabled without a valid video (`VideoUploadPanel.tsx` lines 1321–1324). Changing a confirmed client or campaign still clears the match.

3. `0ffd7bd53f7edf2270e2f7b8fd85352010078bd8` — Make the video file limit line a touch smaller. The line under Choose File is 12px through `.vu-limits` (`theme.css` line 1037, `VideoUploadPanel.tsx` line 1469). Other `panel-sub` text stays 13px.

4. `97a1df87e8f30e1ba95c132b8ea3d78a77843327` — Rename the page headings. `/admin` is “Admin Settings” (`en.ts` `admin.title`, line 631). Spanish stays “Ajustes de administración” (`es.ts` line 631). Polish stays “Ustawienia administracji” (`pl.ts` line 645). `/settings`, including the `/profile` redirect, is “Profile Settings” (`en.ts` `settings.title`, line 1660). Spanish stays “Ajustes del perfil” (`es.ts` line 1660). Polish stays “Ustawienia profilu” (`pl.ts` line 1674). The sidebar links stay “Admin” and “Settings” (`en.ts` lines 619 and 620).

5. `95e2e8309beed63eab04c0439ec6886c44c649c8` — Let an employee change email on the same domain. The button is Edit Email (`en.ts` line 1678). Save Email patches `{ email }` to `/api/auth/me`. The full domain after `@` must match, exact and case-insensitive (`employees.py` lines 713–726, route at `auth.py` lines 78–81). A different domain shows `Use another {domain} address.` and does not send the patch (`SettingsPage.tsx` lines 402–404). That sentence stays in a `role="alert"` (lines 620–622). A duplicate returns `That email is already registered.` The WorkOS id stays. A different WorkOS identity cannot sign in through the new address. See Fixed on the parent. Personal Info still edits the name. Upload Photo stays.

6. `cb2fcb691d8e154260809e40421bbb7ef0cd52d1` — Capitalize the analyst suggestion label. The label is “Try Asking:” (`en.ts` `analyst.tryLabel`, line 357). The accessible name is “Try Asking” (`tryAria`, line 356). Spanish stays “Prueba a preguntar:” (`es.ts` line 357). Polish stays “Spróbuj zapytać:” (`pl.ts` line 363). The chips still send `analyst.tryAsking.t0` through `t3`.

7. `3850a1acfa16e184bed096870da12e5dd20df93f` — Add settings integrations and two-factor sign-in.

- Two-Factor Authentication on Profile Settings is an authenticator-app step (`TwoFactorCard.tsx`). Set Up stores a pending secret and shows it once (`totp.py` `begin_setup`). Confirm with a current 6-digit code turns it on and returns eight recovery codes once (`confirm_setup`). Cancel deletes only a pending row. Turn Off requires a current code or a recovery code. A wrong code returns 409 `That code is not valid.` The secret is encrypted. Recovery codes are stored as sha256 hashes. Sign-in consumes one code with a compare-and-swap, including when two checks overlap. See Fixed on the parent. The same time step cannot be reused (`last_step`). The body is “Use an authenticator app for a second sign-in step after your password.” (`en.ts` line 1727). See On the parent `dc02927`.
- Sign-in paths that issue a session go through `open_login` (`oauth.py` lines 68–84). When two-factor is on, they set cookie `ci_2fa` for 300 seconds and do not set `ci_session`. The Google callback redirects to `/?mfa=1` (`auth.py` lines 253–257). JSON email and OAuth finish return `{ok:true, authenticated:false, gate:"mfa"}`. `POST /api/auth/2fa/verify` with that cookie and a valid code creates the session and sets `last_login_at` (`two_factor.py` lines 91–120). Five wrong attempts drop the challenge even when those failures overlap (`totp.py` `_spend_attempt`, lines 332–350). An expired cookie or a disabled authenticator drops it too. `login_identity` itself still creates a session. The login screen shows Authenticator Code and Verify only when `?mfa=1` was in the address or the email sign-in returned that gate (`AuthScreens.tsx` `TwoFactorPrompt`, `LoginPage`). The default Welcome Back screen does not show Verification Code until Use A Sign-In Code Instead.
- Integrations are Meta Ads, TikTok Ads, and Google Analytics 4 (`IntegrationCards.tsx`). Each row has Connect or Disconnect. The accessible name is “Connect Meta Ads”, “Connect TikTok Ads”, or “Connect Google Analytics 4”. The visible word stays Connect. Connect posts `POST /api/auth/integrations/{provider}/start` and navigates to the returned URL. A missing client id, redirect, or client secret returns 409 `{Name} is not configured.` and does not mark the row connected. Status is `GET /api/auth/integrations/{provider}/status`. Disconnected is exactly `{"connected": false}`. Connected may add `account` and `scope`. The linked account is a separate line only when `account` is non-empty. Disconnect posts `.../disconnect`. The callback lands on `/settings?integration={provider}&result=connected|failed|expired`.
- Meta uses the Facebook dialog and `ads_read` (`integrations_oauth.py`). TikTok uses the business portal and `auth_code` or `code`. GA4 reuses the Google client id and secret, PKCE, and scope `https://www.googleapis.com/auth/analytics.readonly`. Tokens stay encrypted in `oauth_tokens` for that employee. `account_ref` is the discovered ad account or GA4 property, never the token. GA4 has no import route. Connecting GA4 does not import rows. A connected Meta or TikTok token is attached to the existing `connect-meta`, `connect-tiktok`, and `sync-now` jobs as `_ads_bearer` and removed before the job is saved (`product.py` `_attach_ads_token`, lines 2749–2773, stripped at line 2857). A scheduled run of those sources uses the job owner's connected token. See Fixed on the parent. No connection leaves the workspace `CREATIVE_INTEL_KEY_META` / `CREATIVE_INTEL_KEY_TIKTOK` path alone. The callback stores that token only for the employee who started the connection. A connected account whose token cannot be read fails the import. Those key names are not the OAuth client secrets. The OAuth secrets are `CREATIVE_INTEL_META_CLIENT_SECRET` and `CREATIVE_INTEL_TIKTOK_CLIENT_SECRET`. Client ids and redirect URIs are `CREATIVE_INTEL_META_CLIENT_ID`, `CREATIVE_INTEL_META_REDIRECT_URI`, `CREATIVE_INTEL_TIKTOK_CLIENT_ID`, `CREATIVE_INTEL_TIKTOK_REDIRECT_URI`, and `CREATIVE_INTEL_GA4_REDIRECT_URI` (`config.py` lines 46–58). GA4 also needs `CREATIVE_INTEL_GOOGLE_CLIENT_ID` and the Google client secret.
- Alembic revision `0013` adds `oauth_tokens.account_ref` and the tables `employee_totp` and `totp_challenges`. It does not add columns to `employees`.

How those seven were checked, on the commits that introduced them: the step-chip Playwright test passed, including a 390px-wide dialog, and `VideoUpload.test.tsx` passed 29. The file-limit Playwright check read `font-size` 12px at desktop and 390px. Admin and Settings Playwright passed 3, and the page-title vitest file passed 50. Edit Email vitest plus locale parity passed 32, three auth tests passed, and `e2e/auth.spec.ts` passed 4, including the email editor at 1280px and 390px. Analyst vitest passed 17 and `e2e/analyst.spec.ts` passed 1. Integrations and two-factor: `tests/test_two_factor.py` and `tests/test_integrations_oauth.py` passed 9, related OAuth pytest passed 44, Settings plus locale parity plus auth vitest passed 64, and the Settings Playwright journey passed 1. `pnpm build` ran `tsc --noEmit` on the commits that changed the UI. The full UI suite and the full backend suite were not re-run for the day. This Audit.md replacement does not re-run them.

Re-read the cited files at `origin/main`. Line numbers in the inventory were opened on `3850a1a`. If a later commit moves a line, follow the symbol, not the stale number.

Four source reads covered the routed app: shell, sign-in, Dashboard, Campaigns, and Creatives; Compare, Benchmarks, Insights, Reports, and Workbook; Ask, Analyst, Settings, Admin, and the Providers screen; the model path and the Analyze Video wizard, including resume. The inventory line numbers were opened on `3850a1a`. This file re-read the symbols named in Adjustments on main for 2026-10-09. Unrouted files are not live tabs: `OverviewPage.tsx`, `layouts/AppLayout.tsx`, `components/FilterBar.tsx`, `components/AskBar.tsx`, `components/SyncJobs.tsx`. `router.tsx` does not mount them.

## Resume

The Resume button in `VideoUploadCard.tsx` line 294 still opens `{ draftId }` and does not pass a stage. That is the restore path. Do not report the missing `stage` argument as a defect.

Stages are `video`, `client`, `dataset`, and `review` (`VideoUploadPanel.tsx` lines 44 and 59, `videoUploadApi.ts` line 41).

On open, `VideoUploadPanel.tsx` lines 778–781 choose the step in this order:

1. `open.stage`, when the caller passed one. Recent Uploads View passes `review` and Retry passes `video` (`VideoUploadCard.tsx` lines 327–330). Those win.
2. The step stored for that draft id in `localStorage` key `ci-video-draft-stage:<employeeId>`. The value is a map of draft id to a stage (`readDraftStage` in `videoUploadApi.ts` lines 48–89).
3. `spec.wizardStage` (`storedStage` at `VideoUploadPanel.tsx` lines 71–72, field at `videoUploadApi.ts` line 196).
4. `stageForSpec` (`VideoUploadPanel.tsx` lines 61–66). Missing or invalid video returns `video`. Otherwise an unconfirmed client returns `client`. Otherwise no dataset returns `dataset`. Otherwise `review`. This is only the fallback.

Continue does not require those gates. The Continue button (`VideoUploadPanel.tsx` lines 1922–1924) is not disabled on them. Continue and Back call `goStage` (lines 1001–1007), which writes the stage map and then `persistLeaveFields`. Closing the dialog, the overlay, or Escape calls `leaveAndClose` (lines 1010–1019, overlay at 1387, close button at 1400, Escape at 851–852 through `closeRef` at 1021). Analyze calls `forgetDraftStage` and then `onClose` (lines 1365–1370). It does not use `leaveAndClose`.

The chosen stage is written in the same synchronous block as `setDraft` (lines 775–795), before `await loadRows` (line 812). A render cannot record the default `video` step over a stored later step.

A step-only leave does not PATCH. `persistLeaveFields` (lines 960–998) patches only when the client, campaign, creative key, or platform differs from the last saved spec. A confirmed match returns first unless the client, campaign, or creative key changed (lines 975–976), because any spec PATCH clears matches (`product.py` lines 2018–2022). `fieldSnap` treats a missing platform as `meta` on both sides (lines 75–86), so the default does not count as a change. Closing an unchanged wizard sends no PATCH and leaves a confirmed match in place.

Typed client, campaign, creative key, and platform are included when they differ, so Resume can show them again. `wizardStage` is stamped on `persistSpec` (line 907), upload (line 1082), import (line 1218), and the leave body (line 985). A video file that was chosen and never uploaded is not restored. CSV or XLSX text that was never imported is not restored. Boot clears that staged file and text (lines 728–740). An uploaded video and an imported dataset come back from the draft.

The same browser keeps one step per draft id. Opening a second draft does not erase the first. Delete forgets only that id (`VideoUploadCard.tsx` line 185). A successful Analyze forgets only that id. Switching accounts clears the previous account's map (lines 130–136). A dead pin forgets only that pinned id (line 120). The pin key `ci-video-draft:<employeeId>` is separate from the stage map.

In-progress Recent Uploads Continue also passes only `{ draftId }` (lines 383–384) and therefore uses the same stored step. View and Retry pass a stage and win over it.

## Shell and sign-in

Signed-in employees get `AppShell`. Nav labels come from `en.ts` `nav.*`: Dashboard, Campaigns, Creatives, Compare, Benchmarks, Saved Insights, Generated Reports, Blank Workbook, Ask The Data, AI Analyst, then AI Providers and Admin only when `me.is_admin`, then Settings (`AppShell.tsx` lines 10–27). Collapse is stored as `ci-shell-collapsed`. The brand mark goes to `/`. Open Menu, Close Menu, and Collapse Sidebar are local. The search box is `GlobalSearch.tsx`: after the first query it loads campaigns meta, creatives, and analyst creatives, and a submit goes to `/campaigns?find=`. Suggestion rows go to campaigns, creatives, or insights. The bell (`AppShell.tsx` line 117) goes to `/insights`. It is not an inbox. The dot at line 119 is always painted.

`/` is the dashboard. `/dashboard` replaces to `/`. `/profile` replaces to `/settings`. Admin and Providers are wrapped in `AdminOnly`. A non-admin sees “Admin Access Required.” `get_current_admin` in `deps.py` lines 90–98 returns 403, and `/api/admin` and `/api/admin/providers` use that guard.

`SampleScopeBanner` is mounted from `AppShell` and renders only while `ci-sample-scope` is valid. Return To My Scope restores the saved filters and removes that key.

Sign-in is email password, email code, or Google.

- Refresh Access (`AuthScreens.tsx` line 67) calls `GET /api/auth/me`.
- Log Out (`AuthScreens.tsx` line 70 and `AccountMenu.tsx` line 141) calls `POST /api/auth/logout`.
- Work Email, password, Remember Me, and Show/Hide Password are local. Remember Me writes `ci-remember-email`. The password-mode label “Work Email” is a literal at `EmailSignIn.tsx` line 146, not `auth.login.workEmail`.
- Sign In posts `/api/auth/email/signin`. Forgot Password posts `/api/auth/email/reset`. The success sentence is the English string at `AuthProvider.tsx` line 214.
- Use A Sign-In Code Instead is local. Send Sign-In Code posts `/api/auth/email/code`. Success copy is hardcoded at `AuthProvider.tsx` line 187. Verify & Sign In posts `/api/auth/email/code/signin`.
- When the password or code sign-in body has `gate` `"mfa"`, `AuthProvider.tsx` lines 170–172 and 199–201 set `mfaRequired` and do not call `afterLogin`. Verify posts `/api/auth/2fa/verify` (`verifyMfa`, lines 217–228). The Google callback with two-factor on goes to `/?mfa=1` without `ci_session`. With two-factor off, that callback still goes to `/` and sets `ci_session`.
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
- Open {name} in Creatives (line 707) goes to `/creatives` with no `?find=` and no creative key. Creatives already honors `?find=` (`CreativesPage.tsx` lines 200–207).
- Insight Type (line 725): Audience Retention, Hook Analysis, Video Length, Format Comparison. Local.
- Recommendation links in `InsightList` (`product.tsx` line 721) are plain `<a href>`: View Creatives and Explore Creatives go to `/creatives`, View Campaigns to `/campaigns`, See Recommendations to `/insights`.
- See All on recommendations (line 801) goes to `/insights`.
- Upload Video, Resume, Discard, and the Recent Uploads row are the wizard card. See Resume and the wizard section.

Video Length sets `bench` equal to `yours` (`DashboardPage.tsx` lines 345–347), so the bars compare each bucket with itself. Duration `0` is dropped before bucketing (line 322, `if (!seconds) continue`).

Top Creatives, the benchmark chart, and the recommendation rail stay on `Skeleton` when `data` is null (lines 634–654, 665–718, 803–807), including after an error. Hook and format tabs treat a failed fetch as the empty copy.

## Campaigns

Campaigns loads the campaign list, benchmarks, meta, compare, and daily endpoints. Status and spend bands are real scope axes. The backend resolves them into a campaign allowlist. The name search is local.

`GET /api/campaigns/{name:path}` (`product.py` lines 205–220) is the drawer. `_campaign_path_name` (lines 189–202) takes the name from one decode of the raw request target, so a slash stays a slash and a literal `%20` stays `%20`. `campaign_detail_payload` (`actions.py` lines 653–705) strips the name, resolves the query as a scope, and reads `benchmark(..., "campaign")`. A name that is not in that grouping returns `None`. The route then answers 404 with `error` set to `No campaign matches the current filters.` `app.py` lines 39–42 unwrap a dict `detail`, so the JSON body is that `error` field. The same query is then copied and its campaign axis is set to that one name (`actions.py` lines 673–676). `build_creatives_list` sums only the ads in that campaign. A confirmed match still replaces key equality, the same way the Creatives page does. Each row has `creative_key`, `campaigns`, `platform`, `format`, `metrics`, `brand_seconds`, and `product_seconds`. They sort by impressions descending and stop at 25. Recommendations are the CPA bullet texts from `campaign_recommendations`, flattened to strings. An empty name is 409.

`/api/campaigns/meta` (line 157) and `/api/campaigns/recommendations` (line 171) are registered before `{name:path}`. A campaign whose name is exactly `meta` or `recommendations` still hits those static routes. `scopedPath` (`client.ts` lines 104–143) appends the shared filter scope to a campaign drawer. The path is compared without its query (lines 108–111). The exact bases `/api/campaigns/meta` and `/api/campaigns/recommendations` are not drawers. A name that only begins with `meta` or `recommendations` is a drawer and keeps the filters. The recommendations route still receives them, because line 121 matches that prefix on its own.

The three table exports are registered before the catch-all `POST /api/{action:path}` (`product.py` lines 2621–2628). They are not entries in `_ACTION_ROUTES` (lines 964–975). `POST /api/export` (line 1536) is still the one-pager and still requires 1–50 creative keys.

Controls:

- Apply Filters and Reset Filters (lines 411 and 414). Reset also clears the name search.
- Client, Spend Range, KPI Focus, Campaign Objective, Team, Market, Campaign Status, Platform (lines 425–502). KPI Focus is not sent. Objective options are raw meta strings, not `filters.objectives.*`.
- How Campaign Status Is Determined is an `InfoTip` (line 484). Local.
- More Filters / Fewer Filters (line 505) reveals Project, Vertical, and Funnel Stage. Those selects write the shared scope.
- Platform Metric (line 585): Spend, Impressions, or Clicks. Local.
- Search Campaigns (line 606). `?find=` is copied only into the initial state (lines 108–109). A later navigation to the same route does not update the box. Global search uses that query (`GlobalSearch.tsx` lines 130–132).
- Compare Selected (line 614) goes to `/compare` with the selected names. One campaign is enough. An empty selection only sets a status line. The compare page asks for two to four.
- Export (line 616) posts `/api/exports/campaigns` (lines 336–340) with `{ names, filters: scopeBody(scope) }` and downloads `campaigns.csv`. The route (`product.py` lines 1492–1504) requires a non-empty name list. An empty list is 409. Names absent from the scoped campaign group are omitted. A header-only file is still 200. The response is `text/csv; charset=utf-8` with `Content-Disposition: attachment; filename="campaigns.csv"`. A string cell that starts with `=`, `+`, `-`, or `@` is prefixed with a quote (`actions.py` lines 708–718). Numbers stay numbers. At most 500 names.
- Select All and the row checkbox are the compare selection.
- Details (line 669) opens the drawer. The effect (lines 358–381) clears that name’s payload, then calls `GET` `scopedPath(/api/campaigns/${encodeURIComponent(name)}, scope)`. It runs again when the open name or the scope changes. Success stores the detail and clears that name’s error. Failure stores `ApiError.message` (lines 375–378). `EmptyState` prints it (lines 734–735). A 404 from this route carries `error`, so the drawer shows `No campaign matches the current filters.` The client’s `Request failed (${status})` (`client.ts` lines 32–33) is only for a non-OK body that has no `error` field.
- Delete Sample, Confirm Delete, and Cancel (`SampleDelete.tsx` lines 105–123) are admin-only and sample-campaign-only. They call the demo-pack impact and campaign-delete routes.
- Retry (line 686) refetches a failed campaign list.
- See All (line 742) goes to `/insights`.
- Rail links (lines 230–267) are `<a href>`: View Campaigns reloads `/campaigns`, View Recommendations goes to `/creatives`, See Insights to `/insights`, View Details to `/compare` with no campaign state.

“vs. Benchmark” is one shared number. `benchVal` comes from `focus.metrics[kpiKey].current` (lines 385–387). `focus` is filled only from `location.state` (lines 126–144). Every row prints that same value (line 666). With no navigation state the cell is Unavailable.

A failed daily series becomes `[]` (`useDaily` in `product.tsx` line 190). That array is truthy, so the trend still mounts `TrendChart` (lines 571–579). The skeleton at line 580 is only while `daily` is null. Platform bars stay on `Skeleton` when `benchPlatform.data` is null (line 599) and use `EmptyState` when the groups are empty (line 598).

## Creatives

Creatives loads `/api/creatives`, compare KPIs, and a retention curve for the open row.

Controls:

- Apply Filters and Reset Filters (lines 431 and 434). Reset also clears sort, view, length, benchmark, selection, and the open detail.
- Video Length and Benchmark (lines 457 and 466) are local. Length filters the rows already returned. Benchmark only changes the badge.
- See All on Top Creatives (line 527) navigates to `/creatives`, the current page.
- List View and Grid View (lines 564 and 569). Grid cards are not buttons and do not open the detail (lines 650–669).
- Sort By (line 575): Top Performing, Highest CTR, Highest ROAS, Most Impressions. Local.
- Export (line 579) posts `/api/exports/creatives` (line 404) with `{ creative_keys: keys, filters: scopeBody(scope) }` for every visible key. The checkboxes are ignored. The route (`product.py` lines 1507–1521) requires a non-empty key list, keeps request order, skips a key that is not in the scoped list, and downloads `creatives.csv`. An empty list is 409. A header-only file is still 200. At most 500 keys. An explicit empty campaign list matches nothing, so the file is header-only (`actions.py` lines 778–779). A string value is one filter. `_list_filters` (lines 755–763) wraps it into a one-item list before the lookup at line 778. An empty filter object is still unrestricted.
- Select All and the row checkbox write `selected` (lines 188 and 618). `selected` is only read to paint the checkbox (line 389). `creatives.compareSelected` exists in `en.ts` and is not rendered.
- The creative name (line 623) toggles the detail panel and loads `GET /api/retention/curve`.
- See All on Top Learnings and on Next Tests (lines 685 and 706) go to `/insights`. Next Tests are three fixed sentences (lines 376–380) whenever any creative is in scope.

`secondsOf` returns a real zero (`CreativesPage.tsx` lines 72–73). The detail then uses a truthiness check: `secondsOf(datum) ? ... : "—"` (line 120). The length column does the same (`s ? \`${s}s\` : "—"` at line 636). The short, sweet, and long filters require `s > 0` (lines 219–221). A zero-length creative looks unmeasured and is excluded from every length bucket.

A failed creatives table has no Retry (lines 672–673). The campaign table does.

## Compare

Compare has no `FilterPanel`. It loads catalogs through scoped `GET /api/campaigns` and `GET /api/creatives`, then compares with scoped `GET /api/compare/campaigns` or `GET /api/compare`, at most four. The first boot picks the top four campaigns by spend, or a `?mode=&campaigns=|creatives=` link, and runs only when at least two ids validate (`ComparePage.tsx` lines 377–409). `booted` makes that effect return on later scope changes. Option lists still refresh, because they use `useScopedApi` (lines 289–290). Leaving the route remounts the page, so the next visit boots again. While it stays mounted, including when Return To My Scope writes the shared filter, cards, ranking, and the trend stay on the last run until Apply.

Controls:

- Compare By (line 670) sets the mode and clears the selection and both results.
- Add and remove chips (lines 682–694). At most four. Local until Apply.
- Rank By (lines 698–701) stores the metric. Apply (line 708) sends it (lines 626–628). Apply is disabled while loading or when fewer than two are picked.
- Trend metric (line 749), comparison metric (line 780), and baseline (line 795) are local.
- Period disclosure (line 895), A/B From and To (lines 907–919), and Compare Periods (line 923). Compare Periods calls scoped `GET /api/compare/periods`. It does not send `label_a` or `label_b`, so the API default is Period A / Period B (`product.py` lines 309–312). Empty dates set an error and do not call the API.

Campaign trends call scoped `GET /api/kpis/daily?days=30` per ranked campaign. The daily effect depends on `[mode, campaignData]` (line 434) and reads `scope` inside (line 420). Creative curves call unscoped `GET /api/retention/curve`. Creative mode replaces the attribute table with backend rows whose labels are English (`actions.py` lines 831–854, used at lines 593–596).

`daily_series` (`benchmarks.py` lines 208–231) keeps only dates that have rows, then the last `days` of those dates. Compare does not join series on the date. Each campaign’s points are its own day order (`ComparePage.tsx` lines 517–523). `trendLabels` come from the first non-empty series (lines 527–530). `TrendChart` plots point `i` at `x(i)` (`charts.tsx` lines 51–52) and places a label with `labels.indexOf` (lines 85–86). Different date sets, or a repeated `MM-DD` after `date.slice(5)`, misalign the lines. A missing daily response becomes `[]` (lines 426–428) and then `compare.noDaily`, with no error. The trend chart draws an uncomputable ROAS, CTR, CPA, or CPM as `0` (lines 518–521).

These strings are hardcoded English, not `t()`: the five suggested tests and their bodies (lines 247–253); `is …% higher` / `lower` (line 551); `Fill All Four Period Dates.` (line 355); `Select at least two campaigns to compare.` (line 301); `Select at least two creatives to compare.` (line 329); `Request Failed` (lines 318, 347, and 368); `Top Creative` and `Last 30 Days` (lines 486–487); `Unassigned` and `Video` (lines 501–502). A creative deep link runs `ctr` (line 396) while Rank By still shows the default `roas` (line 269) until Apply. A creative test can still be suggested from the default `ctr` idea when every compared KPI is missing (lines 576–588). The first takeaway can be a raw winner id because `why.top` is pushed as text (lines 560–561).

## Benchmarks

Benchmarks groups with scoped `GET /api/benchmarks?group_by=`. Saved cards are `GET`/`POST /api/views` and `POST /api/views/delete`. Opening one calls `applySavedView`, which writes global filters and navigates. Create Benchmark stores the live scope, KPI, and axis. The page’s own client, vertical, platform, market, objective, and funnel controls call `setFilter` immediately (lines 283–310), so they change the shared scope for every page before Apply. Apply (line 314) only increments `applied`. Reset (line 317) calls `clearFilters()` on the shared scope.

Controls:

- Create Benchmark (line 276). It calls an unscoped `GET /api/benchmarks` and discards the result (line 209), then `POST /api/views`.
- Platform options are only Meta and TikTok (lines 291–295).
- View All (line 329) goes to `/insights`.
- Open Benchmark (line 341) and Delete (line 344).
- Group By (lines 375–378). The select offers `platform`, `hook_type`, `format`, and `creator_vs_branded` (`AXES` at lines 31–33). `GROUPABLE` is `platform`, `campaign`, `hook_type`, `creator_vs_branded`, `edit_style`, `format`, and `vertical` (`benchmarks.py` lines 10–11). `format` and `vertical` are `ads` columns, so both groupings return rows. `benchmark()` still raises `ValueError` for a name outside that tuple (lines 236–237), and the panel then renders `benchmarks.error` (line 428). The vertical count uses `group_by=vertical` (line 112) and fills lines 474–476 from that response.
- Export, desktop (line 380) and overflow (line 371), posts `{ group_by: axis, filters: scopeBody(scope) }` to `/api/exports/benchmarks` (line 244). The route (`product.py` lines 1524–1534) returns `benchmarks.csv`. `group_by` must be in `GROUPABLE` (`TableExportBody`, lines 475–481). Anything else is 409. An empty filter object is unrestricted.
- Select All (lines 393–395) checks every row. The three-benchmark cap and `benchmarks.maxCompare` exist only in `toggle` (lines 159–165). Charts still use `compared.slice(0, 3)` (lines 134–137), so extra checked rows are omitted with no status. Clear All (line 434) clears the local selection.
- Open AI Analyst (line 498) and Open Reports (line 499).

Coverage and Platform cells are canned `filters.allVerticals` or `filters.allPlatforms` (lines 414–415), not the row’s coverage. `MiniBars` turns a null CPM, CPA, or ROAS into `0` (line 442). CPM ignores the API value and recomputes `spend / impressions * 1000` (lines 262–267), including when the API nulled CPM for mixed currency (`summarize`, `benchmarks.py` lines 153–154).

## Insights

Insights loads reach-objective cards from scoped `GET /api/analyst/creatives?objective=reach`. The backend treats that `objective` as the analysis objective and does not use it as a campaign filter (`product.py` lines 1121–1128). Page search, client, platform, market, type, and date are local state. Save Insight posts the global `scopeBody(scope)` plus `filters.kpi` and `view: "main"` (`InsightsPage.tsx` lines 213–215). It ignores the page’s own client, platform, and market. Conversations and views load once (lines 94–103, deps `[]`).

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
- Campaign checklist (line 617). The empty label is All Campaigns. Generate then sends `campaigns: null` (line 447). `expert2_report_route` (`actions.py` line 1401) turns a missing or empty list into `None`. `campaign_kpis` (`benchmarks.py` lines 839–841) then keeps every campaign still in the filter scope.
- KPI checklist (line 626). An empty selection still sends `["cpa", "ctr"]` (line 448) while the control reads Select KPIs.
- Benchmarks (line 637). The id `industry` is sent as `hook_type` (line 449). The English label is Scope Average (`en.ts` line 241). `rank_by` is always `cpa`. A benchmark name that is in `GROUPABLE`, which now includes `format` and `vertical`, is grouped by that column (`benchmarks.py` lines 1936–1937). The Reports screen still sends `hook_type` for Scope Average.
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

The nav label is Blank Workbook. Preview uses scoped creatives and `/api/kpis/compare` through `useCompare`, which refetches on the whole filters object, including `kpi`. Create downloads `GET /api/analyst/workbook` with name, description, modules, and KPIs only. The handler builds a cover plus seven blank sheets (`product.py` lines 1187–1206). The about copy says that on purpose (`en.ts` lines 1555 and 1581). Module cards other than summary and breakdown do not change the file.

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

There is no error branch. `previewFailedTitle` exists in `en.ts` (line 1569) and is unused. If compare or `/api/creatives` fails, the preview stays a `Skeleton` (lines 400–403 and 458–461).

## Ask

Ask submits `POST /api/ask` with the filter scope captured at send time (`scopeRef` in `AskPage.tsx` lines 101–102 and 130–133). Prompt chips, suggested questions, and follow-ups call the same `ask()`. Production does not auto-send. A demo workspace, `useCampaignMeta().data?.demo === true`, sends the current composer text once (lines 110–153).

When the managed LLM is paused, the ask job fails with `AI is not configured. Contact your administrator.` (`provider_inventory.py` lines 43–44, `providers.py` lines 1105–1106, `qa.py` lines 490–500). `product.py` lines 996–1003 return that string as `detail.error` through `_conflict`, because the paused text has no `[provider=` marker. Ask shows `ApiError.message` (lines 135–136 and 244–245). A chosen-model transport failure marked `[provider=` becomes 502 through `_provider_failure` (`product.py` lines 74–88).

Controls: the composer and Ask button (lines 220–227); prompt chips `ask.prompts.p0`–`p3` (lines 231–239); suggested questions `s0`–`s5` (lines 332–344); follow-ups `f0`–`f2` after an answer (lines 304–313); recent chats (lines 346–363) from `GET /api/analyst/conversations`, linking to `/analyst?conversation=`. The destination does not load the transcript. See Analyst. KPI, trend, and source blocks render the answer plus scoped compare, daily, and benchmark calls (lines 249–302). Ask money uses the USD formatter in `product.tsx`.

## Analyst

Analyst Run, Ask, 3 Points, try-asking chips, and follow-ups all `POST /api/analyst/ask` with `scopeBody(scope)` (`AnalystPage.tsx` lines 419–438). The handler is deterministic. `run_analyst` calls `analyst_chat.answer_turn` and does not consult the provider (`worker_handlers.py` lines 147–173). `answer_turn` uses templates (`analyst_chat.py` lines 705–784). There is no `NOT_CONFIGURED` check on this path. A paused model does not stop Analyst.

`AnalystRoute` passes the employee id (`router.tsx` lines 34–37 and 64). The page clears chat state when that key changes (`AnalystPage.tsx` lines 386–396).

Controls:

- Clear (`clearAll`, lines 459–465, button at 930) clears the transcript, composer, error, scope text, and active id. It does not call `clearFilters`.
- Reset (line 998) calls `clearFilters()` and sets the local range to `"all"`. It does not reset Objective or Language. The next ask still sends the previous objective and language (lines 1038–1054).
- Run Analysis (lines 933–935), Ask (lines 942–957), 3 Points (lines 959–969). An empty 3 Points uses `analyst.condenseLast` when a thread exists. `max_points` is 3.
- Try Asking (`en.ts` line 357, rendered at lines 976–987). The label is “Try Asking:”. Each chip sends that suggestion.
- Campaign, platform, client, and project (lines 1004–1069) write the shared filters.
- Date range (lines 1022–1036) is local state, initial `"all"` (line 347). Charts use `FilterContext` through `useScopedApi`. A range chosen on another page stays in effect while this select says All Time, until the user changes it.
- Objective (lines 1038–1047) is page-local and is sent on the ask body. It is not written back to the shared filters.
- Language (lines 1050–1054). `auto` omits language. The options are the hardcoded strings Auto, Polski, and English. The backend rejects anything else (`product.py` lines 1333–1340). Spanish is not offered.
- New Conversation (lines 1072–1075) posts `/api/analyst/conversations`.
- Report (lines 1077–1080) posts `/api/analyst/report` through the API client.
- Report XLSX (lines 1082–1085) fetches the same route with a raw `fetch` (lines 150–161). A 401 does not run the API client’s login gate.
- Blank Workbook (lines 1087–1090) is `GET /api/analyst/workbook` through a raw `fetch` (lines 513–541). The comment at lines 514–516 claims session re-gating that this fetch does not do. The server builds a blank workbook (`product.py` lines 1187–1206).
- Previous analyses (lines 1093–1110) set `activeId` and `setMessages([])` (lines 1101–1104). The Ask deep link only calls `setActiveId` (lines 375–378). Nothing calls `GET /api/analyst/conversations/{id}` (`product.py` lines 1089–1103 returns messages). The next ask still sends `conversation_id`, so the server thread continues while the screen stays empty.
- Save To Next-Flight Plan and Dismiss (lines 903–913) post accepted or rejected while the finding is proposed.
- Follow-up chips (lines 1179–1186) send the returned follow-up text.

Charts on this page use `/api/benchmarks`, `/api/campaigns`, and `/api/creatives`. The page does not call `GET /api/analyst/creatives`.

## Settings

The page heading is “Profile Settings” (`en.ts` line 1660). The sidebar link stays “Settings” (`en.ts` line 620).

`applyLive` (`SettingsPage.tsx` lines 246–251) applies theme, accent, density, language, and timezone on each autosave commit. Language and timezone are also restored for the signed-in employee by `LocalePrefsSync` (`i18n/index.tsx` lines 160–162). Accent and density CSS variables are rewritten when Settings is mounted (line 329) and then left on `documentElement`.

The prefs key is `ci-settings-prefs:<employeeId>` (`prefs.ts` lines 106–147), with a one-time read of the legacy global key. `src/state/notificationPrefs.ts` is unused. Nothing imports it.

Live on commit: theme, accent, density, language, timezone.

Saved on this page and not read by Dashboard, the router, or Ask: workspace name, Default View, Default Currency, Default Date Range, Default Campaign View, Email Reports, Campaign Updates, AI Insights, Product Updates, Data Usage, Share Analytics, and the retention select. Workspace name autosaves after 450 ms, trims, caps at 80, and rejects a blank (lines 284–302). No other page reads `prefs.workspace`. Unmount clears the debounce without flushing (lines 305–307), so a name typed and left within 450 ms is dropped. Default View, currency, date-range, and campaign-view option labels are English arrays (lines 66–69 and 937–973). The retention hint says the browser preference is not workspace retention (`en.ts` line 1825).

Theme is saved per employee, but the painted mode is the global `ci-theme` key (`useTheme.ts` lines 6–18 and 45–51). The live tree mounts `useTheme` only from Settings. Account switch applies language and timezone and does not call `setThemeMode` for the new employee. Accent and density update only when Settings mounts.

Backend actions, not prefs:

- Retry (lines 575–577) re-saves the prefs already on screen, and only after a local save failed.
- Reset Defaults (lines 579–581) writes `DEFAULTS` and applies them. No confirm.
- Edit Email (lines 641–643) opens the address field (lines 601–623). Save Email (lines 394–425) patches `{ email }` to `/api/auth/me`. The domain after `@` must match the stored address (`employees.py` lines 713–726, route at `auth.py` line 81). A different domain shows `Use another {domain} address.` and does not send the patch (lines 402–404). That sentence stays in a `role="alert"` (lines 620–622). Cancel closes the field. The same address closes it without a patch (lines 407–410). An invalid address is refused. A duplicate returns `That email is already registered.` The WorkOS id is left unchanged. A different WorkOS identity cannot sign in through the new address (`ensure_identity`, lines 278–285). Personal Info still edits the first and last name.
- Upload Photo posts `/api/auth/me/avatar` with a raw `fetch` (lines 445–472).
- Save Profile patches `/api/auth/me` (lines 359–382). The avatar URL is included only if it changed.
- Remove Avatar patches `avatar_url: ""` (lines 428–442). The fallback error is the English sentence “Could not remove avatar.” (line 439).
- Change Password posts `/api/auth/email/reset` (lines 475–487). It sends a reset email. The form does not set a new password.
- Log Out (lines 838–842) posts `/api/auth/logout` and is shown only when the session count is under 2.
- Log Out Everywhere (lines 832–836) confirms, then posts `/api/auth/sessions/revoke-all`. The handler destroys every session and clears the cookie (`auth.py`). It is shown only when the count is at least 2, in place of Log Out.
- Two-Factor Authentication is `TwoFactorCard` (`SettingsPage.tsx` line 846). The body is “Use an authenticator app for a second sign-in step after your password.” (`en.ts` line 1727). Set Up, Confirm, Turn Off, Copy Key, and I Saved These Codes are real controls. On is the pill only after confirm. The secret is `data-testid="totp-secret"`.
- Export Data posts `/api/auth/export` (lines 519–530). That route is still absent. The button remains.
- Google Drive Connect and Disconnect live on `GoogleDriveCard.tsx` lines 35–89.
- Meta Ads, TikTok Ads, and Google Analytics 4 are `IntegrationCards` (`SettingsPage.tsx` line 1025). They are not Unavailable pills.

The only `status` output requires `op !== null` (line 715). Save Profile, avatar upload and remove, Change Password, Log Out Everywhere, and Export Data set `status` in `catch` and clear `op` or `sessionOp` in `finally`. Those updates land in one paint, so the error never shows. A rejected photo sets `status` without setting `op` (lines 447–449). Success still uses the toast. Edit Email does not use that `status` line. Its error stays on the alert at lines 620–622. Two-factor and integration errors use their own `role="alert"` or `role="status"` and do show.

The Google SSO row shows Connected unless the check is still loading or `connected === false` (lines 790–796). `useGoogleStatus` sets `connected` to null and `error` to true on failure (`useGoogleStatus.ts` lines 54–57). The Drive card shows a retry for that state (`GoogleDriveCard.tsx` lines 76–81). The SSO row does not. Not Connected and Connected on that row both use `pill-ok` (lines 779, 793, and 795). `theme.css` line 916 paints `pill-ok` and `pill-info` as the brand teal.

Data tools on this page: retention patterns call `GET /api/retention/patterns`. Create Cohort posts `/api/cohorts` with the current filter scope (`DataTools.tsx` lines 272–346) and has no in-flight lock. Build calls `GET /api/cohorts/build`. Delete confirms and is rendered only for admins.

No key this slice calls is missing in `es.ts` or `pl.ts`. Extra keys in Spanish and Polish are allowed. English button labels in this slice stay title case.

## Admin

`/admin` renders only for `me.is_admin`. The page heading is “Admin Settings” (`en.ts` line 631). The sidebar link stays “Admin” (`en.ts` line 619).

Controls on `AdminEmployeesPage.tsx`:

- Export report (line 449) builds a client CSV of the loaded rows and audit events.
- Create Team (line 452) writes `localStorage` key `ci-local-teams`. The team column stays “—” (line 569).
- Add Employee (line 455) posts `/api/admin/employees`. It creates an active employee and sends no invite. The loading label is the English literal `Adding…` (line 850).
- Search, status, role, and Refresh (lines 479–515) load `GET /api/admin/employees` and `GET /api/admin/audit?limit=20`. Status and role are also filtered locally.
- Approve, Suspend, and Reactivate (lines 582–621). Suspending an admin confirms. The backend refuses to remove the last active admin (`employees.py` lines 953–972).
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

Frame-eligible entries from `VIDEO_MODEL_SUPPORT` (`provider_inventory.py` lines 628–669) that also sit on `VISION_ROSTER` (`providers.py` lines 1003–1013) are `gemini` / `gemini-3.5-flash-lite`, `gemini` / `gemini-3.7-flash`, and `anthropic` / `claude-haiku-4-5`. These roster ids are absent, so `frame_eligible` is false: `nvidia` / `meta/muse-glimmer-30b`, `openai` / `gpt-5.6-luna`, `openai` / `gpt-5.6-sol`, `anthropic` / `claude-opus-5`, `zai` / `glm-5v-turbo`, `zai` / `glm-5.2`. `providers_status` still lists a provider with a key as vision configured (`product.py` lines 127–134). The wizard repeats that (`VideoUploadPanel.tsx` lines 1727–1732). If the bundle constructs and the frame filter then empties the roster, `readiness` keeps the reason `provider mode is 'live': switch on a live provider` (`video_analysis.py` lines 63–70).

The catalog cache TTL is 24 hours (`provider_inventory.py` line 48). Activate requires an exact offered cache row fresher than 24 hours (`admin_providers.py` lines 214–230). Deactivate clears the singleton. A revision mismatch returns 409 and does not write (lines 195–199 and 265–268). Adopt copies a legacy secret once and does not activate.

Provider screen controls (`ProvidersPage.tsx`):

- Reload Provider List (lines 307–309) calls `GET /api/admin/providers`.
- The active and paused banner (lines 327–359). The paused body says AI Analyst is paused (`en.ts` lines 778–779). Analyst does not check the provider. Ask does fail closed.
- Use as active (lines 648–652) confirms in `requestActivate` or `requestDeactivate` (lines 602–629), then posts activate or deactivate with `current_revision`.
- Save Key and Replace Key (lines 479–500 and 703–706). The input is cleared and never prefilled. A 409, including a secret over 4096 characters (`admin_providers.py` lines 331–334) and a failed check of the active key (lines 386–392), calls `setCardError` (line 500). It does not store a deactivate retry.
- Show Key and Hide Key (lines 687–696).
- Remove Key (lines 528–548) confirms, then PUTs `secret: ""` and `confirm: true`. The backend deactivates if that provider is active (lines 337–364). A 409 on this request calls `setCardError` (line 548). It does not call `runDeactivate`.
- Save Base URL (lines 506–522). A 409, including an unsafe base URL (`admin_providers.py` lines 322–324), calls `setCardError` (line 522).
- Test Connection and Cancel Test (lines 554–581 and 754–771). The test does not change activation.
- Search models (lines 781–794) filters the offered list. Refresh Models (function lines 584–596, button line 801) posts `.../refresh` and does not activate. A 409, including “no secret stored” (`admin_providers.py` lines 488–491), calls `setRefreshError` (line 596). The alert under the search box (lines 821–827) retries that refresh. It does not deactivate.
- The model select (lines 834–861) uses the exact offered id.
- Conflict Retry (lines 246–260, button at line 319). Only activate and deactivate store a retry action (`runActivate` line 222, `runDeactivate` line 239). Retry then repeats that action against the refetched revision (lines 251–258). `isConflict` is still any `ApiError` with status 409 (lines 108–109). Save Key, Save Base URL, Remove Key, and Refresh Models do not pass an action into it. The card prints their message in `role="alert"` (line 671).

Any in-flight provider action shows “Activating…” on every card. The shared `busy` flag is rendered inside each card, and only the exact string `"deactivate"` selects the other label (lines 665–668).

`POST /api/drafts/{id}/analyze` (`product.py` lines 2506–2557) calls `bind_snapshot`, then `readiness()`, and returns 409 when not ready. The job payload stores that snapshot. The draft becomes `queued`.

One Analyse press binds the snapshot in `bind_snapshot` (`video_analysis.py` lines 88–135). The worker re-checks in `check_snapshot` (lines 145–158) at the start of `run` (line 485), after the pipeline (line 546), and again inside the publish transaction (line 585). A changed input raises and does not publish. Metrics come from `measured_from_records` (line 553, function at 245–378) using the confirmed match records, not the LLM. A total with no known contributor becomes `None` (lines 367–371). A zero impression pool leaves CTR null and adds `missing is not zero` (lines 354–359). Silent clips set `audio` to `None` in `prepare_media` (lines 189–200). `run_pipeline` then skips STT (`creative.py` lines 1106–1113) and still calls `llm.structure` (line 1130). That skip is reached only if the vision-roster gate has already passed. Draft success status is `ready_for_review` (`video_analysis.py` lines 627–628). `jobs.complete` sets the job row to `completed` (`jobs.py` lines 203–217), and the worker applies that after the handler returns (`worker.py` lines 110–119). The worker sets `analyzing` at start and `failed` or `cancelled` on the way out (`worker_handlers.py` lines 233–270). The provider receives JPEG bytes and WAV bytes, not the file path (`video_analysis.py` lines 526–539). Frames require a JPEG magic header (`video.py` lines 256–268). Audio is 16 kHz mono PCM (`video.py` lines 19 and 200–218). `readiness` labels the send as `sampled JPEG frames + 16kHz mono WAV` (lines 73–74).

Annotate runs before `llm.structure` (`creative.py` line 1086, then 1130). With no managed selection, the LLM slot is already the not-configured error. Publish does not happen. The draft is marked `failed` (`worker_handlers.py` lines 261–270). The vision call still ran.

`POST /api/ask` is the model call on the ask surface (`product.py` lines 978–1007). `run_ask` passes `prov.llm` only in live mode (`worker_handlers.py` lines 125–138). Analyst ask, analyst creatives, and the analyst report do not call the model.

## Analyze Video wizard

Besides resume, these controls are wired:

- Card Upload opens a new panel (`VideoUploadCard.tsx` line 279). A dropped mp4 or mov opens the panel with that file (lines 166–173 and 265–269).
- Resume, Discard, Continue, View, Retry, Cancel Analysis, and Delete behave as in the Resume section. Cancel Analysis is shown only with `live_job_id` (lines 355–361) and posts cancel, then patches the draft. Delete asks, then deletes and forgets the stage.
- Choose file, Upload, Replace, and Remove (`VideoUploadPanel.tsx` lines 1453–1517). The limit line under Choose File is 12px (line 1469, `theme.css` line 1037). Upload calls media upload, validate, and a spec PATCH. Remove deletes draft videos first (lines 1105–1123).
- Creative key (lines 1443–1448). The placeholder `video-upload-sample` (line 1447) is hardcoded English.
- Client and campaign, catalogue or custom (lines 1524–1585), and confirm selection (lines 1560–1566). The standing match-clear sentence is not rendered.
- Platform (lines 1595–1599).
- Dataset file, CSV text, sheet picker, and Import (lines 1601–1641). Import posts the dataset and stamps `wizardStage`. With no dataset, the step does not add a standing note (line 1681).
- Dataset version switch patches `dataset_version` (lines 1646–1650). The current option uses `datasetCurrent` (line 1658). Duration uses `durationValue` (line 1498). English is `{duration} Seconds` and `{name} (Current)`. Spanish is `{duration} s` and `{name} (actual)`. Polish is `{duration} s` and `{name} (bieżący)`.
- Match method, Propose, Confirm, and row checkboxes (lines 1787–1808 and 1875–1897). Changing the selection or the creative key drops a confirmed match locally.
- Back and Continue call `goStage` (lines 1912 and 1923). Save Draft calls `persistSpec` and re-confirms a held match (lines 1916–1920 and 930–952).
- Analyze posts `/api/drafts/{id}/analyze` (lines 1349–1370). `canAnalyze` (lines 1321–1322) requires a valid video, a confirmed client and campaign, a confirmed match, and a draft that is not `queued` or `analyzing`. It does not read `providerStatus`. The comment at lines 1317–1320 says the readiness block is display-only and the server 409 is the gate. The client comment in `videoUploadApi.ts` lines 290–294 says the submit stays disabled until vision is configured. The button does not do that.
- Findings seek, correct, accept, reject, and Mark reviewed call the correction and review endpoints (lines 1823–1868).
- The provider line (lines 1720–1734) is display-only, from `GET /api/providers/status`.
- The review footer note (lines 1907–1908) is empty when the video is not valid (`analyzeReason`, lines 1323–1324). Analyze stays disabled.

A step chip earlier than the open step is a button (lines 1406–1415) and calls `goStage`. The current step and later steps are text (lines 1418–1429). From the first step, none of the later chips are buttons.

`METHOD_LABELS` is fixed English (lines 98–104): Platform ID, Exact Filename, Explicit Tag, Fuzzy Filename, Manual. Moment flags are fixed English (lines 201–205): Brand, Product, Logo, CTA, End.

## Assets

`GET /assets/{name}` serves a dist file when it exists (`product.py` lines 3014–3021). A missing dist file with extension `.png`, `.svg`, `.ico`, or `.webp` is served from `ASSETS_DIR` with `max-age=86400` (lines 3025–3031). `.js`, `.css`, and `.woff2` still 404 when missing from dist. `/favicon.png`, `/foap-logo.png`, and `/foap-mark.png` are unchanged. The 404 on `/assets/favicon.png` and `/assets/foap-logo.png` is fixed on `dc02927`. See On the parent `dc02927`.

## Already on main before this push

`dc02927` is the parent of this push: the ready audit fixes, the Render site address in the docs, and the previous `Audit.md`. `7a9440a` is the attempt-counter fix. `da25a6e` is the four fixes under Fixed on the parent, and its parent `49a2e23` changes `Audit.md` only. This push is the TypeScript build, the Compare late-response drop, and this file. Do not report the old Unavailable pills, the old page titles, the old suggestion label, the three standing notes, or a step chip that cannot go back, unless the cited lines no longer do what this file says. Do not report the items This push or On the parent `dc02927` says are fixed, unless the cited lines no longer do what that section says.

These were already true before 2026-10-09 and stay true:
- Drawer creative metrics stay inside the open campaign (`actions.py` lines 673–676). Totals still come from `benchmark(..., "campaign")` (lines 667–668).
- `scopedPath` treats only the exact `/api/campaigns/meta` and `/api/campaigns/recommendations` bases as static (`client.ts` lines 105–111). A name such as `meta-launch` keeps the shared filters.
- A campaign name that contains `/` or a literal `%20` opens through `GET /api/campaigns/{name:path}` (`product.py` lines 189–220). The handler decodes the raw target once.
- An explicit empty campaign list exports no creative rows (`actions.py` lines 778–779). The campaign CSV already omitted every requested name for that filter.

These were already true before the 2026-10-08 export-filter commit and stay true:

- The drawer route exists (`product.py` lines 205–220, `CampaignsPage.tsx` lines 358–381). An unknown name is 404 with `error` set to `No campaign matches the current filters.`
- Table CSV: `POST /api/exports/campaigns`, `/api/exports/creatives`, and `/api/exports/benchmarks` (`product.py` lines 1492–1533). `POST /api/export` (line 1536) is still the one-pager.
- `format` and `vertical` are in `GROUPABLE` (`benchmarks.py` lines 10–11). `BenchmarksPage.tsx` lines 31–33 and 112 call those names.
- A provider validation 409 stays on the card (`ProvidersPage.tsx` lines 500, 522, 548, and 596). It does not call `runDeactivate`.

## Defects still true

This inventory was not retested as a whole. The MFA check on `7a9440a` did not cover it. Items This push or On the parent `dc02927` fixes are not repeated here. Do not report them unless the cited lines no longer do what that section says.

P2. Compare copy listed in the Compare section stays English in Spanish and Polish. Compare’s redraw, date alignment, and late-response drop are fixed. See This push and On the parent `dc02927`.

P2. Campaign “vs. Benchmark” is one shared number, or Unavailable. Checked creative export, the grid card, Open in Creatives `?find=`, and a later campaign `?find=` are fixed on `dc02927`. A creative link dropping its selection was not rechecked.

P2. Money on Dashboard, Campaigns, and Ask is USD. The dashboard date window is the first and last day of the latest 30 dates with rows, written into the shared scope, not Settings’ Default Date Range. Length bars, duration `0` on the dashboard, and the Creatives `0s` label are fixed on `dc02927`. The Creatives learnings length bucket still requires `s > 0` (`CreativesPage.tsx` line 337).

P2. Several failures render as a skeleton or as an empty state: dashboard charts and recommendations, campaign platform bars, daily series, Insights cards, and the Workbook preview. Insights filters do not filter the panels their labels name. Saved Analyst conversations and the Ask deep link do not load messages.

P2. The Analyst date select can read All Time while the shared date filter is still applied. Reset does not clear Objective or Language. Clear does not clear shared filters.

P2. Workspace name, default view, currency, date range, campaign view, notification toggles, and privacy toggles stay on Settings. Export Data still posts `/api/auth/export`, and that route is still absent. Notification toggles do not send email. A visible profile failure, the Google status failure, the Not Connected pill, and the Theme select are fixed on `dc02927`.

P2. The paused-provider banner says AI Analyst is paused. Analyst does not check the provider. Ask does fail closed with the administrator sentence.

P2. Vision readiness is not “a configured vision key.” `eligible_vision_roster` returns empty when `LiveBundle()` cannot construct an STT adapter. Unverified vision roster ids are still advertised as configured, and the not-ready reason can be the generic live-mode sentence. Activating the managed model does not enable frame analysis.

P3. Analyze is offered when the status line says vision is missing (`VideoUploadPanel.tsx` lines 1321–1322). The server 409 is the real gate. A paused managed LLM is discovered at structuring, after vision has been called.

P3. Wizard method labels (`VideoUploadPanel.tsx` lines 98–104) and moment flags (lines 201–205) stay English. The creative-key placeholder `video-upload-sample` (line 1447) stays English. Duration and the current-dataset label are localized.

P3. Provider cards show “Activating…” for every in-flight action. Workbook and spreadsheet downloads, and avatar upload, bypass the API client’s 401 gate. Add Employee’s loading label, several Settings option lists, and the Analyst language options are hardcoded English. A workspace name left within 450 ms is dropped. Cohort Create has no in-flight lock. Create Team does not appear in the employee table. The Insights empty titles share one string. Reports’ Save as Template is never read. Benchmark Select All exceeds the three-row chart cap without a status.

## Checks not performed

No Render click-through, live provider, ffmpeg run, or the five Notino clips. `7a9440a` ran `tests/test_two_factor.py` (7 passed). The checks for this push are listed under This push. The checks for `dc02927` are listed under On the parent `dc02927`. The full UI suite and the full backend suite were not re-run on 2026-10-09. The checks named under Adjustments on main for 2026-10-09 ran on the commits that introduced each change. Ruff passed on the new Python modules when integrations landed. Pre-existing ruff findings in `product.py` were left as they were. `tests/test_table_exports.py` was not re-run on 2026-10-09. The last full backend run, before an earlier parent changed Python, failed four tests: `tests/test_ci_app.py::test_security_headers_health_readiness` (`ModuleNotFoundError: No module named 'tests'`), `tests/test_ci_app.py::test_no_licensing_concepts` (the walker does not skip `.venv`), and `tests/test_web_shell.py` `test_favicon_asset_serves` plus `test_logo_and_mark_assets_serve` (404 on `/assets/favicon.png` and `/assets/foap-logo.png`). The parent `dc02927` re-ran those two asset tests and they passed. This push did not re-run them. The two `test_ci_app.py` failures were not re-run. `client.ts` lines 32–33 still turn a non-OK body with no `error` field into `Request failed (${status})`. This drawer route puts `error` on the 404, so that fallback is not the drawer copy. Spanish and Polish catalogs were checked for missing keys by `parity.test.ts` on this push. They were not opened line by line for Compare. `benchmarks.py` was not edited.
