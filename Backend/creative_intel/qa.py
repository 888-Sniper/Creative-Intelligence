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


def _vtr(group):
    """Pooled VTR = sum(video_views) / sum(impressions), plus raw totals."""
    impr = sum(r["impressions"] for r in group)
    views = sum(r["video_views"] for r in group)
    return (views / impr) if impr else 0.0, views, impr


def _cpa(group):
    spend = sum(r["spend"] for r in group)
    conv = sum(r["conversions"] for r in group)
    return (spend / conv) if conv else 0.0, spend, conv


def _fact_pack(conn, limit=8):
    """Compact computed facts for the LLM asker. Every number below is
    derived from uploaded rows/annotations in this call."""
    rows = _ads(conn)
    anns = _annotations(conn)
    spend = sum(r["spend"] for r in rows)
    impr = sum(r["impressions"] for r in rows)
    clicks = sum(r["clicks"] for r in rows)
    conv = sum(r["conversions"] for r in rows)
    by_campaign, by_hook, by_format = {}, {}, {}
    for r in rows:
        by_campaign.setdefault(r["campaign"] or "(uncategorised)", []).append(r)
        hook = (anns.get(r["creative_key"], {}) or {}).get("hook_type")
        if hook:
            by_hook.setdefault(hook, []).append(r)
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

    def _vtr(group):
        impr = sum(x["impressions"] for x in group)
        views = sum(x["video_views"] for x in group)
        return round(views / impr, 4) if impr else None

    early, late = [], []
    with_cta, without_cta = [], []
    slot_hits = {}
    durations = {}
    for key in {r["creative_key"] for r in rows}:
        got = conn.execute("SELECT duration_s FROM creatives WHERE creative_key=?",
                           (key,)).fetchone()
        if got and got[0]:
            durations[key] = got[0]
    for r in rows:
        ann = anns.get(r["creative_key"], {}) or {}
        start = _product_start(ann)
        if start is not None:
            (early if start <= PRODUCT_EARLY_S else late).append(r)
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
    curves = conn.execute(
        "SELECT creative_key, MIN(t_sec), MAX(t_sec) FROM retention"
        " GROUP BY creative_key").fetchall()
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
            "early": {"n_creatives": len({x["creative_key"] for x in early}),
                      "vtr": _vtr(early)} if early else None,
            "late": {"n_creatives": len({x["creative_key"] for x in late}),
                     "vtr": _vtr(late)} if late else None},
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
    }
    return pack


_USED_SOURCES = {
    "totals": ("Uploaded CSV", "Benchmark Derived"),
    "campaigns": ("Uploaded CSV", "Benchmark Derived"),
    "hooks": ("Annotation", "Uploaded CSV", "Benchmark Derived"),
    "formats": ("Annotation", "Uploaded CSV", "Benchmark Derived"),
    "funnel": ("Uploaded CSV", "Benchmark Derived"),
    "verticals": ("Uploaded CSV", "Benchmark Derived"),
    "markets": ("Uploaded CSV", "Benchmark Derived"),
    "product_timing": ("Annotation", "Uploaded CSV", "Benchmark Derived"),
    "lengths": ("Uploaded CSV", "Benchmark Derived"),
    "cta": ("Annotation", "Uploaded CSV", "Benchmark Derived"),
    "structure": ("Annotation",),
    "quintiles": ("Uploaded CSV", "Benchmark Derived"),
    "retention": ("Uploaded CSV", "Benchmark Derived"),
}


def _llm_answer(conn, question, llm):
    """LLM answer strictly over _fact_pack. Raises ProviderUnavailable
    on any failure so the caller falls back to the rule engine."""
    from . import providers
    pack = _fact_pack(conn)
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


def answer(conn, question, llm=None):
    """Answer strictly from uploaded rows + annotations + transcripts.

    llm (optional LiveLlm-compatible) answers over a computed fact pack;
    any live failure falls back to the deterministic rule engine, and
    both paths open the review-to-zero row.
    """
    from . import benchmarks, providers
    ensure(conn)
    rows = _ads(conn)
    if not rows:
        return {"answer": "No uploaded data yet. Upload a Meta or TikTok "
                "export before asking questions.",
                "sources": [], "review_id": None}
    if llm is not None:
        try:
            return _llm_answer(conn, question, llm)
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
        by_key = {}
        for r in rows:
            by_key.setdefault(r["creative_key"], []).append(r)
        top = max(by_key.items(),
                  key=lambda kv: sum(x["spend"] for x in kv[1]))
        key, group = top
        spend = sum(x["spend"] for x in group)
        parts.append("Top creative by spend is %r at $%s."
                     % (key, f"{spend:,.2f}"))
        cite("Uploaded CSV")
        ann = conn.execute(
            "SELECT annotation_json FROM annotations WHERE creative_key=?",
            (key,)).fetchone()
        if ann and ann[0]:
            a = json.loads(ann[0])
            parts.append("Annotation: hook=%s, format=%s."
                         % (a.get("hook_type", "?"),
                            a.get("creator_vs_branded", "?")))
            cite("Annotation")
        tr = conn.execute(
            "SELECT transcript FROM creatives WHERE creative_key=?",
            (key,)).fetchone()
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
            ev, evv, evi = _vtr(early)
            lv, lvv, lvi = _vtr(late)
            verdict = "yes" if ev > lv else "no"
            parts.append(
                "%s: early product appearance holds VTR %.1f%% (%d views / "
                "%d impr across %s) vs late %.1f%% (%d views / %d impr "
                "across %s)."
                % (verdict.title(), 100.0 * ev, evv, evi,
                   ", ".join(sorted({x["creative_key"] for x in early})),
                   100.0 * lv, lvv, lvi,
                   ", ".join(sorted({x["creative_key"] for x in late}))))
            cite("Uploaded CSV")
            cite("Annotation")
            cite("Benchmark Derived")
        else:
            v, vv, vi = _vtr(rows)
            top = max(rows, key=lambda r: r["video_views"])
            parts.append(
                "Blended VTR is %.1f%% (%d views / %d impr across %d rows; "
                "top views from %r). Add product-timing annotations to "
                "split early vs late appearance."
                % (100.0 * v, vv, vi, len(rows), top["creative_key"]))
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
    if not parts:
        spend = sum(r["spend"] for r in rows)
        parts.append("Insufficient data: I can answer about spend, CTR, CPA, "
                     "VTR, TikTok formats, or best creatives — all from "
                     "uploaded rows. The dataset holds %d uploaded rows at "
                     "$%s total spend."
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
    return {"answer": text, "sources": ordered, "review_id": cur.lastrowid}


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
