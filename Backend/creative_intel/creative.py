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
import re

SCHEMA_VERSION = "v0"

HOOK_TYPES = ("question", "bold_claim", "demo_open", "social_proof",
              "offer", "story", "pattern_interrupt", "other")

HOOK_MODALITIES = ("visual", "spoken", "text", "unknown")

EDIT_STYLES = ("talking_head", "ugc", "product_demo", "montage",
               "slideshow_static", "cinematic", "testimonial",
               "screen_recording", "mixed", "other")

# Foap Analyst classification dimensions (spec section 7). Optional on
# top of the v0 schema: old annotations without them stay valid.
OPENING_DELIVERY = ("direct_to_camera", "voiceover", "text_led",
                    "product_first", "demonstration", "silent_aesthetic",
                    "mixed", "unknown")

NARRATIVES = ("peer_recommendation", "first_use", "educational",
              "demonstration", "testimonial", "story", "other",
              "unknown")

MESSAGE_CLASSES = ("promotional", "neutral", "mixed", "unknown")

PROMOTION_KINDS = ("discount", "price", "retail_offer", "subtle_mention",
                   "explicit_sales", "absent", "unknown")

FORMAT_KINDS = ("creator_led", "branded", "hybrid", "b_roll",
                "graphics_remix", "dialogue", "solo_creator", "other",
                "unknown")

MEDIA_KINDS = ("video", "image", "audio", "unknown")

# Dimensions a human analyst may confirm. Auto saves preserve confirmed
# values instead of silently overwriting them.
CONFIRMABLE_DIMS = ("opening_delivery", "hook_type", "hook_modality",
                    "narrative", "message_class", "promotion_kind",
                    "format_kind", "creator_vs_branded", "edit_style")

# Keys copied from the structurer JSON. Analyst dimensions are in
# this list so a value the model returns is stored; omitting one
# leaves the blank "unknown" for apply_observation_facts to fill.
STRUCTURE_COPY_KEYS = ("hook_type", "hook_modality", "hook_confidence",
                       "brand_seconds", "product_seconds", "logo_seconds",
                       "structure", "creator_vs_branded",
                       "creator_confidence", "edit_style",
                       "edit_confidence", "duration_s",
                       "pace_cuts_per_min", "opening_delivery",
                       "narrative", "message_class", "promotion_kind",
                       "format_kind")

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
        # Analyst dimensions (spec section 7). "unknown" is a real
        # state: unclassified, never a silent default claim.
        "opening_delivery": "unknown",
        "narrative": "unknown",
        "message_class": "unknown",
        "promotion_kind": "unknown",
        "format_kind": "unknown",
        "media_kind": "unknown",
        "frame_times": [],
        "timestamp_resolution_s": 0.0,
        "execution": {"product_first_s": None, "logo_first_s": None,
                      "spoken_brand_s": None, "has_cta": None,
                      "end_frame": "", "pace": ""},
        "concept": {"creator_id": "", "angle": "", "use_case": "",
                    "tags": []},
        # Machine observations with supporting evidence spans.
        "evidence": [],
        # Human-confirmed dimensions: {dim: value}. Auto analysis
        # preserves these on save instead of overwriting them.
        "confirmed": {},
        # Measured brand recall stays absent until a study or supplied
        # measurement provides it. Early logo exposure is not recall.
        "measured_recall": None,
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
                import math as _math
                if not _math.isfinite(float(seg.get(key, 0))):
                    raise ValueError("non-finite")
            except (TypeError, ValueError):
                errors.append("structure.%s.%s not numeric" % (slot, key))
    for key in ("brand_seconds", "product_seconds", "logo_seconds"):
        for span in ann.get(key, []) or []:
            if span.get("end_s", 0) < span.get("start_s", 0):
                errors.append("%s span end_s < start_s" % key)
    for key in ("hook_confidence", "creator_confidence"):
        try:
            import math as _math
            c = float(ann.get(key, -1))
            if not _math.isfinite(c) or not 0.0 <= c <= 1.0:
                errors.append("%s must be 0..1" % key)
        except (TypeError, ValueError):
            errors.append("%s must be 0..1" % key)
    if ann.get("status") not in STATUSES:
        errors.append("status must be one of %s" % (list(STATUSES),))
    # Analyst dimensions are optional (v0 annotations stay valid) but
    # constrained when present.
    for key, allowed in (("opening_delivery", OPENING_DELIVERY),
                         ("narrative", NARRATIVES),
                         ("message_class", MESSAGE_CLASSES),
                         ("promotion_kind", PROMOTION_KINDS),
                         ("format_kind", FORMAT_KINDS),
                         ("media_kind", MEDIA_KINDS)):
        if key in ann and ann.get(key) not in allowed:
            errors.append("%s must be one of %s" % (key, list(allowed)))
    for item in ann.get("evidence", []) or []:
        if not isinstance(item, dict) or not item.get("dimension"):
            errors.append("evidence entries need a dimension")
            break
        try:
            float(item.get("confidence", -1))
        except (TypeError, ValueError):
            errors.append("evidence confidence must be numeric")
            break
    return errors


_SPEECH_LANGUAGE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")
_PERSON_WORD = re.compile(
    r"\b(man|woman|person|creator|guy|girl|people|face|unboxing)\b",
    re.IGNORECASE)
_SCREEN_WORD = re.compile(r"\b(phone|screen|app)\b", re.IGNORECASE)
# Whole English words. "app" sits inside "happy", and "off" sits
# inside "officer". Inflected stems stay substrings below.
_ENGLISH_RETAIL_WORD = re.compile(
    r"\b(?:apps?|shops?|baskets?|buy|orders?)\b")
_ENGLISH_DISCOUNT_WORD = re.compile(r"\b(?:discounts?|off)\b")
# "i found" sits inside "ai foundation". Slovenian cues stay
# substrings because they are inflected on purpose.
_ENGLISH_NARRATIVE = re.compile(
    r"\b(?:i found|my favorite|my favourite)\b")
_NARRATIVE_CUES = ("jaz ", "jaz,", "sem našla", "sem nasla")
_RETAIL_STEMS = ("aplikac", "košar", "kosar", "nakup")
_DISCOUNT_STEMS = ("popust", "akcij")
# Imperative shop or app lines. A narrative mention of the app
# ("vrnem v aplikacijo") is not in this list. "nakupuj" also matches
# "nakupuješ", which is the spoken form of the same call to action.
_CTA_PHRASES = (
    "shop now", "buy now", "add to basket", "add to cart",
    "go to shopping", "order now", "swipe up",
    "nakupuj", "ujemi ponudb", "skoči", "skociti", "skočiti",
    "poskrbi", "preveri ponudb", "v košarico", "v kosarico",
    "pojdi v ko",
)


def clean_speech_language(value):
    """A BCP-47 tag safe to put on a speech request, or ""."""
    text = str(value or "").strip()
    if _SPEECH_LANGUAGE.match(text):
        return text
    return ""


def language_from_overlays(labels):
    """Nova-3 language tag implied by on-screen copy, or "".

    Detection without a tag mislabels Slovenian as Bulgarian.
    Slovenian, Czech, and Croatian are Nova-3 languages that the
    detector does not return, and each has letters the others lack.
    Latin copy with none of those letters returns "" so the caller
    can detect the language instead of forcing English.
    """
    parts = []
    for label in labels or []:
        if isinstance(label, dict):
            parts.append(str(label.get("text_overlay") or ""))
    text = " ".join(parts).casefold()
    if not text:
        return ""
    if any(ch in text for ch in "ěřů"):
        return "cs"
    if any(ch in text for ch in "ćđ"):
        return "hr"
    if any(ch in text for ch in "čšž"):
        return "sl"
    return ""


def overlay_is_cta(text):
    """True when the overlay tells the viewer to shop or open the app."""
    folded = str(text or "").casefold()
    return any(phrase in folded for phrase in _CTA_PHRASES)


def _frame_rows(labels):
    return [label for label in (labels or []) if isinstance(label, dict)]


def normalize_frame_flags(labels):
    """Mark imperative overlays as calls to action.

    Only the last sampled time is the end frame. A product page in
    the middle of the clip is not the closing card.
    """
    rows = _frame_rows(labels)
    if not rows:
        return labels
    last_t = max(float(row.get("t_sec") or 0) for row in rows)
    for row in rows:
        if overlay_is_cta(row.get("text_overlay")):
            row["cta_visible"] = True
        try:
            t_sec = float(row.get("t_sec") or 0)
        except (TypeError, ValueError):
            t_sec = 0.0
        row["end_frame"] = abs(t_sec - last_t) <= 0.05
    return labels


def _label_has_person(row):
    return _PERSON_WORD.search(str(row.get("label") or "")) is not None


def _first_time(rows, flag):
    times = []
    for row in rows:
        if not row.get(flag):
            continue
        try:
            times.append(float(row.get("t_sec")))
        except (TypeError, ValueError):
            continue
    return min(times) if times else None


def _flag_span(rows, pred):
    times = []
    for row in rows:
        if not pred(row):
            continue
        try:
            times.append(float(row.get("t_sec")))
        except (TypeError, ValueError):
            continue
    if not times:
        return None
    return {"start_s": min(times), "end_s": max(times), "confidence": 0.8}


def _observed_runs(rows, flag):
    """One span per contiguous run of frames where flag is true.

    An explicit false frame ends the run. True at 0, false at 3,
    and true at 6 stay two spans, so second 3 is not inside one.
    """
    timed = []
    for row in rows:
        if not isinstance(row, dict) or flag not in row:
            continue
        try:
            t_sec = float(row.get("t_sec"))
        except (TypeError, ValueError):
            continue
        timed.append((t_sec, row.get(flag) is True))
    timed.sort(key=lambda item: item[0])
    spans = []
    start = None
    end = None
    for t_sec, visible in timed:
        if visible:
            if start is None:
                start = t_sec
            end = t_sec
        elif start is not None:
            spans.append({"start_s": start, "end_s": end})
            start = None
            end = None
    if start is not None:
        spans.append({"start_s": start, "end_s": end})
    return spans


def _reconcile_observed_span(ann, rows, key, flag):
    """Store the frame runs in place of the model spans.

    Benchmarks and retention read the span list. Execution reads
    the first true flag. A model span at 0s cannot stand when the
    frame at 0s is false and the first true frame is later.
    """
    if not any(isinstance(row, dict) and row.get(flag) is True
               for row in rows):
        return
    ann[key] = _observed_runs(rows, flag)


def reconcile_creator_mode(labels, current):
    """A person on camera is never a brand-only spot.

    branded means the brand is the speaker. A creator plus brand or
    app screens is hybrid. With no person in the frame labels, the
    model's value stands.
    """
    rows = _frame_rows(labels)
    person = any(_label_has_person(row) for row in rows)
    brandish = any(row.get("brand_visible") or row.get("logo_visible")
                   or row.get("cta_visible") or overlay_is_cta(
                       row.get("text_overlay"))
                   for row in rows)
    if person and brandish:
        return "hybrid"
    if person:
        return "creator"
    if current in CREATOR_MODES:
        return current
    return "branded"


def _derive_edit_style(rows):
    person = any(_label_has_person(row) for row in rows)
    screen = any(_SCREEN_WORD.search(str(row.get("label") or ""))
                 for row in rows)
    if person and screen:
        return "ugc"
    if screen:
        return "screen_recording"
    if person:
        return "talking_head"
    return ""


def _derive_opening(rows, transcript):
    if not rows:
        return ""
    first = min(rows, key=lambda row: float(row.get("t_sec") or 0))
    text = str(first.get("text_overlay") or "").strip()
    if text:
        return "text_led"
    if _label_has_person(first):
        return "direct_to_camera"
    if first.get("product_visible"):
        return "product_first"
    if str(transcript or "").strip():
        return "voiceover"
    return ""


def _retail_cta(text):
    folded = str(text or "").casefold()
    if _ENGLISH_RETAIL_WORD.search(folded):
        return True
    return any(stem in folded for stem in _RETAIL_STEMS)


def _derive_promotion(rows):
    text = " ".join(str(row.get("text_overlay") or "") for row in rows)
    folded = text.casefold()
    if ("%" in folded or _ENGLISH_DISCOUNT_WORD.search(folded)
            or any(stem in folded for stem in _DISCOUNT_STEMS)):
        return "discount"
    has_price = any(mark in text for mark in ("€", "$", "£"))
    if _retail_cta(folded):
        return "retail_offer"
    if has_price:
        return "price"
    return ""


def _derive_narrative(rows, transcript):
    blob = (str(transcript or "") + " " + " ".join(
        str(row.get("text_overlay") or "") for row in rows)).casefold()
    if _ENGLISH_NARRATIVE.search(blob):
        return "peer_recommendation"
    if any(token in blob for token in _NARRATIVE_CUES):
        return "peer_recommendation"
    return ""


def _derive_format(rows):
    person = any(_label_has_person(row) for row in rows)
    screen = any(_SCREEN_WORD.search(str(row.get("label") or ""))
                 for row in rows)
    if person and screen:
        return "hybrid"
    if person:
        return "creator_led"
    if screen:
        return "branded"
    return ""


def apply_observation_facts(ann, labels, duration_s=None, transcript=""):
    """Fill facts the frames and the probed duration already decide.

    The structurer is still asked for these fields. This pass
    replaces a branded label when a person is on camera, replaces
    an untouched edit style, fills analyst dimensions left unknown,
    and stores the probed clip length instead of the last frame time.
    Pace is cuts per minute from the cut flags, not a model guess.
    """
    rows = _frame_rows(labels)
    ann = dict(ann) if isinstance(ann, dict) else blank_annotation()
    ann["creator_vs_branded"] = reconcile_creator_mode(
        rows, ann.get("creator_vs_branded"))
    try:
        edit_conf = float(ann.get("edit_confidence") or 0)
    except (TypeError, ValueError):
        edit_conf = 0.0
    if ann.get("edit_style") in (None, "", "other") and edit_conf == 0.0:
        derived_edit = _derive_edit_style(rows)
        if derived_edit:
            ann["edit_style"] = derived_edit
            ann["edit_confidence"] = 0.6
    derived = {
        "opening_delivery": _derive_opening(rows, transcript),
        "narrative": _derive_narrative(rows, transcript),
        "promotion_kind": _derive_promotion(rows),
        "format_kind": _derive_format(rows),
    }
    if derived["promotion_kind"] or any(
            row.get("cta_visible") for row in rows):
        derived["message_class"] = "promotional"
    else:
        derived["message_class"] = ""
    for key, value in derived.items():
        if value and ann.get(key) in (None, "", "unknown"):
            ann[key] = value
    execution = dict(ann.get("execution") or {})
    execution["product_first_s"] = _first_time(rows, "product_visible")
    execution["logo_first_s"] = _first_time(rows, "logo_visible")
    _reconcile_observed_span(ann, rows, "product_seconds", "product_visible")
    _reconcile_observed_span(ann, rows, "logo_seconds", "logo_visible")
    _reconcile_observed_span(ann, rows, "brand_seconds", "brand_visible")
    execution["has_cta"] = (any(row.get("cta_visible") for row in rows)
                            if rows else None)
    ends = [row for row in rows if row.get("end_frame")]
    if ends:
        execution["end_frame"] = str(
            ends[-1].get("text_overlay") or ends[-1].get("label") or "")
    ann["execution"] = execution
    structure = ann.get("structure")
    if isinstance(structure, dict):
        cta = _flag_span(rows, lambda row: row.get("cta_visible"))
        if cta:
            structure["cta"] = cta
        end = _flag_span(rows, lambda row: row.get("end_frame"))
        if end:
            structure["endframe"] = end
        if not str(transcript or "").strip():
            voice = structure.get("voiceover")
            if isinstance(voice, dict):
                voice["start_s"] = 0.0
                voice["end_s"] = 0.0
                voice["confidence"] = 0.0
    try:
        duration = float(duration_s) if duration_s is not None else 0.0
    except (TypeError, ValueError):
        duration = 0.0
    if duration > 0:
        ann["duration_s"] = round(duration, 3)
        cuts = sum(1 for row in rows if row.get("cut") is True)
        ann["pace_cuts_per_min"] = round(cuts * 60.0 / duration, 2)
    return ann


def _confirmed_of(ann):
    confirmed = (ann or {}).get("confirmed")
    return dict(confirmed) if isinstance(confirmed, dict) else {}


def set_classification(conn, creative_key, dim, value, evidence=None,
                       measured_recall=None, video_id=None):
    """Human correction path for one classification dimension.

    Validates the value, appends the supporting evidence entry and
    locks the dimension: later auto saves preserve it instead of
    silently overwriting the analyst's judgement. measured_recall may
    only be set here with an explicit study reference — never inferred
    from logo exposure or audio mentions. Without video_id the edit
    targets the same approved-or-latest row the global readers see.
    """
    allowed = {"opening_delivery": OPENING_DELIVERY,
               "hook_type": HOOK_TYPES, "hook_modality": HOOK_MODALITIES,
               "narrative": NARRATIVES, "message_class": MESSAGE_CLASSES,
               "promotion_kind": PROMOTION_KINDS,
               "format_kind": FORMAT_KINDS,
               "creator_vs_branded": CREATOR_MODES,
               "edit_style": EDIT_STYLES}.get(dim)
    if allowed is None:
        raise ValueError("dimension %r is not human-confirmable" % (dim,))
    if value not in allowed:
        raise ValueError("%s must be one of %s" % (dim, list(allowed)))
    scope = video_id if video_id is not None \
        else annotation_scope_for_key(conn, creative_key)
    ann = scoped_annotation(conn, creative_key, scope)
    ann = dict(ann) if isinstance(ann, dict) else blank_annotation()
    ann[dim] = value
    confirmed = _confirmed_of(ann)
    confirmed[dim] = value
    ann["confirmed"] = confirmed
    if evidence is not None:
        entry = dict(evidence)
        entry["dimension"] = dim
        entry["value"] = value
        entry["by"] = "human"
        ann.setdefault("evidence", []).append(entry)
    if measured_recall is not None:
        if not isinstance(measured_recall, dict) or \
                not measured_recall.get("study"):
            raise ValueError("measured recall needs a study reference")
        ann["measured_recall"] = measured_recall
    save_annotation(conn, creative_key, ann, video_id=scope)
    return ann


def brand_evidence_summary(ann):
    """Four distinct brand states; recall is never inferred.

    Returns {"visible": spans, "spoken_s": t|None,
    "opportunity": note, "recall": measured|None}. An audio mention is
    not proof every viewer heard it; early logo exposure is not proof
    of recall.
    """
    ann = ann or {}
    visible = list(ann.get("brand_seconds") or []) + \
        list(ann.get("logo_seconds") or [])
    spoken = ann.get("brand_audio_mention_s")
    opportunity = None
    if visible or spoken is not None:
        bits = []
        if visible:
            first = min(s.get("start_s", 0) for s in visible
                        if isinstance(s, dict))
            bits.append("brand/logo visible from ~%ss in sampled frames"
                        % first)
        if spoken is not None:
            bits.append("brand spoken at ~%ss of the supplied audio"
                        % spoken)
        opportunity = ("opportunity to encounter the brand: %s. This is"
                       " exposure opportunity, not measured recall."
                       % "; ".join(bits))
    return {"visible": visible, "spoken_s": spoken,
            "opportunity": opportunity,
            "recall": ann.get("measured_recall")}


def message_class_of(ann, ads_row=None):
    """Resolve promotional classification: explicit import value first,
    then the annotation, else unknown. Never guessed from a name."""
    imported = ((ads_row or {}).get("message_class") or "").strip().lower()
    if imported in MESSAGE_CLASSES and imported != "unknown":
        return imported
    labelled = ((ann or {}).get("message_class") or "").strip().lower()
    if labelled in MESSAGE_CLASSES:
        return labelled
    return "unknown"


def _attach_prior_media(conn, creative_key, ann, video_id=""):
    """Fill source_url from the bound upload when the annotation lacks one.

    Media uploaded before any annotation exists cannot link at upload
    time; the pipeline (or a later manual annotate) creating the first
    annotation picks that upload up here instead of leaving the
    creative without a preview. Prefers the media bound to this
    asset version's video row so a shared creative name never links
    a sibling version's bytes; falls back to the newest upload for
    the key (legacy/global flows). Never overwrites an existing value.
    """
    if not isinstance(ann, dict) or ann.get("source_url"):
        return
    row = None
    if video_id:
        try:
            video = conn.execute("SELECT media_id FROM videos WHERE id=?",
                                 (video_id,)).fetchone()
            if video and video[0]:
                row = (video[0],)
        except Exception:
            row = None
    if row is None:
        try:
            row = conn.execute(
                "SELECT id FROM media WHERE creative_key=? ORDER BY id DESC"
                " LIMIT 1", (creative_key,)).fetchone()
        except Exception:
            return
    if row:
        ann["source_url"] = "/media/%d" % row[0]


def save_annotation(conn, creative_key, ann, video_id="", keep=(),
                    commit=True):
    """Persist an annotation, preserving analyst-confirmed dimensions.

    Auto analysis never silently overwrites human-confirmed labels:
    locked dimensions are restored from the stored revision — except
    dimensions named in keep, which carry an explicit human edit that
    must replace the previous decision (see apply_corrections: a new
    authorised correction wins over the old locked value, and the
    confirmed map is updated to the new value). video_id scopes the
    row to one immutable asset version (see scoped_annotation);
    commit=False defers the commit for a caller-owned transaction.
    """
    ann = dict(ann)
    if ann.get("status") != "human_verified":
        # Auto analysis never silently overwrites human-confirmed
        # labels: restore locked dimensions from the stored revision
        # of the SAME scoped row (a sibling asset version's locks
        # must never bleed across).
        try:
            row = conn.execute("SELECT annotation_json FROM annotations"
                               " WHERE creative_key=? AND video_id=?",
                               (creative_key,
                                video_id or "")).fetchone()
        except Exception:
            row = None
        if row:
            try:
                prior = json.loads(row[0])
            except (ValueError, TypeError):
                prior = {}
            locked = {dim: value for dim, value in
                      _confirmed_of(prior).items() if dim not in keep}
            if locked:
                for dim, value in locked.items():
                    ann[dim] = value
                merged = _confirmed_of(ann)
                merged.update(locked)
                ann["confirmed"] = merged
    errors = validate(ann)
    if errors:
        raise ValueError("; ".join(errors))
    _attach_prior_media(conn, creative_key, ann, video_id=video_id)
    conn.execute(
        "INSERT INTO annotations (creative_key, schema_version,"
        " annotation_json, updated_at, video_id)"
        " VALUES (?, ?, ?, ?, ?) ON CONFLICT (creative_key, video_id)"
        " DO UPDATE SET"
        " schema_version=excluded.schema_version,"
        " annotation_json=excluded.annotation_json,"
        " updated_at=excluded.updated_at",
        (creative_key, SCHEMA_VERSION, json.dumps(ann),
         datetime.datetime.now(datetime.timezone.utc).isoformat(),
         video_id or ""))
    conn.execute("UPDATE creatives SET status=? WHERE creative_key=?",
                 (ann["status"], creative_key))
    if commit:
        conn.commit()


def scoped_annotation(conn, creative_key, video_id):
    """One asset version's annotation, or None.

    Exact (creative_key, video_id) match only — never the legacy ''
    row, never a sibling version's row. Draft-scoped paths (read,
    correct, approve, export) must resolve through the draft's bound
    video id so two uploads sharing one editable creative name can
    never see each other's findings.
    """
    try:
        row = conn.execute("SELECT annotation_json FROM annotations"
                           " WHERE creative_key=? AND video_id=?",
                           (creative_key, video_id or "")).fetchone()
    except Exception:
        return None
    if not row:
        return None
    try:
        ann = json.loads(row[0])
    except (ValueError, TypeError):
        return None
    return ann if isinstance(ann, dict) else None


def _ranked_key_rows(conn, creative_key):
    """(annotation, video_id, updated_at) rows for one creative name,
    human_verified first, then latest stamp."""
    try:
        rows = conn.execute("SELECT annotation_json, video_id, updated_at"
                            " FROM annotations WHERE creative_key=?",
                            (creative_key,)).fetchall()
    except Exception:
        return []
    anns = []
    for row in rows or []:
        try:
            ann = json.loads(row[0])
        except (ValueError, TypeError):
            continue
        if isinstance(ann, dict):
            anns.append((ann, row[1] if len(row) > 1 else "",
                         row[2] if len(row) > 2 else ""))
    if not anns:
        return []
    # Human-verified first; among equals, latest stamp wins.
    best = None
    for entry in anns:
        ann, _vid, stamp = entry
        if best is None:
            best = entry
            continue
        verified = ann.get("status") == "human_verified"
        best_verified = best[0].get("status") == "human_verified"
        if verified and not best_verified:
            best = entry
        elif verified == best_verified \
                and str(stamp or "") > str(best[2] or ""):
            best = entry
    ranked = [best]
    ranked.extend(e for e in anns if e is not best)
    return ranked


def annotation_for_key(conn, creative_key):
    """Global reporting reader for one creative name.

    Prefers the human_verified scoped row (the approved result is the
    reporting truth), else the latest-updated row. Tenant-visible
    surfaces keep working across asset versions without ever
    inventing numbers.
    """
    ranked = _ranked_key_rows(conn, creative_key)
    return ranked[0][0] if ranked else None


def annotation_scope_for_key(conn, creative_key):
    """video_id of the row annotation_for_key would return ('' when
    none): lets global write flows target the same row they read."""
    ranked = _ranked_key_rows(conn, creative_key)
    return ranked[0][1] if ranked else ""


def _report_bundle(conn, creative_key, owner=None, admin=False):
    """Applicable confirmation carrying a resolvable video, else None."""
    from creative_intel import drafts as _drafts_mod
    try:
        bundle = _drafts_mod.confirmed_bundle_for_key(
            conn, creative_key, owner=owner, admin=admin)
    except Exception:
        return None
    if isinstance(bundle, dict) and bundle.get("video_id"):
        return bundle
    return None


def _row_owner(conn, video_id):
    """Owning employee of one video version, or '' when the row is
    version-less legacy (a global annotation, not a private video
    result) or unresolvable."""
    if not video_id:
        return ""
    try:
        row = conn.execute(
            "SELECT d.owner_employee_id FROM videos v"
            " JOIN drafts d ON d.id = v.draft_id"
            " WHERE v.id = ?", (video_id,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    return row[0] or ""


def _report_selection(conn, creative_key, owner=None, admin=False):
    """(annotation_or_None, video_id): one call, one selection.

    The confirming video version's own row when the viewer has an
    applicable confirmation (None when that video has no stored
    analysis). Otherwise, a lone stored row is returned only with
    an authorised reader: its video owner (or any admin), or — for
    a version-less legacy row that cannot be anyone's private
    video result — any viewer. Anything else yields (None, ''),
    so export blocks and reporting shows no borrowed findings."""
    bundle = _report_bundle(conn, creative_key, owner=owner,
                            admin=admin)
    if bundle is not None:
        vid = bundle["video_id"]
        return scoped_annotation(conn, creative_key, vid), vid
    ranked = _ranked_key_rows(conn, creative_key)
    if len(ranked) != 1:
        return None, ""
    ann, vid, _stamp = ranked[0]
    if not vid:
        return ann, ""
    if admin:
        return ann, vid
    if owner and _row_owner(conn, vid) == owner:
        return ann, vid
    return None, ""


def video_duration(conn, video_id):
    """One video version's own length, or None when unknown."""
    try:
        row = conn.execute("SELECT duration_s FROM videos WHERE id=?",
                           (video_id,)).fetchone()
    except Exception:
        return None
    if not row or not row[0]:
        return None
    return row[0]


def report_unavailable_fields(conn, creative_key, owner=None,
                              admin=False):
    """(transcript, status, duration_or_None) for a key with no
    authorised annotation — or None when no findings exist at all.

    Findings that exist but are not the viewer's are never
    surfaced: a confirmed-but-unanalysed video reports its own
    length with empty words and status; any other unauthorised
    case reports all empty. Only when no analysis rows exist does
    the caller keep the shared copies (nothing exists to leak, so
    pre-analysis drafts keep their working display)."""
    from creative_intel import drafts as _drafts_mod
    try:
        bundle = _drafts_mod.confirmed_bundle_for_key(
            conn, creative_key, owner=owner, admin=admin)
    except Exception:
        bundle = None
    bvid = bundle.get("video_id") or "" \
        if isinstance(bundle, dict) else ""
    if bvid:
        return "", "", video_duration(conn, bvid)
    try:
        ranked = _ranked_key_rows(conn, creative_key)
    except Exception:
        ranked = []
    if ranked:
        return "", "", None
    return None


def annotation_for_report(conn, creative_key, owner=None, admin=False):
    """One consistent result identity for reporting surfaces, or
    None when no authorised result exists. See _report_selection.

    With no viewer identity (owner None, not admin) the legacy
    global reader stands: viewer-less aggregate surfaces keep
    their existing semantics, and no per-viewer claim is made."""
    if owner is None and not admin:
        return annotation_for_key(conn, creative_key)
    ann, _vid = _report_selection(conn, creative_key, owner=owner,
                                  admin=admin)
    return ann


def annotation_scope_for_report(conn, creative_key, owner=None,
                                admin=False):
    """video_id of the row annotation_for_report would return ( ''
    when none): lets export and reporting pair the selected
    annotation with the same version's transcript."""
    if owner is None and not admin:
        return annotation_scope_for_key(conn, creative_key)
    _ann, vid = _report_selection(conn, creative_key, owner=owner,
                                  admin=admin)
    if _ann is None:
        return ""
    return vid


def mark_verified(conn, creative_key, video_id=None):
    """Manual-verify hook: flip the annotation + creative to
    human_verified. Without video_id acts on the approved-or-latest
    row, matching the global readers."""
    scope = video_id if video_id is not None \
        else annotation_scope_for_key(conn, creative_key)
    ann = scoped_annotation(conn, creative_key, scope)
    if not isinstance(ann, dict):
        raise ValueError("no annotation for %r: annotate first" % creative_key)
    ann["status"] = "human_verified"
    save_annotation(conn, creative_key, ann, video_id=scope)
    return ann


def _require_live_attempt(conn, job_id, run_token):
    """No-op without a job; otherwise prove this attempt still owns
    it (see jobs.require_live_attempt). The legacy pipeline persists
    incrementally between provider calls, so the guard runs before
    each write — shrinking a minutes-wide race to microseconds
    (the guided path instead batches all writes into one guarded
    publication transaction)."""
    if job_id is None:
        return
    from creative_intel import jobs as _jobs_mod
    _jobs_mod.require_live_attempt(conn, job_id, run_token)


def run_pipeline(conn, creative_key, providers, media=None, brand_terms=None,
                 progress=None, cancelled=None, persist=True, job_id=None,
                 run_token=None, speech_language=None):
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

    persist=False generates the full report without touching the
    published creative record (no transcript, annotation, duration, or
    pipeline writes): the caller verifies freshness first and then
    publishes the complete result in one step, so a concurrent
    finisher can never be clobbered by an in-flight job's
    intermediate save.
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
    # Frames before speech: on-screen copy chooses the language.
    # Deepgram's default is English, and detect_language labels
    # Slovenian as Bulgarian, so a tag from the overlays is required
    # before the audio is sent.
    times = media.get("image_times")
    if times:
        # Frames extracted for these exact seconds (full-video plan:
        # dense opening, even middle, end-frame sample). Telling the
        # vision model the true seconds is what makes late CTA /
        # logo / end-frame timing exact instead of front-loaded.
        frames = [{"t_sec": t} for t in times]
    else:
        frames = providers.vision.sample_frames(creative_key)
    frame_times = sorted(float(f.get("t_sec", 0)) for f in frames
                         if isinstance(f, dict))
    gaps = [b - a for a, b in zip(frame_times, frame_times[1:]) if b > a]
    # "First observed at 1.0s" means first sampled frame at 1.0s, not
    # necessarily first appearance: resolution is the sampling step.
    timestamp_resolution_s = round(min(gaps), 2) if gaps else 0.0
    has_audio = audio_blob is not None
    has_images = bool(media.get("images") or frame_times)
    if has_audio and has_images:
        media_kind = "video"
    elif has_images:
        media_kind = "image"
    elif has_audio:
        media_kind = "audio"
    else:
        media_kind = "unknown"
    stages.append({"stage": "frame-sample", "frames": len(frames),
                   "covers_s": max([f["t_sec"] for f in frames] + [0]),
                   "confidence": 1.0 if frames else 0.0})

    checkpoint(40, "frame-sample")
    labels = providers.vision.annotate(frames, images=media.get("images"))
    labels = normalize_frame_flags(labels)
    cut_times = []
    for lbl in labels:
        if not isinstance(lbl, dict) or lbl.get("cut") is not True:
            continue
        try:
            cut_times.append(round(float(lbl.get("t_sec")), 3))
        except (TypeError, ValueError):
            continue
    if persist and media.get("duration_s"):
        _require_live_attempt(conn, job_id, run_token)
        conn.execute("UPDATE creatives SET duration_s=? WHERE creative_key=?",
                     (media["duration_s"], creative_key))
    stages.append({"stage": "vision-annotate", "labels": len(labels),
                   "cuts": cut_times,
                   "confidence": sum(lbl.get("confidence", 0) for lbl in labels)
                   / len(labels) if labels else 0.0})
    checkpoint(55, "vision-annotate")

    if audio_blob is None and (media.get("images") or
                               media.get("image_times")):
        # Silent clip (or image-only upload): no audio track to
        # transcribe. Skip STT with an explicit stage note and continue
        # through structure instead of failing the whole pipeline.
        transcript, conf = "", 0.0
        stages.append({"stage": "transcribe", "confidence": conf,
                       "skipped": "silent: no audio track"})
    else:
        speech = (clean_speech_language(speech_language)
                  or language_from_overlays(labels))
        checkpoint(60, "transcribe")
        transcript, conf = providers.stt.transcribe(
            creative_key, audio_bytes=audio_blob, mime=audio_mime,
            timings_out=timings, language=speech or None)
        stages.append({"stage": "transcribe", "confidence": conf,
                       "language": speech or "detect"})
        checkpoint(75, "transcribe")
    if persist:
        _require_live_attempt(conn, job_id, run_token)
        conn.execute("UPDATE creatives SET transcript=? WHERE creative_key=?",
                     (transcript, creative_key))

    checkpoint(80, "vision-annotate")
    ann = providers.llm.structure(transcript, labels)
    ann = apply_observation_facts(
        ann, labels, media.get("duration_s"), transcript)
    checkpoint(90, "llm-structure")
    ann["schema_version"] = SCHEMA_VERSION
    ann["status"] = "auto"
    ann["media_kind"] = media_kind
    ann["frame_times"] = frame_times
    ann["timestamp_resolution_s"] = timestamp_resolution_s
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
    # Preserve a prior analysis stamp across the intermediate save:
    # without this, job A finishing its pipeline would wipe job B's
    # newer stamped result before A's own staleness check runs. (The
    # guided video-analysis path avoids the hazard entirely with
    # persist=False: nothing below runs, and the caller publishes the
    # complete result only after its freshness checks pass.)
    if persist:
        _require_live_attempt(conn, job_id, run_token)
        try:
            prior_row = conn.execute(
                "SELECT annotation_json FROM annotations WHERE creative_key=?",
                (creative_key,)).fetchone()
            prior_block = (json.loads(prior_row[0]).get("analysis")
                           if prior_row else None)
        except (ValueError, TypeError):
            prior_block = None
        if isinstance(prior_block, dict) \
                and not isinstance(ann.get("analysis"), dict):
            ann["analysis"] = prior_block
        save_annotation(conn, creative_key, ann)
    mean_conf = (ann["hook_confidence"] + ann["creator_confidence"]) / 2
    stages.append({"stage": "llm-structure", "confidence": round(mean_conf, 3),
                   "gate": "needs HUMAN-VERIFIED before export"})
    if persist:
        _require_live_attempt(conn, job_id, run_token)
        conn.execute("UPDATE creatives SET pipeline_json=? WHERE creative_key=?",
                     (json.dumps(stages), creative_key))
        conn.commit()
    return {"creative_key": creative_key, "stages": stages,
            "annotation": ann, "frame_labels": labels,
            "transcript": transcript}
