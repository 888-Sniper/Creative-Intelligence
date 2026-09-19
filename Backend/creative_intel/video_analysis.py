"""Video-upload analysis: snapshot binding, prepare, run, measure.

One Analyse press binds an IMMUTABLE snapshot (video version, dataset
version, confirmed mapping). The worker re-resolves and compares it:
changed inputs abort instead of analysing the wrong thing, and a
late result never overwrites a newer analysis.

Honesty rules (frozen contract):
- Only frame-eligible models (native-video|image in VIDEO_MODEL_SUPPORT)
  touch frames. Unverified ids are never offered the frame path, even
  though LiveVision.annotate would attempt them per-call.
- Metrics come from the confirmed records via the analytics layer
  (pooled totals here), never the LLM. Missing is not zero; a zero
  denominator yields no rate. No benchmarks, retention curves, spend
  efficiency claims, or causal language: suggestions are hypotheses.
- Silent clips skip STT with an explicit note (run_pipeline handles
  audio=None + images); absent speech/branding stays "unknown"/absent.
"""

import datetime
import json
import os
import tempfile
import uuid

ANALYSIS_VERSION = "v1"


class AnalysisUnavailable(Exception):
    """Honest stop: honest state + recovery action for the caller."""


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def eligible_vision_roster():
    """Configured live vision entries that may consume frames.

    Intersects the live bundle roster with the verified support
    table: native-video and image levels qualify; text-only, audio,
    and unverified ids do not. Empty (or mock mode) means analysis
    is unavailable — never a mock substitution.
    """
    from creative_intel import provider_inventory as inv
    from creative_intel import providers as prov_mod
    if prov_mod.mode() != "live":
        return []
    try:
        bundle = prov_mod.LiveBundle()
    except prov_mod.ProviderUnavailable:
        return []
    return [(p, m, t) for p, m, t in bundle.VISION_ROSTER
            if inv.frame_eligible(p, m)]


def readiness():
    """What Stage D shows: selected provider, content sent, storage."""
    roster = eligible_vision_roster()
    if not roster:
        from creative_intel import providers as prov_mod
        reason = ("provider mode is %r: switch on a live provider"
                  % prov_mod.mode())
        try:
            prov_mod.LiveBundle()
        except prov_mod.ProviderUnavailable as exc:
            reason = str(exc)
        return {"ready": False, "reason": reason, "model": "",
                "provider": "", "level": "",
                "sends": "sampled JPEG frames + 16kHz mono WAV "
                         "(never the raw video file)",
                "storage": "private media store; derived frames kept "
                           "with the draft, deleted with it"}
    provider, model, _tier = roster[0]
    from creative_intel import provider_inventory as inv
    level, _doc = inv.frame_support(provider, model)
    return {"ready": True, "reason": "", "model": model,
            "provider": provider, "level": level,
            "sends": "sampled JPEG frames + 16kHz mono WAV "
                     "(never the raw video file)",
            "storage": "private media store; derived frames kept "
                       "with the draft, deleted with it"}


def bind_snapshot(conn, draft_id):
    """Verify preconditions and freeze the analysis snapshot.

    An incomplete draft may be saved at any time, but combined
    analysis requires an authorised, confirmed campaign destination:
    the draft's own spec must carry clientConfirmed with a named
    client and campaign (owner-or-admin writes only, like every other
    draft mutation). Reports without a client column inherit the
    confirmed destination explicitly in the snapshot — the
    association is never left ambiguous.
    """
    from creative_intel import drafts as drafts_mod
    draft = drafts_mod.get_draft(conn, draft_id)
    if draft is None:
        raise AnalysisUnavailable("unknown upload draft")
    video = drafts_mod.active_video(conn, draft_id)
    if video is None:
        raise AnalysisUnavailable("validate the video before analysing")
    try:
        spec = json.loads(draft.get("spec_json") or "{}")
    except ValueError:
        spec = {}
    if not isinstance(spec, dict):
        spec = {}
    client = str(spec.get("client") or "").strip()
    campaign = str(spec.get("campaign") or "").strip()
    if not spec.get("clientConfirmed") or not client or not campaign:
        raise AnalysisUnavailable(
            "confirm the client and campaign before analysing: "
            "combined analysis needs a confirmed destination")
    version = draft.get("dataset_version") or ""
    if not version:
        raise AnalysisUnavailable("import performance data before analysing")
    matches = [m for m in _all_matches(conn, draft_id) if m["confirmed"]]
    if not matches:
        raise AnalysisUnavailable("confirm the video-to-data match first")
    match = matches[0]
    return {"draft_id": draft_id, "video_id": video["id"],
            "creative_key": video["creative_key"],
            "video_sha256": video.get("sha256") or "",
            "duration_s": float(video.get("duration_s") or 0.0),
            "media_id": int(video.get("media_id") or 0),
            "dataset_version": version,
            "match_confirmed_at": match.get("confirmed_at") or "",
            "match_method": match.get("method") or "",
            "client": client, "campaign": campaign,
            "records": json.loads(match.get("record_json") or "[]"),
            "analysis_version": ANALYSIS_VERSION}


def _all_matches(conn, draft_id):
    cur = conn.execute("SELECT * FROM matches WHERE draft_id = ?",
                       (draft_id,))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def check_snapshot(conn, snapshot):
    """Re-resolve at job time: inputs must equal the bound snapshot."""
    fresh = bind_snapshot(conn, snapshot["draft_id"])
    for key in ("video_id", "media_id", "creative_key", "video_sha256",
                "dataset_version", "match_confirmed_at",
                "client", "campaign"):
        if (fresh.get(key) or "") != (snapshot.get(key) or ""):
            raise AnalysisUnavailable(
                "inputs changed since Analyse was pressed (%s): "
                "re-confirm the match and analyse again" % key)
    if not fresh["match_confirmed_at"]:
        raise AnalysisUnavailable("match confirmation was cleared: "
                                  "re-confirm before analysing")
    return fresh


def prepare_media(src_path, duration_s, want_audio=True):
    """ffmpeg breakdown: exact per-timestamp JPEGs + 16kHz mono WAV.

    Returns {images, image_times, audio, audio_mime, sampling}.
    Audio-free clips return audio None (honest silent path, not an
    error). Raises AnalysisUnavailable when ffmpeg is missing or the
    clip yields no frames.
    """
    from creative_intel import video as video_mod
    if not video_mod.have_ffmpeg():
        raise AnalysisUnavailable("ffmpeg is not installed: cannot "
                                  "prepare frames/audio on this host")
    times = video_mod.sample_times(duration_s)
    workdir = tempfile.mkdtemp(prefix="video-prep-")
    try:
        images = []
        for t in times:
            dst = os.path.join(workdir, "f.jpg")
            try:
                blob = video_mod.extract_frame_at(src_path, t, dst)
            except Exception as exc:
                raise AnalysisUnavailable("frame extraction failed at "
                                          "%ss: %s" % (t, exc))
            if isinstance(blob, (bytes, bytearray)):
                images.append(blob)
            else:
                with open(dst, "rb") as fh:
                    images.append(fh.read())
        audio = None
        if want_audio:
            try:
                audio = video_mod.extract_audio(
                    src_path, os.path.join(workdir, "a.wav"))
            except Exception:
                audio = None  # audio-free clip: STT is skipped, not faked
        sampling = {"method": "dense-opening/even-middle/end-frame",
                    "frame_times": times,
                    "max_frames": video_mod.MAX_FRAMES,
                    "audio": "16kHz mono WAV" if audio else "absent"}
        return {"images": [bytes(b) for b in images],
                "image_times": times, "audio": audio,
                "audio_mime": "audio/wav" if audio else "",
                "sampling": sampling}
    finally:
        for name in ("f.jpg", "a.wav"):
            try:
                os.unlink(os.path.join(workdir, name))
            except OSError:
                pass
        try:
            os.rmdir(workdir)
        except OSError:
            pass


def measured_from_records(records):
    """Deterministic performance summary over the confirmed set.

    Pooled totals only (sum then divide, never average row rates).
    Returns {totals, pooled_link_ctr_pct|null, coverage, warnings}.
    """
    # Every known total is accumulated independently: a missing CTR
    # denominator (or any other unknown metric) prevents only its own
    # ratio — never erases other known measurements. Only records with
    # BOTH impressions and link clicks known enter the CTR pool;
    # unavailable totals stay out, genuine zeros stay in. A total with
    # no known contributor at all is returned as None ("not supplied"),
    # never as a false zero.
    totals = {"records": 0, "impressions": 0, "link_clicks": 0,
              "clicks_all": 0, "spend": 0.0, "conversions": 0.0,
              "video_views": 0, "views_25": 0, "views_50": 0,
              "views_75": 0, "views_100": 0}
    known = set()
    warnings = []
    pool_impressions = 0
    pool_clicks = 0
    pool_records = 0
    currencies, dates, platforms = set(), set(), set()
    spend_by_currency: dict = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        totals["records"] += 1
        try:
            parsed = json.loads(rec.get("missing_json") or "[]")
            missing = set(parsed) if isinstance(parsed, list) else set()
        except (ValueError, TypeError):
            missing = set()
        # An explicit null is unknown, with or without a marker.
        for num_key in ("impressions", "link_clicks", "clicks", "spend",
                        "conversions", "video_views", "views_25",
                        "views_50", "views_75", "views_100"):
            if rec.get(num_key) is None:
                missing.add(num_key)

        def _num(value):
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return None

        def _float(value):
            try:
                return float(value or 0)
            except (TypeError, ValueError):
                return None

        imp = None if "impressions" in missing \
            else _num(rec.get("impressions"))
        lnk = None if "link_clicks" in missing \
            else _num(rec.get("link_clicks"))
        # Supplied-but-unparseable counts are unknown, not zero: warn
        # once per record (marked-missing rows are already covered by
        # the coverage warning below).
        if ("impressions" not in missing and imp is None) or \
                ("link_clicks" not in missing and lnk is None):
            warnings.append(
                "record %s has non-numeric counts: excluded from "
                "pooled totals" % rec.get("id"))
        if imp is not None:
            totals["impressions"] += imp
            known.add("impressions")
        if lnk is not None:
            totals["link_clicks"] += lnk
            known.add("link_clicks")
        # The CTR pool needs BOTH sides known: unknown clicks can
        # never drag a rate to 0%, and each known total above is still
        # preserved when the other side is missing.
        if imp is not None and lnk is not None:
            pool_records += 1
            pool_impressions += imp
            pool_clicks += lnk
        for key, num in (("clicks", "clicks_all"), ("video_views", None),
                         ("views_25", None), ("views_50", None),
                         ("views_75", None), ("views_100", None)):
            if key in missing:
                continue
            value = _num(rec.get(key))
            if value is not None:
                totals[num or key] += value
                known.add(num or key)
        if "conversions" not in missing:
            value = _float(rec.get("conversions"))
            if value is not None:
                totals["conversions"] += value
                known.add("conversions")
        if "spend" not in missing:
            amount = _float(rec.get("spend"))
            if amount is not None:
                totals["spend"] += amount
                known.add("spend")
                cur = str(rec.get("currency") or "").strip() or "unspecified"
                spend_by_currency[cur] = spend_by_currency.get(cur, 0.0) \
                    + amount
                currencies.add(cur)
        if rec.get("date"):
            dates.add(str(rec["date"]))
        if rec.get("platform"):
            platforms.add(str(rec["platform"]))
    if totals["records"] and pool_records < totals["records"]:
        warnings.append("%d of %d records lack impression/click counts: "
                        "pooled CTR covers %d"
                        % (totals["records"] - pool_records,
                           totals["records"], pool_records))
    ctr = None
    if pool_impressions > 0:
        ctr = round(pool_clicks / pool_impressions * 100, 2)
    elif totals["records"]:
        warnings.append("no comparable impression/click pairs: no rate "
                        "computed (missing is not zero)")
    if len(currencies) > 1:
        # A combined spend across currencies is meaningless: the
        # combined total is unavailable (None, never a genuine zero)
        # and spend is kept per-currency instead.
        totals["spend"] = None
        warnings.append("mixed currencies %s: spend kept per-currency, "
                        "not combined" % sorted(currencies))
    for total_key in ("impressions", "link_clicks", "clicks_all",
                      "spend", "conversions", "video_views", "views_25",
                      "views_50", "views_75", "views_100"):
        if total_key not in known:
            totals[total_key] = None
    coverage = {"platforms": sorted(platforms),
                "currencies": sorted(currencies),
                "date_range": [min(dates), max(dates)] if dates else [],
                "spend_by_currency": spend_by_currency,
                "ctr_records": pool_records}
    return {"totals": totals, "pooled_link_ctr_pct": ctr,
            "coverage": coverage, "warnings": warnings}


def suggest_tests(annotation, measured, transcript=""):
    """Small set of hypotheses grounded in observed absences.

    Rule-based and deterministic (testable without a provider).
    Every entry says what to change and which evidence motivates
    it; none claims a proven cause or a guaranteed lift.
    """
    ann = annotation or {}
    out = []

    def add(test_id, change, why, evidence):
        out.append({"id": test_id, "hypothesis": change, "why": why,
                    "evidence": evidence, "status": "suggested"})

    try:
        hook_conf = float(ann.get("hook_confidence") or 0.0)
    except (TypeError, ValueError):
        hook_conf = 0.0
    if hook_conf < 0.5:
        add("hook-clarity",
            "Test an opening that states the payoff in the first 2 seconds.",
            "hook classification confidence is %.2f (uncertain)"
            % hook_conf,
            [{"kind": "annotation", "field": "hook_confidence"}])
    labels = [] if not isinstance(ann.get("frame_labels"), list) \
        else ann["frame_labels"]
    if labels and not any(isinstance(l, dict) and l.get("cta_visible")
                          for l in labels):
        add("cta-presence",
            "Test a version with an explicit on-screen call to action.",
            "no sampled frame shows a call to action",
            [{"kind": "frames", "note": "cta_visible absent in all "
                                        "sampled frames"}])
    first_product = ((ann.get("execution") or {}).get("product_first_s")
                     if isinstance(ann.get("execution"), dict) else None)
    if first_product is None:
        add("product-timing",
            "Test showing the product within the first 3 seconds.",
            "no product appearance was identified in sampled frames",
            [{"kind": "annotation", "field": "execution.product_first_s"}])
    if not (ann.get("transcript_words") or transcript):
        add("silent-cut",
            "Test this cut against a version with a spoken hook: the "
            "supplied clip carries no transcribed speech.",
            "no transcript segments were produced",
            [{"kind": "transcript", "note": "empty"}])
    return out[:4]


def run(conn, snapshot, owner="", media_dir="", providers=None,
        progress=None, cancelled=None, queued_at=""):
    """Execute the bound analysis. Returns the persisted result."""
    from creative_intel import creative as creative_mod
    from creative_intel import drafts as drafts_mod
    from creative_intel import media as media_mod

    def checkpoint(pct, stage=""):
        if cancelled is not None and cancelled():
            from creative_intel.jobs import JobCancelled
            raise JobCancelled("video analysis cancelled at %s" % stage)
        if progress is not None:
            try:
                progress(pct, stage)
            except Exception:
                pass

    fresh = check_snapshot(conn, snapshot)
    checkpoint(5, "snapshot")
    key = fresh["creative_key"]
    video_id = fresh["video_id"]
    # Before any provider work: a late result must never overwrite a
    # newer analysis of the same asset version. (The pipeline itself
    # no longer writes — see persist=False below — so these guards
    # only ever see other jobs' rows, never this job's own partial
    # output.)
    _guard_not_stale(conn, key, queued_at, video_id)
    pre_identity = _analysis_identity(conn, key, video_id)
    conn.execute(
        "INSERT OR IGNORE INTO creatives (creative_key, platform, name,"
        " status) VALUES (?, ?, ?, 'auto')",
        (key, (fresh["records"][0].get("platform") or "")
         if fresh["records"] else "", key))
    conn.commit()
    try:
        store = media_dir
        if not store:
            from ci_backend import actions as legacy
            store = legacy._media_dir()
        src = media_mod.file_path(conn, store, fresh["media_id"])
    except ValueError as exc:
        raise AnalysisUnavailable("stored video is unavailable: %s" % exc)
    checkpoint(10, "prepare")
    prep = prepare_media(src, fresh["duration_s"] or 15.0,
                         want_audio=True)
    checkpoint(25, "prepared")
    prov = providers
    if prov is None:
        from creative_intel import providers as prov_mod
        prov = prov_mod.Providers(
            db_path=_identity_db(conn))
        roster = eligible_vision_roster()
        if not roster:
            raise AnalysisUnavailable(
                readiness()["reason"] or "no video-eligible provider")
        import copy
        prov = copy.copy(prov)
        prov.vision = prov_mod.LiveVision(roster)
    media = {"audio": ((prep["audio"], prep["audio_mime"])
                       if prep["audio"] else (None, None)),
             "images": prep["images"], "image_times": prep["image_times"],
             "duration_s": fresh["duration_s"]}
    # Deferred publish: the pipeline below generates the full report
    # WITHOUT writing to the published creative record (persist=False),
    # so an in-flight job can never clobber a concurrent finisher's
    # rows — not even briefly. Freshness is verified first; only then
    # is the complete result published in one step. An abort anywhere
    # before publish leaves no trace and needs no repair.
    report = creative_mod.run_pipeline(
        conn, key, prov, media=media, progress=progress,
        cancelled=cancelled, persist=False)
    # Post-pipeline re-verification (M2): provider calls take
    # minutes, during which inputs may have changed or a concurrent
    # job may have finished. Re-bind the snapshot, re-run the
    # queued-at guard, and abort if another analysis landed while
    # this one was running. A changed stamp here proves a concurrent
    # finisher — never overwrite it.
    fresh = check_snapshot(conn, snapshot)
    _guard_not_stale(conn, key, queued_at, video_id)
    if _analysis_identity(conn, key, video_id) != pre_identity:
        raise AnalysisUnavailable(
            "another analysis finished or the findings were corrected"
            " while this one was running: discarding this result")
    checkpoint(90, "measured")
    measured = measured_from_records(fresh["records"])
    ann = report["annotation"]
    transcript = report.get("transcript") or ""
    ann["frame_labels"] = [
        {"t_sec": l.get("t_sec"), "label": l.get("label"),
         "brand_visible": l.get("brand_visible"),
         "product_visible": l.get("product_visible"),
         "logo_visible": l.get("logo_visible"),
         "text_overlay": l.get("text_overlay"),
         "cta_visible": l.get("cta_visible"),
         "end_frame": l.get("end_frame")}
        for l in (report.get("frame_labels") or [])]
    ann["analysis"] = {
        "version": ANALYSIS_VERSION,
        "revision": uuid.uuid4().hex,
        "at": utcnow(),
        "model": _vision_model(prov),
        "sampling": prep["sampling"],
        "coverage": {"frames": len(prep["images"]),
                     "clip_s": fresh["duration_s"]},
        "snapshot": {k: fresh[k] for k in
                     ("video_id", "media_id", "video_sha256",
                      "dataset_version", "match_confirmed_at",
                      "match_method", "client", "campaign")},
        "measured": measured,
        "suggested_tests": suggest_tests(ann, measured, transcript)}
    # Publish the complete result in one all-or-nothing transaction.
    # The transaction is acquired FIRST, then the snapshot, the
    # queued-at guard, and the revision identity are rechecked
    # INSIDE it: a dataset change or cleared match committed by
    # another request after the post-pipeline check is visible to
    # the in-transaction re-bind and aborts the publish instead of
    # saving a stale result. A check outside the transaction would
    # merely move the same race.
    checkpoint(95, "publish")
    if fresh["media_id"]:
        ann.setdefault("source_url", "/media/%d" % fresh["media_id"])
    try:
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        fresh = check_snapshot(conn, snapshot)
        _guard_not_stale(conn, key, queued_at, video_id)
        if _analysis_identity(conn, key, video_id) != pre_identity:
            raise AnalysisUnavailable(
                "another analysis finished or the findings were"
                " corrected while this one was running:"
                " discarding this result")
        # Cancellation is rechecked inside the same transaction: a
        # cancel landing after the final checkpoint must still stop
        # the publish, and the job-state change need not touch the
        # input snapshot the checks above verify.
        if cancelled is not None and cancelled():
            from creative_intel.jobs import JobCancelled
            raise JobCancelled("video analysis cancelled at publish")
        drafts_mod.set_video_transcript(conn, video_id, transcript,
                                        commit=False)
        conn.execute("UPDATE creatives SET transcript=?,"
                     " pipeline_json=? WHERE creative_key=?",
                     (transcript, json.dumps(report["stages"]), key))
        creative_mod.save_annotation(conn, key, ann, video_id=video_id,
                                     commit=False)
        drafts_mod.update_draft(conn, fresh["draft_id"],
                                status="ready_for_review", commit=False)
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    return {"creative_key": key, "draft_id": fresh["draft_id"],
            "stages": report["stages"], "measured": measured,
            "analysis_version": ANALYSIS_VERSION,
            "revision": ann["analysis"]["revision"]}


# Fields a human reviewer may correct on a finished analysis.
# Classification dimensions reuse the locked-confirmation path (a
# corrected value is preserved over later auto saves, like any
# analyst judgement); transcript text, frame moments, and test
# verdicts are stored directly. Anything else is rejected — a review
# note alone never rewrites the underlying finding.
CORRECTION_TEST_STATUSES = ("suggested", "accepted", "rejected")

CORRECTION_FRAME_FLAGS = ("brand_visible", "product_visible",
                          "logo_visible", "cta_visible", "end_frame")

MAX_CORRECTION_TRANSCRIPT = 20000
MAX_CORRECTION_LABEL = 200
MAX_CORRECTION_FRAMES = 512


def _correction_dims():
    from creative_intel import creative as creative_mod
    return {
        "hook_type": creative_mod.HOOK_TYPES,
        "hook_modality": creative_mod.HOOK_MODALITIES,
        "opening_delivery": creative_mod.OPENING_DELIVERY,
        "narrative": creative_mod.NARRATIVES,
        "message_class": creative_mod.MESSAGE_CLASSES,
        "promotion_kind": creative_mod.PROMOTION_KINDS,
        "format_kind": creative_mod.FORMAT_KINDS,
        "creator_vs_branded": creative_mod.CREATOR_MODES,
        "edit_style": creative_mod.EDIT_STYLES,
    }


def apply_corrections(conn, creative_key, corrections, by="",
                      video_id="", expected_revision="",
                      duration_s=None):
    """Apply human corrections to a stored analysis; returns the
    actually persisted annotation (re-read after save).

    The correction targets one immutable asset version (video_id):
    the stored row and its snapshot identity must belong to that
    version, so one upload can never edit a sibling version's
    findings. expected_revision (when given) must equal the stored
    revision — a stale edit against already-corrected content is
    rejected instead of silently winning. Only the correctable fields
    are accepted; unknown fields, illegal enum values, out-of-range
    confidences/timestamps (frame moments are bounded by the clip
    duration when known), and verdicts for unknown test ids raise
    ValueError. Dimension corrections lock like analyst
    confirmations, and the save preserves exactly the corrected
    values (keep=) instead of restoring the previous locked ones —
    a repeated correction replaces the earlier decision. Every call
    mints a fresh analysis revision and appends a {by, at, fields}
    log entry, so an approval granted before the correction can never
    silently cover the new content — the caller invalidates any
    recorded review.
    """
    from creative_intel import creative as creative_mod
    from creative_intel import drafts as drafts_mod
    if not isinstance(corrections, dict) or not corrections:
        raise ValueError("corrections need at least one field")
    dims = _correction_dims()
    known = set(dims) | {"hook_confidence", "transcript",
                         "frame_labels", "tests"}
    unknown = [k for k in corrections if k not in known]
    if unknown:
        raise ValueError("uncorrectable field(s): %s"
                         % ", ".join(sorted(unknown)[:5]))
    ann = creative_mod.scoped_annotation(conn, creative_key, video_id)
    if not isinstance(ann, dict) \
            or not isinstance(ann.get("analysis"), dict):
        raise ValueError("no stored analysis of this video to correct")
    stored_snap = ann["analysis"].get("snapshot") or {}
    if video_id and stored_snap.get("video_id", video_id) != video_id:
        raise ValueError("stored analysis belongs to another video")
    if expected_revision and ann["analysis"].get("revision", "") \
            != expected_revision:
        raise ValueError("stored result changed since you read it: "
                         "re-read the findings and correct again")
    if duration_s is not None:
        try:
            clip_s = float(duration_s)
        except (TypeError, ValueError):
            raise ValueError("clip duration is unavailable")
        if clip_s <= 0:
            raise ValueError("clip duration is unavailable")
    else:
        clip_s = None
    touched = []

    def _confirm(dim, value):
        ann[dim] = value
        confirmed = ann.get("confirmed")
        confirmed = dict(confirmed) if isinstance(confirmed, dict) \
            else {}
        confirmed[dim] = value
        ann["confirmed"] = confirmed
        entry = {"dimension": dim, "value": value, "by": by or "human"}
        evidence = ann.get("evidence")
        if not isinstance(evidence, list):
            evidence = []
            ann["evidence"] = evidence
        evidence.append(entry)

    for dim, allowed in dims.items():
        if dim in corrections and corrections[dim] is not None:
            if corrections[dim] not in allowed:
                raise ValueError("%s must be one of %s"
                                 % (dim, list(allowed)))
            _confirm(dim, corrections[dim])
            touched.append(dim)
    if "hook_confidence" in corrections \
            and corrections["hook_confidence"] is not None:
        try:
            conf = float(corrections["hook_confidence"])
        except (TypeError, ValueError):
            raise ValueError("hook_confidence must be 0..1")
        if not 0.0 <= conf <= 1.0:
            raise ValueError("hook_confidence must be 0..1")
        ann["hook_confidence"] = conf
        touched.append("hook_confidence")
    if "frame_labels" in corrections \
            and corrections["frame_labels"] is not None:
        labels = corrections["frame_labels"]
        if not isinstance(labels, list) \
                or len(labels) > MAX_CORRECTION_FRAMES:
            raise ValueError("frame_labels must be a list of at most %d"
                             % MAX_CORRECTION_FRAMES)
        normalised = []
        for item in labels:
            if not isinstance(item, dict):
                raise ValueError("frame_labels entries must be objects")
            try:
                moment = float(item.get("t_sec"))
            except (TypeError, ValueError):
                raise ValueError("frame moment t_sec must be numeric")
            import math as _math
            if not _math.isfinite(moment):
                raise ValueError(
                    "frame moment t_sec must be a finite number")
            if moment < 0:
                raise ValueError("frame moment t_sec cannot be negative")
            if clip_s is not None and moment > clip_s:
                raise ValueError(
                    "frame moment t_sec %.1f exceeds the %.1f-second"
                    " clip" % (moment, clip_s))
            label = item.get("label", "")
            if not isinstance(label, str) \
                    or len(label) > MAX_CORRECTION_LABEL:
                raise ValueError("frame moment label must be text of at"
                                 " most %d chars" % MAX_CORRECTION_LABEL)
            entry = {"t_sec": moment, "label": label}
            for flag in CORRECTION_FRAME_FLAGS:
                if flag in item and item[flag] is not None:
                    entry[flag] = bool(item[flag])
            overlay = item.get("text_overlay", "")
            if overlay is not None:
                if not isinstance(overlay, str) or len(overlay) > 500:
                    raise ValueError("text_overlay must be text of at"
                                     " most 500 chars")
                entry["text_overlay"] = overlay
            normalised.append(entry)
        ann["frame_labels"] = normalised
        touched.append("frame_labels")
    if "tests" in corrections and corrections["tests"] is not None:
        ops = corrections["tests"]
        if not isinstance(ops, list) or not ops:
            raise ValueError("tests must be a non-empty list")
        stored = ann["analysis"].get("suggested_tests")
        if not isinstance(stored, list):
            raise ValueError("stored analysis has no suggested tests")
        by_id = {t.get("id"): t for t in stored
                 if isinstance(t, dict) and t.get("id")}
        for op in ops:
            if not isinstance(op, dict) or not op.get("id"):
                raise ValueError("test verdicts need an id")
            if op.get("id") not in by_id:
                raise ValueError("unknown suggested test %r"
                                 % (op.get("id"),))
            if op.get("status") not in CORRECTION_TEST_STATUSES:
                raise ValueError("test status must be one of %s"
                                 % list(CORRECTION_TEST_STATUSES))
            by_id[op["id"]]["status"] = op["status"]
        touched.append("tests")
    if "transcript" in corrections \
            and corrections["transcript"] is not None:
        text = corrections["transcript"]
        if not isinstance(text, str) \
                or len(text) > MAX_CORRECTION_TRANSCRIPT:
            raise ValueError("transcript must be text of at most %d chars"
                             % MAX_CORRECTION_TRANSCRIPT)
        if video_id:
            drafts_mod.set_video_transcript(conn, video_id, text)
        conn.execute("UPDATE creatives SET transcript=? WHERE creative_key=?",
                     (text, creative_key))
        touched.append("transcript")
    if not touched:
        raise ValueError("corrections need at least one field")
    log = ann["analysis"].get("corrections")
    if not isinstance(log, list):
        log = []
        ann["analysis"]["corrections"] = log
    log.append({"by": by or "human", "at": utcnow(),
                "fields": sorted(touched)})
    ann["analysis"]["revision"] = uuid.uuid4().hex
    # keep=touched: the corrected values replace the previous locked
    # decisions instead of being restored over. Return the row as
    # actually persisted — never the pre-save dict.
    creative_mod.save_annotation(conn, creative_key, ann,
                                 video_id=video_id, keep=touched)
    conn.commit()
    persisted = creative_mod.scoped_annotation(conn, creative_key,
                                               video_id)
    if not isinstance(persisted, dict):
        raise ValueError("correction did not persist")
    return persisted


def _vision_model(prov):
    try:
        provider, model, _tier = prov.vision.roster[0]
        return "%s/%s" % (provider, model)
    except (AttributeError, IndexError, TypeError, ValueError):
        return ""


def _scoped_block(conn, creative_key, video_id=""):
    """The stored analysis block for one asset version, or {}."""
    from creative_intel import creative as creative_mod
    ann = creative_mod.scoped_annotation(conn, creative_key, video_id)
    if not isinstance(ann, dict):
        return {}
    block = ann.get("analysis")
    return block if isinstance(block, dict) else {}


def _analysis_at(conn, creative_key, video_id=""):
    """Stamp of the currently stored analysis block, or ''."""
    try:
        return _scoped_block(conn, creative_key, video_id).get("at", "")
    except ValueError:
        return ""


def _analysis_revision(conn, creative_key, video_id=""):
    """Unique revision of the stored analysis block, or ''.

    Human corrections mint a fresh revision without touching `at`,
    so staleness checks must compare revisions — not stamps — to
    notice a correction that landed mid-run.
    """
    try:
        return _scoped_block(conn, creative_key, video_id).get(
            "revision", "")
    except ValueError:
        return ""


def _parse_stamp(value):
    """Parsed datetime for an ISO analysis stamp, else None."""
    try:
        text = str(value or "").strip().replace("Z", "+00:00")
        moment = datetime.datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment


def _analysis_identity(conn, creative_key, video_id=""):
    """(revision, at) of the stored analysis block for one version."""
    block = _scoped_block(conn, creative_key, video_id)
    return (block.get("revision", ""), block.get("at", ""))


def _guard_not_stale(conn, creative_key, queued_at, video_id=""):
    """A late result never overwrites a newer analysis (same version)."""
    if not queued_at:
        return
    try:
        prior = _scoped_block(conn, creative_key, video_id).get("at", "")
    except ValueError:
        return
    if not prior:
        return
    queued_moment, prior_moment = _parse_stamp(queued_at), _parse_stamp(prior)
    if queued_moment is not None and prior_moment is not None:
        newer = prior_moment > queued_moment
    else:
        # Unparseable stamps: fail closed on string inequality only
        # when the raw values differ and look ordered.
        newer = prior > queued_at if isinstance(prior, str) \
            and isinstance(queued_at, str) else False
    if newer:
        raise AnalysisUnavailable(
            "a newer analysis already exists: discarding this late result")


def _identity_db(conn):
    try:
        for _seq, _name, path in conn.execute("PRAGMA database_list"):
            if _name == "main" and path:
                return str(path)
    except Exception:
        pass
    return None
