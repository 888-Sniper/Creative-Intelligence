# Creative Intelligence audit for 2026-10-08

Review `origin/main` after `git fetch`. Confirm that `origin/main` and GitHub `main` name the same SHA. A behind local checkout or a missing local `main` branch is not a reason to stop; use `git show origin/main:PATH`. Stop only if the remote identities differ or the worktree is dirty.

This is the product repo https://github.com/888-Sniper/Creative-Intelligence. The parent of this push is `4315234d601e19b1c36aa3242e4c145644066ea5` (`Reconcile video timing, cuts, narrative, and audio errors`). This push closes the three remaining timing and cache defects. Do not call the product perfect. Do not edit, commit, push, build, install, start the server, or activate a provider. Do not treat an unrun live model, live browser, or a previously stored analysis as a source defect. Report only defects still present at the reviewed SHA, with severity, observed behavior, file and line, and the evidence that reproduces them. State checks not performed.

Confirm the push with both ends named:

```
git diff --stat 4315234d601e19b1c36aa3242e4c145644066ea5 origin/main
```

The diff is `Backend/creative_intel/creative.py`, `Backend/creative_intel/video.py`, `tests/test_video_analysis.py`, and `Audit.md`.

## Frame spans

When any sampled frame has the flag true, `product_seconds`, `logo_seconds`, and `brand_seconds` become the visible runs in those frames. A model span is not kept beside them.

A frame at 0 seconds with the product absent, and a frame at 9 seconds with the product present, stores one span `[9, 9]`. `execution.product_first_s` is 9. Benchmarks read that same start through `_span_min`. Suggested tests may still recommend an earlier product, because 9 is after 3 seconds. That recommendation agrees with both reads.

True at 0, false at 3, and true at 6 stores `[0, 0]` and `[6, 6]`. `retention._span_covers` is false at 3 seconds and true at 0 and 6. Consecutive true frames stay one span from the first of that run to the last.

## WAV cache

`video.prepare` reads a cached WAV only when the file is a complete RIFF (`declared size + 8` equals the byte length). An empty or truncated file is deleted, then extraction runs again. A disk-full extract that leaves an empty file still raises on the next call. It does not return `audio=None`. A missing audio stream remains silence, and that failure does not leave a cache file that later calls treat as silence.

## Checks

```
uv run --extra dev pytest tests/test_video_analysis.py tests/test_live_providers.py tests/test_pipeline.py tests/test_cohort_delete.py tests/test_admin_providers.py tests/test_acceptance_10.py -q --tb=line
```

The locks for this push are the early-model and gap cases in `test_product_span_matches_the_flagged_frame`, and `test_failed_wav_cache_is_not_silence`.

The five local Notino clips are not in this repo. Do not upload them. This push does not re-analyze them.
