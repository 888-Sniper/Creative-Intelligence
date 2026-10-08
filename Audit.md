# Creative Intelligence audit for 2026-10-08

Review `origin/main` after `git fetch`. Confirm that `origin/main` and GitHub `main` name the same SHA. A behind local checkout or a missing local `main` branch is not a reason to stop; use `git show origin/main:PATH`. Stop only if the remote identities differ or the worktree is dirty.

This is the product repo https://github.com/888-Sniper/Creative-Intelligence. The parent of this push is `b7699bcf077bab9a67c0562e4bc0be3d14c3850a` (`Record the button and settings functionality check`). This push makes Resume reopen the Analyze Video wizard on the step that was left open. Do not call the product perfect. Do not edit, commit, push, build, install, start the server, or activate a provider. Do not treat an unrun live model, live browser, Playwright run, Render click-through, or the five Notino clips as a source defect. Report only defects still present at the reviewed SHA, with severity, observed behavior, file and line, and the evidence that reproduces them. State checks not performed.

Confirm the push with both ends named:

```
git diff --stat b7699bcf077bab9a67c0562e4bc0be3d14c3850a origin/main
```

The product diff is the video-upload wizard (`videoUploadApi.ts`, `VideoUploadPanel.tsx`, `VideoUploadCard.tsx`, `VideoUpload.test.tsx`) plus this file. No Python file changes. Re-read those files at `origin/main`.

## What should be true

The Resume button in `VideoUploadCard.tsx` line 294 still opens `{ draftId }` and does not pass a stage. That is the restore path. Do not report the missing `stage` argument as a defect.

On open, `VideoUploadPanel.tsx` lines 778–781 choose the step in this order:

1. `open.stage`, when the caller passed one. Recent Uploads View passes `review` and Retry passes `video` (`VideoUploadCard.tsx` lines 383–384). Those win.
2. The step stored for that draft id in `localStorage` key `ci-video-draft-stage:<employeeId>`. The value is a map of draft id to `video`, `client`, `dataset`, or `review` (`readDraftStage` in `videoUploadApi.ts` line 77).
3. `spec.wizardStage`, when a save wrote one (`videoUploadApi.ts` line 196).
4. `stageForSpec` (`VideoUploadPanel.tsx` lines 61–66), the earliest incomplete saved gate. This is only the fallback for a draft that has no stored step.

Continue and Back call `goStage` (`VideoUploadPanel.tsx` lines 1001–1007) and write that map immediately, including when Continue has moved past an unconfirmed client or a missing dataset. Closing the dialog, the overlay, or Escape calls `leaveAndClose` (line 1010) and writes the same step before the panel unmounts.

A step-only leave does not PATCH the draft. `persistLeaveFields` (lines 960–998) patches only when the client, campaign, creative key, or platform differs from the last saved spec. A confirmed match blocks that patch unless the client, campaign, or creative key changed, because any spec PATCH clears matches on the server. Closing an unchanged wizard therefore leaves a confirmed match in place.

Typed client and campaign text is included in that patch, so Resume can show it again. A video file that was chosen and never uploaded is not restored. CSV or XLSX text that was never imported is not restored. An uploaded video and an imported dataset are already on the draft and come back with it.

The same browser keeps one step per draft id. Opening a second draft does not erase the first draft's step. Deleting a draft, or a successful Analyze, forgets only that draft's step. Switching accounts clears the previous account's map.

## How to confirm

From `apps/creative-intelligence-ui`:

```
pnpm exec vitest run src/components/VideoUpload.test.tsx
pnpm exec tsc --noEmit
```

On this machine the video-upload file passed 28 tests, and `tsc --noEmit` exited 0. The full UI suite passed 306 tests across 38 files (`pnpm exec vitest run`). The backend suite was not re-run. This push does not change Python. Playwright was not run. The live Render site, live providers, and the five Notino clips were not used.

The new tests cover a valid video whose saved gate is the client step: Resume opens Review when that step was stored; Continue to the dataset step is what a later open shows; closing after typing a client and campaign restores both the dataset step and those names; closing an unchanged review draft sends no PATCH.

## Unchanged defects

This push does not touch the defects recorded on the parent. They are still present:

- Campaign details request `GET /api/campaigns/${name}` at `CampaignsPage.tsx` line 361. No such route exists. The drawer shows “Request failed (404)”.
- `secondsOf(datum) ? ... : "—"` at `CreativesPage.tsx` line 119 treats a duration of `0` as missing.
- Compare does not redraw on a shared-filter change while mounted (`ComparePage.tsx` lines 377–409 and 411–434). The trend chart aligns days by index (`ComparePage.tsx` lines 517–531, `charts.tsx` lines 51–58).
- Reports with every campaign unchecked send `campaigns: null` (`ReportsPage.tsx` line 447), and the report then includes every campaign (`actions.py` line 1217, `benchmarks.py` line 839).
- Settings outside theme, accent, density, language, and timezone (`SettingsPage.tsx` lines 232–237) stay on the Settings page.
- `GET /assets/favicon.png` and `GET /assets/foap-logo.png` 404. The React shell uses `/favicon.png` and `/foap-logo.png`.
- Wizard method labels (`VideoUploadPanel.tsx` lines 98–107) and the moment flags at lines 201–205 stay English.

The four backend failures named on the parent (tests import, `.venv` licensing scan, and the two `/assets` PNG assertions) were not re-run and were not changed.
