# Creative Intelligence audit for 2026-10-08

Review `origin/main` after `git fetch`. Confirm that `origin/main` and GitHub `main` name the same SHA. A behind local checkout or a missing local `main` branch is not a reason to stop; use `git show origin/main:PATH`. Stop only if the remote identities differ or the worktree is dirty.

This is the product repo https://github.com/888-Sniper/Creative-Intelligence. The parent of this push is `6af23f919d9fbb0f4c68597e79d2dd0c170de940` (`Isolate audio extracts so a failure keeps the published cache`). This push changes the Analyze Video wizard copy and layout, and the short success notices. Do not call the product perfect. Do not edit, commit, push, build, install, start the server, or activate a provider. Do not treat an unrun live model, live browser, or a previously stored analysis as a source defect. Report only defects still present at the reviewed SHA, with severity, observed behavior, file and line, and the evidence that reproduces them. State checks not performed.

Confirm the push with both ends named:

```
git diff --stat 6af23f919d9fbb0f4c68597e79d2dd0c170de940 origin/main
```

The diff is the Analyze Video wizard, its English copy, the Spanish and Polish keys those screens need, the settings success notices, the wizard tests, and `Audit.md`.

## Wizard copy

English visible words in the Analyze Video wizard are title case. `Save Draft`, `Creative Key`, `Upload Your Video`, `Choose File`, and `No File Chosen` are the labels. The creative-key hint is gone. The format line sits under the file control and reads `MP4 / MOV, Up To {size}, Up To {duration} Seconds`, with no leading dot and no middle dot.

The file control is a button plus the chosen name. The real input stays `#vu-file` and is visually hidden, and its label is still `Video File`.

Success notices use a capital on each word. That includes `Draft Deleted.`, `Draft Saved.`, `Analysis Queued ({model}).`, `Defaults Restored.`, `Profile Saved.`, `Avatar Removed.`, `Password Reset Email Sent.`, `All Sessions Signed Out.`, `Workspace Data Exported.`, and `All Changes Saved.`

The queued notice is raised on the uploads card before the dialog closes, so closing the panel does not drop it. `Draft Deleted.` is the card toast after confirm delete.

## Layout

The footer note sits on its own line above the actions. Back, Save Draft, and Continue or Analyze stay on the right. The dataset file button shares the platform row and shows the chosen filename beside the button. A staged replacement uploads with `Upload Video`. The picker `Replace` stays hidden while that file is staged. Catalogue selects hide while custom client and campaign names are open. The confirmed pill reads `Selection Confirmed`. The full sentence stays on the status line. The unfinished-upload chip wraps inside the card. The delete confirmation has a 10px gap. Review impressions do not fall back to the click count. Hook options show the existing hook labels and keep the stored codes.

Spanish and Polish keep normal sentence case. They carry the new keys (`chooseFileBtn`, `noFileChosen`, `providerSendsBody`, `notConfirmed`, `confirmedPill`).

## Checks

```
cd apps/creative-intelligence-ui && pnpm exec vitest run src/components/VideoUpload.test.tsx src/pages/SettingsPage.test.tsx src/i18n/parity.test.ts
cd apps/creative-intelligence-ui && pnpm exec playwright test e2e/04-video-upload.spec.ts
```

Those were 52 unit tests and 3 browser tests on this machine, after a production UI build served by the isolated e2e backend. An unrun Render page is not a source defect. This push does not change video analysis, the audio cache, or the five local Notino clips. Do not upload them.
