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


def _ann_fingerprint(ann):
    """Stable snapshot of one annotation for change detection."""
    import json as _json
    try:
        return _json.dumps(ann, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return repr(sorted((ann or {}).items()))


def _finite_or_na(value):
    """Render guard: non-finite numbers print as n/a, never nan/inf."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        import math as _math
        if not _math.isfinite(value):
            return "n/a"
    return value


def check_reviews(conn):
    """Review-to-zero gate: every grounded Q&A answer must be reviewed
    before the one-pager may export."""
    from . import qa
    pending = qa.pending_count(conn)
    if pending:
        raise ExportBlocked(
            ["gate:review-to-zero: %d QA review(s) still pending" % pending])


def _export_card(conn, key, owner=None, admin=False, override=False):
    """One export card from a single consistent result snapshot.

    Returns (card, missing_entry): card is None when the key cannot
    export. Raises ExportBlocked when the annotation or transcript
    changes between the approval read and the content read — a
    concurrent correction must leave the export on the complete old
    approved version or refuse it, never mix old approval with new
    unreviewed content (override does not waive this).
    """
    from creative_intel import creative as _creative_mod
    from creative_intel import drafts as _drafts_mod
    row = conn.execute(
        "SELECT name, platform, transcript FROM creatives"
        " WHERE creative_key=?",
        (key,)).fetchone()
    if not row:
        return None, key + " (unknown)"
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
        return None, key + " (no authorised result)"
    if ann.get("status") != "human_verified" and not override:
        return None, key
    fingerprint = _ann_fingerprint(ann)
    # The selected version's own transcript — even when empty
    # (a silent clip has no speech). "No speech" and "no valid
    # result identity" are separate states: only a missing
    # identity falls back to the shared display copy.
    transcript = _drafts_mod.get_video_transcript(conn, vid) \
        if vid else shared_transcript
    # Re-read inside the same snapshot: a correction landing
    # between the approval check and the content read changes the
    # revision (every correction mints one), so any difference
    # proves the export would mix versions.
    ann_again = _creative_mod.annotation_for_report(
        conn, key, owner=owner, admin=admin) or {}
    transcript_again = _drafts_mod.get_video_transcript(conn, vid) \
        if vid else shared_transcript
    if _ann_fingerprint(ann_again) != fingerprint \
            or transcript_again != transcript:
        raise ExportBlocked(
            ["gate:export changed during read; retry: %s" % key])
    return {"creative_key": key, "name": name, "platform": platform,
            "hook_type": ann.get("hook_type", ""),
            "creator_vs_branded": ann.get("creator_vs_branded", ""),
            "transcript": transcript}, None


def build_one_pager(conn, creative_keys, benchmarks, override=False,
                    owner=None, admin=False):
    # Review-to-zero is enforced here (not just at the route), so no
    # caller — HTTP, worker, or test — can export past pending QA.
    # The card reads run in one IMMEDIATE transaction when the
    # caller is not already inside one: a concurrent correction
    # either lands fully before the export (seen as unapproved and
    # blocked) or waits until the reads finish. The per-card
    # re-read above still guards callers that arrived mid-transaction.
    own_txn = not conn.in_transaction
    missing = []
    cards = []
    try:
        if own_txn:
            conn.execute("BEGIN IMMEDIATE")
        check_reviews(conn)
        for key in creative_keys:
            card, miss = _export_card(conn, key, owner=owner,
                                      admin=admin, override=override)
            if card is not None:
                cards.append(card)
            elif miss:
                missing.append(miss)
        if own_txn:
            conn.commit()
    except Exception:
        if own_txn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
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
                     % (group, _finite_or_na(vals.get("cpa")),
                        _finite_or_na(vals.get("ctr")),
                        _finite_or_na(vals.get("spend"))))
    return {"markdown": "\n".join(lines), "cards": cards,
            "override": override, "missing": missing}
