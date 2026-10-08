# Creative Intelligence audit for 2026-10-08

Review `origin/main` after `git fetch`. Confirm that `origin/main` and GitHub `main` name the same SHA. A behind local checkout or a missing local `main` branch is not a reason to stop; use `git show origin/main:PATH`. Stop only if the remote identities differ or the worktree is dirty.

This is the product repo https://github.com/888-Sniper/Creative-Intelligence. The parent of this push is `2a15c075bac53166913ffebbf01cf5692fe585a5` (`Add the audit for the video analysis fix`). This push stops English promotion cues from matching inside unrelated words. `Happy birthday` stays `unknown`. `Meet our officer` stays `unknown`. Inflected stems still match: `nakup` inside `nakupuj`, `aplikac` inside `aplikaciji`, `popust`, and `akcij`. The analysis behavior from `0a30b34642cb06714b7e94e154cf14a72fb80170` remains in the tree. Do not edit, commit, push, build, install, start the server, upload the five Notino clips again, or activate a provider. Do not treat an unrun live Deepgram call, live Gemini call, live browser, or the five stored clip reports as a source defect. Report only defects still present at the reviewed SHA, with severity, observed behavior, file and line, and the evidence that reproduces them. State checks not performed.

The five clips that motivated the analysis fix are local files, not fixtures in this repo: `04-quentin-retargeting-si.mp4`, `05-quentin-retargeting-si.mp4`, `06-amadea-retargeting-si.mp4`, `07-amadea-retargeting-si.mp4`, and `08-amadea-retargeting-si.mp4`. Clips 04, 05, 07, and 08 are a music bed. An empty transcript on those four is correct. Clip 06 is spoken Slovenian. On-screen Slovenian text and the imported pooled click-through rate were already correct and this push does not recalculate that rate.

## Speech language

Frames are annotated before speech. `run_pipeline` in `Backend/creative_intel/creative.py` appends `ingest`, then `frame-sample`, then `vision-annotate`, then `transcribe`, then `llm-structure`. That is still five stages. A clip with images and no audio skips speech and records `skipped`: `silent: no audio track`.

When `speech_language` is a tag matching `^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$`, that tag is sent. When it is empty, `language_from_overlays` reads `text_overlay`: `ě`, `ř`, or `ů` selects `cs`; otherwise `ć` or `đ` selects `hr`; otherwise `č`, `š`, or `ž` selects `sl`. Copy with none of those letters returns `""`. `deepgram_listen_query` in `Backend/creative_intel/providers.py` then sends `language=<tag>` when a tag exists, and `detect_language=true` when it does not. The query never defaults to English and never sends `language=multi`. The same tag is added to the Groq form when set. `detect_language=true` alone is the fallback for unmarked copy. It is not the path for these Slovenian overlays, because a live probe labeled clip 06 as Bulgarian.

`POST /api/drafts/{draft_id}/analyze` accepts optional `speech_language` (`AnalyzeBody` in `Backend/ci_backend/routers/product.py`). A non-empty value that fails the tag check raises `ValueError`, which that route returns as 409. The job payload stores the tag, and `run_video_analysis` in `Backend/ci_backend/worker_handlers.py` passes `brand_terms` and `speech_language` into `video_analysis.run`. There is no new control in `apps/creative-intelligence-ui`. `POST /api/pipeline/run` still has no `speech_language` field. That route calls `run_pipeline` without the argument, so overlay selection still applies there.

## Creator, edit, and analyst fields

`STRUCTURE_COPY_KEYS` in `Backend/creative_intel/creative.py` includes `edit_style`, `edit_confidence`, `opening_delivery`, `narrative`, `message_class`, `promotion_kind`, and `format_kind`. `LiveLlm.structure` and `ManagedLlm.structure` copy that tuple onto the annotation. A model value outside the allowed set still fails validation.

`apply_observation_facts` runs after structure and before `validate`:

- A frame label matching `\b(man|woman|person|creator|guy|girl|people|face|unboxing)\b` plus a brand, logo, call to action, or call-to-action overlay becomes `hybrid`. A person with none of those becomes `creator`. With no person, a model value in `creator`, `branded`, or `hybrid` is kept, and anything else becomes `branded`.
- `edit_style` is derived only when the stored style is missing or `other` and `edit_confidence` is 0. Person plus `phone`, `screen`, or `app` becomes `ugc` at confidence 0.6. Screen alone becomes `screen_recording`. Person alone becomes `talking_head`. A model style with confidence above 0 is kept.
- Analyst fields are filled only when missing or `unknown`. Text on the first sampled frame becomes `text_led`. A person with no text becomes `direct_to_camera`. A product with no person and no text becomes `product_first`. A transcript with no opening text becomes `voiceover`. First-person cues (`jaz `, `jaz,`, `sem našla`, `sem nasla`, `i found`, `my favorite`, `my favourite`) become `peer_recommendation`. A discount cue becomes `discount`: `%`, the stems `popust` and `akcij`, or the whole words `discount`, `discounts`, and `off`. A retail cue becomes `retail_offer`: the whole words `app`, `apps`, `shop`, `shops`, `basket`, `baskets`, `buy`, `order`, and `orders`, or the stems `aplikac`, `košar`, `kosar`, and `nakup`. A currency mark with no retail cue becomes `price`. `app` does not match inside `happy` or `application`. `off` does not match inside `officer`. Any derived promotion or `cta_visible` frame sets `message_class` to `promotional`. Person plus screen becomes format `hybrid`; person alone becomes `creator_led`; screen alone becomes `branded`.

`STRUCTURE_PROMPT` states the same creator, edit, duration, pace, and analyst enums, and tells the model to leave voiceover at confidence 0 when the transcript is empty.

## Frame flags, duration, pace, and suggested tests

`normalize_frame_flags` runs on the vision labels before structure. An overlay whose casefold contains one of `shop now`, `buy now`, `add to basket`, `add to cart`, `go to shopping`, `order now`, `swipe up`, `nakupuj`, `ujemi ponudb`, `skoči`, `skociti`, `skočiti`, `poskrbi`, `preveri ponudb`, `v košarico`, `v kosarico`, or `pojdi v ko` sets `cta_visible`. `nakupuj` also matches `nakupuješ`. The bare stem `aplikac` is a retail-promotion cue inside `_retail_cta` and is not a call-to-action phrase, so an opening line that only says the viewer goes into the app does not become a call to action. Only sampled frames within 0.05 seconds of the last sampled `t_sec` have `end_frame` true.

`apply_observation_facts` sets `execution.product_first_s` and `execution.logo_first_s` from the earliest true flag, sets `execution.has_cta` from the flags, and copies the last end-frame overlay into `execution.end_frame`. When those flags exist, the structure `cta` and `endframe` spans use the minimum and maximum flagged times at confidence 0.8. An empty transcript sets the voiceover span to start 0, end 0, confidence 0. When `duration_s` is greater than 0, annotation `duration_s` becomes that probed length rounded to 3 decimals, and `pace_cuts_per_min` becomes the count of frames with `cut is True`, times 60, divided by that duration. A model that forgets every cut stores pace 0.

`suggest_tests` in `Backend/creative_intel/video_analysis.py` treats `cta_visible` or a call-to-action overlay as a call to action. Product timing uses `execution.product_first_s` when that value is numeric, otherwise the earliest `product_visible` frame. No product time suggests product timing with the absent-product reason. A first product after 3 seconds suggests it with the late-product reason. A product at or before 3 seconds does not. The function still returns at most four suggestions. Pooled link click-through rate remains link clicks divided by impressions, not the average of row rates (`pool_clicks / pool_impressions * 100`).

## Vision roster and the admin gate

`VIDEO_MODEL_SUPPORT` marks `gemini-3.5-flash-lite` and `gemini-3.7-flash` as `image`. They are frame-eligible and not native-video eligible. The Gemini 2.5 rows stay `native-video`. `eligible_vision_roster` keeps a roster entry only when `frame_eligible` is true and the provider is configured. A fresh database with no `active_provider_selection` still raises `NOT_CONFIGURED_MESSAGE` (`AI is not configured. Contact your administrator.`) from `ManagedLlm` resolution in `Backend/creative_intel/dispatcher.py`. This push does not activate a model and does not fall back to another roster.

## How to confirm

From the repo root, with the dev extra:

```
uv run --extra dev pytest tests/test_video_analysis.py tests/test_live_providers.py tests/test_pipeline.py tests/test_cohort_delete.py tests/test_admin_providers.py tests/test_acceptance_10.py -q --tb=line
```

The locks for this push are `test_promotion_cues_do_not_match_inside_unrelated_words`, `test_observation_facts_use_frames_and_probed_duration`, the product-visible and late-product cases in `test_suggest_tests_grounded_in_absences`, `test_deepgram_query_detects_unless_language_is_known`, and `test_frame_eligible_covers_ffmpeg_outputs` (`gemini-3.5-flash-lite` and `gemini-3.7-flash` frame-eligible, and `gemini-3.5-flash-lite` not video-eligible).

Confirm these spots by reading the reviewed SHA:

- `language_from_overlays`, `normalize_frame_flags`, `reconcile_creator_mode`, `apply_observation_facts`, and the stage order in `run_pipeline` (`Backend/creative_intel/creative.py`).
- `deepgram_listen_query`, `VISION_PROMPT`, and `STRUCTURE_PROMPT` (`Backend/creative_intel/providers.py`).
- The `STRUCTURE_COPY_KEYS` copy in `ManagedLlm.structure` and the unchanged `NOT_CONFIGURED_MESSAGE` raise (`Backend/creative_intel/dispatcher.py`).
- `_frames_have_cta`, `_product_first_s`, and `suggest_tests` (`Backend/creative_intel/video_analysis.py`).
- The two Gemini 3 image rows (`Backend/creative_intel/provider_inventory.py`).
- `speech_language` on `AnalyzeBody` and the video-analysis job payload (`Backend/ci_backend/routers/product.py`).
- The worker call that passes `brand_terms` and `speech_language` (`Backend/ci_backend/worker_handlers.py`).

## Known limits that are not defects of this push

A Croatian overlay that uses only `č`, `š`, or `ž` is sent as Slovenian until the request sets `speech_language`. A vision label that says `woman` can mark a brand film `hybrid`. Pace is 0 when duration is known and no frame has `cut` true. Human-confirmed dimensions still win when an annotation is saved. The five Notino reports already stored from the earlier run are unchanged until someone analyzes those drafts again.
