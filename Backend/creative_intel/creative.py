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


def save_annotation(conn, creative_key, ann):
    errors = validate(ann)
    if errors:
        raise ValueError("; ".join(errors))
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


def run_pipeline(conn, creative_key, providers, media=None):
    """Run all five stages with the given provider bundle; returns stage report.

    media is optional: {"audio": (bytes, mime), "images": [jpeg bytes]}.
    Mocks ignore it; live adapters fail closed without it.
    """
    creative = conn.execute("SELECT * FROM creatives WHERE creative_key=?",
                            (creative_key,)).fetchone()
    if not creative:
        raise ValueError("unknown creative %r" % creative_key)
    stages = [{"stage": "ingest", "confidence": 1.0}]
    media = media or {}

    audio_blob, audio_mime = media.get("audio") or (None, None)
    timings = []
    transcript, conf = providers.stt.transcribe(
        creative_key, audio_bytes=audio_blob, mime=audio_mime,
        timings_out=timings)
    stages.append({"stage": "transcribe", "confidence": conf})
    conn.execute("UPDATE creatives SET transcript=? WHERE creative_key=?",
                 (transcript, creative_key))

    frames = providers.vision.sample_frames(creative_key)
    stages.append({"stage": "frame-sample", "frames": len(frames),
                   "confidence": 1.0 if frames else 0.0})

    labels = providers.vision.annotate(frames, images=media.get("images"))
    stages.append({"stage": "vision-annotate", "labels": len(labels),
                   "confidence": sum(l.get("confidence", 0) for l in labels)
                   / len(labels) if labels else 0.0})

    ann = providers.llm.structure(transcript, labels)
    ann["schema_version"] = SCHEMA_VERSION
    ann["status"] = "auto"
    if timings:
        # Word-level audio timings ({w, t}) when the STT adapter
        # supplies them — basis for audible-mention analysis.
        ann["transcript_words"] = timings[:300]
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
