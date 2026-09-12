"""Grounded Q&A over uploaded data only.

Source priority (every cited fact carries one):
1. Uploaded CSV -- highest
2. Annotation -- analyst-written labels on creatives
3. ASR Transcript -- machine transcript, may contain errors
4. Benchmark Derived -- computed from the above, lowest

Review-to-zero gate: each answer opens a pending review row. The
one-pager export stays blocked until every review is marked reviewed
(see export_gate.check_reviews).
"""

import datetime
import json
import math

PRODUCT_EARLY_S = 3.0
BRAND_EARLY_S = 3.0

SOURCE_PRIORITY = ("Uploaded CSV", "Annotation", "ASR Transcript",
                   "Benchmark Derived")

QA_DDL = """
CREATE TABLE IF NOT EXISTS qa_reviews (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL DEFAULT '',
    question TEXT NOT NULL DEFAULT '',
    answer TEXT NOT NULL DEFAULT '',
    sources_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending'
);
"""


def ensure(conn):
    conn.execute(QA_DDL)
    conn.commit()


def pending_count(conn):
    ensure(conn)
    return conn.execute(
        "SELECT COUNT(*) FROM qa_reviews WHERE status='pending'").fetchone()[0]


def _ads(conn):
    cols = [c[0] for c in
            conn.execute("SELECT * FROM ads LIMIT 0").description]
    return [dict(zip(cols, v)) for v in
            conn.execute("SELECT * FROM ads").fetchall()]


def _annotations(conn):
    """Map creative_key -> annotation dict ({} when absent or unparseable)."""
    try:
        pairs = conn.execute(
            "SELECT creative_key, annotation_json FROM annotations").fetchall()
    except Exception:
        return {}
    out = {}
    for key, raw in pairs:
        try:
            out[key] = json.loads(raw) if raw else {}
        except ValueError:
            out[key] = {}
    return out


def _product_start(ann):
    """Earliest product-appearance second from an annotation, else None."""
    if not isinstance(ann, dict):
        return None
    direct = ann.get("product_first_visible_s")
    if (isinstance(direct, (int, float)) and not isinstance(direct, bool)
            and math.isfinite(direct)):
        return float(direct)
    spans = ann.get("product_seconds") or []
    starts = [float(s["start_s"]) for s in spans
              if isinstance(s, dict)
              and isinstance(s.get("start_s"), (int, float))
              and not isinstance(s.get("start_s"), bool)
              and math.isfinite(s["start_s"])]
    return min(starts) if starts else None


def _cpa(group):
    spend = sum(r["spend"] for r in group)
    conv = sum(r["conversions"] for r in group)
    return (spend / conv) if conv else 0.0, spend, conv


def _view_rate(group):
    """A15: (label, value, num, den) for one row group.

    Completions-based VTR when the group measured completions,
    otherwise the explicitly-labelled play rate (plays over
    impressions). Rows are full ads dicts, so missing_json
    distinguishes unmeasured numerators from measured zeros via the
    shared registry field_state — an unmeasured rate yields None,
    never a false 0.0.
    """
    from creative_intel import analyst_metrics as _metrics
    for metric_id, label in (("vtr", "VTR"), ("view_rate", "play rate")):
        spec = _metrics.METRICS[metric_id]
        state, usable = _metrics.field_state(group, spec["numerator"])
        if state == _metrics.UNSUPPORTED or not usable:
            continue
        num = sum((r or {}).get(spec["numerator"], 0) or 0 for r in usable)
        den = sum((r or {}).get(spec["denominator"], 0) or 0 for r in usable)
        if not den:
            continue
        return label, round(num / den, 4), num, den
    return "play rate", None, 0, 0


def _pct(value):
    """Percent text for an optional rate: n/a, never a false 0.0%."""
    return ("%.1f%%" % (100.0 * value)) if value is not None else "n/a"


def _rate_noun(label):
    return "completions" if label == "VTR" else "views"


def _rate_json(group):
    """JSON-safe _view_rate for LLM fact packs."""
    label, value, num, den = _view_rate(group)
    return {"label": label, "value": value,
            "numerator": num, "denominator": den}


def _show_metric(metric, value):
    if metric in ("cpa",):
        return "$%.2f" % value
    if metric in ("ctr", "vtr"):
        return "%.2f%%" % (value * 100.0)
    if metric == "roas":
        # One decimal everywhere (KPI cards, benchmark context, Ask
        # takeaways): the winner sentence shares the same precision,
        # so ties are judged exactly as displayed.
        return "%.1fx" % value
    return str(value)


def _fact_pack(conn, limit=8, scope=None):
    """Compact computed facts for the LLM asker. Every number below is
    derived from uploaded rows/annotations in this call. scope (the
    shared analysis Scope or a plain filter dict) restricts the rows
    first, so Ask answers the filtered dataset it was asked about."""
    from . import benchmarks
    scope = (scope if isinstance(scope, benchmarks.Scope)
             else benchmarks.Scope(scope))
    rows = [r for r in _ads(conn) if scope.match(r)]
    anns = _annotations(conn)
    spend = sum(r["spend"] for r in rows)
    impr = sum(r["impressions"] for r in rows)
    clicks = sum(r["clicks"] for r in rows)
    conv = sum(r["conversions"] for r in rows)
    by_campaign, by_hook, by_format, by_style = {}, {}, {}, {}
    for r in rows:
        by_campaign.setdefault(r["campaign"] or "(uncategorised)", []).append(r)
        hook = (anns.get(r["creative_key"], {}) or {}).get("hook_type")
        if hook:
            by_hook.setdefault(hook, []).append(r)
        style = (anns.get(r["creative_key"], {}) or {}).get("edit_style")
        if style:
            by_style.setdefault(style, []).append(r)
        if (r["platform"] or "").lower() == "tiktok":
            mode = (anns.get(r["creative_key"], {}) or {}).get(
                "creator_vs_branded") or "(unannotated)"
            by_format.setdefault(mode, []).append(r)

    def _kpis(group):
        spend = sum(x["spend"] for x in group)
        impr = sum(x["impressions"] for x in group)
        clicks = sum(x["clicks"] for x in group)
        conv = sum(x["conversions"] for x in group)
        keys = sorted({x["creative_key"] for x in group})
        return {"n_creatives": len(keys), "spend": round(spend, 2),
                "ctr": round(clicks / impr, 4) if impr else None,
                "cpa": round(spend / conv, 2) if conv else None}

    camps = sorted(by_campaign.items(),
                   key=lambda kv: sum(x["spend"] for x in kv[1]),
                   reverse=True)[:limit]
    by_funnel, by_vertical, by_market = {}, {}, {}
    for r in rows:
        by_funnel.setdefault(
            r.get("funnel_stage") or "(unset)", []).append(r)
        if r.get("vertical"):
            by_vertical.setdefault(r["vertical"], []).append(r)
        if r.get("market"):
            by_market.setdefault(r["market"], []).append(r)

    def _timed(group):
        stats = _kpis(group)
        # A15: completions-based VTR when measured, else an explicit
        # play rate — never plays masquerading as VTR.
        label, value, _num, _den = _view_rate(group)
        stats["rate_label"] = label
        stats["rate"] = value
        return stats

    def _timing_block(early_group, late_group):
        block = {}
        if early_group:
            block["early"] = {
                "n_creatives": len({x["creative_key"]
                                    for x in early_group}),
                **_timed(early_group)}
        else:
            block["early"] = None
        if late_group:
            block["late"] = {
                "n_creatives": len({x["creative_key"]
                                    for x in late_group}),
                **_timed(late_group)}
        else:
            block["late"] = None
        return block

    early, late = [], []
    brand_early, brand_late = [], []
    logo_early, logo_late = [], []
    audio_early, audio_late = [], []
    with_cta, without_cta = [], []
    slot_hits = {}
    durations = {}
    for key in {r["creative_key"] for r in rows}:
        got = conn.execute("SELECT duration_s FROM creatives WHERE creative_key=?",
                           (key,)).fetchone()
        if got and got[0]:
            durations[key] = got[0]
    def _span_min(ann, key):
        spans = (ann or {}).get(key) or []
        starts = [s.get("start_s") for s in spans
                  if isinstance(s, dict)
                  and isinstance(s.get("start_s"), (int, float))
                  and not isinstance(s.get("start_s"), bool)]
        return min(starts) if starts else None

    for r in rows:
        ann = anns.get(r["creative_key"], {}) or {}
        start = _product_start(ann)
        if start is not None:
            (early if start <= PRODUCT_EARLY_S else late).append(r)
        brand = _span_min(ann, "brand_seconds")
        if brand is not None:
            (brand_early if brand <= BRAND_EARLY_S else brand_late).append(r)
        logo = _span_min(ann, "logo_seconds")
        if logo is not None:
            (logo_early if logo <= BRAND_EARLY_S else logo_late).append(r)
        mention = ann.get("brand_audio_mention_s")
        if isinstance(mention, (int, float)) and not isinstance(mention, bool):
            (audio_early if mention <= BRAND_EARLY_S else audio_late).append(r)
        struct = ann.get("structure") or {}
        cta = ann.get("cta") or (struct.get("cta") or {})
        has_cta = bool(isinstance(cta, str) and cta.strip()) or (
            isinstance(cta, dict) and
            (cta.get("end_s") or 0) > (cta.get("start_s") or 0))
        (with_cta if has_cta else without_cta).append(r)
        for slot, seg in struct.items():
            if isinstance(seg, dict) and (seg.get("end_s") or 0) > (
                    seg.get("start_s") or 0):
                slot_hits[slot] = slot_hits.get(slot, 0) + 1
    by_length = {"<=15s": [], "15-30s": [], ">30s": []}
    for r in rows:
        dur = durations.get(r["creative_key"])
        if dur is None:
            continue
        bucket = "<=15s" if dur <= 15 else ("15-30s" if dur <= 30 else ">30s")
        by_length[bucket].append(r)
    by_key = {}
    for r in rows:
        by_key.setdefault(r["creative_key"], []).append(r)

    def _score(group):
        spend = sum(x["spend"] for x in group)
        conv = sum(x["conversions"] for x in group)
        if conv:
            return (0, spend / conv)
        impr = sum(x["impressions"] for x in group)
        clicks = sum(x["clicks"] for x in group)
        if impr:
            return (1, -(clicks / impr))
        return (2, 0.0)

    ranked = sorted(by_key, key=lambda k: _score(by_key[k]))
    nq = max(1, len(ranked) // 5)
    quintiles = {
        "top_20_pct": ranked[:nq],
        "bottom_20_pct": ranked[-nq:] if len(ranked) > 1 else [],
    }
    retention = {}
    scoped_keys = {r["creative_key"] for r in rows if r["creative_key"]}
    curves = [(k, t0, t1) for k, t0, t1 in conn.execute(
        "SELECT creative_key, MIN(t_sec), MAX(t_sec) FROM retention"
        " GROUP BY creative_key").fetchall() if k in scoped_keys]
    if curves:
        drops = []
        for key, _t0, _t1 in curves:
            pts = conn.execute(
                "SELECT retention_pct FROM retention WHERE creative_key=?"
                " ORDER BY t_sec", (key,)).fetchall()
            if len(pts) >= 2:
                drops.append(pts[0][0] - pts[-1][0])
        retention = {"creatives_with_curves": len(curves),
                     "avg_drop_pts": round(sum(drops) / len(drops), 2)
                     if drops else None}
    pack = {
        "totals": {"rows": len(rows), "spend": round(spend, 2),
                   "ctr": round(clicks / impr, 4) if impr else None,
                   "cpa": round(spend / conv, 2) if conv else None},
        "campaigns": [{"campaign": name, **_kpis(group)}
                      for name, group in camps],
        "hooks": [{"hook": hook, **_kpis(group)}
                  for hook, group in sorted(
                      by_hook.items(),
                      key=lambda kv: sum(x["spend"] for x in kv[1]),
                      reverse=True)[:limit]],
        "styles": [{"style": style, **_kpis(group)}
                   for style, group in sorted(
                       by_style.items(),
                       key=lambda kv: sum(x["spend"] for x in kv[1]),
                       reverse=True)[:limit]],
        "formats": [{"format": mode, **_kpis(group)}
                    for mode, group in sorted(
                        by_format.items(),
                        key=lambda kv: sum(x["spend"] for x in kv[1]),
                        reverse=True)[:limit]],
        "funnel": [{"stage": stage, **_kpis(group)}
                   for stage, group in sorted(
                       by_funnel.items(),
                       key=lambda kv: sum(x["spend"] for x in kv[1]),
                       reverse=True)[:limit]],
        "verticals": [{"vertical": name, **_kpis(group)}
                      for name, group in sorted(
                          by_vertical.items(),
                          key=lambda kv: sum(x["spend"] for x in kv[1]),
                          reverse=True)[:limit]],
        "markets": [{"market": name, **_kpis(group)}
                    for name, group in sorted(
                        by_market.items(),
                        key=lambda kv: sum(x["spend"] for x in kv[1]),
                        reverse=True)[:limit]],
        "product_timing": {
            "early_s": PRODUCT_EARLY_S,
            # A15: labelled rates for the LLM prompt — VTR only when
            # completions were measured, else an explicit play rate.
            "early": {"n_creatives": len({x["creative_key"] for x in early}),
                      "rate": _rate_json(early)} if early else None,
            "late": {"n_creatives": len({x["creative_key"] for x in late}),
                     "rate": _rate_json(late)} if late else None},
        "brand_timing": {"cutoff_s": BRAND_EARLY_S,
                         **_timing_block(brand_early, brand_late)},
        "logo_timing": {"cutoff_s": BRAND_EARLY_S,
                        **_timing_block(logo_early, logo_late)},
        "audio_timing": {"cutoff_s": BRAND_EARLY_S,
                         **_timing_block(audio_early, audio_late)},
        "lengths": [{"bucket": bucket, **_kpis(group)} for bucket, group in
                    by_length.items() if group],
        "cta": {"with_cta": _kpis(with_cta) if with_cta else None,
                "without_cta": _kpis(without_cta) if without_cta else None},
        "structure": {"slots_annotated": slot_hits,
                      "n_annotated_creatives": sum(
                          1 for k in {r["creative_key"] for r in rows}
                          if anns.get(k))},
        "quintiles": quintiles,
        "retention": retention or None,
        "scope": scope.describe(),
    }
    return pack


_USED_SOURCES = {
    "totals": ("Uploaded CSV", "Benchmark Derived"),
    "campaigns": ("Uploaded CSV", "Benchmark Derived"),
    "hooks": ("Annotation", "Uploaded CSV", "Benchmark Derived"),
    "styles": ("Annotation", "Uploaded CSV", "Benchmark Derived"),
    "formats": ("Annotation", "Uploaded CSV", "Benchmark Derived"),
    "funnel": ("Uploaded CSV", "Benchmark Derived"),
    "verticals": ("Uploaded CSV", "Benchmark Derived"),
    "markets": ("Uploaded CSV", "Benchmark Derived"),
    "product_timing": ("Annotation", "Uploaded CSV", "Benchmark Derived"),
    "brand_timing": ("Annotation", "Uploaded CSV", "Benchmark Derived"),
    "logo_timing": ("Annotation", "Uploaded CSV", "Benchmark Derived"),
    "audio_timing": ("Annotation", "Uploaded CSV", "Benchmark Derived"),
    "lengths": ("Uploaded CSV", "Benchmark Derived"),
    "cta": ("Annotation", "Uploaded CSV", "Benchmark Derived"),
    "structure": ("Annotation",),
    "quintiles": ("Uploaded CSV", "Benchmark Derived"),
    "retention": ("Uploaded CSV", "Benchmark Derived"),
}


def _llm_answer(conn, question, llm, scope=None):
    """LLM answer strictly over _fact_pack. Raises ProviderUnavailable
    on any failure so the caller falls back to the rule engine."""
    from . import providers
    pack = _fact_pack(conn, scope=scope)
    try:
        data = _extract_json_obj(providers, llm, question, pack)
    except Exception:
        raise providers.ProviderUnavailable("ask model output unusable")
    text = data.get("answer") if isinstance(data, dict) else None
    used = data.get("used") if isinstance(data, dict) else None
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise providers.ProviderUnavailable("ask model output unusable")
    cites = []
    for section in used if isinstance(used, list) else []:
        for label in _USED_SOURCES.get(section, ()):
            if label not in cites:
                cites.append(label)
    if not cites:
        cites = ["Uploaded CSV", "Benchmark Derived"]
    ordered = sorted(set(cites), key=SOURCE_PRIORITY.index)
    cur = conn.execute(
        "INSERT INTO qa_reviews (ts, question, answer, sources_json)"
        " VALUES (?, ?, ?, ?)",
        (datetime.datetime.now(datetime.timezone.utc).isoformat(),
         question, text.strip(), json.dumps(ordered)))
    conn.commit()
    return {"answer": text.strip() + " [LLM]", "sources": ordered,
            "review_id": cur.lastrowid}


def _extract_json_obj(providers, llm, question, pack):
    ask = getattr(llm, "ask_facts", None)
    if not callable(ask):
        raise providers.ProviderUnavailable("ask model has no ask_facts")
    raw = ask(question, pack)
    if not isinstance(raw, str):
        raise providers.ProviderUnavailable("non-text ask output")
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise providers.ProviderUnavailable("no JSON in ask output")
    try:
        return json.loads(raw[start:end + 1])
    except ValueError:
        raise providers.ProviderUnavailable("ask output is not valid JSON")


def answer(conn, question, llm=None, scope=None):
    """Answer strictly from uploaded rows + annotations + transcripts.

    llm (optional LiveLlm-compatible) answers over a computed fact pack;
    any live failure falls back to the deterministic rule engine, and
    both paths open the review-to-zero row. scope (the shared analysis
    Scope or a plain filter dict) restricts every number on both
    paths, so Ask answers the filtered dataset it was asked about.
    """
    from . import benchmarks, providers
    ensure(conn)
    scope = (scope if isinstance(scope, benchmarks.Scope)
             else benchmarks.Scope(scope))
    rows = [r for r in _ads(conn) if scope.match(r)]
    if not rows:
        if _ads(conn):
            return {"answer": "No uploaded rows match the current scope "
                    "(%s). Loosen the filters and ask again."
                    % scope.describe(),
                    "sources": [], "review_id": None,
                    "scope": scope.describe()}
        return {"answer": "No uploaded data yet. Upload a Meta or TikTok "
                "export before asking questions.",
                "sources": [], "review_id": None,
                "scope": scope.describe()}
    if llm is not None:
        try:
            return _llm_answer(conn, question, llm, scope=scope)
        except providers.ProviderUnavailable:
            pass  # live failed: rules below never leave the user empty-handed
    q = (question or "").lower()
    parts, cites = [], []

    def cite(label):
        if label not in cites:
            cites.append(label)

    if any(w in q for w in ("spend", "cost", "budget")):
        total = sum(r["spend"] for r in rows)
        top_spend = max(rows, key=lambda r: r["spend"])
        parts.append("Total spend across %d uploaded rows is $%s. Top spend "
                     "row is %r at $%s."
                     % (len(rows), f"{total:,.2f}",
                        top_spend["creative_key"],
                        f"{top_spend['spend']:,.2f}"))
        cite("Uploaded CSV")
    if any(w in q for w in ("ctr", "click")):
        impr = sum(r["impressions"] for r in rows)
        clicks = sum(r["clicks"] for r in rows)
        top_reach = max(rows, key=lambda r: r["impressions"])
        if impr:
            parts.append("Blended CTR is %.2f%% (%d clicks; top reach row "
                         "is %r at %d impressions)."
                         % (100.0 * clicks / impr, clicks,
                            top_reach["creative_key"],
                            top_reach["impressions"]))
        else:
            parts.append("Blended CTR is 0.00%% (%d clicks on zero "
                         "impressions — no rate to report)." % clicks)
        cite("Benchmark Derived")
        cite("Uploaded CSV")
    if any(w in q for w in ("cpa", "conversion", "result")):
        value, spend, conv = _cpa(rows)
        top_conv = max(rows, key=lambda r: r["conversions"])
        if conv:
            parts.append("Blended CPA is $%.2f across %s conversions. Top "
                         "conversions row is %r at %s."
                         % (value, conv, top_conv["creative_key"],
                            top_conv["conversions"]))
        else:
            parts.append("No conversions yet, so there is no CPA to report "
                         "($%s spend). Top conversions row is %r at %s."
                         % (f"{spend:,.2f}", top_conv["creative_key"],
                            top_conv["conversions"]))
        cite("Benchmark Derived")
        cite("Uploaded CSV")
    if any(w in q for w in ("best", "top", "winner", "creative")):
        # Answer at the requested level: an explicit platform/campaign
        # question ranks platforms/campaigns, otherwise creatives.
        # (Platform words do not trigger this branch on their own; the
        # trigger above still applies.)
        if any(w in q for w in ("platform", "meta", "tiktok")):
            _level, _lname = "platform", "platform"
        elif "campaign" in q:
            _level, _lname = "campaign", "campaign"
        else:
            _level, _lname = "creative_key", "creative"

        def _group_label(raw):
            if _level == "platform":
                low = str(raw or "").lower()
                return {"meta": "Meta", "tiktok": "TikTok"}.get(low, str(raw))
            return str(raw)

        by_key = {}
        for r in rows:
            by_key.setdefault(r[_level] or "(unattributed)", []).append(r)
        # A named metric picks the ranking; bare "best/top/winner"
        # falls back to spend, labelled as such.
        metric = None
        if any(w in q for w in ("cpa", "conversion", "result")):
            metric = "cpa"
        elif any(w in q for w in ("ctr", "click")):
            metric = "ctr"
        elif "roas" in q:
            metric = "roas"
        elif any(w in q for w in ("vtr", "view-through", "view through",
                                  "view rate", "completion")):
            metric = "vtr"

        # A15: one rate id per scope for fair ranking — VTR when
        # the scope measured completions, else the explicit play rate.
        _rate_id = "view_rate"
        _rate_label = "PLAY RATE"
        if metric == "vtr":
            from creative_intel import benchmarks as _bench
            _rate_label = _view_rate(rows)[0]
            _rate_id = "vtr" if _rate_label == "VTR" else "view_rate"

        def _group_metric(group):
            spend = sum(x["spend"] for x in group)
            impr = sum(x["impressions"] for x in group)
            clicks = sum(x["clicks"] for x in group)
            conv = sum(x["conversions"] for x in group)
            rev = sum(x.get("revenue") or 0 for x in group)
            if metric == "cpa":
                return (spend / conv) if conv else None
            if metric == "ctr":
                return (clicks / impr) if impr else None
            if metric == "roas":
                return (rev / spend) if spend else None
            if metric == "vtr":
                return _bench.pooled_registry_ratio(group, _rate_id)
            return spend

        ranked = [(k, _group_metric(g)) for k, g in by_key.items()]
        ranked = [(k, v) for k, v in ranked if v is not None]
        _metric_name = _rate_label if metric == "vtr" else (
            metric.upper() if metric else "")
        if metric is not None and not ranked:
            parts.append("No %s has a computable %s, so there is "
                         "no %s winner to name." % (_lname, _metric_name,
                                                    _metric_name))
            cite("Uploaded CSV")
        else:
            reverse = metric not in ("cpa",)
            ordered = sorted(ranked, key=lambda kv: kv[1],
                             reverse=reverse)
            # Ties are judged on the DISPLAYED value: anything the UI
            # prints identically shares the lead, so the winner sentence
            # can never crown a leader the takeaways call tied.
            disp = {k: _show_metric(metric, v) for k, v in ordered}
            top_disp = disp[ordered[0][0]]
            leaders = [k for k, _v in ordered if disp[k] == top_disp]
            group = by_key[leaders[0]]
            shown = ", ".join(_group_label(k) for k in leaders)
            if metric is None:
                spend = sum(x["spend"] for x in group)
                parts.append("Top %s by spend is %s at $%s."
                             % (_lname, shown, f"{spend:,.2f}"))
            elif len(leaders) > 1:
                parts.append("Top %s by %s is tied: %s at %s."
                             % (_lname, _metric_name, shown, top_disp))
            else:
                parts.append("Top %s by %s is %s at %s."
                             % (_lname, _metric_name, shown, top_disp))
            cite("Uploaded CSV")
        key = leaders[0] if ranked else None
        ann = conn.execute(
            "SELECT annotation_json FROM annotations WHERE creative_key=?",
            (key,)).fetchone() if _level == "creative_key" and ranked else None
        if ann and ann[0]:
            a = json.loads(ann[0])
            parts.append("Annotation: hook=%s, format=%s."
                         % (a.get("hook_type", "?"),
                            a.get("creator_vs_branded", "?")))
            cite("Annotation")
        tr = conn.execute(
            "SELECT transcript FROM creatives WHERE creative_key=?",
            (key,)).fetchone() if _level == "creative_key" and ranked else None
        if tr and tr[0]:
            parts.append("Transcript excerpt: %s" % tr[0][:200])
            cite("ASR Transcript")
    if any(w in q for w in ("vtr", "view-through", "view through",
                            "view rate", "completion")):
        anns = _annotations(conn)
        early, late = [], []
        for r in rows:
            start = _product_start(anns.get(r["creative_key"], {}))
            if start is None:
                continue
            (early if start <= PRODUCT_EARLY_S else late).append(r)
        if early and late:
            # A15: per-side labelled rates — VTR where completions
            # were measured, play rate elsewhere; never mixed blindly.
            elab, ev, evv, evi = _view_rate(early)
            llab, lv, lvv, lvi = _view_rate(late)
            if ev is None or lv is None:
                verdict = "unclear"
            else:
                verdict = "yes" if ev > lv else "no"
            parts.append(
                "%s: early product appearance holds %s %s (%d %s / "
                "%d impr across %s) vs late %s %s (%d %s / %d impr "
                "across %s)."
                % (verdict.title(), elab, _pct(ev), evv,
                   _rate_noun(elab), evi,
                   ", ".join(sorted({x["creative_key"] for x in early})),
                   llab, _pct(lv), lvv, _rate_noun(llab), lvi,
                   ", ".join(sorted({x["creative_key"] for x in late}))))
            cite("Uploaded CSV")
            cite("Annotation")
            cite("Benchmark Derived")
        else:
            blab, v, vv, vi = _view_rate(rows)
            top = max(rows, key=lambda r: r["video_views"])
            parts.append(
                "Blended %s is %s (%d %s / %d impr across %d rows; "
                "top views from %r). Add product-timing annotations to "
                "split early vs late appearance."
                % (blab, _pct(v), vv, _rate_noun(blab), vi, len(rows),
                   top["creative_key"]))
            cite("Uploaded CSV")
            cite("Benchmark Derived")
    if any(w in q for w in ("tiktok", "format", "creator", "branded")):
        tik = [r for r in rows if (r["platform"] or "").lower() == "tiktok"]
        if not tik:
            parts.append("No TikTok rows in the uploaded data yet. Upload a "
                         "TikTok export before asking about formats.")
            cite("Uploaded CSV")
        else:
            anns = _annotations(conn)
            groups = {}
            for r in tik:
                mode = (anns.get(r["creative_key"], {}) or {}).get(
                    "creator_vs_branded", "") or "(unannotated)"
                groups.setdefault(mode, []).append(r)
            bits = []
            for mode in sorted(groups):
                group = groups[mode]
                value, spend, conv = _cpa(group)
                keys = sorted({x["creative_key"] for x in group})
                bits.append("%s: %d creatives (%s) at $%.2f spend, CPA $%.2f"
                            % (mode, len(keys), ", ".join(keys),
                               spend, value))
            parts.append("TikTok formats — " + "; ".join(bits) + ".")
            cite("Uploaded CSV")
            if any(k != "(unannotated)" for k in groups):
                cite("Annotation")
    pack = None

    def scoped_pack():
        nonlocal pack
        if pack is None:
            pack = _fact_pack(conn, scope=scope)
        return pack

    def _money(value):
        return ("$%s" % f"{value:,.2f}") if value is not None else "n/a"

    if any(w in q for w in ("style", "editing", "talking head", "ugc",
                            "montage", "cinematic", "testimonial")):
        styles = scoped_pack()["styles"]
        if not styles:
            parts.append("No editing-style labels in scope yet — annotate "
                         "creatives to unlock style comparisons.")
            cite("Annotation")
        else:
            bits = ["%s: %d creatives at %s spend, CPA %s" % (
                s["style"], s["n_creatives"], _money(s["spend"]),
                _money(s["cpa"])) for s in styles]
            parts.append("Editing styles in scope — " + "; ".join(bits) + ".")
            cite("Uploaded CSV")
            cite("Annotation")
            cite("Benchmark Derived")
    def _timing_bits(label, timing):
        bits = []
        for side, when in (("early", "within the first %ss"),
                           ("late", "after %ss")):
            group = timing[side]
            if group:
                bits.append(
                    "%s %s: %d creatives at %s spend, %s %s, CTR %s, CPA %s"
                    % (label, when % timing["cutoff_s"],
                       group["n_creatives"], _money(group["spend"]),
                       group.get("rate_label", "play rate"),
                       ("%.2f%%" % (100.0 * group["rate"])
                        if group.get("rate") is not None else "n/a"),
                       ("%.2f%%" % (100.0 * group["ctr"])
                        if group.get("ctr") is not None else "n/a"),
                       _money(group["cpa"])))
        return bits

    if "brand" in q or "logo" in q:
        for label, key in (("Brand", "brand_timing"),
                           ("Logo", "logo_timing")):
            timing = scoped_pack()[key]
            bits = _timing_bits(label, timing)
            if not bits:
                parts.append("No %s appearance timings annotated in scope "
                             "yet." % label.lower())
                cite("Annotation")
            else:
                parts.append("; ".join(bits) + ".")
                cite("Uploaded CSV")
                cite("Annotation")
                cite("Benchmark Derived")
    if any(w in q for w in ("audio", "mention", "said", "spoken")):
        timing = scoped_pack()["audio_timing"]
        bits = _timing_bits("Audible brand mention", timing)
        if not bits:
            parts.append("No audible brand mentions timed in scope yet — "
                         "run the pipeline with brand terms to unlock this.")
            cite("Annotation")
        else:
            parts.append("; ".join(bits) + ".")
            cite("Uploaded CSV")
            cite("Annotation")
            cite("Benchmark Derived")
    if "hook" in q:
        hooks = scoped_pack()["hooks"]
        if not hooks:
            parts.append("No hook labels in scope yet — annotate creatives "
                         "to unlock hook comparisons.")
            cite("Annotation")
        else:
            bits = ["%s: %d creatives at %s spend, CPA %s" % (
                h["hook"], h["n_creatives"], _money(h["spend"]),
                _money(h["cpa"])) for h in hooks]
            parts.append("Hooks in scope — " + "; ".join(bits) + ".")
            cite("Uploaded CSV")
            cite("Annotation")
            cite("Benchmark Derived")
    if any(w in q for w in ("length", "duration", "long", "short",
                            "15s", "30s", "seconds")):
        lengths = scoped_pack()["lengths"]
        if not lengths:
            parts.append("No video durations recorded in scope yet.")
            cite("Uploaded CSV")
        else:
            bits = ["%s: %d creatives at %s spend, CPA %s, CTR %s" % (
                b["bucket"], b["n_creatives"], _money(b["spend"]),
                _money(b["cpa"]),
                ("%.2f%%" % (100.0 * b["ctr"]) if b.get("ctr") is not None
                 else "n/a")) for b in lengths]
            parts.append("Video length in scope — " + "; ".join(bits) + ".")
            cite("Uploaded CSV")
            cite("Benchmark Derived")
    if "cta" in q or "call to action" in q:
        cta = scoped_pack()["cta"]
        bits = []
        for label, key in (("with CTA", "with_cta"),
                           ("without CTA", "without_cta")):
            group = cta.get(key)
            if group:
                bits.append("%s: %d creatives at %s spend, CPA %s, CTR %s"
                            % (label, group["n_creatives"],
                               _money(group["spend"]), _money(group["cpa"]),
                               ("%.2f%%" % (100.0 * group["ctr"])
                                if group.get("ctr") is not None else "n/a")))
        if not bits:
            parts.append("No CTA annotations in scope yet.")
            cite("Annotation")
        else:
            parts.append("CTA in scope — " + "; ".join(bits) + ".")
            cite("Uploaded CSV")
            cite("Annotation")
            cite("Benchmark Derived")
    if any(w in q for w in ("funnel", "upper", "lower", "stage", "tof",
                            "mof", "bof")):
        funnel = scoped_pack()["funnel"]
        if not funnel:
            parts.append("No funnel data in scope.")
            cite("Uploaded CSV")
        else:
            bits = ["%s: %d creatives at %s spend, CPA %s" % (
                s["stage"], s["n_creatives"], _money(s["spend"]),
                _money(s["cpa"])) for s in funnel]
            parts.append("Funnel in scope — " + "; ".join(bits) + ".")
            cite("Uploaded CSV")
            cite("Benchmark Derived")
    markets = scoped_pack()["markets"] if (
        "market" in q or "country" in q or "geo" in q or "region" in q) else []
    if "market" in q or "country" in q or "geo" in q or "region" in q:
        if not markets:
            nobits = [m["market"] for m in scoped_pack()["markets"]]
            parts.append("No market split in scope%s." % (
                " (only %s)" % ", ".join(nobits) if nobits else ""))
            cite("Uploaded CSV")
        else:
            bits = ["%s: %d creatives at %s spend, CPA %s" % (
                m["market"], m["n_creatives"], _money(m["spend"]),
                _money(m["cpa"])) for m in markets]
            parts.append("Markets in scope — " + "; ".join(bits) + ".")
            cite("Uploaded CSV")
            cite("Benchmark Derived")
    verticals = scoped_pack()["verticals"] if "vertical" in q else []
    if "vertical" in q:
        if not verticals:
            parts.append("No vertical split in scope.")
            cite("Uploaded CSV")
        else:
            bits = ["%s: %d creatives at %s spend, CPA %s" % (
                v["vertical"], v["n_creatives"], _money(v["spend"]),
                _money(v["cpa"])) for v in verticals]
            parts.append("Verticals in scope — " + "; ".join(bits) + ".")
            cite("Uploaded CSV")
            cite("Benchmark Derived")
    if any(w in q for w in ("top vs", "top versus", "bottom", "quintile",
                            "best vs", "worst", "winners", "losers")):
        quint = scoped_pack()["quintiles"]
        top, bottom = quint["top_20_pct"], quint["bottom_20_pct"]
        if not top:
            parts.append("Not enough ranked creatives in scope for a "
                         "top-vs-bottom split.")
            cite("Uploaded CSV")
        else:
            def _side(keys):
                group = [r for r in rows if r["creative_key"] in keys]
                spend = sum(x["spend"] for x in group)
                conv = sum(x["conversions"] for x in group)
                return "%s at %s spend, CPA %s" % (
                    ", ".join(keys), _money(spend),
                    _money(spend / conv if conv else None))
            line = "Top 20%% in scope: %s." % _side(top)
            if bottom:
                line += " Bottom 20%% in scope: %s." % _side(bottom)
            parts.append(line)
            cite("Uploaded CSV")
            cite("Benchmark Derived")
    if any(w in q for w in ("retention", "drop", "lose viewers", "dropoff",
                            "drop-off", "watch time")):
        ret = scoped_pack()["retention"]
        if not ret:
            parts.append("No retention curves in scope yet — upload a "
                         "retention export to analyse drop-off.")
            cite("Uploaded CSV")
        else:
            line = ("%d creatives carry curves in scope (avg total drop "
                    "%s pts)." % (
                        ret["creatives_with_curves"],
                        ret["avg_drop_pts"]
                        if ret["avg_drop_pts"] is not None else "n/a"))
            try:
                from . import retention as retention_mod
                pats = retention_mod.patterns(conn, scope)["patterns"][:3]
                for p in pats:
                    line += (" Normal loss: ~%s pts %s%s." % (
                        p["avg_drop_pts"],
                        ("during " + p["slot"]) if p["slot"] else "per video",
                        " with product demo on screen"
                        if p["product_demo"] else ""))
            except ValueError:
                pass
            parts.append(line)
            cite("Uploaded CSV")
            cite("Benchmark Derived")
    if any(w in q for w in ("structure", "slots", "section")):
        struct = scoped_pack()["structure"]
        hits = struct.get("slots_annotated") or {}
        if not hits:
            parts.append("No structure slots annotated in scope yet.")
            cite("Annotation")
        else:
            bits = ["%s on %d creatives" % (slot, n)
                    for slot, n in sorted(hits.items(),
                                          key=lambda kv: -kv[1])]
            parts.append("Structure in scope (%d annotated creatives): %s."
                         % (struct.get("n_annotated_creatives", 0),
                            ", ".join(bits)))
            cite("Annotation")
    if not parts:
        spend = sum(r["spend"] for r in rows)
        parts.append("Insufficient data: I can answer about spend, CTR, CPA, "
                     "VTR, TikTok formats, best creatives, hooks, editing "
                     "styles, video length, CTA, funnel, markets, verticals, "
                     "top-vs-bottom, retention, structure, or brand timing — "
                     "all from uploaded rows. The "
                     "dataset holds %d uploaded rows at $%s total spend."
                     % (len(rows), f"{spend:,.2f}"))
        cite("Uploaded CSV")

    ordered = sorted(set(cites), key=SOURCE_PRIORITY.index)
    text = " ".join(parts)
    cur = conn.execute(
        "INSERT INTO qa_reviews (ts, question, answer, sources_json)"
        " VALUES (?, ?, ?, ?)",
        (datetime.datetime.now(datetime.timezone.utc).isoformat(),
         question, text, json.dumps(ordered)))
    conn.commit()
    return {"answer": "%s (Scope: %s)" % (text, scope.describe()),
            "sources": ordered, "review_id": cur.lastrowid,
            "scope": scope.describe()}


def list_reviews(conn):
    ensure(conn)
    cols = ("id", "ts", "question", "answer", "sources_json", "status")
    return [dict(zip(cols, r)) for r in conn.execute(
        "SELECT id, ts, question, answer, sources_json, status"
        " FROM qa_reviews ORDER BY id DESC LIMIT 50")]


def mark_reviewed(conn, review_id):
    ensure(conn)
    conn.execute("UPDATE qa_reviews SET status='reviewed' WHERE id=?",
                 (review_id,))
    conn.commit()
    return pending_count(conn)
