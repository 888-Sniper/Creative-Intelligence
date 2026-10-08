# Creative Intelligence audit for 2026-10-08

Review `origin/main` after `git fetch`. Confirm that `origin/main` and GitHub `main` name the same SHA. A behind local checkout or a missing local `main` branch is not a reason to stop; use `git show origin/main:PATH`. Stop only if the remote identities differ or the worktree is dirty.

This is the product repo https://github.com/888-Sniper/Creative-Intelligence. The parent of this push is `aa9b09e2850933ce2bb8dc22d00a555cf473eec3` (`Title-case the analyze video wizard and its notices`). This push moves two Analyze Video labels onto translation keys. Do not call the product perfect. Do not edit, commit, push, build, install, start the server, or activate a provider. Do not treat an unrun live model, live browser, or a previously stored analysis as a source defect. Report only defects still present at the reviewed SHA, with severity, observed behavior, file and line, and the evidence that reproduces them. State checks not performed.

Confirm the push with both ends named:

```
git diff --stat aa9b09e2850933ce2bb8dc22d00a555cf473eec3 origin/main
```

The diff is the duration value and the active-dataset option in the Analyze Video wizard, the English, Spanish, and Polish keys for those two strings, the render test that selects each language, and `Audit.md`.

## Localized labels

`apps/creative-intelligence-ui/src/components/VideoUploadPanel.tsx` no longer hardcodes the duration detail or the active dataset suffix.

The duration detail uses `dashboard.videoUpload.durationValue`. English is `{duration} Seconds`. Spanish and Polish are `{duration} s`. A 15 second video therefore reads `15 Seconds` in English and `15 s` in Spanish and Polish. A missing video still shows `—`.

The active imported-dataset option uses `dashboard.videoUpload.datasetCurrent`. English is `{name} (Current)`. Spanish is `{name} (actual)`. Polish is `{name} (bieżący)`. The filename stays as stored. An inactive option stays the raw filename, with no suffix. English wizard copy stays title case. Spanish and Polish stay sentence case.

## Checks

```
cd apps/creative-intelligence-ui && pnpm exec vitest run src/components/VideoUpload.test.tsx src/pages/SettingsPage.test.tsx src/i18n/parity.test.ts
cd apps/creative-intelligence-ui && pnpm exec tsc --noEmit
```

Those were 53 unit tests and a clean TypeScript check on this machine. The new test renders the video stage and the dataset stage inside `LocaleProvider` with English, Spanish, and Polish selected. Playwright was not run. Its setup builds the UI and starts a server, and the existing browser spec only asserts the English validation sentence, which already comes from `validMsg`. An unrun Render page is not a source defect. This push does not change video analysis, the audio cache, or the five local Notino clips. Do not upload them.
