# Creative Intelligence audit for 2026-10-08

Review `origin/main` after `git fetch`. Confirm that `origin/main` and GitHub `main` name the same SHA. A behind local checkout or a missing local `main` branch is not a reason to stop; use `git show origin/main:PATH`. Stop only if the remote identities differ or the worktree is dirty.

This is the product repo https://github.com/888-Sniper/Creative-Intelligence. The parent of this push is `7ea1fa734c494ab214e68ca5167dc011f6869627` (`Discard the audio cache when extraction fails`). This push closes the concurrent-extract collision. Do not call the product perfect. Do not edit, commit, push, build, install, start the server, or activate a provider. Do not treat an unrun live model, live browser, or a previously stored analysis as a source defect. Report only defects still present at the reviewed SHA, with severity, observed behavior, file and line, and the evidence that reproduces them. State checks not performed.

Confirm the push with both ends named:

```
git diff --stat 7ea1fa734c494ab214e68ca5167dc011f6869627 origin/main
```

The diff is `Backend/creative_intel/video.py`, `tests/test_video.py`, `tests/test_video_analysis.py`, and `Audit.md`.

## WAV cache

Each `extract_audio` call writes a private temporary WAV (`.audio-` plus `.wav`). The cache path is replaced only after ffmpeg exits 0 and the data chunk contains samples. A failure deletes that temporary file only. It leaves the cache path in place, including a WAV another call has already published.

Two simultaneous `video.prepare` calls for the same valid clip both return audio. The cache directory keeps one `_audio.wav` with samples and no `.audio-` temporary. Three trials of that pair succeed.

A header whose data chunk has zero samples is still not audio. The next `video.prepare` extracts again. Corrupt AAC (`0xA5` across `mdat`) still makes ffmpeg exit 69, both prepares raise, and no cache WAV remains. An empty disk-full file still raises on the retry. A missing audio stream stays silence.

## Checks

```
uv run --extra dev pytest tests/test_video_analysis.py tests/test_video.py tests/test_live_providers.py tests/test_pipeline.py tests/test_cohort_delete.py tests/test_admin_providers.py tests/test_acceptance_10.py -q --tb=line
```

The locks for this push are `test_concurrent_prepares_keep_the_published_wav`, `test_failed_extract_keeps_a_published_cache`, and `test_extract_audio_temps_are_unique`.

The five local Notino clips are not in this repo. Do not upload them. This push does not re-analyze them.
