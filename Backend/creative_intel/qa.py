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


def answer(conn, question):
    """Answer strictly from uploaded rows + annotations + transcripts."""
    from . import benchmarks
    ensure(conn)
    rows = _ads(conn)
    if not rows:
        return {"answer": "No uploaded data yet. Upload a Meta or TikTok "
                "export before asking questions.",
                "sources": [], "review_id": None}
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
        parts.append("Blended CPA is $%.2f across %s conversions. Top "
                     "conversions row is %r at %s."
                     % (value, conv, top_conv["creative_key"],
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
