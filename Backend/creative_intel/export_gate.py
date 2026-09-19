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


def build_one_pager(conn, creative_keys, benchmarks, override=False,
                    owner=None, admin=False):
    missing = []
    cards = []
    from creative_intel import creative as _creative_mod
    from creative_intel import drafts as _drafts_mod
    for key in creative_keys:
        row = conn.execute(
            "SELECT name, platform, transcript FROM creatives"
            " WHERE creative_key=?",
            (key,)).fetchone()
        if not row:
            missing.append(key + " (unknown)")
            continue
        name, platform, shared_transcript = row
        # One consistent result identity: the viewer's applicable
        # confirmation selects the video version, and approval, hook
        # classification, and transcript all come from that same
        # version's rows. An older approved result never authorises
        # another video's content, and the shared creatives copy is
        # only a fallback for legacy version-less rows.
        ann = _creative_mod.annotation_for_report(
            conn, key, owner=owner, admin=admin) or {}
        vid = _creative_mod.annotation_scope_for_report(
            conn, key, owner=owner, admin=admin)
        if not ann:
            # No authorised result for this viewer: never substitute
            # another video's findings, and never authorise export
            # off them.
            missing.append(key + " (no authorised result)")
            continue
        if ann.get("status") != "human_verified" and not override:
            missing.append(key)
            continue
        # The selected version's own transcript — even when empty
        # (a silent clip has no speech). "No speech" and "no valid
        # result identity" are separate states: only a missing
        # identity falls back to the shared display copy.
        transcript = _drafts_mod.get_video_transcript(conn, vid) \
            if vid else shared_transcript
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
