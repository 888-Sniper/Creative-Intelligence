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


def _receipt_row(conn, pack_key=None):
    row = conn.execute(
        "SELECT pack_key, batch_id, workspace, imported_by, imported_at,"
        " data_start, data_end, status, counts_json, removed_at"
        " FROM demo_packs WHERE pack_key=?",
        (pack_key or PACK_KEY,)).fetchone()
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


def pack_status(conn, pack_key=None):
    """Receipt + live remaining counts; derives partially_removed."""
    pack_key = pack_key or PACK_KEY
    receipt = _receipt_row(conn, pack_key)
    if receipt is None:
        return {"status": "not_added", "pack_key": pack_key,
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
                         (status, pack_key))
            conn.commit()
            receipt["status"] = status
    campaigns = [
        {"campaign_id": r[0], "campaign": r[1]}
        for r in conn.execute(
            "SELECT campaign_id, campaign FROM ads WHERE import_id=?"
            " GROUP BY campaign_id ORDER BY campaign",
            (receipt["batch_id"],)).fetchall()]
    return {"status": status, "pack_key": pack_key, "receipt": receipt,
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


def _import_ads_rows(conn, batch_id, day_list, keep=None):
    """Deterministic daily facts via the real upsert path."""
    from creative_intel import ingest as _ingest
    rng = _random.Random(20260913)
    rows = []
    indices = tuple(keep) if keep is not None else tuple(range(len(CAMPAIGNS)))
    for ci in indices:
        camp = CAMPAIGNS[ci]
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
                        # Synthetic facts report revenue, so ROAS
                        # computes honestly over this pack.
                        "revenue_reported": True,
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
                                  filters={"sample_batch": [batch_id]},
                                  benchmark_scope="filters",
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


def delete_campaign(conn, batch_id, campaign_id, delete_views=True):
    """Normal campaign delete, scoped to the pack by stable id.

    delete_views=False preserves tracked views (migration keeps v1
    views review-only even when their campaign filter goes stale).
    Deleted media rows are always untracked so later verification
    never counts dead member keys."""
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
            conn.execute("DELETE FROM demo_batch_members WHERE batch_id=?"
                         " AND table_name='media' AND record_key=?",
                         (batch_id, str(mid)))
        if delete_views:
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


def remove_pack(conn, batch_id, media_dir=None, pack_key=None):
    """Remove ALL remaining pack rows (batch-scoped only). The
    receipt survives with status removed; nothing is re-added."""
    import os as _os
    import shutil as _shutil
    from ci_backend.actions import _media_dir
    pack_key = pack_key or PACK_KEY
    receipt = _receipt_row(conn, pack_key)
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
                 " WHERE pack_key=?", (_utcnow(), pack_key))
    conn.commit()
    return {"removed": True, "receipt": _receipt_row(conn, pack_key)}


# ============================================================
# v2 presentation pack: exactly 5 campaigns x 3 creatives.
#
# v2 keeps the v1 catalogue identities it needs (campaign IDs
# SMP-01/03/05/07/09 and slug-based creative keys are unchanged, so
# provenance survives) and drops the other five campaigns. v1 rows
# and receipts are never mutated except through the explicit,
# authorised migration below.
# ============================================================

PACK_KEY_V2 = "foap-presentation-pack-v2"

# Indices into the v1 CAMPAIGNS/CREATIVES catalogue.
V2_KEPT = (0, 2, 4, 6, 8)

V2_CAMPAIGN_IDS = tuple("SMP-%02d" % (i + 1) for i in V2_KEPT)

V2_CONV_IDS = tuple("sample-conv-%02d" % (i + 1) for i in range(6))

# Stale-importing guard: a receipt stuck in importing with no writer
# for longer than this is recoverable by an explicit admin retry.
STALE_IMPORTING_SECONDS = 15 * 60

SAMPLE_VIEWS_V2 = (
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
     {"filters": {"campaign": ["First Light Ritual", "One Sip Ahead",
                               "The 6AM Commitment", "Find Your Focus"]},
      "kpi": "roas", "view": "compare", "benchmark": "campaign",
      "benchmark_scope": "filters", "rank_by": "roas",
      "compare_mode": "campaigns"}),
    ("Sample \u2014 Compare: Morning Rituals (CTR)",
     {"filters": {"campaign": ["First Light Ritual", "One Sip Ahead"]},
      "kpi": "ctr", "view": "compare", "benchmark": "campaign",
      "benchmark_scope": "filters", "rank_by": "ctr",
      "compare_mode": "campaigns"}),
    ("Sample \u2014 Compare: Home Fitness (CPA)",
     {"filters": {"campaign": ["Make Room For Better",
                               "The 6AM Commitment"]},
      "kpi": "cpa", "view": "compare", "benchmark": "platform",
      "benchmark_scope": "global", "rank_by": "cpa",
      "compare_mode": "campaigns"}),
    ("Sample \u2014 Compare: Focus Creatives (CTR)",
     {"filters": {"campaign": ["Find Your Focus"],
                  "creative": ["smp-focus-desk-noise",
                               "smp-focus-focus-session",
                               "smp-focus-one-button"]},
      "kpi": "ctr", "view": "compare", "benchmark": "hook_type",
      "benchmark_scope": "filters", "rank_by": "ctr",
      "compare_mode": "creatives"}),
)

SAMPLE_QUESTIONS_V2 = SAMPLE_QUESTIONS

V2_REPORT_JOBS = (
    ("Sample Report \u2014 Pack Overview (Markdown)", "one-pager",
     None, ["roas", "ctr"]),
    ("Sample Report \u2014 Avenlo Skin (Markdown)", "one-pager",
     ["First Light Ritual"], ["ctr", "cpa"]),
    ("Sample Report \u2014 Pack Overview (CSV)", "csv", None,
     ["roas", "ctr", "cpa", "spend"]),
    ("Sample Report \u2014 Client Comparison (CSV)",
     "csv", None, ["ctr", "cpa", "conversions"]),
    ("Sample Report \u2014 Fitness Push (Excel)", "xlsx",
     ["The 6AM Commitment"], ["ctr", "cpa"]),
    ("Sample Report \u2014 Pack Overview (Slides)", "pptx", None,
     ["roas", "ctr"]),
)

# (title, v1 campaign indexes covered; None = every kept campaign).
# Workbooks ship prefilled with the pack's own summed raw inputs so
# every formula sheet computes live — they are worked examples over
# synthetic demonstration data, not blank templates.
V2_WORKBOOKS = (
    ("Sample Workbook \u2014 Pack Overview", None),
    ("Sample Workbook \u2014 Avenlo Skin", (0,)),
    ("Sample Workbook \u2014 Folden Home", (4,)),
)


def _v2_campaign_name(v1_idx):
    return CAMPAIGNS[v1_idx][1]


def preview_v2(conn, workspace=""):
    """What Add Demo Data Once (v2) will create (no writes)."""
    return {
        "pack_key": PACK_KEY_V2,
        "workspace": workspace,
        "synthetic": True,
        "campaigns": [
            {"campaign_id": campaign_id(i), "name": CAMPAIGNS[i][1],
             "client": CAMPAIGNS[i][2], "project": CAMPAIGNS[i][3],
             "vertical": CAMPAIGNS[i][4], "market": CAMPAIGNS[i][5],
             "team": CAMPAIGNS[i][6],
             "creatives": [CREATIVES[i * 3 + j][1] for j in range(3)]}
            for i in V2_KEPT],
        "totals": {"campaigns": 5, "creatives": 15,
                   "days": PACK_DAYS,
                   "saved_views": len(SAMPLE_VIEWS_V2),
                   "conversations": len(SAMPLE_QUESTIONS_V2),
                   "reports": len(V2_REPORT_JOBS),
                   "workbooks": len(V2_WORKBOOKS)},
        "replenish": False,
    }


def _v1_active_receipt(conn):
    row = _receipt_row(conn, PACK_KEY)
    if row is None or row["status"] == "removed":
        return None
    return row


def migration_preview(conn):
    """Explicit preview of a v1 -> v2 migration (no writes).

    Only demonstrably sample-owned surplus records are listed for
    deletion (v1 batch members under surplus campaign IDs, verified
    live). v1-tracked views/conversations are listed as review-only:
    name-adoption in v1 means ownership is uncertain, so they are
    NEVER auto-deleted.
    """
    v1 = _receipt_row(conn, PACK_KEY)
    if v1 is None:
        return {"eligible": False, "reason": "no v1 pack receipt"}
    if v1["status"] == "removed":
        return {"eligible": False,
                "reason": "v1 pack was removed; removal is retained,"
                          " import v2 explicitly for a fresh pack"}
    batch = v1["batch_id"]
    surplus_ids = ["SMP-%02d" % (i + 1) for i in range(10)
                   if i not in V2_KEPT]
    surplus = []
    for cid in surplus_ids:
        live = conn.execute(
            "SELECT COUNT(*) FROM ads WHERE import_id=? AND campaign_id=?",
            (batch, cid)).fetchone()[0]
        name = conn.execute(
            "SELECT campaign FROM ads WHERE import_id=? AND campaign_id=?"
            " LIMIT 1", (batch, cid)).fetchone()
        keys = [r[0] for r in conn.execute(
            "SELECT DISTINCT creative_key FROM ads WHERE import_id=?"
            " AND campaign_id=?", (batch, cid))]
        members = set(_member_keys(conn, batch, "creatives"))
        owned_keys = [k for k in keys if k in members]
        media_n = conn.execute(
            "SELECT COUNT(*) FROM media WHERE creative_key IN (%s)" % (
                ",".join("?" * len(keys)) or "SELECT '' WHERE 0"),
            keys).fetchone()[0] if keys else 0
        surplus.append({"campaign_id": cid,
                        "campaign": name[0] if name else "",
                        "already_deleted": live == 0,
                        "ads_rows": live,
                        "creatives": owned_keys,
                        "media_rows": media_n})
    review_views = [
        {"id": vid}
        for vid in _member_keys(conn, batch, "saved_views")
        if conn.execute("SELECT 1 FROM saved_views WHERE id=?",
                        (vid,)).fetchone()]
    review_convs = [
        {"id": cid}
        for cid in _member_keys(conn, batch, "analyst_conversations")
        if conn.execute("SELECT 1 FROM analyst_conversations WHERE id=?",
                        (cid,)).fetchone()]
    return {"eligible": True, "v1_status": v1["status"],
            "v1_batch_id": batch,
            "retain": [{"campaign_id": campaign_id(i),
                        "campaign": _v2_campaign_name(i)} for i in V2_KEPT],
            "surplus": surplus,
            "review_only": {"saved_views": review_views,
                            "analyst_conversations": review_convs,
                            "note": "v1 name-adopted rows: ownership"
                                    " uncertain, never auto-deleted"},
            "v1_data_window": {"start": v1["data_start"],
                               "end": v1["data_end"]}}


def _v2_set_status(conn, status, counts=None, error=""):
    if counts is None:
        receipt = _receipt_row(conn, PACK_KEY_V2)
        try:
            counts = _json.loads(receipt["counts_json"] or "{}")
        except ValueError:
            counts = {}
    counts = dict(counts)
    if error:
        counts["error"] = str(error)
    else:
        counts.pop("error", None)
    conn.execute("UPDATE demo_packs SET status=?, counts_json=?"
                 " WHERE pack_key=?",
                 (status, _json.dumps(counts), PACK_KEY_V2))
    conn.commit()


def _v2_stale_importing(conn):
    receipt = _receipt_row(conn, PACK_KEY_V2)
    if receipt is None or receipt["status"] != "importing":
        return False
    try:
        started = _dt.datetime.strptime(
            receipt["imported_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=_dt.timezone.utc)
        age = (_dt.datetime.now(_dt.timezone.utc) - started).total_seconds()
    except (ValueError, TypeError):
        return True
    return age > STALE_IMPORTING_SECONDS


def import_pack_v2(conn, imported_by="", workspace="", media_dir=None):
    """One-time v2 import (5 campaigns x 3 creatives). Never installs
    beside an active v1 pack: an added/partial v1 pack refuses with a
    migration pointer instead.
    """
    from creative_intel import ingest as _ingest
    v1 = _v1_active_receipt(conn)
    if v1 is not None:
        return {"created": False, "migration_required": True,
                "status": pack_status(conn, PACK_KEY_V2),
                "preview": migration_preview(conn)}
    existing = _receipt_row(conn, PACK_KEY_V2)
    if existing is not None and existing["status"] not in ("failed",):
        if existing["status"] == "importing" and not _v2_stale_importing(conn):
            st = pack_status(conn, PACK_KEY_V2)
            st["created"] = False
            return st
        if existing["status"] == "importing":
            conn.execute("UPDATE demo_packs SET status='failed',"
                         " counts_json=? WHERE pack_key=?",
                         (_json.dumps({"error": "stale importing receipt;"
                                                " safe to retry"}),
                          PACK_KEY_V2))
            conn.commit()
            existing = _receipt_row(conn, PACK_KEY_V2)
        else:
            st = pack_status(conn, PACK_KEY_V2)
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
                     " WHERE pack_key=?", (PACK_KEY_V2,))
        conn.commit()
    else:
        batch_id = "smp2-%s" % _uuid.uuid4().hex[:12]
        start, end, day_list = _date_range()
        try:
            conn.execute(
                "INSERT INTO demo_packs (pack_key, batch_id, workspace,"
                " imported_by, imported_at, data_start, data_end,"
                " status, counts_json) VALUES (?, ?, ?, ?, ?, ?, ?,"
                " 'importing', '{}')",
                (PACK_KEY_V2, batch_id, workspace, imported_by,
                 _utcnow(), start, end))
            conn.commit()
        except Exception:
            conn.rollback()
            st = pack_status(conn, PACK_KEY_V2)
            st["created"] = False
            return st
    counts = {}
    try:
        res = _import_ads_rows(conn, batch_id, day_list, keep=V2_KEPT)
        counts["ads_rows"] = res["inserted"] + res["updated"]
        _ingest.record_import(
            conn, {"filename": "sample-pack-v2", "mapping": "generated",
                   "unmapped": []}, "meta", PACK_SOURCE,
            filename="sample-pack-v2", imported_by=imported_by,
            counts={"imported": counts["ads_rows"], "quarantined": 0})
        from creative_intel import creative as _creative
        from creative_intel import media as _media
        from creative_intel import demo_art as _art
        from ci_backend.actions import _media_dir
        for ci in V2_KEPT:
            for ki in range(3):
                key = creative_key(ci, ki)
                spec = CREATIVES[ci * 3 + ki]
                conn.execute(
                    "INSERT OR IGNORE INTO creatives (creative_key,"
                    " platform, name, duration_s, status, transcript,"
                    " pipeline_json) VALUES (?, 'meta/tiktok', ?, ?,"
                    " 'auto', '', ?)",
                    (key, spec[1], float(spec[3]),
                     _json.dumps({"provenance": "sample",
                                  "pack_key": PACK_KEY_V2,
                                  "batch_id": batch_id})))
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
        counts["campaigns"] = len(V2_KEPT)
        store = _media_dir(media_dir)
        _media.ensure_schema(conn)
        n_media = 0
        for ci in V2_KEPT:
            for ki in range(3):
                key = creative_key(ci, ki)
                have = conn.execute(
                    "SELECT 1 FROM media WHERE creative_key=?"
                    " AND mime LIKE 'image/%%' LIMIT 1",
                    (key,)).fetchone()
                if not have:
                    slug = CREATIVES[ci * 3 + ki][0]
                    blob, w, h, _aspect = _art.v2_art_for_creative(slug)
                    rec = _media.save_media_bytes(
                        conn, store, key, key + ".png", blob,
                        width=w, height=h)
                    _track(conn, batch_id, "media", rec["id"])
                    n_media += 1
        counts["media"] = n_media
        conn.commit()
    except Exception as exc:
        conn.rollback()
        _v2_set_status(conn, "failed", {"error": "core: %s" % exc})
        raise
    return {"batch_id": batch_id, "phase": "core", "counts": counts,
            "data_start": start, "data_end": end, "created": True,
            "pack_key": PACK_KEY_V2}


def _v2_checkpoint(conn, batch_id, phase, extra=None):
    receipt = _receipt_row(conn, PACK_KEY_V2)
    try:
        counts = _json.loads(receipt["counts_json"] or "{}")
    except ValueError:
        counts = {}
    counts["phase"] = phase
    if extra:
        counts.update(extra)
    conn.execute("UPDATE demo_packs SET counts_json=? WHERE pack_key=?",
                 (_json.dumps(counts), PACK_KEY_V2))
    conn.commit()


def _v2_own_view_id(conn, batch_id, name):
    """Id of OUR tracked view with this name, else None. A same-named
    untracked row is user-owned and must never be adopted."""
    for vid in _member_keys(conn, batch_id, "saved_views"):
        row = conn.execute("SELECT id, name FROM saved_views WHERE id=?",
                           (vid,)).fetchone()
        if row and row[1] == name:
            return row[0]
    return None


def _v2_claim_view(conn, batch_id, name, state):
    """Create-or-reuse ONLY our own view; disambiguate on collision.

    Retry safety: an earlier attempt may already own "name (Sample N)"
    (when a same-named user row forced disambiguation). That tracked
    row is reused — a retry must never mint "(Sample 3)". A same-named
    untracked row is user-owned and must never be adopted."""
    from ci_backend.actions import save_view
    own = _v2_own_view_id(conn, batch_id, name)
    if own is not None:
        return own, False
    prefix = "%s (Sample " % name
    for vid in _member_keys(conn, batch_id, "saved_views"):
        row = conn.execute("SELECT id, name FROM saved_views WHERE id=?",
                           (vid,)).fetchone()
        if row and str(row[1]).startswith(prefix):
            return row[0], False
    target = name
    if conn.execute("SELECT 1 FROM saved_views WHERE name=?",
                    (target,)).fetchone():
        n = 2
        while conn.execute("SELECT 1 FROM saved_views WHERE name=?",
                           ("%s (Sample %d)" % (target, n),)).fetchone():
            n += 1
        target = "%s (Sample %d)" % (target, n)
    rec = save_view(conn, target, dict(state))
    _track(conn, batch_id, "saved_views", rec["id"])
    conn.commit()
    return rec["id"], True


def _v2_claim_conversation(conn, batch_id, imported_by, question, scope,
                           objective, language):
    """Create-or-reuse ONLY our own conversation. Identity is the
    tracked batch id — never a title, owner or timestamp match. A
    crash between answer_turn and tracking can leave one untracked
    orphan row; a retry deliberately creates a fresh conversation
    rather than adopting any untracked row, because a genuine
    user-created conversation can share owner/title/scope/timing
    and must never be absorbed into (or deleted with) the pack."""
    from creative_intel import analyst_chat as _chat
    title = question[:60]
    for cid in _member_keys(conn, batch_id, "analyst_conversations"):
        row = conn.execute(
            "SELECT id, title FROM analyst_conversations WHERE id=?",
            (cid,)).fetchone()
        if row and row[1] == title:
            return row[0], False
    turn = _chat.answer_turn(
        conn, imported_by, question, None, scope=dict(scope),
        objective=objective, language=language)
    conv_id = turn["conversation_id"]
    _track(conn, batch_id, "analyst_conversations", conv_id)
    for (mid,) in conn.execute(
            "SELECT id FROM analyst_messages WHERE conversation_id=?",
            (conv_id,)):
        _track(conn, batch_id, "analyst_messages", conv_id)
    for (fid,) in conn.execute(
            "SELECT id FROM analyst_findings WHERE conversation_id=?",
            (conv_id,)):
        _track(conn, batch_id, "analyst_findings", fid)
    conn.commit()
    return conv_id, True


def verify_pack_v2(conn, batch_id, media_dir=None):
    """Check required records AND file references. Returns (ok, detail).
    DB and filesystem failures are reported separately. Acceptance is
    strict: 5 campaigns, 15 creatives, 15 tracked media rows, every
    expected report/workbook file, 10 tracked views and 6 tracked
    conversations — a pack with no media or files never passes, and
    a missing tracked row fails instead of being skipped."""
    import os as _os
    from ci_backend.actions import _media_dir
    detail = {"db": {}, "files": {}}
    camps = conn.execute(
        "SELECT COUNT(DISTINCT campaign_id) FROM ads WHERE import_id=?",
        (batch_id,)).fetchone()[0]
    detail["db"]["campaigns"] = camps
    keys = _member_keys(conn, batch_id, "creatives")
    alive = conn.execute(
        "SELECT COUNT(*) FROM creatives WHERE creative_key IN (%s)" % (
            ",".join("?" * len(keys)) or "SELECT '' WHERE 0"),
        keys).fetchone()[0] if keys else 0
    detail["db"]["creatives"] = alive
    media_ids = _member_keys(conn, batch_id, "media")
    alive_media = conn.execute(
        "SELECT COUNT(*) FROM media WHERE id IN (%s)" % (
            ",".join("?" * len(media_ids)) or "SELECT '' WHERE 0"),
        media_ids).fetchone()[0] if media_ids else 0
    detail["db"]["media_rows"] = alive_media
    detail["db"]["media_missing_rows"] = sorted(
        set(media_ids) - {
            str(r[0]) for r in conn.execute(
                "SELECT id FROM media WHERE id IN (%s)" % (
                    ",".join("?" * len(media_ids)) or "SELECT '' WHERE 0"),
                media_ids)} if media_ids else [])
    fkeys = _member_keys(conn, batch_id, "sample_files")
    alive_files = conn.execute(
        "SELECT COUNT(*) FROM sample_files WHERE file_key IN (%s)" % (
            ",".join("?" * len(fkeys)) or "SELECT '' WHERE 0"),
        fkeys).fetchone()[0] if fkeys else 0
    detail["db"]["sample_files"] = alive_files
    detail["db"]["sample_files_expected"] = (
        len(V2_REPORT_JOBS) + len(V2_WORKBOOKS))
    view_ids = _member_keys(conn, batch_id, "saved_views")
    alive_views = conn.execute(
        "SELECT COUNT(*) FROM saved_views WHERE id IN (%s)" % (
            ",".join("?" * len(view_ids)) or "SELECT '' WHERE 0"),
        view_ids).fetchone()[0] if view_ids else 0
    detail["db"]["saved_views"] = alive_views
    detail["db"]["saved_views_expected"] = len(SAMPLE_VIEWS_V2)
    conv_ids = _member_keys(conn, batch_id, "analyst_conversations")
    alive_convs = conn.execute(
        "SELECT COUNT(*) FROM analyst_conversations WHERE id IN (%s)" % (
            ",".join("?" * len(conv_ids)) or "SELECT '' WHERE 0"),
        conv_ids).fetchone()[0] if conv_ids else 0
    detail["db"]["conversations"] = alive_convs
    detail["db"]["conversations_expected"] = len(SAMPLE_QUESTIONS_V2)
    ok = (camps == 5 and alive == 15 and alive_media == 15
          and alive_files == detail["db"]["sample_files_expected"]
          and alive_views == detail["db"]["saved_views_expected"]
          and alive_convs == detail["db"]["conversations_expected"])
    missing_media, missing_files = list(
        detail["db"]["media_missing_rows"]), []
    detail["db"]["sample_files_missing_rows"] = sorted(
        set(fkeys) - {
            r[0] for r in conn.execute(
                "SELECT file_key FROM sample_files WHERE file_key IN (%s)"
                % (",".join("?" * len(fkeys)) or "SELECT '' WHERE 0"),
                fkeys)} if fkeys else [])
    missing_files.extend(detail["db"]["sample_files_missing_rows"])
    detail["db"]["saved_views_missing_rows"] = sorted(
        set(view_ids) - {
            str(r[0]) for r in conn.execute(
                "SELECT id FROM saved_views WHERE id IN (%s)" % (
                    ",".join("?" * len(view_ids)) or "SELECT '' WHERE 0"),
                view_ids)} if view_ids else [])
    detail["db"]["conversations_missing_rows"] = sorted(
        set(conv_ids) - {
            str(r[0]) for r in conn.execute(
                "SELECT id FROM analyst_conversations WHERE id IN (%s)"
                % (",".join("?" * len(conv_ids)) or "SELECT '' WHERE 0"),
                conv_ids)} if conv_ids else [])
    if (detail["db"]["saved_views_missing_rows"]
            or detail["db"]["conversations_missing_rows"]):
        ok = False
    store = _media_dir(media_dir)
    for mid in media_ids:
        row = conn.execute("SELECT stored_name FROM media WHERE id=?",
                           (mid,)).fetchone()
        if not row:
            continue  # already counted in media_missing_rows above
        path = _os.path.join(store, row[0])
        if not _os.path.isfile(path):
            missing_media.append(mid)
    for fk in fkeys:
        row = conn.execute("SELECT name FROM sample_files WHERE file_key=?",
                           (fk,)).fetchone()
        if not row:
            continue  # already counted in sample_files_missing_rows
        path = _os.path.join(store, "sample", batch_id, row[0])
        if not _os.path.isfile(path):
            missing_files.append(fk)
    detail["files"]["missing_media"] = missing_media
    detail["files"]["missing_sample_files"] = sorted(set(missing_files))
    if missing_media or missing_files:
        ok = False
    return ok, detail


def finalize_pack_v2(conn, batch_id, imported_by="", media_dir=None,
                     core_counts=None):
    """Showcase layer with durable per-item checkpoints. Skip-if-ours
    (tracked) so retries never duplicate rows or overwrite user edits;
    same-named user rows are never adopted. Sets added only after
    verify_pack_v2 passes on records AND files."""
    import base64 as _b64
    from ci_backend.actions import _media_dir, save_view
    from creative_intel import benchmarks as _bench
    from creative_intel import analyst_workbook as _wb
    _ = save_view
    counts = dict(core_counts or {})
    store = _media_dir(media_dir)
    # Any showcase failure (conversations, reports, workbooks) is
    # recorded as a recoverable failed receipt — never a silent
    # partial pack. Per-item checkpoints already committed stay, so
    # a retry resumes without duplicating tracked rows.
    try:
        _finalize_showcase_v2(conn, batch_id, imported_by, store, counts)
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        _v2_set_status(conn, "failed", dict(counts),
                       error="finalize: %s; safe to retry" % exc)
        raise
    return _finish_pack_v2(conn, batch_id, media_dir, counts)


def _v2_workbook_prefill(conn, batch_id, campaign_indexes):
    """Prefill rows [(creative_key, {input_field: value})] summed over
    this batch's own ads rows. Facts the pack never synthesises
    (reach, watch time, creator, concept) stay blank, which the
    sheet legend defines as missing — never a measured zero."""
    out = []
    for ci in campaign_indexes:
        for ki in range(3):
            key = creative_key(ci, ki)
            agg = conn.execute(
                "SELECT COALESCE(SUM(impressions),0),"
                " COALESCE(SUM(video_starts),0),"
                " COALESCE(SUM(views_2s),0),"
                " COALESCE(SUM(views_3s),0),"
                " COALESCE(SUM(views_25),0),"
                " COALESCE(SUM(views_50),0),"
                " COALESCE(SUM(views_75),0),"
                " COALESCE(SUM(views_100),0),"
                " COALESCE(SUM(spend),0) FROM ads"
                " WHERE import_id=? AND creative_key=?",
                (batch_id, key)).fetchone()
            if not agg or not agg[0]:
                continue
            dur = conn.execute(
                "SELECT duration_s FROM creatives WHERE creative_key=?",
                (key,)).fetchone()
            vals = {"impressions": agg[0], "video_starts": agg[1],
                    "views_2s": agg[2], "views_3s": agg[3],
                    "views_25": agg[4], "views_50": agg[5],
                    "views_75": agg[6], "views_100": agg[7],
                    "spend": round(agg[8], 2)}
            if dur and dur[0]:
                vals["duration_s"] = dur[0]
            out.append((key, vals))
    return out


def _finalize_showcase_v2(conn, batch_id, imported_by, store, counts):
    """Views, conversations, reports, workbooks with checkpoints."""
    import base64 as _b64
    from creative_intel import benchmarks as _bench
    from creative_intel import analyst_workbook as _wb
    n_views = 0
    for name, state in SAMPLE_VIEWS_V2:
        _, created = _v2_claim_view(conn, batch_id, name, state)
        n_views += int(created)
    counts["saved_views"] = n_views
    _v2_checkpoint(conn, batch_id, "views", counts)
    n_convs = 0
    for question, scope, objective, language in SAMPLE_QUESTIONS_V2:
        scoped = dict(scope or {})
        scoped["sample_batch"] = [batch_id]
        _, created = _v2_claim_conversation(
            conn, batch_id, imported_by, question, scoped,
            objective, language)
        n_convs += int(created)
    counts["conversations"] = n_convs
    counts["findings"] = len(_member_keys(conn, batch_id,
                                          "analyst_findings"))
    _v2_checkpoint(conn, batch_id, "conversations", counts)
    ext_by_fmt = {"one-pager": ("md", "text/markdown"),
                  "csv": ("csv", "text/csv"),
                  "xlsx": ("xlsx", "application/vnd.openxmlformats-"
                           "officedocument.spreadsheetml.sheet"),
                  "pptx": ("pptx", "application/vnd.openxmlformats-"
                           "officedocument.presentationml.presentation")}
    n_reports = 0
    for title, fmt, camps, kpis in V2_REPORT_JOBS:
        fname = "%s.%s" % (title.replace(" \u2014 ", " - "),
                           ext_by_fmt[fmt][0])
        present = conn.execute(
            "SELECT 1 FROM sample_files WHERE file_key=?",
            ("%s/%s" % (batch_id, fname),)).fetchone()
        if present:
            continue
        # Sample-only by construction: the batch axis keeps real
        # uploads out even on a mixed database.
        rep = _bench.build_report(conn, camps, kpis, "platform", fmt,
                                  filters={"sample_batch": [batch_id]},
                                  benchmark_scope="filters",
                                  rank_by=kpis[0])
        if fmt == "one-pager":
            blob = ("> Sample Data \u2014 synthetic demonstration figures,"
                    " not real client performance.\n\n"
                    + rep["markdown"]).encode("utf-8")
        elif fmt == "csv":
            blob = rep["csv"].encode("utf-8")
        elif fmt == "pptx":
            blob = _b64.b64decode(rep["pptx_b64"])
        else:
            blob = _b64.b64decode(rep["xlsx_b64"])
        _store_sample_file(conn, store, batch_id, fname, fmt,
                           ext_by_fmt[fmt][1], blob)
        n_reports += 1
    counts["reports"] = n_reports
    n_books = 0
    for title, scope_idx in V2_WORKBOOKS:
        fname = "%s.xlsx" % title.replace(" \u2014 ", " - ")
        present = conn.execute(
            "SELECT 1 FROM sample_files WHERE file_key=?",
            ("%s/%s" % (batch_id, fname),)).fetchone()
        if present:
            continue
        blob = _wb.build_blank_workbook(
            prefill=_v2_workbook_prefill(
                conn, batch_id, scope_idx if scope_idx is not None
                else V2_KEPT),
            cover={"name": title,
                   "description": "Worked sample over the one-time"
                   " presentation pack (%s): Input rows are prefilled"
                   " with the pack's summed synthetic figures, so the"
                   " formula sheets compute live. Synthetic"
                   " demonstration data." % PACK_KEY_V2,
                   "modules": ["Metrics", "Benchmarks"],
                   "kpis": ["ROAS", "CTR", "CPA"]})
        _store_sample_file(
            conn, store, batch_id, fname, "workbook",
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet", blob)
        n_books += 1
    counts["workbooks"] = n_books
    _v2_checkpoint(conn, batch_id, "files", counts)


def _finish_pack_v2(conn, batch_id, media_dir, counts):
    """Strict acceptance gate: added only after verify_pack_v2
    passes on records AND files."""
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
    ok, detail = verify_pack_v2(conn, batch_id, media_dir)
    if not ok:
        _v2_set_status(conn, "failed",
                       dict(counts, verify=detail,
                            error="verify failed; safe to retry"))
        return {"created": False, "counts": counts, "verify": detail,
                "receipt": _receipt_row(conn, PACK_KEY_V2)}
    receipt = _receipt_row(conn, PACK_KEY_V2)
    merged = dict(_json.loads(receipt["counts_json"] or "{}"))
    merged.update(counts)
    merged.pop("error", None)
    merged["phase"] = "added"
    conn.execute("UPDATE demo_packs SET status='added', counts_json=?"
                 " WHERE pack_key=?",
                 (_json.dumps(merged), PACK_KEY_V2))
    conn.commit()
    return {"created": True, "counts": merged,
            "receipt": _receipt_row(conn, PACK_KEY_V2)}


def migrate_to_v2(conn, imported_by="", authorize=False, media_dir=None):
    """Authorised v1 -> v2 migration. Deletes ONLY live surplus
    sample-owned campaigns (never restores user-deleted ones; tracked
    v1 views stay review-only and are never deleted by the nested
    campaign path), then runs the full v2 artwork/showcase
    verification: the v2 receipt is marked added only when it
    passes, failed with detail otherwise."""
    prev = migration_preview(conn)
    if not prev.get("eligible"):
        raise ValueError(prev.get("reason", "migration not eligible"))
    if not authorize:
        return {"authorized": False, "preview": prev}
    batch = prev["v1_batch_id"]
    deleted, kept_deleted = [], []
    for item in prev["surplus"]:
        if item["already_deleted"]:
            kept_deleted.append(item["campaign_id"])
            continue
        delete_campaign(conn, batch, item["campaign_id"],
                        delete_views=False)
        deleted.append(item["campaign_id"])
    v1 = _receipt_row(conn, PACK_KEY)
    counts = {
        "campaigns": len(V2_KEPT), "creatives": 15,
        "ads_rows": conn.execute(
            "SELECT COUNT(*) FROM ads WHERE import_id=?",
            (batch,)).fetchone()[0],
        "migrated_from": PACK_KEY, "phase": "migrated",
    }
    try:
        conn.execute(
            "INSERT INTO demo_packs (pack_key, batch_id, workspace,"
            " imported_by, imported_at, data_start, data_end,"
            " status, counts_json) VALUES (?, ?, ?, ?, ?, ?, ?,"
            " 'migrated', ?)",
            (PACK_KEY_V2, batch, v1["workspace"], imported_by,
             _utcnow(), v1["data_start"], v1["data_end"],
             _json.dumps(counts)))
    except Exception:
        conn.execute("UPDATE demo_packs SET status='migrated', counts_json=?"
                     " WHERE pack_key=?",
                     (_json.dumps(counts), PACK_KEY_V2))
    conn.commit()
    ok, detail = verify_pack_v2(conn, batch, media_dir)
    if not ok:
        counts = dict(counts, verify=detail,
                      error="migration verify failed; safe to retry import")
        conn.execute("UPDATE demo_packs SET status='failed', counts_json=?"
                     " WHERE pack_key=?",
                     (_json.dumps(counts), PACK_KEY_V2))
        conn.commit()
        return {"authorized": True, "deleted": deleted,
                "kept_deleted": kept_deleted, "verified": False,
                "verify": detail,
                "receipt": _receipt_row(conn, PACK_KEY_V2)}
    counts = dict(counts, verify=detail, phase="added")
    conn.execute("UPDATE demo_packs SET status='added', counts_json=?"
                 " WHERE pack_key=?",
                 (_json.dumps(counts), PACK_KEY_V2))
    conn.execute("UPDATE demo_packs SET status='migrated' WHERE pack_key=?",
                 (PACK_KEY,))
    conn.commit()
    return {"authorized": True, "deleted": deleted,
            "kept_deleted": kept_deleted, "verified": True,
            "verify": detail,
            "receipt": _receipt_row(conn, PACK_KEY_V2)}

