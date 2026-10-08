# Creative Intelligence audit for 2026-10-08

Review `origin/main` after `git fetch`. Confirm that `origin/main` and GitHub `main` name the same SHA. A behind local checkout or a missing local `main` branch is not a reason to stop; use `git show origin/main:PATH`. Stop only if the remote identities differ or the worktree is dirty.

This is the product repo https://github.com/888-Sniper/Creative-Intelligence. The parent of this push is `fdd18e3afb63d649ab23ee5ca0c9bd4fa22c4886` (`Audit video analysis data field by field`). This push closes the four data defects that check found. Do not call the product perfect. Do not edit, commit, push, build, install, start the server, or activate a provider. Do not treat an unrun live model, live browser, or a previously stored analysis as a source defect. Report only defects still present at the reviewed SHA, with severity, observed behavior, file and line, and the evidence that reproduces them. State checks not performed.

Confirm the push with both ends named:

```
git diff --stat fdd18e3afb63d649ab23ee5ca0c9bd4fa22c4886 origin/main
```

The diff is `Backend/creative_intel/creative.py`, `Backend/creative_intel/video.py`, `Backend/creative_intel/video_analysis.py`, `tests/test_pipeline.py`, `tests/test_video_analysis.py`, and `Audit.md`.

## Product, logo, and brand times

`apply_observation_facts` still sets `execution.product_first_s` and `execution.logo_first_s` from the earliest true flag. It now writes `product_seconds`, `logo_seconds`, and `brand_seconds` from those same flags when the model span is missing or starts later. A frame at 0 seconds and a model span at 9 seconds persist as one span starting at 0. A model span that already starts at or before the flagged frame is kept. Benchmarks read those span lists through `_span_min`. Suggested tests read `execution.product_first_s`. Those two reads must agree on the case above.

## Pace evidence

`pace_cuts_per_min` is `round(cuts * 60 / duration, 2)` where a cut is `cut is True`. The vision-annotate stage stores those times on `cuts`. `saved_frame_labels` stores `cut` on each saved frame. One cut in a 15-second clip is 4 cuts per minute, and both the stage and the saved frame show that cut. `execution.pace` stays `""`. No reader treats that empty string as the pace.

## Narrative cues

English cues are whole phrases: `i found`, `my favorite`, and `my favourite`. `AI foundation models` stays `unknown`. `I found this` is `peer_recommendation`. The cues `jaz `, `jaz,`, `sem našla`, and `sem nasla` stay substrings.

## Audio extraction

`prepare_media` treats a missing audio stream as silence (`audio` is None and `sampling.audio` is `absent`). `audio_track_missing` matches `no audio track`, `does not contain any stream`, and `matches no streams`. Any other extraction error, including `No space left on device`, raises `AnalysisUnavailable` and does not skip speech. `video.prepare` uses the same distinction and lets the error propagate.

## Checks

```
uv run --extra dev pytest tests/test_video_analysis.py tests/test_live_providers.py tests/test_pipeline.py tests/test_cohort_delete.py tests/test_admin_providers.py tests/test_acceptance_10.py -q --tb=line
```

The new locks are `test_product_span_matches_the_flagged_frame`, `test_saved_frames_keep_cut_flags`, `test_audio_extraction_failure_is_not_silence`, and `test_vision_stage_records_cut_times`.

The five local Notino clips are not in this repo. Do not upload them. This push does not re-analyze them.
