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
        parts.append("Total spend across %d uploaded rows is $%s."
                     % (len(rows), f"{total:,.2f}"))
        cite("Uploaded CSV")
    if any(w in q for w in ("ctr", "click")):
        impr = sum(r["impressions"] for r in rows)
        clicks = sum(r["clicks"] for r in rows)
        if impr:
            parts.append("Blended CTR is %.2f%% (%d clicks)."
                         % (100.0 * clicks / impr, clicks))
        else:
            parts.append("Blended CTR is 0.00%% (%d clicks on zero "
                         "impressions — no rate to report)." % clicks)
        cite("Benchmark Derived")
    if any(w in q for w in ("cpa", "conversion", "result")):
        spend = sum(r["spend"] for r in rows)
        conv = sum(r["conversions"] for r in rows)
        parts.append("Blended CPA is $%.2f across %s conversions."
                     % ((spend / conv) if conv else 0.0, conv))
        cite("Benchmark Derived")
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
    if not parts:
        spend = sum(r["spend"] for r in rows)
        parts.append("The dataset holds %d uploaded rows at $%s total "
                     "spend. Ask about spend, CTR, CPA, or best creatives."
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
