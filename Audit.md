# Creative Intelligence audit for 2026-10-08

Review `origin/main` after `git fetch`. Confirm that `origin/main` and GitHub `main` name the same SHA. A behind local checkout or a missing local `main` branch is not a reason to stop; use `git show origin/main:PATH`. Stop only if the remote identities differ or the worktree is dirty.

This is the product repo https://github.com/888-Sniper/Creative-Intelligence. The parent of this push is `e3626a543ff2065cc9821285f8c4d2ae07bcda40` (`Store visibility runs and reject an incomplete audio cache`). This push closes the failed-extract cache defect. Do not call the product perfect. Do not edit, commit, push, build, install, start the server, or activate a provider. Do not treat an unrun live model, live browser, or a previously stored analysis as a source defect. Report only defects still present at the reviewed SHA, with severity, observed behavior, file and line, and the evidence that reproduces them. State checks not performed.

Confirm the push with both ends named:

```
git diff --stat e3626a543ff2065cc9821285f8c4d2ae07bcda40 origin/main
```

The diff is `Backend/creative_intel/video.py`, `tests/test_video.py`, `tests/test_video_analysis.py`, and `Audit.md`.

## WAV cache

`extract_audio` writes to a temporary `.wav`. `video.prepare` publishes that file on the cache path only after ffmpeg exits 0 and the data chunk contains samples. Any failed extraction deletes the temporary file and the cache path.

A complete RIFF is not enough. A header whose data chunk has zero samples is removed, and the next call extracts again. It does not return that file as audio.

Corrupt the AAC payload of a synthetic MP4 with `0xA5`. Direct ffmpeg exits 69 and leaves a WAV whose RIFF length matches and whose data chunk size is 0. The first `video.prepare` raises `ProviderUnavailable`. The cache directory has no `_audio.wav` and no `.partial.wav`. The second `video.prepare` raises again.

An empty file left by a disk-full extract still raises on the next call. A missing audio stream stays silence (`audio` is None) and does not leave a cache file that a later call treats as audio. A WAV that contains samples is still reused.

## Checks

```
uv run --extra dev pytest tests/test_video_analysis.py tests/test_video.py tests/test_live_providers.py tests/test_pipeline.py tests/test_cohort_delete.py tests/test_admin_providers.py tests/test_acceptance_10.py -q --tb=line
```

The locks for this push are `test_header_only_wav_from_failed_extract_is_not_audio` and `test_failed_aac_does_not_leave_a_header_cache`. `test_failed_wav_cache_is_not_silence` still holds.

The five local Notino clips are not in this repo. Do not upload them. This push does not re-analyze them.
