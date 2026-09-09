"""Header and row normalisation: Meta / TikTok / generic agency exports
into the canonical creative_grain fields (Schema v0).
"""

CANONICAL_FIELDS = [
    "client", "project", "campaign_id", "creative_id", "platform",
    "vertical", "market", "objective", "funnel_stage", "date",
    "spend", "impr", "clicks", "video_views", "conversions", "revenue",
]

NUMERIC_FIELDS = {"spend", "impr", "clicks", "video_views", "conversions", "revenue"}


def _norm(header):
    return " ".join(str(header).strip().lower().split())


META_ALIASES = {
    "campaign name": "campaign_id",
    "campaign": "campaign_id",
    "ad name": "creative_id",
    "ad": "creative_id",
    "day": "date",
    "date": "date",
    "amount spent (eur)": "spend",
    "amount spent": "spend",
    "spend": "spend",
    "impressions": "impr",
    "link clicks": "clicks",
    "clicks": "clicks",
    "3-sec video views": "video_views",
    "video views": "video_views",
    "thruplays": "video_views",
    "results": "conversions",
    "purchases": "conversions",
    "purchase value": "revenue",
    "purchase conversion value": "revenue",
}

TIKTOK_ALIASES = {
    "campaign name": "campaign_id",
    "campaign": "campaign_id",
    "adgroup name": "creative_id",
    "ad group": "creative_id",
    "ad name": "creative_id",
    "ad": "creative_id",
    "date": "date",
    "cost": "spend",
    "spend": "spend",
    "impressions": "impr",
    "impression": "impr",
    "clicks": "clicks",
    "click": "clicks",
    "video views": "video_views",
    "6s views": "video_views",
    "conversions": "conversions",
    "conversion": "conversions",
    "total revenue": "revenue",
    "total purchase value": "revenue",
    "shop revenue": "revenue",
}

GENERIC_ALIASES = {
    "campaign": "campaign_id",
    "adgroup": "creative_id",
    "creative": "creative_id",
    "creative name": "creative_id",
    "date": "date",
    "day": "date",
    "cost": "spend",
    "spend": "spend",
    "impressions": "impr",
    "clicks": "clicks",
    "click": "clicks",
    "views": "video_views",
    "video views": "video_views",
    "conv": "conversions",
    "conversions": "conversions",
    "conversion": "conversions",
    "revenue": "revenue",
    "conversion value": "revenue",
}

ADAPTERS = {"meta": META_ALIASES, "tiktok": TIKTOK_ALIASES, "generic": GENERIC_ALIASES}


def detect_source(headers):
    """Score headers against each adapter; return the best adapter name."""
    cleaned = [_norm(h) for h in headers]
    best, best_score = "generic", -1
    for name, aliases in ADAPTERS.items():
        score = sum(1 for h in cleaned if h in aliases)
        if score > best_score:
            best, best_score = name, score
    return best


def map_headers(headers, adapter):
    """Return (mapping, unmapped): canonical field per header index."""
    aliases = ADAPTERS[adapter]
    mapping, unmapped = {}, []
    for i, header in enumerate(headers):
        target = aliases.get(_norm(header))
        if target is None and _norm(header) in CANONICAL_FIELDS:
            target = _norm(header)
        if target is None:
            unmapped.append(header)
        else:
            mapping[i] = target
    return mapping, unmapped


def _coerce_date(raw):
    """Accept ISO dates and Excel serials; pass anything else through for
    validation to reject with a reason."""
    import datetime
    import re
    text = str(raw).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text
    # US export style MM/DD/YYYY. Ambiguous day-first dates are NOT guessed:
    # anything else falls through to validation for an explicit reason.
    us = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", text)
    if us:
        month, day, year = (int(us.group(1)), int(us.group(2)),
                            us.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f"{year}-{month:02d}-{day:02d}"
    if re.match(r"^\d{4,6}$", text):
        num = int(text)
        if 20000 <= num <= 80000:
            return (datetime.date(1899, 12, 30)
                    + datetime.timedelta(days=num)).isoformat()
    return text


def normalise_row(values, mapping):
    """Map one raw row into canonical fields; coerce numerics, default 0."""
    row = {}
    for i, field in mapping.items():
        raw = values[i] if i < len(values) else ""
        if field == "date":
            row[field] = _coerce_date(raw)
        elif field in NUMERIC_FIELDS:
            cleaned = str(raw).replace(",", "").strip()
            for symbol in "$€£¥":
                cleaned = cleaned.replace(symbol, "")
            cleaned = cleaned.strip()
            try:
                row[field] = float(cleaned or 0)
            except ValueError:
                # Keep the raw text so validation quarantines it with a
                # reason instead of silently coercing to zero.
                row[field] = str(raw).strip()
        else:
            row[field] = str(raw).strip()
    for field in CANONICAL_FIELDS:
        row.setdefault(field, 0.0 if field in NUMERIC_FIELDS else "")
    return row


def validate_row(row):
    """Accept a canonical row or reject it with a reason. Never guesses."""
    import math
    import re
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(row.get("date", ""))):
        return False, f"bad date: {row.get('date')!r}"
    for field in ("campaign_id", "creative_id"):
        if not str(row.get(field, "")).strip():
            return False, f"missing {field}"
    for field in NUMERIC_FIELDS:
        value = row.get(field)
        if (not isinstance(value, (int, float))
                or not math.isfinite(value) or value < 0):
            return False, f"bad {field}: {value!r}"
    return True, ""


def ingest_file(path, adapter=None):
    """End-to-end file ingest: detect, map, normalise, validate.

    Returns {"source", "mapping", "unmapped", "rows", "quarantined"}.
    Unmapped columns and invalid rows are reported with reasons,
    never silently dropped.
    """
    import csv
    import os
    if not os.path.isfile(path):
        raise ValueError(f"not a readable file: {path}")
    with open(path, newline="") as fh:
        reader = csv.reader(fh)
        try:
            headers = next(reader)
        except StopIteration:
            raise ValueError(f"empty file, no header row: {path}")
        values = [r for r in reader if any(c.strip() for c in r)]
    source = adapter or detect_source(headers)
    mapping, unmapped = map_headers(headers, source)
    rows, quarantined = [], []
    for lineno, vals in enumerate(values, start=2):
        row = normalise_row(vals, mapping)
        ok, reason = validate_row(row)
        if ok:
            rows.append(row)
        else:
            quarantined.append({"source_row": lineno, "reason": reason})
    return {"source": source, "mapping": mapping, "unmapped": unmapped,
            "rows": rows, "quarantined": quarantined}
