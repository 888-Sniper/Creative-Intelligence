"""One-time presentation sample pack (``foap-presentation-pack-v1``).

Unlike the legacy ``load_demo_dataset`` filler (which re-inserts
whatever is missing on every call), this pack is imported EXACTLY
once per database under a persistent receipt in ``demo_packs``.
Every created row is tracked in ``demo_batch_members`` by stable
record identity — never by display name — so renames keep their
cleanup provenance and deleted rows are never resurrected.

All figures are synthetic demonstration data for fictional clients;
nothing here claims real Foap client performance.
"""

import datetime as _dt
import hashlib as _hashlib
import json as _json
import random as _random
import uuid as _uuid

PACK_KEY = "foap-presentation-pack-v1"
PACK_SOURCE = "sample"
PACK_DAYS = 180

STATUSES = ("not_added", "importing", "added", "partially_removed",
            "removed", "failed")

# Campaign: (slug, name, client, project, vertical, market, team,
#   objective, funnel, weight, base_ctr, conv_rate, revenue_per_conv,
#   spend_scale, ramp, meta_share)
# ramp: linear drift of volume across the window (+ improving,
# - declining). Profiles are deliberately varied (strong converter,
# high-attention/weak-sales, improver, decliner, big-spend mid-pack,
# underperformer).
CAMPAIGNS = (
    ("first-light", "First Light Ritual", "Avenlo Skin",
     "Avenlo Skin Launch", "Beauty", "United Kingdom", "Growth",
     "Conversions", "Lower", 0.13, 0.021, 0.055, 62.0, 1.0, 0.10,
     0.55),
    ("after-hours", "After Hours Reset", "Avenlo Skin",
     "Avenlo Skin Always On", "Beauty", "France", "Brand",
     "Conversions", "Lower", 0.10, 0.017, 0.042, 58.0, 0.8, 0.05,
     0.60),
    ("one-sip", "One Sip Ahead", "Brimora Coffee",
     "Brimora Coffee Trial", "Food & Beverage", "Malaysia",
     "Performance", "Conversions", "Lower", 0.11, 0.019, 0.048,
     24.0, 0.9, 0.55, 0.50),
    ("slow-mornings", "Slow Mornings Club", "Brimora Coffee",
     "Brimora Coffee Ritual", "Food & Beverage", "Singapore",
     "Brand", "Traffic", "Upper", 0.09, 0.034, 0.012, 22.0, 0.7,
     0.15, 0.45),
    ("make-room", "Make Room For Better", "Folden Home",
     "Folden Home Organisation", "Home & Living", "Australia",
     "Performance", "Conversions", "Lower", 0.10, 0.018, 0.050,
     74.0, 0.9, 0.20, 0.55),
    ("small-space", "Small Space, Big Possibilities", "Folden Home",
     "Folden Home Compact", "Home & Living", "Germany", "Growth",
     "Traffic", "Mid", 0.07, 0.011, 0.018, 40.0, 0.6, -0.05,
     0.50),
    ("commitment", "The 6AM Commitment", "Veyra Active",
     "Veyra Active Mornings", "Fitness", "United States", "Growth",
     "Conversions", "Lower", 0.16, 0.016, 0.038, 48.0, 1.4, 0.30,
     0.55),
    ("beyond-monday", "Move Beyond Monday", "Veyra Active",
     "Veyra Active Routine", "Fitness", "Canada", "Performance",
     "Conversions", "Mid", 0.09, 0.015, 0.035, 45.0, 0.8, -0.35,
     0.50),
    ("focus", "Find Your Focus", "Noven Audio",
     "Noven Audio Work", "Consumer Technology", "United Kingdom",
     "Performance", "Conversions", "Lower", 0.09, 0.020, 0.052,
     89.0, 0.9, 0.25, 0.60),
    ("switch-off", "Switch Off The City", "Noven Audio",
     "Noven Audio Commute", "Consumer Technology", "Australia",
     "Brand", "Traffic", "Upper", 0.06, 0.026, 0.020, 85.0, 0.6,
     0.10, 0.45),
)

# Creative: (slug, name, format, secs, hook, modality, style, mode,
#   brand_s, product_s, platform_bias, weight)
# platform_bias shifts performance toward one platform so Meta and
# TikTok have different winning creatives.
CREATIVES = (
    # 01 First Light Ritual (skincare)
    ("mirror-test", "The Mirror Test", "9:16 Video", 18, "question",
     "spoken", "ugc", "creator", 3.0, 2.0, "meta", 0.40),
    ("three-steps", "Morning In Three Steps", "9:16 Video", 24,
     "demo_open", "visual", "product_demo", "creator", 4.0, 1.5,
     "tiktok", 0.35),
    ("texture", "Texture In Motion", "1:1 Video", 15,
     "pattern_interrupt", "visual", "cinematic", "branded", 2.0,
     5.0, "meta", 0.25),
    # 02 After Hours Reset (skincare)
    ("commute-calm", "From Commute To Calm", "9:16 Video", 21,
     "story", "spoken", "ugc", "creator", 5.0, 8.0, "tiktok",
     0.40),
    ("evening-shelf", "The Evening Shelf", "4:5 Video", 27,
     "social_proof", "spoken", "testimonial", "creator", 6.0, 4.0,
     "meta", 0.35),
    ("one-routine", "One Routine, One Week", "16:9 Video", 75,
     "demo_open", "visual", "product_demo", "branded", 8.0, 3.0,
     "meta", 0.25),
    # 03 One Sip Ahead (coffee)
    ("first-meeting", "Before The First Meeting", "9:16 Video", 14,
     "bold_claim", "text", "product_demo", "creator", 2.5, 1.0,
     "tiktok", 0.40),
    ("desk-brew", "The Desk-Side Brew", "9:16 Video", 19,
     "demo_open", "visual", "ugc", "hybrid", 3.5, 2.0, "meta",
     0.35),
    ("thirty-seconds", "Thirty Seconds To Coffee", "1:1 Video", 30,
     "offer", "text", "montage", "branded", 4.0, 6.0, "tiktok",
     0.25),
    # 04 Slow Mornings Club (coffee)
    ("unrushed", "Weekend, Unrushed", "9:16 Video", 33,
     "story", "visual", "cinematic", "creator", 6.0, 10.0,
     "tiktok", 0.40),
    ("two-mugs", "Two Mugs, One Morning", "4:5 Video", 22,
     "social_proof", "spoken", "talking_head", "creator", 5.0,
     7.0, "meta", 0.35),
    ("steam", "Steam And Stillness", "16:9 Video", 45,
     "pattern_interrupt", "visual", "cinematic", "branded", 7.0,
     12.0, "tiktok", 0.25),
    # 05 Make Room For Better (home)
    ("drawer-reset", "The Drawer Reset", "9:16 Video", 26,
     "demo_open", "visual", "product_demo", "creator", 4.0, 2.0,
     "meta", 0.40),
    ("one-shelf", "One Shelf, Three Uses", "1:1 Video", 31,
     "question", "spoken", "ugc", "hybrid", 5.0, 3.0, "tiktok",
     0.35),
    ("cleaner-start", "A Cleaner Start", "4:5 Video", 20,
     "bold_claim", "text", "montage", "branded", 3.0, 5.0,
     "meta", 0.25),
    # 06 Small Space, Big Possibilities (home)
    ("corner", "A Corner Reimagined", "16:9 Video", 38,
     "demo_open", "visual", "product_demo", "creator", 6.0, 4.0,
     "meta", 0.40),
    ("room-more", "Room For One More", "9:16 Video", 17,
     "question", "spoken", "ugc", "creator", 3.0, 2.0, "tiktok",
     0.35),
    ("checklist", "The Apartment Checklist", "1:1 Video", 29,
     "offer", "text", "slideshow_static", "branded", 5.0, 8.0,
     "meta", 0.25),
    # 07 The 6AM Commitment (fitness)
    ("alarm", "Alarm To Action", "9:16 Video", 16,
     "pattern_interrupt", "visual", "ugc", "creator", 2.5, 1.5,
     "tiktok", 0.40),
    ("ten-minutes", "The First Ten Minutes", "9:16 Video", 42,
     "demo_open", "spoken", "product_demo", "hybrid", 6.0, 3.0,
     "meta", 0.35),
    ("your-pace", "Your Pace, Your Start", "4:5 Video", 24,
     "social_proof", "spoken", "testimonial", "creator", 5.0,
     9.0, "tiktok", 0.25),
    # 08 Move Beyond Monday (fitness)
    ("midweek", "The Midweek Reset", "9:16 Video", 23,
     "question", "spoken", "talking_head", "creator", 4.0, 6.0,
     "meta", 0.40),
    ("train-where", "Train Where You Are", "1:1 Video", 28,
     "demo_open", "visual", "ugc", "creator", 5.0, 2.0,
     "tiktok", 0.35),
    ("small-wins", "Small Wins, Daily", "9:16 Video", 19,
     "story", "text", "montage", "branded", 3.0, 4.0, "meta",
     0.25),
    # 09 Find Your Focus (headphones)
    ("desk-noise", "Desk Noise, Meet Silence", "16:9 Video", 32,
     "pattern_interrupt", "visual", "product_demo", "branded",
     5.0, 7.0, "meta", 0.40),
    ("focus-session", "Inside A Focus Session", "1:1 Video", 36,
     "demo_open", "spoken", "screen_recording", "hybrid", 7.0,
     5.0, "tiktok", 0.35),
    ("one-button", "One Button, Clearer Work", "9:16 Video", 18,
     "bold_claim", "text", "ugc", "creator", 3.0, 2.0, "meta",
     0.25),
    # 10 Switch Off The City (headphones)
    ("own-world", "Commute In Your Own World", "9:16 Video", 25,
     "story", "visual", "cinematic", "creator", 4.0, 6.0,
     "tiktok", 0.40),
    ("platform-test", "The Train-Platform Test", "9:16 Video", 21,
     "demo_open", "spoken", "product_demo", "creator", 5.0, 3.0,
     "meta", 0.35),
    ("street-sofa", "From Street To Sofa", "4:5 Video", 34,
     "question", "spoken", "testimonial", "branded", 6.0, 9.0,
     "tiktok", 0.25),
)

SUBJECT_BY_INDEX = ("skincare", "skincare", "coffee", "coffee",
                    "home", "home", "fitness", "fitness",
                    "headphones", "headphones")


def creative_key(campaign_idx, creative_idx):
    slug = CAMPAIGNS[campaign_idx][0]
    cslug = CREATIVES[campaign_idx * 3 + creative_idx][0]
    return "smp-%s-%s" % (slug, cslug)


def campaign_id(campaign_idx):
    return "SMP-%02d" % (campaign_idx + 1)


def _utcnow():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _receipt_row(conn):
    row = conn.execute(
        "SELECT pack_key, batch_id, workspace, imported_by, imported_at,"
        " data_start, data_end, status, counts_json, removed_at"
        " FROM demo_packs WHERE pack_key=?", (PACK_KEY,)).fetchone()
    if not row:
        return None
    keys = ("pack_key", "batch_id", "workspace", "imported_by",
            "imported_at", "data_start", "data_end", "status",
            "counts_json", "removed_at")
    return dict(zip(keys, row))


def _track(conn, batch_id, table_name, record_key):
    conn.execute(
        "INSERT OR IGNORE INTO demo_batch_members"
        " (batch_id, table_name, record_key) VALUES (?, ?, ?)",
        (batch_id, table_name, str(record_key)))


def _member_keys(conn, batch_id, table_name):
    return [r[0] for r in conn.execute(
        "SELECT record_key FROM demo_batch_members"
        " WHERE batch_id=? AND table_name=?", (batch_id, table_name))]


def remaining_counts(conn, batch_id):
    """Live counts of surviving pack rows (edits preserved, deletes kept)."""
    ads = conn.execute(
        "SELECT COUNT(*) FROM ads WHERE import_id=?",
        (batch_id,)).fetchone()[0]
    camps = conn.execute(
        "SELECT COUNT(DISTINCT campaign_id) FROM ads WHERE import_id=?",
        (batch_id,)).fetchone()[0]
    keys = _member_keys(conn, batch_id, "creatives")
    creatives = conn.execute(
        "SELECT COUNT(*) FROM creatives WHERE creative_key IN (%s)" % (
            ",".join("?" * len(keys)) or "SELECT '' WHERE 0"),
        keys).fetchone()[0] if keys else 0
    out = {"ads_rows": ads, "campaigns": camps, "creatives": creatives}
    for table in ("annotations", "retention", "media", "saved_views",
                  "analyst_conversations", "analyst_messages",
                  "analyst_findings", "sample_files"):
        mkeys = _member_keys(conn, batch_id, table)
        if not mkeys:
            out[table] = 0
            continue
        if table == "annotations":
            col, tname = "creative_key", "annotations"
        elif table == "retention":
            out[table] = conn.execute(
                "SELECT COUNT(*) FROM retention WHERE creative_key IN (%s)"
                % ",".join("?" * len(mkeys)), mkeys).fetchone()[0]
            continue
        elif table == "media":
            col, tname = "id", "media"
        elif table == "saved_views":
            col, tname = "id", "saved_views"
        elif table == "analyst_conversations":
            col, tname = "id", "analyst_conversations"
        elif table == "analyst_messages":
            out[table] = conn.execute(
                "SELECT COUNT(*) FROM analyst_messages"
                " WHERE conversation_id IN (%s)"
                % ",".join("?" * len(mkeys)), mkeys).fetchone()[0]
            continue
        elif table == "analyst_findings":
            col, tname = "id", "analyst_findings"
        else:
            col, tname = "file_key", "sample_files"
        try:
            out[table] = conn.execute(
                "SELECT COUNT(*) FROM %s WHERE %s IN (%s)"
                % (tname, col, ",".join("?" * len(mkeys))),
                mkeys).fetchone()[0]
        except Exception:
            out[table] = 0
    return out


def pack_status(conn):
    """Receipt + live remaining counts; derives partially_removed."""
    receipt = _receipt_row(conn)
    if receipt is None:
        return {"status": "not_added", "pack_key": PACK_KEY,
                "receipt": None, "remaining": {}, "imported": {},
                "campaigns": []}
    try:
        imported = _json.loads(receipt["counts_json"] or "{}")
    except ValueError:
        imported = {}
    remaining = remaining_counts(conn, receipt["batch_id"])
    status = receipt["status"]
    if status == "added":
        imp_ads = (imported.get("ads_rows") or 0)
        if imp_ads and remaining.get("ads_rows", 0) < imp_ads:
            status = "partially_removed"
            conn.execute("UPDATE demo_packs SET status=? WHERE pack_key=?",
                         (status, PACK_KEY))
            conn.commit()
            receipt["status"] = status
    campaigns = [
        {"campaign_id": r[0], "campaign": r[1]}
        for r in conn.execute(
            "SELECT campaign_id, campaign FROM ads WHERE import_id=?"
            " GROUP BY campaign_id ORDER BY campaign",
            (receipt["batch_id"],)).fetchall()]
    return {"status": status, "pack_key": PACK_KEY, "receipt": receipt,
            "remaining": remaining, "imported": imported,
            "campaigns": campaigns}


def preview(conn, workspace=""):
    """What Add Demo Data Once will create (no writes)."""
    legacy_campaigns = conn.execute(
        "SELECT COUNT(DISTINCT campaign) FROM ads WHERE source='demo'"
    ).fetchone()[0]
    legacy_creatives = conn.execute(
        "SELECT COUNT(*) FROM creatives WHERE creative_key LIKE 'demo-%'"
    ).fetchone()[0]
    return {
        "pack_key": PACK_KEY,
        "workspace": workspace,
        "synthetic": True,
        "campaigns": [
            {"name": c[1], "client": c[2], "project": c[3],
             "vertical": c[4], "market": c[5], "team": c[6],
             "creatives": [CREATIVES[i * 3 + j][1] for j in range(3)]}
            for i, c in enumerate(CAMPAIGNS)],
        "totals": {"campaigns": len(CAMPAIGNS), "creatives": 30,
                   "days": PACK_DAYS,
                   "saved_views": 10, "conversations": 6,
                   "findings": "10+", "reports": 6, "workbooks": 3},
        "legacy_demo": {"campaigns": legacy_campaigns,
                        "creatives": legacy_creatives},
        "replenish": False,
    }


def _date_range():
    end = _dt.date.today() - _dt.timedelta(days=1)
    start = end - _dt.timedelta(days=PACK_DAYS - 1)
    days = [(start + _dt.timedelta(days=i)).isoformat()
            for i in range(PACK_DAYS)]
    return start.isoformat(), end.isoformat(), days


def _import_ads_rows(conn, batch_id, day_list):
    """Deterministic daily facts via the real upsert path."""
    from creative_intel import ingest as _ingest
    rng = _random.Random(20260913)
    rows = []
    for ci, camp in enumerate(CAMPAIGNS):
        (slug, name, client, project, vertical, market, team,
         objective, funnel, weight, ctr, cvr, rpc, spend_scale,
         ramp, meta_share) = camp
        cid = campaign_id(ci)
        for plat, share in (("meta", meta_share),
                            ("tiktok", 1.0 - meta_share)):
            for day_i, iso in enumerate(day_list):
                t = day_i / (PACK_DAYS - 1)
                # Campaign flight: staggered starts/ends so status
                # and coverage differ honestly across the pack.
                start_off = (ci * 7) % 30
                length = PACK_DAYS - start_off - ((ci * 13) % 20)
                if day_i < start_off or day_i >= start_off + length:
                    continue
                drift = 1.0 + ramp * (t - 0.5)
                week = 1.0 + 0.18 * (1 if (day_i % 7) < 5 else -1)
                base_impr = 42000.0 * weight * share * drift * week
                for ki in range(3):
                    spec = CREATIVES[ci * 3 + ki]
                    cw = spec[11]
                    bias = 1.18 if spec[10] == plat else 0.86
                    impr = base_impr * cw * 3 * bias
                    impr *= 1.0 + rng.uniform(-0.16, 0.16)
                    clicks = impr * ctr * bias
                    clicks *= 1.0 + rng.uniform(-0.14, 0.14)
                    spend = (520.0 * weight * share * spend_scale
                             * drift * cw * 3)
                    spend *= 1.0 + rng.uniform(-0.12, 0.12)
                    conv = clicks * cvr * bias
                    conv *= 1.0 + rng.uniform(-0.12, 0.12)
                    revenue = conv * rpc
                    revenue *= 1.0 + rng.uniform(-0.10, 0.10)
                    views = impr * (0.30 + 0.12 * (ki == 1))
                    v25 = views * 0.72
                    v50 = views * 0.48
                    v75 = views * 0.30
                    v100 = views * 0.18
                    rows.append({
                        "platform": plat, "source": PACK_SOURCE,
                        "campaign": name, "adset": "%s %s" % (
                            plat.title(), team),
                        "ad_name": spec[1],
                        "creative_key": creative_key(ci, ki),
                        "spend": round(spend, 2),
                        "impressions": max(0, int(impr)),
                        "clicks": max(0, int(clicks)),
                        "conversions": round(max(0.0, conv), 1),
                        "video_views": max(0, int(views)),
                        "views_25": max(0, int(v25)),
                        "views_50": max(0, int(v50)),
                        "views_75": max(0, int(v75)),
                        "views_100": max(0, int(v100)),
                        "video_starts": max(0, int(impr * 0.42)),
                        "views_2s": max(0, int(impr * 0.36)),
                        "views_3s": max(0, int(impr * 0.31)),
                        "views_6s": max(0, int(impr * 0.24)),
                        "link_clicks": max(0, int(clicks * 0.7)),
                        "client": client, "project": project,
                        "team": team, "vertical": vertical,
                        "market": market, "objective": objective,
                        "funnel_stage": funnel, "date": iso,
                        "revenue": round(max(0.0, revenue), 2),
                        "campaign_id": cid, "currency": "USD",
                        "format": spec[2], "import_id": batch_id,
                    })
    return _ingest.upsert_rows(conn, rows)


def _pack_annotation(ci, ki):
    from creative_intel import creative as _creative
    spec = CREATIVES[ci * 3 + ki]
    (_slug, _name, _fmt, secs, hook, modality, style, mode,
     brand_s, product_s) = spec[0], spec[1], spec[2], spec[3], \
        spec[4], spec[5], spec[6], spec[7], spec[8], spec[9]
    ann = _creative.blank_annotation()
    ann.update({"hook_type": hook, "hook_modality": modality,
                "hook_confidence": 0.85,
                "creator_vs_branded": mode,
                "creator_confidence": 0.85,
                "edit_style": style, "edit_confidence": 0.8,
                "duration_s": float(secs),
                "pace_cuts_per_min": 8.0, "status": "auto",
                "brand_seconds": [{"start_s": brand_s,
                                   "end_s": round(brand_s + 2.0, 1)}],
                "product_seconds": [{"start_s": product_s,
                                     "end_s": round(product_s + 3.0,
                                                   1)}],
                "logo_seconds": [{"start_s": round(brand_s + 0.5, 1),
                                  "end_s": round(brand_s + 1.5, 1)}]})
    hook_end = min(3.0, secs)
    ann["structure"] = {
        slot: {"start_s": 0.0,
               "end_s": hook_end if slot == "hook" else float(secs),
               "confidence": 0.85}
        for slot in _creative.STRUCTURE_SLOTS}
    return ann


def _pack_retention_points(secs, variant):
    import math as _math
    steps = 9
    decay = 1.9 + 0.5 * (variant % 3)
    return [(round(secs * i / (steps - 1), 1),
             round(100.0 * _math.exp(-decay * i / (steps - 1)), 1))
            for i in range(steps)]


def import_pack(conn, imported_by="", workspace="", media_dir=None):
    """One-time import. Idempotent: a receipt row means never re-add.

    Returns {"receipt": ..., "created": bool, "counts": {...}}.
    Concurrent callers: exactly one INSERTs the receipt; the loser
    sees the row and returns it without writing data.
    A receipt in failed status allows one safe retry (same batch,
    upserts only — edits elsewhere untouched, deletes not restored).
    """
    from creative_intel import creative as _creative
    from creative_intel import ingest as _ingest
    from creative_intel import media as _media
    from creative_intel import demo_art as _art
    from ci_backend.actions import _media_dir

    existing = _receipt_row(conn)
    if existing is not None and existing["status"] != "failed":
        st = pack_status(conn)
        st["created"] = False
        return st
    if existing is not None:
        batch_id = existing["batch_id"]
        start, end = existing["data_start"], existing["data_end"]
        day_list = [(start and _dt.date.fromisoformat(start)
                     + _dt.timedelta(days=i)).isoformat()
                    for i in range(PACK_DAYS)] if start else []
        if not day_list:
            _, _, day_list = _date_range()
        conn.execute("UPDATE demo_packs SET status='importing'"
                     " WHERE pack_key=?", (PACK_KEY,))
        conn.commit()
    else:
        batch_id = "smp-%s" % _uuid.uuid4().hex[:12]
        start, end, day_list = _date_range()
        try:
            conn.execute(
                "INSERT INTO demo_packs (pack_key, batch_id, workspace,"
                " imported_by, imported_at, data_start, data_end,"
                " status, counts_json) VALUES (?, ?, ?, ?, ?, ?, ?,"
                " 'importing', '{}')",
                (PACK_KEY, batch_id, workspace, imported_by,
                 _utcnow(), start, end))
            conn.commit()
        except Exception:
            # Lost the race: another request is importing (or
            # finished). Return its receipt, write nothing.
            conn.rollback()
            st = pack_status(conn)
            st["created"] = False
            return st

    counts = {}
    try:
        res = _import_ads_rows(conn, batch_id, day_list)
        counts["ads_rows"] = res["inserted"] + res["updated"]
        _ingest.record_import(
            conn, {"filename": "sample-pack-v1", "mapping": "generated",
                   "unmapped": []}, "meta", PACK_SOURCE,
            filename="sample-pack-v1", imported_by=imported_by,
            counts={"imported": counts["ads_rows"], "quarantined": 0})
        # Creative rows (stable keys; never overwrite user edits on
        # retry — INSERT OR IGNORE only fills gaps from a failure).
        n_creatives = 0
        for ci in range(len(CAMPAIGNS)):
            for ki in range(3):
                key = creative_key(ci, ki)
                spec = CREATIVES[ci * 3 + ki]
                cur = conn.execute(
                    "INSERT OR IGNORE INTO creatives (creative_key,"
                    " platform, name, duration_s, status, transcript,"
                    " pipeline_json) VALUES (?, 'meta/tiktok', ?, ?,"
                    " 'auto', '', ?)",
                    (key, spec[1], float(spec[3]),
                     _json.dumps({"provenance": "sample",
                                  "pack_key": PACK_KEY,
                                  "batch_id": batch_id})))
                if cur.rowcount:
                    n_creatives += 1
                _track(conn, batch_id, "creatives", key)
                _creative.save_annotation(conn, key,
                                          _pack_annotation(ci, ki))
                _track(conn, batch_id, "annotations", key)
                pts = _pack_retention_points(spec[3], ki)
                conn.execute(
                    "INSERT OR REPLACE INTO retention (creative_key,"
                    " t_sec, retention_pct, source) VALUES %s" % (
                        ",".join(["(?, ?, ?, 'sample-curve')"]
                                 * len(pts),)),
                    [v for p in pts for v in (key, p[0], p[1])])
                _track(conn, batch_id, "retention", key)
        counts["creatives"] = len(
            _member_keys(conn, batch_id, "creatives"))
        counts["campaigns"] = len(CAMPAIGNS)
        # Distinct per-subject artwork (local bytes, no external URLs).
        store = _media_dir(media_dir)
        _media.ensure_schema(conn)
        n_media = 0
        for ci in range(len(CAMPAIGNS)):
            subject = SUBJECT_BY_INDEX[ci]
            for ki in range(3):
                key = creative_key(ci, ki)
                have = conn.execute(
                    "SELECT 1 FROM media WHERE creative_key=?"
                    " AND mime LIKE 'image/%%' LIMIT 1",
                    (key,)).fetchone()
                if not have:
                    rec = _media.save_media_bytes(
                        conn, store, key, key + ".png",
                        _art.art_for_subject(subject, ki))
                    _track(conn, batch_id, "media", rec["id"])
                    n_media += 1
        counts["media"] = n_media
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.execute("UPDATE demo_packs SET status='failed',"
                     " counts_json=? WHERE pack_key=?",
                     (_json.dumps({"error": str(exc)}), PACK_KEY))
        conn.commit()
        raise
    return {"batch_id": batch_id, "phase": "core", "counts": counts,
            "data_start": start, "data_end": end,
            "day_list": day_list}


SAMPLE_VIEWS = (
    ("Sample \u2014 Benchmark: Platform ROAS",
     {"filters": {}, "kpi": "roas", "view": "benchmark",
      "benchmark": "platform", "benchmark_scope": "filters",
      "rank_by": "roas"}),
    ("Sample \u2014 Benchmark: Hook CTR",
     {"filters": {}, "kpi": "ctr", "view": "benchmark",
      "benchmark": "hook_type", "benchmark_scope": "filters",
      "rank_by": "ctr"}),
    ("Sample \u2014 Benchmark: Creator Vs Branded CPA",
     {"filters": {"vertical": ["Beauty"]}, "kpi": "cpa",
      "view": "benchmark", "benchmark": "creator_vs_branded",
      "benchmark_scope": "global", "rank_by": "cpa"}),
    ("Sample \u2014 Benchmark: Format CPM",
     {"filters": {"market": ["United Kingdom"]}, "kpi": "cpm",
      "view": "benchmark", "benchmark": "format",
      "benchmark_scope": "filters", "rank_by": "cpm"}),
    ("Sample \u2014 Benchmark: Market CPA",
     {"filters": {}, "kpi": "cpa", "view": "benchmark",
      "benchmark": "market", "benchmark_scope": "global",
      "rank_by": "cpa"}),
    ("Sample \u2014 Benchmark: Objective ROAS",
     {"filters": {"platform": ["meta"]}, "kpi": "roas",
      "view": "benchmark", "benchmark": "objective",
      "benchmark_scope": "filters", "rank_by": "roas"}),
    ("Sample \u2014 Compare: Four Contrasts (ROAS)",
     {"filters": {"campaign": ["First Light Ritual",
                               "Slow Mornings Club",
                               "The 6AM Commitment",
                               "Small Space, Big Possibilities"]},
      "kpi": "roas", "view": "compare", "benchmark": "campaign",
      "benchmark_scope": "filters", "rank_by": "roas"}),
    ("Sample \u2014 Compare: Avenlo Skin (CTR)",
     {"filters": {"client": ["Avenlo Skin"]}, "kpi": "ctr",
      "view": "compare", "benchmark": "campaign",
      "benchmark_scope": "filters", "rank_by": "ctr"}),
    ("Sample \u2014 Compare: Coffee Creatives (CTR)",
     {"filters": {"campaign": ["One Sip Ahead",
                               "Slow Mornings Club"]},
      "kpi": "ctr", "view": "compare", "benchmark": "hook_type",
      "benchmark_scope": "filters", "rank_by": "ctr"}),
    ("Sample \u2014 Compare: Home Markets (CPA)",
     {"filters": {"campaign": ["Make Room For Better",
                               "Small Space, Big Possibilities"]},
      "kpi": "cpa", "view": "compare", "benchmark": "platform",
      "benchmark_scope": "global", "rank_by": "cpa"}),
)

SAMPLE_QUESTIONS = (
    ("Which campaign has the strongest ROAS in the selected period?",
     {}, "conversions", "en"),
    ("Which creative gets clicks but converts less efficiently?",
     {}, "conversions", "en"),
    ("How does Meta compare with TikTok for Avenlo Skin?",
     {"client": ["Avenlo Skin"]}, "reach", "en"),
    ("Which campaign improved most against the previous period?",
     {}, "conversions", "en"),
    ("What should we test next for Folden Home?",
     {"client": ["Folden Home"]}, "conversions", "en"),
    ("Which hook types drive the highest CTR?",
     {"platform": ["tiktok"]}, "reach", "en"),
)


def _store_sample_file(conn, store, batch_id, name, fmt, mime, blob):
    import hashlib as _hl
    import os as _os
    digest = _hl.sha256(blob).hexdigest()
    rel = _os.path.join("sample", batch_id, name)
    dest = _os.path.join(store, rel)
    _os.makedirs(_os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(blob)
    file_key = "%s/%s" % (batch_id, name)
    conn.execute(
        "INSERT OR REPLACE INTO sample_files (file_key, batch_id, name,"
        " format, mime, bytes, sha256, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (file_key, batch_id, name, fmt, mime, len(blob), digest,
         _utcnow()))
    _track(conn, batch_id, "sample_files", file_key)
    return file_key


def finalize_pack(conn, batch_id, imported_by="", media_dir=None,
                  core_counts=None):
    """Showcase layer: views, conversations, files. Runs once per
    receipt; every insert is skip-if-present so a failed-import retry
    never duplicates rows or overwrites user edits."""
    import base64 as _b64
    from ci_backend.actions import _media_dir, save_view
    from creative_intel import analyst_chat as _chat
    from creative_intel import benchmarks as _bench
    from creative_intel import analyst_workbook as _wb

    counts = dict(core_counts or {})
    store = _media_dir(media_dir)
    # 6 benchmark + 4 compare setups through the real save path.
    n_views = 0
    for name, state in SAMPLE_VIEWS:
        present = conn.execute(
            "SELECT id FROM saved_views WHERE name=?", (name,)).fetchone()
        if present:
            _track(conn, batch_id, "saved_views", present[0])
            continue
        rec = save_view(conn, name, dict(state))
        _track(conn, batch_id, "saved_views", rec["id"])
        n_views += 1
    counts["saved_views"] = n_views
    # 6 sample conversations with real computed answers; findings
    # persist with evidence exactly like live turns.
    n_convs = 0
    for question, scope, objective, language in SAMPLE_QUESTIONS:
        present = conn.execute(
            "SELECT id FROM analyst_conversations"
            " WHERE owner_employee_id=? AND title=?"
            " AND scope_json=? LIMIT 1",
            (imported_by, question[:60], _json.dumps(dict(scope))),
        ).fetchone()
        if present:
            conv_id = present[0]
        else:
            turn = _chat.answer_turn(
                conn, imported_by, question, None, scope=dict(scope),
                objective=objective, language=language)
            conv_id = turn["conversation_id"]
            n_convs += 1
        _track(conn, batch_id, "analyst_conversations", conv_id)
        for (mid,) in conn.execute(
                "SELECT id FROM analyst_messages WHERE conversation_id=?",
                (conv_id,)):
            _track(conn, batch_id, "analyst_messages", conv_id)
        for (fid,) in conn.execute(
                "SELECT id FROM analyst_findings WHERE conversation_id=?",
                (conv_id,)):
            _track(conn, batch_id, "analyst_findings", fid)
    counts["conversations"] = n_convs
    counts["findings"] = len(_member_keys(conn, batch_id,
                                          "analyst_findings"))
    # 6 genuine reports through the real export path (2 per format
    # across one-pager, csv, xlsx) + 3 workbook configurations.
    report_jobs = (
        ("Sample Report \u2014 Pack Overview (Markdown)", "one-pager",
         None, ["roas", "ctr"]),
        ("Sample Report \u2014 Avenlo Skin (Markdown)", "one-pager",
         ["First Light Ritual", "After Hours Reset"], ["ctr", "cpa"]),
        ("Sample Report \u2014 Pack Overview (CSV)", "csv", None,
         ["roas", "ctr", "cpa", "spend"]),
        ("Sample Report \u2014 Client Comparison (CSV)",
         "csv", None, ["ctr", "cpa", "conversions"]),
        ("Sample Report \u2014 Pack Overview (Excel)", "xlsx", None,
         ["roas", "cpa"]),
        ("Sample Report \u2014 Fitness Push (Excel)", "xlsx",
         ["The 6AM Commitment", "Move Beyond Monday"], ["ctr", "cpa"]),
    )
    ext_by_fmt = {"one-pager": ("md", "text/markdown"),
                  "csv": ("csv", "text/csv"),
                  "xlsx": ("xlsx", "application/vnd.openxmlformats-"
                           "officedocument.spreadsheetml.sheet")}
    n_reports = 0
    for title, fmt, camps, kpis in report_jobs:
        fname = "%s.%s" % (title.replace(" \u2014 ", " - "),
                           ext_by_fmt[fmt][0])
        present = conn.execute(
            "SELECT 1 FROM sample_files WHERE file_key=?",
            ("%s/%s" % (batch_id, fname),)).fetchone()
        if present:
            continue
        rep = _bench.build_report(conn, camps, kpis, "platform", fmt,
                                  filters={}, benchmark_scope="filters",
                                  rank_by=kpis[0])
        if fmt == "one-pager":
            blob = ("> Sample Data \u2014 synthetic demonstration figures,"
                    " not real client performance.\n\n"
                    + rep["markdown"]).encode("utf-8")
        elif fmt == "csv":
            blob = rep["csv"].encode("utf-8")
        else:
            blob = _b64.b64decode(rep["xlsx_b64"])
        _store_sample_file(conn, store, batch_id, fname, fmt,
                           ext_by_fmt[fmt][1], blob)
        n_reports += 1
    counts["reports"] = n_reports
    n_books = 0
    for title in ("Sample Workbook \u2014 Pack Overview",
                  "Sample Workbook \u2014 Avenlo Skin",
                  "Sample Workbook \u2014 Folden Home"):
        fname = "%s.xlsx" % title.replace(" \u2014 ", " - ")
        present = conn.execute(
            "SELECT 1 FROM sample_files WHERE file_key=?",
            ("%s/%s" % (batch_id, fname),)).fetchone()
        if present:
            continue
        blob = _wb.build_blank_workbook(
            cover={"name": title,
                   "description": "Sample configuration over the"
                   " one-time presentation pack (%s). Synthetic"
                   " demonstration data." % PACK_KEY,
                   "modules": ["Metrics", "Benchmarks"],
                   "kpis": ["ROAS", "CTR", "CPA"]})
        _store_sample_file(
            conn, store, batch_id, fname, "workbook",
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet", blob)
        n_books += 1
    counts["workbooks"] = n_books
    if not counts.get("ads_rows"):
        counts["ads_rows"] = conn.execute(
            "SELECT COUNT(*) FROM ads WHERE import_id=?",
            (batch_id,)).fetchone()[0]
    if not counts.get("campaigns"):
        counts["campaigns"] = conn.execute(
            "SELECT COUNT(DISTINCT campaign_id) FROM ads WHERE import_id=?",
            (batch_id,)).fetchone()[0]
    if not counts.get("creatives"):
        counts["creatives"] = len(
            _member_keys(conn, batch_id, "creatives"))
    receipt = _receipt_row(conn)
    merged = dict(_json.loads(receipt["counts_json"] or "{}"))
    merged.update(counts)
    conn.execute("UPDATE demo_packs SET status='added', counts_json=?"
                 " WHERE pack_key=?",
                 (_json.dumps(merged), PACK_KEY))
    conn.commit()
    return {"created": True, "counts": merged,
            "receipt": _receipt_row(conn)}


def campaign_impact(conn, batch_id, campaign_id):
    """Exact affected-record counts before a campaign delete."""
    rows = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT creative_key) FROM ads"
        " WHERE import_id=? AND campaign_id=?",
        (batch_id, campaign_id)).fetchone()
    name = conn.execute(
        "SELECT campaign FROM ads WHERE import_id=? AND campaign_id=?"
        " LIMIT 1", (batch_id, campaign_id)).fetchone()
    keys = [r[0] for r in conn.execute(
        "SELECT DISTINCT creative_key FROM ads WHERE import_id=?"
        " AND campaign_id=?", (batch_id, campaign_id))]
    views = []
    for (vid, vname, vstate) in conn.execute(
            "SELECT id, name, state_json FROM saved_views"):
        try:
            filt = (_json.loads(vstate or "{}").get("filters") or {})
            camps = filt.get("campaign") or []
        except ValueError:
            camps = []
        if name and name[0] in camps and str(vid) in _member_keys(
                conn, batch_id, "saved_views"):
            views.append({"id": vid, "name": vname})
    return {"campaign_id": campaign_id,
            "campaign": name[0] if name else "",
            "ads_rows": rows[0], "creatives": rows[1],
            "creative_keys": keys, "batch_views": views}


def delete_campaign(conn, batch_id, campaign_id):
    """Normal campaign delete, scoped to the pack by stable id."""
    impact = campaign_impact(conn, batch_id, campaign_id)
    if not impact["campaign"]:
        raise ValueError("no sample campaign %r" % (campaign_id,))
    keys = impact["creative_keys"]
    conn.execute("DELETE FROM ads WHERE import_id=? AND campaign_id=?",
                 (batch_id, campaign_id))
    if keys:
        q = ",".join("?" * len(keys))
        conn.execute("DELETE FROM creatives WHERE creative_key IN (%s)"
                     % q, keys)
        conn.execute("DELETE FROM annotations WHERE creative_key IN (%s)"
                     % q, keys)
        conn.execute("DELETE FROM retention WHERE creative_key IN (%s)"
                     % q, keys)
        for (mid, stored) in conn.execute(
                "SELECT id, stored_name FROM media"
                " WHERE creative_key IN (%s)" % q, keys):
            _delete_media_file(conn, mid, stored)
        for view in impact["batch_views"]:
            conn.execute("DELETE FROM saved_views WHERE id=?",
                         (view["id"],))
    conn.commit()
    return impact


def _delete_media_file(conn, media_id, stored_name):
    import os as _os
    from ci_backend.actions import _media_dir
    conn.execute("DELETE FROM media WHERE id=?", (media_id,))
    try:
        path = _os.path.join(_media_dir(None), stored_name or "")
        if stored_name and _os.path.isfile(path):
            _os.remove(path)
    except OSError:
        pass


def creative_impact(conn, batch_id, creative_key):
    rows = conn.execute(
        "SELECT COUNT(*) FROM ads WHERE import_id=?"
        " AND creative_key=?", (batch_id, creative_key)).fetchone()[0]
    name = conn.execute(
        "SELECT name FROM creatives WHERE creative_key=?",
        (creative_key,)).fetchone()
    return {"creative_key": creative_key,
            "name": name[0] if name else "", "ads_rows": rows}


def delete_creative(conn, batch_id, creative_key):
    impact = creative_impact(conn, batch_id, creative_key)
    members = _member_keys(conn, batch_id, "creatives")
    if creative_key not in members:
        raise ValueError("not a sample creative: %r" % (creative_key,))
    conn.execute("DELETE FROM ads WHERE import_id=? AND creative_key=?",
                 (batch_id, creative_key))
    conn.execute("DELETE FROM creatives WHERE creative_key=?",
                 (creative_key,))
    conn.execute("DELETE FROM annotations WHERE creative_key=?",
                 (creative_key,))
    conn.execute("DELETE FROM retention WHERE creative_key=?",
                 (creative_key,))
    for (mid, stored) in conn.execute(
            "SELECT id, stored_name FROM media WHERE creative_key=?",
            (creative_key,)):
        _delete_media_file(conn, mid, stored)
    conn.commit()
    return impact


def rename_campaign(conn, batch_id, campaign_id, name):
    name = str(name or "").strip()
    if not name or len(name) > 120:
        raise ValueError("campaign name must be 1-120 characters")
    cur = conn.execute("UPDATE ads SET campaign=? WHERE import_id=?"
                       " AND campaign_id=?", (name, batch_id,
                                              campaign_id))
    conn.commit()
    if not cur.rowcount:
        raise ValueError("no sample campaign %r" % (campaign_id,))
    return {"campaign_id": campaign_id, "campaign": name,
            "rows": cur.rowcount}


def rename_creative(conn, batch_id, creative_key, name):
    name = str(name or "").strip()
    if not name or len(name) > 120:
        raise ValueError("creative name must be 1-120 characters")
    if creative_key not in _member_keys(conn, batch_id, "creatives"):
        raise ValueError("not a sample creative: %r" % (creative_key,))
    conn.execute("UPDATE creatives SET name=? WHERE creative_key=?",
                 (name, creative_key))
    conn.execute("UPDATE ads SET ad_name=? WHERE import_id=?"
                 " AND creative_key=?", (name, batch_id, creative_key))
    conn.commit()
    return {"creative_key": creative_key, "name": name}


def delete_conversation(conn, batch_id, conversation_id):
    if conversation_id not in _member_keys(
            conn, batch_id, "analyst_conversations"):
        raise ValueError("not a sample conversation")
    conn.execute("DELETE FROM analyst_messages WHERE conversation_id=?",
                 (conversation_id,))
    conn.execute("DELETE FROM analyst_findings WHERE conversation_id=?",
                 (conversation_id,))
    conn.execute("DELETE FROM analyst_conversations WHERE id=?",
                 (conversation_id,))
    conn.commit()
    return {"deleted": conversation_id}


def delete_finding(conn, batch_id, finding_id):
    if finding_id not in _member_keys(conn, batch_id,
                                      "analyst_findings"):
        raise ValueError("not a sample finding")
    conn.execute("DELETE FROM analyst_findings WHERE id=?",
                 (finding_id,))
    conn.commit()
    return {"deleted": finding_id}


def delete_sample_view(conn, batch_id, view_id):
    if str(view_id) not in _member_keys(conn, batch_id, "saved_views"):
        raise ValueError("not a sample view")
    conn.execute("DELETE FROM saved_views WHERE id=?", (view_id,))
    conn.commit()
    return {"deleted": view_id}


def delete_sample_file(conn, batch_id, file_key, media_dir=None):
    import os as _os
    from ci_backend.actions import _media_dir
    if file_key not in _member_keys(conn, batch_id, "sample_files"):
        raise ValueError("not a sample file")
    row = conn.execute(
        "SELECT name FROM sample_files WHERE file_key=?",
        (file_key,)).fetchone()
    conn.execute("DELETE FROM sample_files WHERE file_key=?",
                 (file_key,))
    conn.commit()
    if row:
        try:
            path = _os.path.join(
                _media_dir(media_dir), "sample", batch_id, row[0])
            if _os.path.isfile(path):
                _os.remove(path)
        except OSError:
            pass
    return {"deleted": file_key}


def remove_pack(conn, batch_id, media_dir=None):
    """Remove ALL remaining pack rows (batch-scoped only). The
    receipt survives with status removed; nothing is re-added."""
    import os as _os
    import shutil as _shutil
    from ci_backend.actions import _media_dir
    receipt = _receipt_row(conn)
    if receipt is None or receipt["batch_id"] != batch_id:
        raise ValueError("unknown sample batch")
    if receipt["status"] == "removed":
        return {"removed": False, "receipt": receipt}
    # Performance rows first (rename-proof: import_id, not names).
    conn.execute("DELETE FROM ads WHERE import_id=?", (batch_id,))
    for key in _member_keys(conn, batch_id, "creatives"):
        conn.execute("DELETE FROM creatives WHERE creative_key=?",
                     (key,))
        conn.execute("DELETE FROM annotations WHERE creative_key=?",
                     (key,))
        conn.execute("DELETE FROM retention WHERE creative_key=?",
                     (key,))
    for mid in _member_keys(conn, batch_id, "media"):
        row = conn.execute(
            "SELECT stored_name FROM media WHERE id=?", (mid,)).fetchone()
        conn.execute("DELETE FROM media WHERE id=?", (mid,))
        _delete_media_file(conn, mid, row[0] if row else "")
    for vid in _member_keys(conn, batch_id, "saved_views"):
        conn.execute("DELETE FROM saved_views WHERE id=?", (vid,))
    for cid in _member_keys(conn, batch_id, "analyst_conversations"):
        conn.execute("DELETE FROM analyst_messages WHERE conversation_id=?",
                     (cid,))
        conn.execute("DELETE FROM analyst_findings WHERE conversation_id=?",
                     (cid,))
        conn.execute("DELETE FROM analyst_conversations WHERE id=?",
                     (cid,))
    for fid in _member_keys(conn, batch_id, "analyst_findings"):
        conn.execute("DELETE FROM analyst_findings WHERE id=?", (fid,))
    for fkey in _member_keys(conn, batch_id, "sample_files"):
        row = conn.execute(
            "SELECT name FROM sample_files WHERE file_key=?",
            (fkey,)).fetchone()
        conn.execute("DELETE FROM sample_files WHERE file_key=?",
                     (fkey,))
    try:
        _shutil.rmtree(_os.path.join(_media_dir(media_dir), "sample",
                                     batch_id), ignore_errors=True)
    except OSError:
        pass
    conn.execute("UPDATE demo_packs SET status='removed', removed_at=?"
                 " WHERE pack_key=?", (_utcnow(), PACK_KEY))
    conn.commit()
    return {"removed": True, "receipt": _receipt_row(conn)}

