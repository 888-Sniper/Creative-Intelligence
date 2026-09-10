"""Foap Analyst diagnostic catalogue + five-layer awareness analysis.

Implements the supplied signal → diagnosis → iteration patterns as
individually testable rules with prerequisites, objective
applicability and alternative explanations. Every rule is a
candidate hypothesis, never an automatic causal conclusion: findings
say "plausible", carry confidence dimensions and list what would
disprove them.

Five layers (Reach / Paid Awareness): Stop, Hold, Depth, Brand
delivery, Efficiency & scale. CTR stays a secondary awareness
signal; conversion objectives use CPA/ROAS diagnostics instead.
"""

from __future__ import annotations

from creative_intel import analyst_metrics as metrics

# Reference cohorts smaller than this are exploratory, never proof.
MIN_COHORT_N = 3
PREFERRED_COHORT_N = 6

# Relative margin around the cohort median that counts as a real
# difference (recorded on every finding; no universal thresholds).
MARGIN = 0.15

# Minimum exposure for a creative-level rate to count as evidence.
MIN_IMPRESSIONS = 500


def _measured(result):
    return result is not None and result.get("state") in (
        metrics.MEASURED, metrics.ESTIMATED) and \
        result.get("value") is not None


def classify(value, cohort_values, margin=MARGIN, higher_is_better=True):
    """Rank value against its cohort, transparently.

    Returns {"band": high|average|low|unknown, "method", "n",
    "median", "thresholds", "difference_pp"/"difference_rel"}.
    Bands come from the cohort distribution (tertiles around the
    median with an explicit margin), never from embedded universal
    thresholds. Unknown when the cohort is empty or the value is None.
    """
    vals = sorted(v for v in cohort_values
                  if v is not None and v == v)
    info = {"method": "cohort_tertile_vs_median(margin=%s)" % margin,
            "n": len(vals), "median": None, "thresholds": None,
            "band": "unknown", "difference_pp": None,
            "difference_rel": None}
    if value is None or value != value or not vals:
        return info
    median = metrics._median(vals)
    info["median"] = median
    lo = median * (1 - margin) if higher_is_better else None
    hi = median * (1 + margin)
    if higher_is_better:
        info["thresholds"] = {"low_below": lo, "high_above": hi}
        band = "low" if value < lo else ("high" if value > hi else "average")
        info["difference_pp"] = value - median
    else:
        # Lower is better: mirror the margin around the median.
        info["thresholds"] = {"low_above": median * (1 + margin),
                              "high_below": median * (1 - margin)}
        band = ("low" if value > median * (1 + margin)
                else ("high" if value < median * (1 - margin)
                      else "average"))
        info["difference_pp"] = median - value
    info["band"] = band
    # Same sign convention as difference_pp: positive means better,
    # whichever direction the metric runs.
    gap = (median - value) if not higher_is_better else (value - median)
    info["difference_rel"] = (gap / median) if median else None
    return info


def _finding(rule_id, layer, creative_ids, signal, diagnosis,
             hypothesis, iteration, priority, confidence, observed,
             benchmarks, preserve, change, alternatives, limits,
             metric_ids, scope, dataset_version, test_id=None):
    return {"finding_id": rule_id,
            "scope": scope,
            "dataset_version": dataset_version,
            "creative_ids": list(creative_ids),
            "primary_signal": signal,
            "metric_definition_ids": list(metric_ids),
            "observed_values": dict(observed),
            "benchmark_values": dict(benchmarks),
            "diagnosis": diagnosis,
            "creative_hypothesis": hypothesis,
            "alternative_explanations": list(alternatives),
            "recommended_iteration": iteration,
            "priority": priority,
            "confidence_level": confidence["level"],
            "confidence_reasons": confidence["reasons"],
            "element_to_preserve": preserve,
            "element_to_change": change,
            "supporting_evidence_ids": confidence.get("evidence_ids", []),
            "limitations": list(limits),
            "recommended_test_id": test_id,
            "layer": layer}


def confidence_for(available, required, annotation_status,
                   cohort_n, exposure):
    """Three confidence dimensions, explicit reasons.

    Data completeness, annotation quality and comparison strength are
    scored separately; the level is the weakest dimension. Model
    confidence is not statistical confidence — levels say how much
    weight to give the hypothesis, never a p-value.
    """
    missing = [m for m in required if m not in available]
    reasons = []
    if missing:
        data = "low"
        reasons.append("missing metrics: %s" % ", ".join(missing))
    elif len(available) < len(required):
        data = "medium"
        reasons.append("partial metric coverage")
    else:
        data = "high"
    if annotation_status == "human_verified":
        anno, anno_note = "high", "human-verified observations"
    elif annotation_status == "auto":
        anno, anno_note = "medium", "machine observations, unverified"
    else:
        anno, anno_note = "low", "no creative observations"
    reasons.append(anno_note)
    if cohort_n < MIN_COHORT_N or exposure < MIN_IMPRESSIONS:
        comp = "low"
        reasons.append("exploratory: cohort n=%d, exposure %d"
                       % (cohort_n, exposure))
    elif cohort_n < PREFERRED_COHORT_N:
        comp = "medium"
        reasons.append("small cohort n=%d" % cohort_n)
    else:
        comp = "high"
        reasons.append("cohort n=%d" % cohort_n)
    order = {"low": 0, "medium": 1, "high": 2}
    level = min((data, anno, comp), key=lambda lv: order[lv])
    return {"level": level, "reasons": reasons,
            "dimensions": {"data": data, "annotation": anno,
                           "comparison": comp}}


def _ctx_value(ctx, key):
    return (ctx.get("metrics") or {}).get(key)


def _band(ctx, metric_id, higher_is_better=True):
    """(band, value, classification) for one metric in its cohort."""
    res = _ctx_value(ctx, metric_id)
    value = res.get("value") if _measured(res) else None
    cohort = (ctx.get("cohort") or {}).get(metric_id) or []
    info = classify(value, cohort, higher_is_better=higher_is_better)
    return info["band"], value, info


def _base(ctx, rule_id, layer, metric_ids, required):
    metrics_map = ctx.get("metrics") or {}
    available = [m for m in required
                 if _measured(metrics_map.get(m))]
    conf = confidence_for(
        available, required, ctx.get("annotation_status", "none"),
        ctx.get("cohort_n", 0), ctx.get("exposure", 0))
    return conf


def _observed(ctx, metric_ids):
    out = {}
    for mid in metric_ids:
        res = _ctx_value(ctx, mid)
        if _measured(res):
            out[mid] = {"value": res["value"], "state": res["state"],
                        "basis": res.get("basis", "")}
    return out


def _benchmarks(ctx, metric_ids, higher_map=None):
    out = {}
    for mid in metric_ids:
        _b, _v, info = _band(
            ctx, mid, (higher_map or {}).get(mid, True))
        out[mid] = {"median": info["median"], "n": info["n"],
                    "method": info["method"]}
    return out


# ---------------------------------------------------------------------------
# Table-driven diagnostic catalogue.
#
# Each spec fires only when every named band condition holds on MEASURED
# values; unmeasured prerequisites mean insufficient data (no fire),
# never a silent substitution. "match": "any" fires when at least one
# measured condition holds. Mutex groups resolve incompatible triggers
# by priority: the first firing rule wins and records the suppression.
# ---------------------------------------------------------------------------

RULE_SPECS = [
    # -- Funnel: stop -> hold -> depth -------------------------------------
    {"id": "low_hook", "layer": "stop",
     "objectives": ("reach", "conversions", "any"), "match": "any",
     "bands": {"hook_rate_2s_impr": ["low"],
               "hook_rate_3s_impr": ["low"]},
     "signal": "low early retention ({metric} {value}, low cohort band)",
     "diagnosis": "plausible: the opening may fail to establish"
                  " attention or context within the first seconds — not"
                  " proven; audience, placement and bidding can produce"
                  " the same signal.",
     "hypothesis": "Viewers may skip before the creative's promise lands.",
     "iteration": "Test 3–5 alternative openings while holding body and"
                  " offer constant.",
     "priority": "high", "preserve": "body, offer and CTA (unjudged here)",
     "change": "the first 1–3 seconds (hook delivery and promise)",
     "alternatives": ["audience/placement mix skews early retention",
                      "low exposure noise (see confidence)",
                      "captions-off viewing on silent openings"],
     "limitations": ["opening not yet classified — confirm"
                     " opening_delivery"]},
    {"id": "hook_ok_body_weak", "layer": "hold",
     "objectives": ("reach", "conversions", "any"), "match": "all",
     "bands": {"hook_rate_3s_impr": ["high"],
               "quartile_25_impr": ["low"]},
     "signal": "high 3s retention with low 25% viewing",
     "diagnosis": "plausible: the body may not develop the opening"
                  " promise — viewers stay for the hook, then leave"
                  " during setup.",
     "hypothesis": "The opening earns attention the setup does not"
                   " convert.",
     "iteration": "Preserve the hook; shorten the setup and bring the"
                  " first proof or product moment earlier.",
     "priority": "high", "preserve": "the opening hook",
     "change": "setup length and time-to-first-proof",
     "alternatives": ["duration mix: a long creative lowers 25%"
                      " mechanically",
                      "25% lands at different seconds per duration"],
     "limitations": ["check quartile denominator definition"]},
    {"id": "mid_drop", "layer": "depth",
     "objectives": ("reach", "conversions", "any"), "match": "all",
     "bands": {"quartile_25_impr": ["high"],
               "quartile_50_impr": ["low"]},
     "signal": "high 25% viewing with low 50% viewing",
     "diagnosis": "plausible: the middle may lose momentum —"
                  " repetition or a slow build between setup and payoff.",
     "hypothesis": "Attention survives the opening but leaks mid-creative.",
     "iteration": "Remove repetition; test a relevant interruption or an"
                  " earlier proof point.",
     "priority": "medium", "preserve": "opening and setup",
     "change": "mid-creative pacing and repetition",
     "alternatives": ["duration differences shift what 50% means"],
     "limitations": ["compare same-duration cohorts here"]},
    {"id": "weak_ending", "layer": "depth",
     "objectives": ("reach", "conversions", "any"), "match": "all",
     "bands": {"quartile_50_impr": ["high"],
               "completion_impr": ["low"]},
     "signal": "high 50% viewing with low completion",
     "diagnosis": "plausible: the ending may be unnecessarily long —"
                  " viewers stay past the middle, then leave before the"
                  " payoff.",
     "hypothesis": "The payoff arrives after attention is spent.",
     "iteration": "Shorten the ending or integrate branding into the"
                  " payoff.",
     "priority": "medium", "preserve": "opening through mid-creative",
     "change": "ending length and payoff placement",
     "alternatives": ["long duration explains low completion mechanically"],
     "limitations": ["completion denominator: exposures vs retained"]},
    # -- Attention quality --------------------------------------------------
    {"id": "hook_body_mismatch", "layer": "hold",
     "objectives": ("reach", "conversions", "any"), "match": "all",
     "bands": {"hook_rate_2s_impr": ["high"],
               "awt_per_view": ["low"]},
     "signal": "high early retention with low average watch time",
     "diagnosis": "plausible hook/body mismatch: the opening promises"
                  " what the body does not deliver.",
     "hypothesis": "Curiosity clicks in, then leaves.",
     "iteration": "Align the body with the opening promise.",
     "priority": "high", "preserve": "the opening hook",
     "change": "body relevance to the hook promise",
     "alternatives": ["AWT basis mismatch across rows (see reasons)"],
     "limitations": ["AWT needs a stated per-view basis"]},
    {"id": "narrow_appeal", "layer": "hold",
     "objectives": ("reach", "conversions", "any"), "match": "all",
     "bands": {"hook_rate_2s_impr": ["average"],
               "awt_per_view": ["high"]},
     "signal": "average early retention with high average watch time",
     "diagnosis": "plausible: the body may appeal strongly to a narrower"
                  " group that self-selects past a plain opening.",
     "hypothesis": "Loyal viewers watch long; most never start.",
     "iteration": "Preserve the body; test clearer, more explicit"
                  " openings.",
     "priority": "medium", "preserve": "the body",
     "change": "opening clarity",
     "alternatives": ["niche audience delivery, not creative breadth"],
     "limitations": ["small-cohort AWT is noisy"]},
    {"id": "length_completion", "layer": "depth",
     "objectives": ("reach", "conversions", "any"), "match": "all",
     "bands": {"completion_impr": ["low"], "awt_per_view": ["high"]},
     "signal": "low completion with good average watch time",
     "diagnosis": "plausible: length explains weak completion — viewers"
                  " watch long in seconds but rarely reach 100%.",
     "hypothesis": "Seconds watched are strong; the bar is long.",
     "iteration": "Test a shorter cutdown of the same body.",
     "priority": "medium", "preserve": "body content",
     "change": "duration (cutdown)",
     "alternatives": ["quartile thresholds shift with duration"],
     "limitations": ["judge with seconds, not completion alone"]},
    {"id": "short_completion", "layer": "depth",
     "objectives": ("reach", "conversions", "any"), "match": "all",
     "bands": {"completion_impr": ["high"], "awt_per_view": ["low"]},
     "signal": "high completion with low average watch time",
     "diagnosis": "plausible: short duration explains completion —"
                  " finishing a 6s clip is not deep attention.",
     "hypothesis": "Completion flatters short formats.",
     "iteration": "Evaluate seconds watched alongside completion; do not"
                  " crown short completions as attention winners.",
     "priority": "medium", "preserve": "format efficiency",
     "change": "evaluation metric (add AWT seconds)",
     "alternatives": ["looping playback inflates completions"],
     "limitations": ["completion and AWT answer different questions"]},
    # -- Cost / efficiency (lower-is-better flagged per metric) ------------
    {"id": "costly_quality", "layer": "efficiency",
     "objectives": ("reach", "conversions", "any"), "match": "all",
     "bands": {"vtr": ["high"], "cpcv": ["low"]},
     "higher": {"cpcv": False},
     "signal": "high VTR with high CPCV",
     "diagnosis": "plausible: delivery cost offsets viewing quality —"
                  " completions are good, each one is expensive.",
     "hypothesis": "Media conditions, not the creative, may be the"
                   " problem.",
     "iteration": "Review media conditions (audience, placement,"
                  " bidding) before rebuilding the creative.",
     "priority": "medium", "preserve": "the creative",
     "change": "delivery conditions",
     "alternatives": ["auction competition in this window"],
     "limitations": ["CPCV needs compatible completed views"]},
    {"id": "cheap_views_thin_attention", "layer": "efficiency",
     "objectives": ("reach", "conversions", "any"), "match": "all",
     "bands": {"vtr": ["low"], "cpcv": ["high"]},
     "higher": {"cpcv": False},
     "signal": "low VTR with low CPCV",
     "diagnosis": "plausible: cheap completed views do not alone"
                  " establish strong attention.",
     "hypothesis": "Efficiency without attention is hollow reach.",
     "iteration": "Examine cost and attention quality together; cheap"
                  " views that nobody watches change nothing.",
     "priority": "medium", "preserve": "efficient delivery settings",
     "change": "attention quality (hook and hold)",
     "alternatives": ["view definition differs by placement"],
     "limitations": ["VTR denominator must be stated"]},
    {"id": "costly_reach", "layer": "efficiency",
     "objectives": ("reach", "any"), "match": "all",
     "bands": {"cpm": ["low"], "hook_rate_2s_impr": ["high"]},
     "higher": {"cpm": False},
     "signal": "high CPM with strong retention",
     "diagnosis": "plausible: media/audience cost is the main issue —"
                  " the creative retains, delivery overcharges.",
     "hypothesis": "Good creative, expensive audience.",
     "iteration": "Test delivery conditions (broader audience,"
                  " placements) while preserving the creative.",
     "priority": "high", "preserve": "the creative",
     "change": "audience and placement mix",
     "alternatives": ["seasonal auction pressure"],
     "limitations": ["single-currency scope required for CPM"]},
    {"id": "cheap_no_hold", "layer": "efficiency",
     "objectives": ("reach", "any"), "match": "all",
     "bands": {"cpm": ["high"], "hook_rate_2s_impr": ["low"]},
     "higher": {"cpm": False},
     "signal": "low CPM with weak retention",
     "diagnosis": "plausible: low-cost exposure is not retaining"
                  " attention — reach is cheap because nobody stays.",
     "hypothesis": "The inventory is fine; the opening is not.",
     "iteration": "Test opening, pace and clarity before touching"
                  " delivery.",
     "priority": "high", "preserve": "efficient delivery settings",
     "change": "opening, pace and clarity",
     "alternatives": ["low-quality placement mix"],
     "limitations": ["single-currency scope required for CPM"]},
    {"id": "broad_unproven", "layer": "efficiency",
     "objectives": ("reach", "any"), "match": "all",
     "bands": {"reach": ["high"], "frequency": ["low"]},
     "signal": "high reach with low frequency",
     "diagnosis": "broad delivery with unproven scaling potential —"
                  " many saw it once; repetition effects unknown.",
     "hypothesis": "Scale headroom exists but is untested.",
     "iteration": "Evaluate controlled expansion and related variants.",
     "priority": "low", "preserve": "reach breadth",
     "change": "nothing yet — measure first",
     "alternatives": ["reach estimated by the platform, not counted"],
     "limitations": ["reach never sums across overlapping rows"]},
    # -- Engagement (attention x reaction) ----------------------------------
    {"id": "watched_not_felt", "layer": "depth",
     "objectives": ("reach", "conversions", "any"), "match": "all",
     "bands": {"quartile_50_impr": ["high"],
               "engagement_rate": ["low"]},
     "signal": "strong retention with low engagement",
     "diagnosis": "plausible: viewing does not translate into reactions"
                  " — watched, not felt.",
     "hypothesis": "Passive consumption without a reason to react.",
     "iteration": "Test interaction prompts only when relevant to the"
                  " objective; never chase likes on a Reach brief.",
     "priority": "low", "preserve": "retention strength",
     "change": "reason to react (when objective-relevant)",
     "alternatives": ["engagement definitions differ by platform"],
     "limitations": ["engagement is secondary for awareness"]},
    {"id": "spiky_reactions", "layer": "depth",
     "objectives": ("reach", "conversions", "any"), "match": "all",
     "bands": {"quartile_50_impr": ["low"],
               "engagement_rate": ["high"]},
     "signal": "high engagement with weak retention",
     "diagnosis": "plausible: reactions concentrate around one element"
                  " while most viewers leave.",
     "hypothesis": "One moment works; the whole does not.",
     "iteration": "Examine available comments/sentiment and creative"
                  " context to isolate the spiking element.",
     "priority": "medium", "preserve": "the spiking element",
     "change": "everything around it",
     "alternatives": ["controversy drives comments without attention"],
     "limitations": ["sentiment data rarely available here"]},
    # -- Response (conversion objectives + hold/CTR, CTR/CVR) ---------------
    {"id": "hold_no_click", "layer": "efficiency",
     "objectives": ("conversions", "any"), "match": "all",
     "bands": {"hold_rate": ["high"], "ctr_link": ["low"]},
     "signal": "high hold with low link CTR",
     "diagnosis": "plausible: offer/desire clarity matters — viewers"
                  " stay but see no reason to act.",
     "hypothesis": "Attention without a sharp benefit or offer.",
     "iteration": "Test a sharper benefit or offer framing.",
     "priority": "medium", "preserve": "retention strength",
     "change": "offer/benefit clarity and CTA",
     "alternatives": ["link CTR secondary on Reach briefs"],
     "limitations": ["hold_rate needs a stated numerator/denominator"]},
    {"id": "click_no_convert", "layer": "efficiency",
     "objectives": ("conversions",), "match": "all",
     "bands": {"ctr_link": ["high"], "cvr": ["low"]},
     "signal": "high link CTR with low CVR",
     "diagnosis": "plausible qualification, landing-page, tracking or"
                  " offer mismatch — the creative sells the click, the"
                  " funnel drops it.",
     "hypothesis": "Downstream failure, not creative failure.",
     "iteration": "Investigate downstream factors (page, offer match,"
                  " tracking) before blaming the creative.",
     "priority": "high", "preserve": "the click-driving creative",
     "change": "landing experience and offer match",
     "alternatives": ["attribution window mismatch",
                      "conversion event misdefined"],
     "limitations": ["needs conversion event + attribution stated"]},
    {"id": "promising_undertested", "layer": "efficiency",
     "objectives": ("conversions",), "match": "all",
     "bands": {"cpa": ["high"]},
     "higher": {"cpa": False},
     "spend_band": "low",
     "signal": "good CPA on low spend",
     "diagnosis": "promising but under-tested: efficiency at low spend"
                  " proves little about scale.",
     "hypothesis": "A winner that has not met a real budget yet.",
     "iteration": "Gather sufficient evidence and test controlled"
                  " variations at higher spend.",
     "priority": "medium", "preserve": "the efficient creative",
     "change": "spend level (controlled scale-up)",
     "alternatives": ["early auction luck", "narrow winning pocket"],
     "limitations": ["low-spend CPA is noisy"]},
]

# Mutex groups: first firing rule wins; the rest are recorded as
# suppressed so incompatible triggers never stand side by side.
MUTEX_GROUPS = [
    ["hook_body_mismatch", "narrow_appeal"],
    ["length_completion", "short_completion", "weak_ending"],
    ["costly_quality", "cheap_views_thin_attention"],
    ["costly_reach", "cheap_no_hold"],
]


def _spec_applies(spec, objective):
    objectives = spec.get("objectives", ("any",))
    return "any" in objectives or objective in objectives


def evaluate_spec(ctx, spec):
    """Evaluate one catalogue spec; finding or None (insufficient data
    also yields None — prerequisites never substitute)."""
    objective = ctx.get("objective", "any") or "any"
    if not _spec_applies(spec, objective):
        return None
    higher = spec.get("higher", {})
    bands = spec.get("bands", {})
    hits = {}
    for metric_id, wanted in bands.items():
        band, value, _info = _band(
            ctx, metric_id, higher.get(metric_id, True))
        res = _ctx_value(ctx, metric_id)
        if not _measured(res):
            if spec.get("match") == "any":
                continue
            return None
        if band in wanted:
            hits[metric_id] = (band, value)
        elif spec.get("match", "all") == "all":
            return None
    if not hits:
        return None
    if spec.get("match") == "any" and not any(
            b in bands[m] for m, (b, _v) in hits.items()):
        return None
    metric_ids = sorted(hits)
    required = sorted(bands)
    conf = _base(ctx, spec["id"], spec["layer"], metric_ids, required)
    signal = spec["signal"]
    if "{metric}" in signal:
        first = metric_ids[0]
        _b, value, _i = _band(ctx, first, higher.get(first, True))
        signal = signal.format(metric=first, value=round(value, 1)
                               if value is not None else "?")
    if spec.get("spend_band") == "low":
        spend = ctx.get("spend", 0)
        cohort_spend = ctx.get("cohort_spend") or []
        info = classify(spend, cohort_spend, higher_is_better=False)
        if info["band"] != "high":  # low spend == "high" when lower-better
            return None
    return _finding(
        spec["id"], spec["layer"], [ctx["creative_key"]], signal,
        spec["diagnosis"], spec["hypothesis"], spec["iteration"],
        spec["priority"], conf, _observed(ctx, metric_ids),
        _benchmarks(ctx, metric_ids, higher),
        spec["preserve"], spec["change"], spec["alternatives"],
        spec["limitations"], metric_ids, ctx.get("scope", {}),
        ctx.get("dataset_version", ""))


def evaluate_all(ctx, rules=None):
    """Fire catalogue rules with mutex resolution.

    Returns (findings, suppressed_ids). Suppressions are recorded on
    the winner's limitations so conflicts stay visible.
    """
    specs = rules if rules is not None else RULE_SPECS
    fired = []
    for spec in specs:
        finding = evaluate_spec(ctx, spec)
        if finding is not None:
            fired.append(finding)
    by_id = {f["finding_id"]: f for f in fired}
    suppressed = set()
    for group in MUTEX_GROUPS:
        present = [rid for rid in group if rid in by_id]
        for loser in present[1:]:
            suppressed.add(loser)
            by_id[present[0]]["limitations"] = \
                list(by_id[present[0]]["limitations"]) + \
                ["also matched %s; suppressed as lower priority" % loser]
    findings = [f for f in fired if f["finding_id"] not in suppressed]
    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: order.get(f["priority"], 3))
    return findings, sorted(suppressed)


def rule_hook_hold_combo(ctx):
    """Hook x Hold four-way pattern (multi-metric, one rule).

    low/low, low/high, high/low, high/high — exactly one branch fires,
    so the combination never double-triggers.
    """
    band_hook, _vh, _ih = _band(ctx, "hook_rate_2s_impr")
    band_hold, _vd, _id = _band(ctx, "hold_rate")
    if band_hook not in ("low", "high") or \
            band_hold not in ("low", "high"):
        return None
    texts = {
        ("low", "low"): (
            "weak opening and weak hold",
            "plausible: neither the opening nor the body retains —"
            " rebuild from the hook outward.",
            "Test new openings first; only then rework the body."),
        ("low", "high"): (
            "weak opening but strong hold among starters",
            "plausible: a good body hidden behind a weak opening —"
            " starters stay, most never start.",
            "Keep the body; test clearer openings."),
        ("high", "low"): (
            "strong opening but weak hold",
            "plausible: the hook overpromises or the setup stalls.",
            "Preserve the hook; shorten setup, align body promise."),
        ("high", "high"): (
            "strong opening and strong hold",
            "attention engine works; scale or iterate format variants.",
            "Protect this structure; test creator/format variants for"
            " scale.")}[band_hook, band_hold]
    conf = _base(ctx, "hook_hold_%s_%s" % (band_hook, band_hold),
                 "hold", ["hook_rate_2s_impr", "hold_rate"],
                 ["hook_rate_2s_impr", "hold_rate"])
    finding = _finding(
        "hook_hold_%s_%s" % (band_hook, band_hold), "hold",
        [ctx["creative_key"]], "hook %s / hold %s" % (band_hook,
                                                      band_hold),
        texts[1], texts[0] + ".", texts[2],
        "high" if (band_hook, band_hold) != ("high", "high") else "low",
        conf, _observed(ctx, ["hook_rate_2s_impr", "hold_rate"]),
        _benchmarks(ctx, ["hook_rate_2s_impr", "hold_rate"]),
        "whichever half reads strong", "whichever half reads weak",
        ["audience mix differences between hook and hold cohorts"],
        ["hook and hold need stated, compatible definitions"],
        ["hook_rate_2s_impr", "hold_rate"], ctx.get("scope", {}),
        ctx.get("dataset_version", ""))
    return finding


def rule_quartile_completion_combo(ctx):
    """25% viewing x completion four-way pattern.

    Completion basis (exposures vs retained viewers) is recorded from
    the result basis so the two never silently mix.
    """
    band25, _v25, _i25 = _band(ctx, "quartile_25_impr")
    bandc, _vc, _ic = _band(ctx, "completion_impr")
    if band25 not in ("low", "high") or bandc not in ("low", "high"):
        return None
    comp_res = _ctx_value(ctx, "completion_impr") or {}
    basis = comp_res.get("basis", "")
    texts = {
        ("low", "low"): ("funnel leaks early and late",
                         "Rebuild opening first; ending second."),
        ("low", "high"): ("weak start, strong finish among starters",
                          "Keep the ending; fix the opening."),
        ("high", "low"): ("strong start, weak finish",
                          "Keep the opening; shorten the ending."),
        ("high", "high"): ("strong throughout",
                           "Protect; test scale variants.")}[band25, bandc]
    conf = _base(ctx, "q25_completion_%s_%s" % (band25, bandc),
                 "depth", ["quartile_25_impr", "completion_impr"],
                 ["quartile_25_impr", "completion_impr"])
    limits = ["completion basis here: %s" % (basis or "unstated")]
    return _finding(
        "q25_completion_%s_%s" % (band25, bandc), "depth",
        [ctx["creative_key"]],
        "25%% viewing %s / completion %s" % (band25, bandc),
        "plausible: " + texts[0] + ".", texts[0] + ".", texts[1],
        "medium", conf,
        _observed(ctx, ["quartile_25_impr", "completion_impr"]),
        _benchmarks(ctx, ["quartile_25_impr", "completion_impr"]),
        "whichever quartile reads strong",
        "whichever quartile reads weak",
        ["duration mix across the cohort"], limits,
        ["quartile_25_impr", "completion_impr"], ctx.get("scope", {}),
        ctx.get("dataset_version", ""))


def rule_cost_combo(ctx):
    """CPM x CPCV four-way cost pattern."""
    band_cpm, _vc, _ic = _band(ctx, "cpm", higher_is_better=False)
    band_cpcv, _vv, _iv = _band(ctx, "cpcv", higher_is_better=False)
    # classify() with lower-is-better returns "high" for cheap;
    # translate to cost language explicitly.
    cost_cpm = "high" if band_cpm == "low" else (
        "low" if band_cpm == "high" else band_cpm)
    cost_cpcv = "high" if band_cpcv == "low" else (
        "low" if band_cpcv == "high" else band_cpcv)
    if cost_cpm not in ("low", "high") or \
            cost_cpcv not in ("low", "high"):
        return None
    texts = {
        ("low", "low"): ("cheap reach, cheap completions",
                         "Scale carefully; verify attention quality."),
        ("low", "high"): ("cheap reach, expensive completions",
                          "Fix retention before spending more."),
        ("high", "low"): ("expensive reach, cheap completions",
                          "Creative works; fix delivery cost."),
        ("high", "high"): ("expensive throughout",
                           "Fix delivery first, creative second.")
        }[cost_cpm, cost_cpcv]
    conf = _base(ctx, "cost_%s_%s" % (cost_cpm, cost_cpcv),
                 "efficiency", ["cpm", "cpcv"], ["cpm", "cpcv"])
    return _finding(
        "cost_%s_%s" % (cost_cpm, cost_cpcv), "efficiency",
        [ctx["creative_key"]],
        "CPM %s / CPCV %s" % (cost_cpm, cost_cpcv),
        "plausible: " + texts[0] + ".", texts[0] + ".", texts[1],
        "medium", conf, _observed(ctx, ["cpm", "cpcv"]),
        _benchmarks(ctx, ["cpm", "cpcv"],
                    {"cpm": False, "cpcv": False}),
        "whichever cost side reads low", "whichever cost side reads high",
        ["auction dynamics in this window"],
        ["single-currency scope required"], ["cpm", "cpcv"],
        ctx.get("scope", {}), ctx.get("dataset_version", ""))


def _series_points(ctx):
    """Date-ordered (frequency, vtr, spend, cpa) points with values."""
    pts = []
    for point in ctx.get("series") or []:
        freq = (point.get("frequency") or {}).get("value")
        vtr = (point.get("vtr") or {}).get("value")
        cpa_raw = point.get("cpa") or {}
        cpa = cpa_raw.get("value") if _measured(cpa_raw) else None
        pts.append({"date": point.get("date", ""),
                    "frequency": freq, "vtr": vtr,
                    "spend": point.get("spend", 0), "cpa": cpa})
    return [p for p in pts if p["date"]]


def rule_fatigue(ctx):
    """Rising frequency + declining VTR = possible fatigue.

    Fires only on time-series evidence (3+ dated points); without a
    series there is no fatigue diagnosis, only a limitation.
    """
    pts = _series_points(ctx)
    if len(pts) < 3:
        return None
    first, last = pts[0], pts[-1]
    if first["frequency"] is None or last["frequency"] is None:
        return None
    if first["vtr"] is None or last["vtr"] is None:
        return None
    # Zero baselines carry no relative information (0 * margin is 0,
    # so any non-negative endpoint would read as a move): no verdict.
    freq_up = (first["frequency"] > 0
               and last["frequency"] >= first["frequency"] * (1 + MARGIN))
    vtr_down = (first["vtr"] > 0
                and last["vtr"] <= first["vtr"] * (1 - MARGIN))
    vtr_stable = (first["vtr"] > 0
                  and abs(last["vtr"] - first["vtr"])
                  <= first["vtr"] * MARGIN)
    if freq_up and vtr_down:
        signal = ("frequency %.1f → %.1f with VTR %.1f%% → %.1f%% over"
                  " %d dated points" % (
                      first["frequency"], last["frequency"],
                      first["vtr"], last["vtr"], len(pts)))
        return _finding(
            "fatigue", "efficiency", [ctx["creative_key"]], signal,
            "plausible: possible creative fatigue — the same audience"
            " sees it more and responds less. Time order supports it;"
            " audience-mix change could mimic it.",
            "Repeated exposure wears the creative out.",
            "Test hook, creator or contextual variation; do not simply"
            " raise spend.",
            "high", _base(ctx, "fatigue", "efficiency",
                           ["frequency", "vtr"],
                           ["frequency", "vtr"]),
            {"frequency_first": first["frequency"],
             "frequency_last": last["frequency"],
             "vtr_first": first["vtr"], "vtr_last": last["vtr"],
             "points": len(pts)},
            {}, "current delivery settings",
            "hook, creator or context variation",
            ["audience-mix change over the same window",
             "seasonality or auction shifts"],
            ["needs the dated series; cross-section cannot show fatigue"],
            ["frequency", "vtr"], ctx.get("scope", {}),
            ctx.get("dataset_version", ""))
    if freq_up and vtr_stable:
        return _finding(
            "fatigue_resilient", "efficiency", [ctx["creative_key"]],
            "frequency %.1f → %.1f with stable VTR %.1f%% → %.1f%%" % (
                first["frequency"], last["frequency"],
                first["vtr"], last["vtr"]),
            "plausible resilience to repeated exposure — retention"
            " holds as frequency rises.",
            "This creative tolerates repetition so far.",
            "Monitor efficiency while testing controlled scale.",
            "low", _base(ctx, "fatigue_resilient", "efficiency",
                          ["frequency", "vtr"],
                          ["frequency", "vtr"]),
            {"frequency_first": first["frequency"],
             "frequency_last": last["frequency"],
             "vtr_first": first["vtr"], "vtr_last": last["vtr"],
             "points": len(pts)},
            {}, "current creative and delivery",
            "scale level (controlled)",
            ["short window may miss later fatigue"],
            ["resilience is provisional until longer series exist"],
            ["frequency", "vtr"], ctx.get("scope", {}),
            ctx.get("dataset_version", ""))
    return None


def rule_scale_deterioration(ctx):
    """Strong low-spend results deteriorating at higher spend.

    Needs the dated series: spend rising while CPA worsens (or VTR
    falls). Without time order, no scale diagnosis fires.
    """
    pts = _series_points(ctx)
    if len(pts) < 3:
        return None
    first, last = pts[0], pts[-1]
    spend_up = last["spend"] >= max(first["spend"], 1) * (1 + MARGIN)
    cpa_worse = (first["cpa"] is not None and last["cpa"] is not None
                 and first["cpa"] > 0
                 and last["cpa"] >= first["cpa"] * (1 + MARGIN))
    vtr_down = (first["vtr"] is not None and last["vtr"] is not None
                and first["vtr"] > 0
                and last["vtr"] <= first["vtr"] * (1 - MARGIN))
    if not spend_up or (not cpa_worse and not vtr_down):
        return None
    signal = "spend %.0f → %.0f with %s deteriorating over %d points" % (
        first["spend"], last["spend"],
        "CPA %.2f → %.2f" % (first["cpa"], last["cpa"]) if cpa_worse
        else "VTR %.1f%% → %.1f%%" % (first["vtr"], last["vtr"]),
        len(pts))
    return _finding(
        "scale_deterioration", "efficiency", [ctx["creative_key"]],
        signal,
        "plausible: limited scalability or audience-mix change — early"
        " efficiency came from a narrow pocket that spend outgrew.",
        "Scale diluted what made it work.",
        "Test broader executions and inspect delivery changes"
        " (audience, placement) across the window.",
        "high", _base(ctx, "scale_deterioration", "efficiency",
                       ["cpa" if cpa_worse else "vtr"],
                       ["cpa" if cpa_worse else "vtr"]),
        {"spend_first": first["spend"], "spend_last": last["spend"],
         "points": len(pts)},
        {}, "early efficient pocket", "audience breadth at scale",
        ["auction competition rising in the same window"],
        ["series only; do not read scale from one snapshot"],
        ["cpa" if cpa_worse else "vtr"], ctx.get("scope", {}),
        ctx.get("dataset_version", ""))


def rule_brand_recall_gap(ctx):
    """Strong retention + weak MEASURED brand recall only.

    Fires solely when a study/supplied measurement exists and assesses
    weak recall. Logo exposure or audio mentions never stand in for
    recall — without measured_recall this rule stays silent.
    """
    ann = ctx.get("annotation") or {}
    recall = ann.get("measured_recall")
    if not isinstance(recall, dict) or \
            recall.get("assessment") not in ("weak", "moderate"):
        return None
    band50, _v, _i = _band(ctx, "quartile_50_impr")
    band_hook, _vh, _ih = _band(ctx, "hook_rate_2s_impr")
    if "high" not in (band50, band_hook):
        return None
    conf = _base(ctx, "brand_recall_gap", "brand",
                 ["quartile_50_impr"], ["quartile_50_impr"])
    return _finding(
        "brand_recall_gap", "brand", [ctx["creative_key"]],
        "strong retention with weak measured brand recall (%s)" %
        recall.get("study", "supplied study"),
        "plausible: content overshadows brand linkage — viewers stay"
        " but do not take the brand with them.",
        "Attention without brand encoding.",
        "Integrate brand/product more meaningfully into the payoff,"
        " not as a tacked-on end card.",
        "high", conf,
        _observed(ctx, ["quartile_50_impr"]),
        _benchmarks(ctx, ["quartile_50_impr"]),
        "retentive content", "brand integration",
        ["recall study methodology limits (see study reference)"],
        ["recall claim rests on %s only" % recall.get("study", "?")],
        ["quartile_50_impr"], ctx.get("scope", {}),
        ctx.get("dataset_version", ""))


def _first_span(ann, key):
    spans = [s for s in (ann.get(key) or []) if isinstance(s, dict)]
    if not spans:
        return None
    try:
        return min(float(s.get("start_s", 0)) for s in spans)
    except (TypeError, ValueError):
        return None


def _slot_boundaries(ann):
    """All structure segment boundaries (transitions), in seconds."""
    bounds = set()
    for seg in ((ann.get("structure") or {}).values()):
        if not isinstance(seg, dict):
            continue
        try:
            s0, s1 = float(seg.get("start_s", 0)), float(seg.get("end_s", 0))
        except (TypeError, ValueError):
            continue
        if s1 > s0 > 0:
            bounds.add(round(s0, 2))
    return sorted(bounds)


def rule_drop_near_product(ctx):
    """Measured decline window containing a product appearance.

    Association only, at the interval's resolution: the drop window
    and the product span overlap. Never an exact-second claim.
    """
    ann = ctx.get("annotation") or {}
    product_s = _first_span(ann, "product_seconds")
    if product_s is None:
        return None
    resolution = float(ann.get("timestamp_resolution_s") or 1.0)
    hits = []
    for drop in ctx.get("retention_drops") or []:
        try:
            start, end = float(drop.get("start_s", -1)), \
                float(drop.get("end_s", -1))
        except (TypeError, ValueError):
            continue
        if start - resolution <= product_s <= end + resolution:
            hits.append(drop)
    if not hits:
        return None
    drop = max(hits, key=lambda d: d.get("drop_pts", 0))
    conf = _base(ctx, "drop_near_product", "brand", [], [])
    conf["reasons"] = ["coarse interval association, not causation",
                       "annotation: %s" % ctx.get("annotation_status",
                                                  "none")] + conf["reasons"]
    return _finding(
        "drop_near_product", "brand", [ctx["creative_key"]],
        "measured decline of %.1f pts over %ss–%ss containing the"
        " product appearance (~%ss)" % (
            drop.get("drop_pts", 0), drop.get("start_s"),
            drop.get("end_s"), product_s),
        "plausible: the product transition may interrupt the"
        " narrative — association at interval resolution, not proof.",
        "Viewers leave where the product enters.",
        "Test more natural product integration (earlier, smaller,"
        " voiceover-led).",
        "medium", conf,
        {"drop_pts": drop.get("drop_pts"),
         "window_s": [drop.get("start_s"), drop.get("end_s")],
         "product_first_s": product_s}, {},
        "pre-product narrative", "product transition",
        ["unrelated pacing dip at the same interval",
         "quartile-synthesized curves are coarse by construction"],
        ["interval resolution ±%ss; no exact-second claim" % resolution],
        [], ctx.get("scope", {}), ctx.get("dataset_version", ""))


def rule_drop_near_transition(ctx):
    """Measured decline window containing a structure-slot boundary."""
    ann = ctx.get("annotation") or {}
    bounds = _slot_boundaries(ann)
    if not bounds:
        return None
    resolution = float(ann.get("timestamp_resolution_s") or 1.0)
    hits = []
    for drop in ctx.get("retention_drops") or []:
        try:
            start, end = float(drop.get("start_s", -1)), \
                float(drop.get("end_s", -1))
        except (TypeError, ValueError):
            continue
        near = [b for b in bounds
                if start - resolution <= b <= end + resolution]
        if near:
            hits.append((drop, near))
    if not hits:
        return None
    drop, near = max(hits, key=lambda h: h[0].get("drop_pts", 0))
    conf = _base(ctx, "drop_near_transition", "hold", [], [])
    return _finding(
        "drop_near_transition", "hold", [ctx["creative_key"]],
        "measured decline of %.1f pts over %ss–%ss near a segment"
        " boundary (~%ss)" % (drop.get("drop_pts", 0),
                              drop.get("start_s"), drop.get("end_s"),
                              near[0]),
        "plausible: the transition may weaken continuity —"
        " association at interval resolution.",
        "Viewers leave at the cut.",
        "Shorten the post-cut segment or preserve voiceover"
        " continuity across it.",
        "medium", conf,
        {"drop_pts": drop.get("drop_pts"),
         "window_s": [drop.get("start_s"), drop.get("end_s")],
         "boundary_s": near[0]}, {},
        "pre-cut momentum", "transition continuity",
        ["coincidental pacing dip"],
        ["interval resolution ±%ss; no exact-second claim" % resolution],
        [], ctx.get("scope", {}), ctx.get("dataset_version", ""))


def rule_remix_hook_hold(ctx):
    """Remix/graphics with strong hook but weak hold."""
    ann = ctx.get("annotation") or {}
    if (ann.get("format_kind") or "unknown") != "graphics_remix":
        return None
    band_hook, _vh, _ih = _band(ctx, "hook_rate_2s_impr")
    band_hold, _vd, _id = _band(ctx, "hold_rate")
    if band_hook != "high" or band_hold != "low":
        return None
    conf = _base(ctx, "remix_hook_hold", "hold",
                 ["hook_rate_2s_impr", "hold_rate"],
                 ["hook_rate_2s_impr", "hold_rate"])
    return _finding(
        "remix_hook_hold", "hold", [ctx["creative_key"]],
        "remix/graphics format: strong hook, weak hold",
        "plausible: visual novelty earns the open but does not"
        " sustain interest.",
        "Novelty without substance.",
        "Test a shorter remix or a creator-footage combination.",
        "medium", conf,
        _observed(ctx, ["hook_rate_2s_impr", "hold_rate"]),
        _benchmarks(ctx, ["hook_rate_2s_impr", "hold_rate"]),
        "visual novelty", "sustaining substance",
        ["format labels are analyst-set; verify format_kind"],
        ["single-format read; compare against creator-led cohort"],
        ["hook_rate_2s_impr", "hold_rate"], ctx.get("scope", {}),
        ctx.get("dataset_version", ""))


SPECIAL_RULES = (rule_hook_hold_combo, rule_quartile_completion_combo,
                 rule_cost_combo, rule_fatigue, rule_scale_deterioration,
                 rule_brand_recall_gap, rule_drop_near_product,
                 rule_drop_near_transition, rule_remix_hook_hold)


def evaluate_creative(ctx):
    """All catalogue + special rules for one creative context."""
    findings, suppressed = evaluate_all(ctx)
    for rule in SPECIAL_RULES:
        try:
            finding = rule(ctx)
        except Exception:
            continue
        if finding is not None:
            findings.append(finding)
    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: order.get(f["priority"], 3))
    return findings, suppressed


def _cohort_metric(summaries, metric_id):
    """(values_by_key, cohort_values) for measured creatives only."""
    values = {}
    for summary in summaries:
        res = (summary.get("metrics") or {}).get(metric_id)
        if _measured(res):
            values[summary["creative_key"]] = res["value"]
    return values, sorted(values.values())


def _group_pooled(rows_by_key, keys, metric_id, num_field, den_field,
                  scale=100.0):
    rows = []
    for key in keys:
        rows.extend(rows_by_key.get(key, []))
    return metrics.pooled_ratio(rows, metric_id, num_field, den_field,
                                scale=scale)


def rule_format_comparison(summaries, rows_by_key, scope,
                           dataset_version, objective="reach"):
    """B-roll vs face-to-camera / creator-led vs graphics comparisons.

    Cohort-level, exploratory below MIN_COHORT_N per group: pooled
    group rates with member counts, never a causal verdict.
    """
    def group_of(summary):
        fmt = (summary.get("format_kind") or "unknown")
        opening = (summary.get("opening_delivery") or "unknown")
        if fmt == "b_roll":
            return "b_roll"
        if fmt == "graphics_remix":
            return "graphics_remix"
        if opening == "direct_to_camera" or fmt in ("solo_creator",
                                                    "dialogue"):
            return "face_to_camera"
        if fmt == "creator_led":
            return "creator_led"
        return "other"

    groups = {}
    for summary in summaries:
        groups.setdefault(group_of(summary), []).append(
            summary["creative_key"])
    pairs = [(["b_roll"], ["face_to_camera"], "b_roll_vs_face",
              "Product demonstration may be effective in this cohort.",
              "Test result/demo-first openings."),
             (["face_to_camera", "creator_led"], ["graphics_remix"],
              "human_vs_graphics",
              "Human-led execution may fit this cohort better.",
              "Develop creator-led variants.")]
    findings = []
    for left_names, right_names, rid, hypothesis, iteration in pairs:
        left = [k for name in left_names for k in groups.get(name, [])]
        right = [k for name in right_names for k in groups.get(name, [])]
        if not left or not right:
            continue
        hook_l = _group_pooled(rows_by_key, left, "hook_rate_2s_impr",
                               "views_2s", "impressions")
        hook_r = _group_pooled(rows_by_key, right, "hook_rate_2s_impr",
                               "views_2s", "impressions")
        if not _measured(hook_l) or not _measured(hook_r):
            continue
        diff_pp = hook_l["value"] - hook_r["value"]
        if abs(diff_pp) < 1.0:
            continue  # no meaningful gap, no finding
        winner, loser = (left, right) if diff_pp > 0 else (right, left)
        small = len(winner) < MIN_COHORT_N or len(loser) < MIN_COHORT_N
        conf = {"level": "exploratory" if small else "medium",
                "reasons": ["cohort groups n=%d vs n=%d%s" % (
                    len(winner), len(loser),
                    " (exploratory: below n=%d)" % MIN_COHORT_N
                    if small else ""),
                    "observational grouping; promotion, creator and"
                    " audience confounders uncontrolled"],
                "dimensions": {"data": "medium", "annotation": "medium",
                               "comparison": "low" if small else "medium"}}
        findings.append(_finding(
            rid, "hold", winner + loser,
            "%s hook %.1f%% vs %s %.1f%% (%+.1f pp, n=%d vs n=%d)" % (
                "+".join(left_names), hook_l["value"],
                "+".join(right_names), hook_r["value"], diff_pp,
                len(left), len(right)),
            "plausible association only: " + hypothesis,
            hypothesis, iteration, "medium", conf,
            {"left_hook": hook_l["value"],
             "right_hook": hook_r["value"],
             "diff_pp": diff_pp,
             "left_n": len(left), "right_n": len(right)},
            {}, winner[0] + "-side execution", loser[0] + "-side rework",
            ["confounded by creator, promotion, audience, placement"],
            ["exploratory below n=%d per group — do not present as"
             " proof" % MIN_COHORT_N] if small else
            ["observational; confirm with a controlled variant test"],
            ["hook_rate_2s_impr"], scope, dataset_version))
    return findings


def rule_duration_roles(summaries, scope, dataset_version):
    """Longer wins AWT while shorter wins completion: assign roles.

    Never crowns one universal winner across durations.
    """
    timed = [(s["creative_key"], s.get("duration_s") or 0,
              ((s.get("metrics") or {}).get("awt_per_view") or {}).get(
                  "value"),
              ((s.get("metrics") or {}).get("completion_impr") or {})
              .get("value"))
             for s in summaries]
    timed = [t for t in timed if t[1] > 0 and t[2] is not None
             and t[3] is not None]
    if len(timed) < 2:
        return None
    by_awt = max(timed, key=lambda t: t[2])
    by_comp = max(timed, key=lambda t: t[3])
    if by_awt[0] == by_comp[0]:
        return None
    if not (by_awt[1] > by_comp[1]):
        return None  # the pattern needs longer=AWT, shorter=completion
    conf = {"level": "medium",
            "reasons": ["duration-aware pair, n=2 exemplars",
                        "cohort context in limitations"],
            "dimensions": {"data": "high", "annotation": "medium",
                           "comparison": "medium"}}
    return _finding(
        "duration_roles", "depth", [by_awt[0], by_comp[0]],
        "%s (%ss) leads AWT at %.2fs while %s (%ss) leads completion"
        " at %.1f%%" % (by_awt[0], by_awt[1], by_awt[2], by_comp[0],
                        by_comp[1], by_comp[3]),
        "formats serve different roles: depth vs efficient finish.",
        "Different durations do different jobs.",
        "Recommend roles (long for message depth, short for"
        " efficient completion) rather than one universal winner.",
        "medium", conf,
        {"awt_winner": by_awt[0], "awt_s": by_awt[2],
         "completion_winner": by_comp[0],
         "completion_pct": by_comp[3]}, {},
        "each format in its role", "single-winner ranking",
        ["looping may inflate short completion"],
        ["pairwise illustration; cohort medians in the table"],
        ["awt_per_view", "completion_impr"], scope, dataset_version)


LAYERS = (("stop", "Does the opening capture attention?"),
          ("hold", "Does the creative retain attention after the opening?"),
          ("depth", "How much of the message is consumed?"),
          ("brand", "When and how are brand/product/message presented?"),
          ("efficiency", "What does delivery cost, and how does it scale?"))


def five_layer_summary(ctx, findings):
    """Per-layer status for one creative: strength / concern / unknown.

    A layer reads "concern" when a medium+ confidence finding targets
    it, "strength" when its key metric bands high with nothing against
    it, else "unknown" (insufficient data is a verdict, not a gap).
    """
    key_metrics = {"stop": ["hook_rate_2s_impr", "hook_rate_3s_impr"],
                   "hold": ["hold_rate", "quartile_25_impr"],
                   "depth": ["quartile_50_impr", "completion_impr",
                             "awt_per_view"],
                   "brand": [],
                   "efficiency": ["cpm", "cpcv", "frequency"]}
    layers = []
    for layer, question in LAYERS:
        layer_findings = [f["finding_id"] for f in findings
                          if f.get("layer") == layer]
        strong = [f for f in findings
                  if f.get("layer") == layer
                  and f.get("confidence_level") in ("high", "medium")]
        bands = []
        for mid in key_metrics[layer]:
            band, value, _info = _band(ctx, mid)
            if value is not None:
                bands.append((mid, band, round(value, 2)))
        if strong:
            status = "concern"
        elif any(b == "high" for _, b, _v in bands):
            status = "strength"
        elif bands or layer_findings:
            status = "mixed"
        else:
            status = "unknown"
        layers.append({"layer": layer, "question": question,
                       "status": status, "metric_bands": bands,
                       "finding_ids": layer_findings})
    return layers


