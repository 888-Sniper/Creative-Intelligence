"""Creative annotation schema v0 + pipeline.

Pipeline: ingest -> transcribe -> frame-sample -> vision-annotate ->
LLM-structure, each stage recording confidence. Nothing leaves the Mac
in mock mode; live providers (providers.py) require Keychain keys +
provider_mode=live. Export requires HUMAN-VERIFIED status.

Note: HOOK_TYPES here is the creative-PATTERN taxonomy (question,
bold_claim, ...). The interchange schema (Schema/Canonical Schema V0.json)
tracks hook DELIVERY channel (visual|spoken|text) in a separate hook_type
field. The two axes are complementary, never interchangeable.
"""

import datetime
import json

SCHEMA_VERSION = "v0"

HOOK_TYPES = ("question", "bold_claim", "demo_open", "social_proof",
              "offer", "story", "pattern_interrupt", "other")

HOOK_MODALITIES = ("visual", "spoken", "text", "unknown")

EDIT_STYLES = ("talking_head", "ugc", "product_demo", "montage",
               "slideshow_static", "cinematic", "testimonial",
               "screen_recording", "mixed", "other")

MAX_BRAND_TERMS = 20


def brand_audio_mentions(transcript_words, brand_terms):
    """First audible mention per brand term over timed words.

    transcript_words: [{w, t, level?, end?}, ...] from STT.
    brand_terms: user lexicon (client/brand names) — matching
    without a lexicon would be guessing, so no terms means no
    mentions. Multi-word terms use a sliding window timed at the
    first word. Entries whose timing is segment-level (Groq)
    match approximately: the term fell somewhere inside the
    segment, so matches carry approx=True plus the segment end,
    and the roll-up sets brand_audio_approx. Word-level
    (Deepgram) matches stay exact. Returns
    {"brand_audio_mention_s": float|None, "brand_audio_approx": bool,
     "matches": [{term, t, end?, approx}]}.
    """
    words = [e for e in (transcript_words or [])
             if isinstance(e, dict) and isinstance(e.get("w"), str)
             and isinstance(e.get("t"), (int, float))]
    terms = []
    for term in (brand_terms or [])[:MAX_BRAND_TERMS]:
        parts = str(term or "").casefold().split()
        if parts:
            terms.append(parts)
    matches = []
    lowered = [e["w"].casefold() for e in words]
    for parts in terms:
        needle = " ".join(parts)
        candidates = []
        for i in range(len(lowered) - len(parts) + 1):
            if lowered[i:i + len(parts)] == parts:
                window = words[i:i + len(parts)]
                approx = any(e.get("level") == "segment"
                             for e in window)
                match = {"term": needle,
                         "t": round(float(words[i]["t"]), 2),
                         "approx": approx}
                ends = [e.get("end") for e in window
                        if isinstance(e.get("end"), (int, float))]
                if approx and ends:
                    match["end"] = round(float(max(ends)), 2)
                candidates.append(match)
                break
        # Segment entries hold whole sentences, not words: a term
        # inside one matches approximately (somewhere within the
        # segment window), never at an exact word time.
        for e in words:
            if e.get("level") != "segment":
                continue
            if needle in (e["w"] or "").casefold():
                match = {"term": needle,
                         "t": round(float(e["t"]), 2),
                         "approx": True}
                if isinstance(e.get("end"), (int, float)):
                    match["end"] = round(float(e["end"]), 2)
                candidates.append(match)
                break
        if candidates:
            matches.append(min(candidates, key=lambda m: m["t"]))
    first = min((m["t"] for m in matches), default=None)
    return {"brand_audio_mention_s": first,
            "brand_audio_approx": any(m["approx"] for m in matches),
            "matches": matches}

STRUCTURE_SLOTS = ("hook", "body", "demo", "supers", "cta",
                   "endframe", "voiceover")

CREATOR_MODES = ("creator", "branded", "hybrid")

STATUSES = ("auto", "human_verified")


def blank_annotation():
    return {
        "schema_version": SCHEMA_VERSION,
        "hook_type": "other",
        "hook_modality": "unknown",
        "hook_confidence": 0.0,
        "brand_seconds": [],
        "product_seconds": [],
        "logo_seconds": [],
        "structure": {slot: {"start_s": 0.0, "end_s": 0.0, "confidence": 0.0}
                      for slot in STRUCTURE_SLOTS},
        "creator_vs_branded": "branded",
        "creator_confidence": 0.0,
        "edit_style": "other",
        "edit_confidence": 0.0,
        "duration_s": 0.0,
        "pace_cuts_per_min": 0.0,
        "status": "auto",
    }


def validate(ann):
    errors = []
    if ann.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be %r" % SCHEMA_VERSION)
    if ann.get("hook_type") not in HOOK_TYPES:
        errors.append("hook_type must be one of %s" % (list(HOOK_TYPES),))
    if ("hook_modality" in ann and
            ann.get("hook_modality") not in HOOK_MODALITIES):
        errors.append("hook_modality must be one of %s" % (list(HOOK_MODALITIES),))
    if "edit_style" in ann and ann.get("edit_style") not in EDIT_STYLES:
        errors.append("edit_style must be one of %s" % (list(EDIT_STYLES),))
    if ann.get("creator_vs_branded") not in CREATOR_MODES:
        errors.append("creator_vs_branded must be one of %s" % (list(CREATOR_MODES),))
    for slot in STRUCTURE_SLOTS:
        seg = (ann.get("structure") or {}).get(slot)
        if not isinstance(seg, dict):
            errors.append("structure.%s missing" % slot)
            continue
        if seg.get("end_s", 0) < seg.get("start_s", 0):
            errors.append("structure.%s end_s < start_s" % slot)
        for key in ("start_s", "end_s", "confidence"):
            try:
                float(seg.get(key, 0))
            except (TypeError, ValueError):
                errors.append("structure.%s.%s not numeric" % (slot, key))
    for key in ("brand_seconds", "product_seconds", "logo_seconds"):
        for span in ann.get(key, []) or []:
            if span.get("end_s", 0) < span.get("start_s", 0):
                errors.append("%s span end_s < start_s" % key)
    for key in ("hook_confidence", "creator_confidence"):
        try:
            c = float(ann.get(key, -1))
            if not 0.0 <= c <= 1.0:
                errors.append("%s must be 0..1" % key)
        except (TypeError, ValueError):
            errors.append("%s must be 0..1" % key)
    if ann.get("status") not in STATUSES:
        errors.append("status must be one of %s" % (list(STATUSES),))
    return errors


def _attach_prior_media(conn, creative_key, ann):
    """Fill source_url from the newest upload when the annotation lacks one.

    Media uploaded before any annotation exists cannot link at upload
    time; the pipeline (or a later manual annotate) creating the first
    annotation picks that upload up here instead of leaving the
    creative without a preview. Never overwrites an existing value.
    """
    if not isinstance(ann, dict) or ann.get("source_url"):
        return
    try:
        row = conn.execute(
            "SELECT id FROM media WHERE creative_key=? ORDER BY id DESC"
            " LIMIT 1", (creative_key,)).fetchone()
    except Exception:
        return
    if row:
        ann["source_url"] = "/media/%d" % row[0]


def save_annotation(conn, creative_key, ann):
    errors = validate(ann)
    if errors:
        raise ValueError("; ".join(errors))
    _attach_prior_media(conn, creative_key, ann)
    conn.execute(
        "INSERT INTO annotations (creative_key, schema_version, annotation_json, updated_at)"
        " VALUES (?, ?, ?, ?) ON CONFLICT (creative_key) DO UPDATE SET"
        " schema_version=excluded.schema_version,"
        " annotation_json=excluded.annotation_json,"
        " updated_at=excluded.updated_at",
        (creative_key, SCHEMA_VERSION, json.dumps(ann),
         datetime.datetime.now(datetime.timezone.utc).isoformat()))
    conn.execute("UPDATE creatives SET status=? WHERE creative_key=?",
                 (ann["status"], creative_key))
    conn.commit()


def mark_verified(conn, creative_key):
    """Manual-verify hook: flip latest annotation + creative to human_verified."""
    row = conn.execute("SELECT annotation_json FROM annotations WHERE creative_key=?",
                       (creative_key,)).fetchone()
    if not row:
        raise ValueError("no annotation for %r: annotate first" % creative_key)
    ann = json.loads(row[0])
    ann["status"] = "human_verified"
    save_annotation(conn, creative_key, ann)
    return ann


def run_pipeline(conn, creative_key, providers, media=None, brand_terms=None,
                 progress=None, cancelled=None):
    """Run all five stages with the given provider bundle; returns stage report.

    media is optional: {"audio": (bytes, mime), "images": [jpeg bytes]}.
    Mocks ignore it; live adapters fail closed without it. brand_terms
    is an optional user lexicon for audible brand-mention timing; with
    none supplied no mention is attributed.

    progress(pct, stage) reports 0-100 at stage boundaries; cancelled()
    is polled at the same points and raises JobCancelled so a revoked
    job stops chaining provider work. A single in-flight subprocess or
    HTTP call still runs to its own timeout — cancellation is honored
    between stages, which is where bills and minutes accumulate.
    """
    from creative_intel.jobs import JobCancelled

    def checkpoint(pct, stage):
        if cancelled is not None and cancelled():
            raise JobCancelled("job cancelled at stage %s" % stage)
        if progress is not None:
            progress(pct, stage)

    creative = conn.execute("SELECT * FROM creatives WHERE creative_key=?",
                            (creative_key,)).fetchone()
    if not creative:
        raise ValueError("unknown creative %r" % creative_key)
    stages = [{"stage": "ingest", "confidence": 1.0}]
    checkpoint(10, "ingest")
    media = media or {}

    audio_blob, audio_mime = media.get("audio") or (None, None)
    timings = []
    if audio_blob is None and (media.get("images") or
                               media.get("image_times")):
        # Silent clip (or image-only upload): no audio track to
        # transcribe. Skip STT with an explicit stage note and continue
        # through vision instead of failing the whole pipeline.
        transcript, conf = "", 0.0
        stages.append({"stage": "transcribe", "confidence": conf,
                       "skipped": "silent: no audio track"})
    else:
        checkpoint(20, "transcribe")
        transcript, conf = providers.stt.transcribe(
            creative_key, audio_bytes=audio_blob, mime=audio_mime,
            timings_out=timings)
        stages.append({"stage": "transcribe", "confidence": conf})
        checkpoint(40, "transcribe")
    conn.execute("UPDATE creatives SET transcript=? WHERE creative_key=?",
                 (transcript, creative_key))

    times = media.get("image_times")
    if times:
        # Frames extracted for these exact seconds (full-video plan:
        # dense opening, even middle, end-frame sample). Telling the
        # vision model the true seconds is what makes late CTA /
        # logo / end-frame timing exact instead of front-loaded.
        frames = [{"t_sec": t} for t in times]
    else:
        frames = providers.vision.sample_frames(creative_key)
    stages.append({"stage": "frame-sample", "frames": len(frames),
                   "covers_s": max([f["t_sec"] for f in frames] + [0]),
                   "confidence": 1.0 if frames else 0.0})

    checkpoint(55, "frame-sample")
    labels = providers.vision.annotate(frames, images=media.get("images"))
    if media.get("duration_s"):
        conn.execute("UPDATE creatives SET duration_s=? WHERE creative_key=?",
                     (media["duration_s"], creative_key))
    stages.append({"stage": "vision-annotate", "labels": len(labels),
                   "confidence": sum(lbl.get("confidence", 0) for lbl in labels)
                   / len(labels) if labels else 0.0})

    checkpoint(75, "vision-annotate")
    ann = providers.llm.structure(transcript, labels)
    checkpoint(90, "llm-structure")
    ann["schema_version"] = SCHEMA_VERSION
    ann["status"] = "auto"
    if timings:
        # Word-level audio timings ({w, t}) when the STT adapter
        # supplies them — basis for audible-mention analysis.
        ann["transcript_words"] = timings[:300]
        found = brand_audio_mentions(ann["transcript_words"], brand_terms)
        if found["brand_audio_mention_s"] is not None:
            ann["brand_audio_mention_s"] = found["brand_audio_mention_s"]
            ann["brand_audio_matches"] = found["matches"]
            ann["brand_audio_approx"] = found["brand_audio_approx"]
    errors = validate(ann)
    if errors:
        raise ValueError("structurer produced invalid v0: " + "; ".join(errors))
    save_annotation(conn, creative_key, ann)
    mean_conf = (ann["hook_confidence"] + ann["creator_confidence"]) / 2
    stages.append({"stage": "llm-structure", "confidence": round(mean_conf, 3),
                   "gate": "needs HUMAN-VERIFIED before export"})
    conn.execute("UPDATE creatives SET pipeline_json=? WHERE creative_key=?",
                 (json.dumps(stages), creative_key))
    conn.commit()
    return {"creative_key": creative_key, "stages": stages, "annotation": ann}
