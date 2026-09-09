"""Gated one-pager export.

A creative may appear on the one-pager only when its annotation status
is human_verified, unless the caller passes override=True (logged).
"""


class ExportBlocked(Exception):
    def __init__(self, missing):
        if len(missing) == 1 and missing[0].startswith("gate:"):
            super().__init__(missing[0][len("gate:"):])
            self.missing = []
        else:
            super().__init__("not HUMAN-VERIFIED: %s" % sorted(missing))
            self.missing = sorted(missing)


def check_reviews(conn):
    """Review-to-zero gate: every grounded Q&A answer must be reviewed
    before the one-pager may export."""
    from . import qa
    pending = qa.pending_count(conn)
    if pending:
        raise ExportBlocked(
            ["gate:review-to-zero: %d QA review(s) still pending" % pending])


def build_one_pager(conn, creative_keys, benchmarks, override=False):
    import json
    missing = []
    cards = []
    for key in creative_keys:
        row = conn.execute(
            "SELECT c.name, c.platform, c.transcript, a.annotation_json"
            " FROM creatives c LEFT JOIN annotations a"
            " ON c.creative_key=a.creative_key WHERE c.creative_key=?",
            (key,)).fetchone()
        if not row:
            missing.append(key + " (unknown)")
            continue
        name, platform, transcript, ann_json = row
        ann = json.loads(ann_json) if ann_json else {}
        if ann.get("status") != "human_verified" and not override:
            missing.append(key)
            continue
        cards.append({"creative_key": key, "name": name, "platform": platform,
                      "hook_type": ann.get("hook_type", ""),
                      "creator_vs_branded": ann.get("creator_vs_branded", ""),
                      "transcript": transcript})
    if missing and not override:
        raise ExportBlocked(missing)
    lines = ["# Creative Intelligence — One-Pager", ""]
    for c in cards:
        lines += ["## %s (%s)" % (c["name"] or c["creative_key"], c["platform"]),
                  "- Hook: %s | Format: %s" % (c["hook_type"],
                                                c["creator_vs_branded"]),
                  "", c["transcript"] or "(no transcript)", ""]
    lines += ["## Spend-weighted benchmarks", ""]
    for group, vals in (benchmarks or {}).items():
        lines.append("- %s: CPA $%s, CTR %s, spend $%s"
                     % (group, vals.get("cpa"), vals.get("ctr"),
                        vals.get("spend")))
    return {"markdown": "\n".join(lines), "cards": cards,
            "override": override, "missing": missing}
