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
    """Verify preconditions and freeze the analysis snapshot."""
    from creative_intel import drafts as drafts_mod
    draft = drafts_mod.get_draft(conn, draft_id)
    if draft is None:
        raise AnalysisUnavailable("unknown upload draft")
    videos = drafts_mod.list_videos(conn, draft_id)
    video = None
    for cand in videos:
        try:
            verdict = json.loads(cand.get("validation_json") or "{}")
        except ValueError:
            continue
        if verdict.get("status") == "valid":
            video = cand
            break
    if video is None:
        raise AnalysisUnavailable("validate the video before analysing")
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
    for key in ("video_sha256", "dataset_version", "match_confirmed_at"):
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
            images.append(blob if isinstance(blob, (bytes, bytearray))
                          else open(dst, "rb").read())
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
    totals = {"records": 0, "impressions": 0, "link_clicks": 0,
              "clicks_all": 0, "spend": 0.0, "conversions": 0.0,
              "video_views": 0, "views_25": 0, "views_50": 0,
              "views_75": 0, "views_100": 0}
    warnings = []
    complete = 0
    currencies, dates, platforms = set(), set(), set()
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        totals["records"] += 1
        try:
            imp = int(rec.get("impressions") or 0)
            lnk = int(rec.get("link_clicks") or 0)
        except (TypeError, ValueError):
            warnings.append("record %s has non-numeric counts: excluded "
                            "from pooled totals" % rec.get("id"))
            continue
        has_counts = ("impressions" in rec and "link_clicks" in rec)
        if has_counts:
            complete += 1
            totals["impressions"] += imp
            totals["link_clicks"] += lnk
        for key, num in (("clicks", "clicks_all"), ("video_views", None),
                         ("views_25", None), ("views_50", None),
                         ("views_75", None), ("views_100", None)):
            try:
                totals[num or key] += int(rec.get(key) or 0)
            except (TypeError, ValueError):
                pass
        for key, num in (("spend", False), ("conversions", False)):
            try:
                totals[key] += float(rec.get(key) or 0)
            except (TypeError, ValueError):
                pass
        if rec.get("currency"):
            currencies.add(str(rec["currency"]))
        if rec.get("date"):
            dates.add(str(rec["date"]))
        if rec.get("platform"):
            platforms.add(str(rec["platform"]))
    if totals["records"] and complete < totals["records"]:
        warnings.append("%d of %d records lack impression/click counts: "
                        "pooled CTR covers %d"
                        % (totals["records"] - complete,
                           totals["records"], complete))
    ctr = None
    if totals["impressions"] > 0:
        ctr = round(totals["link_clicks"] / totals["impressions"] * 100, 2)
    elif totals["records"]:
        warnings.append("no impressions supplied: no rate computed "
                        "(missing is not zero)")
    if len(currencies) > 1:
        warnings.append("mixed currencies %s: spend is not combined"
                        % sorted(currencies))
    coverage = {"platforms": sorted(platforms),
                "currencies": sorted(currencies),
                "date_range": [min(dates), max(dates)] if dates else []}
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
    # Before any provider work or persistence: run_pipeline saves
    # the annotation itself, so a staleness check placed after it
    # would always see its own fresh row. A late result must never
    # overwrite a newer analysis.
    _guard_not_stale(conn, key, queued_at)
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
    report = creative_mod.run_pipeline(
        conn, key, prov, media=media, progress=progress,
        cancelled=cancelled)
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
        "at": utcnow(),
        "model": _vision_model(prov),
        "sampling": prep["sampling"],
        "coverage": {"frames": len(prep["images"]),
                     "clip_s": fresh["duration_s"]},
        "snapshot": {k: fresh[k] for k in
                     ("video_sha256", "dataset_version",
                      "match_confirmed_at", "match_method")},
        "measured": measured,
        "suggested_tests": suggest_tests(ann, measured, transcript)}
    creative_mod.save_annotation(conn, key, ann)
    drafts_mod.update_draft(conn, fresh["draft_id"],
                            status="ready_for_review")
    conn.commit()
    return {"creative_key": key, "draft_id": fresh["draft_id"],
            "stages": report["stages"], "measured": measured,
            "analysis_version": ANALYSIS_VERSION}


def _vision_model(prov):
    try:
        provider, model, _tier = prov.vision.roster[0]
        return "%s/%s" % (provider, model)
    except (AttributeError, IndexError, TypeError, ValueError):
        return ""


def _guard_not_stale(conn, creative_key, queued_at):
    """A late result never overwrites a newer analysis."""
    if not queued_at:
        return
    row = conn.execute("SELECT annotation_json FROM annotations"
                       " WHERE creative_key=?", (creative_key,)).fetchone()
    if not row:
        return
    try:
        prior = (json.loads(row[0]).get("analysis") or {}).get("at", "")
    except ValueError:
        return
    if prior and prior > queued_at:
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
