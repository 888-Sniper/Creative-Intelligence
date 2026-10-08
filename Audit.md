# Creative Intelligence audit for 2026-10-08

Review `origin/main` after `git fetch`. Confirm that `origin/main` and GitHub `main` name the same SHA. A behind local checkout or a missing local `main` branch is not a reason to stop; use `git show origin/main:PATH`. Stop only if the remote identities differ or the worktree is dirty.

This is the product repo https://github.com/888-Sniper/Creative-Intelligence. The parent of this push is `6fbf54c25aa868996831d929e86e38bd444533bf` (`Name origin/main in the audit diff`). This push replaces the check. It does not change pipeline code. The data below is what a saved video analysis must contain. Do not call the product perfect. Do not edit, commit, push, build, install, start the server, or activate a provider. Do not treat an unrun live model, live browser, or a previously stored analysis as a source defect. Report only defects still present at the reviewed SHA, with severity, observed behavior, file and line, and the evidence that reproduces them. State checks not performed.

Confirm the push with both ends named:

```
git diff --stat 6fbf54c25aa868996831d929e86e38bd444533bf origin/main
```

The diff is `Audit.md` only.

## Data standard

A saved analysis is right when the probed file, the sampled frames, the transcript, and the imported rows agree with the fields below. Model text that was not re-run is not proof, and it is not a defect by itself. A source defect is a rule in this tree that writes a field the frames, the probe, or the rows do not support, or that drops a field another saved field depends on.

Read `Backend/creative_intel/creative.py` (`apply_observation_facts`, `normalize_frame_flags`, `language_from_overlays`, `run_pipeline`) and `Backend/creative_intel/video_analysis.py` (`prepare_media`, `measured_from_records`, `suggest_tests`, `run`). The locks are:

```
uv run --extra dev pytest tests/test_video_analysis.py tests/test_live_providers.py tests/test_pipeline.py tests/test_cohort_delete.py tests/test_admin_providers.py tests/test_acceptance_10.py -q --tb=line
```

`test_observation_facts_use_frames_and_probed_duration`, `test_promotion_cues_do_not_match_inside_unrelated_words`, and `test_suggest_tests_grounded_in_absences` are the data locks.

## File and sampling

`videos.duration_s` is the ffprobe length. `analysis.coverage.clip_s` copies that length. When it is greater than 0, `annotation.duration_s` is that length rounded to 3 decimals. The last sampled frame is about half a second earlier and must not become the clip length.

`video.sample_times` keeps a 1-second grid through 3 seconds, then a 3-second grid, then one sample at `duration - 0.5`, capped at 16 frames. `prepare_media` extracts a JPEG at each of those seconds and a 16 kHz mono WAV when the clip has audio. `media_kind` is `video` when both exist. `timestamp_resolution_s` is the smallest gap between sample times. `frame_times` is that plan. Stages are exactly five, in order: `ingest`, `frame-sample`, `vision-annotate`, `transcribe`, `llm-structure`. A clip with images and no audio skips speech and records `skipped`: `silent: no audio track`.

## Speech and on-screen copy

`text_overlay` is the on-screen line. It chooses the speech tag when the request did not pass `speech_language`: `ě`, `ř`, or `ů` selects `cs`; otherwise `ć` or `đ` selects `hr`; otherwise `č`, `š`, or `ž` selects `sl`. Other copy sends `detect_language=true`. The query never defaults to English and never sends `language=multi`. An explicit tag matching `^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$` wins. An invalid non-empty tag on `POST /api/drafts/{id}/analyze` is a 409.

An empty transcript sets the voiceover span to start 0, end 0, confidence 0. It must not keep a model span across the clip. Music with no speech stays empty. That empty transcript is not an error.

## Frame flags

`normalize_frame_flags` sets `cta_visible` when the overlay contains `shop now`, `buy now`, `add to basket`, `add to cart`, `go to shopping`, `order now`, `swipe up`, `nakupuj`, `ujemi ponudb`, `skoči`, `skociti`, `skočiti`, `poskrbi`, `preveri ponudb`, `v košarico`, `v kosarico`, or `pojdi v ko`. `nakupuj` also matches `nakupuješ`. The stem `aplikac` is not in that list. Only samples within 0.05 seconds of the last sampled time have `end_frame` true.

`execution.product_first_s` and `execution.logo_first_s` are the earliest true flags. `execution.has_cta` follows `cta_visible`. `execution.end_frame` is the last end-frame overlay, or its label when the overlay is empty. Structure `cta` and `endframe` use the minimum and maximum flagged times at confidence 0.8 when any flag is set.

The saved `frame_labels` in `video_analysis.run` keep `t_sec`, `label`, `brand_visible`, `product_visible`, `logo_visible`, `text_overlay`, `cta_visible`, and `end_frame`. They drop `cut` and `confidence`. `pace_cuts_per_min` was already computed from `cut is True` as `round(cuts * 60 / duration, 2)`. Report a defect if the saved frames are the only persisted frame record and they omit `cut`, because the stored pace then has no saved evidence. `execution.pace` is left `""`. Report a defect if a reader can treat that empty string as the pace.

`brand_seconds`, `product_seconds`, and `logo_seconds` stay whatever the structurer returned. This pass does not rebuild them from the flags. Benchmarks and diagnostics read `product_seconds`. Suggested tests and `execution.product_first_s` read the flags. Report a defect where those two records can disagree for the same frames. `execution.spoken_brand_s` stays null. Audible matches are stored as `brand_audio_mention_s` only when timed words contain a supplied brand term.

## Classifications

These fill only when the stored value is missing or `unknown`, except creator mode, which is reconciled from the frames:

- A person word in a frame label (`man`, `woman`, `person`, `creator`, `guy`, `girl`, `people`, `face`, `unboxing`) plus a brand, logo, call to action, or call-to-action overlay is `hybrid`. A person alone is `creator`. With no person, a model value in `creator`, `branded`, or `hybrid` is kept.
- `edit_style` changes only when it is missing or `other` and `edit_confidence` is 0. Person plus `phone`, `screen`, or `app` becomes `ugc` at confidence 0.6. Screen alone becomes `screen_recording`. Person alone becomes `talking_head`.
- Opening text on the first sample is `text_led`. A person with no text is `direct_to_camera`. A product with no person and no text is `product_first`. A transcript with no opening text is `voiceover`.
- First-person cues `jaz `, `jaz,`, `sem našla`, `sem nasla`, `i found`, `my favorite`, and `my favourite` are `peer_recommendation`. Report a defect if an English cue matches inside an unrelated word the way `app` used to match inside `happy`.
- Discount is `%`, the stems `popust` and `akcij`, or the whole words `discount`, `discounts`, and `off`. Retail is the whole words `app`, `apps`, `shop`, `shops`, `basket`, `baskets`, `buy`, `order`, and `orders`, or the stems `aplikac`, `košar`, `kosar`, and `nakup`. A currency mark with no retail cue is `price`. `Happy birthday` and `Meet our officer` stay `unknown`. Any derived promotion or `cta_visible` frame sets `message_class` to `promotional`.
- Person plus screen is format `hybrid`. Person alone is `creator_led`. Screen alone is `branded`.

`hook_type` and `hook_modality` are copied from the structurer. This pass does not correct them. Human-confirmed dimensions win on a later auto save.

## Measured rows

`measured_from_records` sums, then divides. Pooled link click-through rate is `round(pool_clicks / pool_impressions * 100, 2)` over records that have both impressions and link clicks. It is not the average of row rates. A missing side is excluded from the pool and does not become zero. A total with no known contributor is `None`. Mixed currencies leave combined spend `None` and keep `spend_by_currency`. `unspecified` is its own currency. The same import of two rows for one clip must pool both rows.

Suggested tests, at most four: hook confidence below 0.5 suggests `hook-clarity`. No `cta_visible` and no call-to-action overlay suggests `cta-presence`. No product time suggests `product-timing` with the absent-product reason. A first product after 3 seconds suggests it with the late-product reason. A product at or before 3 seconds does not. An empty transcript suggests `silent-cut`. A visible product at 0 seconds plus a `nakupuj` overlay suggests nothing when the hook confidence is at least 0.5 and a transcript exists.

## Five local clips

These files are not in the repo. Do not upload them. They are the data standard for the rules above, from the ffprobe lengths and the imported sheet, not from a live ad account.

| Clip | Probed length | Impressions | Link clicks | Spend | Conversions | Pooled CTR | Speech |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 04 | 15.800 | 4000 | 100 | 30 | 6 | 2.50 from 2 rows | none |
| 05 | 17.400 | 5000 | 150 | 25 | 8 | 3.00 | none |
| 06 | 23.080 | 2500 | 50 | 10 | 4 | 2.00 | Slovenian when the overlay has `č`, `š`, or `ž` |
| 07 | 15.600 | 8000 | 200 | 40 | 12 | 2.50 | none |
| 08 | 10.360 | 1500 | 45 | 7.5 | 3 | 3.00 | none |

Clip 04 must not be reported as 2.00 by averaging two row rates. Clips 04, 05, 07, and 08 must keep an empty transcript. Clip 06 must not be stored as the English word `Okay.` when the overlay selected `sl`. A creator on camera with a brand or app screen must not stay `branded`. A written `nakupuj`, `ujemi ponudb`, or `poskrbi` line must count as a call to action. Stored duration must be the probed length, not the last sample. Pace must not be a count of `cut=true` frames written straight into a per-minute field.

The tree has not re-analyzed these five files since the rules landed. That absence is not a source defect. It also means this audit cannot call their live transcripts or hook labels perfect.
