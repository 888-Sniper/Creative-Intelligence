"""Upload ingest: Meta / TikTok / Excel / Sheets -> canonical ads rows.

- CSV text accepted for every source (Sheets = paste CSV export or URL
  whose text is fetched upstream; Excel = .xlsx when openpyxl is
  installed, otherwise save-as-CSV and upload the text).
- Header matching is case/space-insensitive with common Meta and TikTok
  Ads Manager export aliases.
"""

import csv
import io
import math

CANONICAL_FIELDS = ("platform", "campaign", "adset", "ad_name",
                    "creative_key", "spend", "impressions", "clicks",
                    "conversions", "video_views", "views_25", "views_50",
                    "views_75", "views_100", "client", "project",
                    "vertical", "market", "objective", "funnel_stage",
                    "date", "revenue")

_ALIASES = {
    "platform": {"platform"},
    "campaign": {"campaign", "campaign name"},
    "adset": {"ad set", "adset", "ad set name", "adgroup", "ad group"},
    "ad_name": {"ad", "ad name"},
    "creative_key": {"creative", "creative key", "creative name", "video name"},
    "spend": {"spend", "amount spent", "cost", "spend (usd)"},
    "impressions": {"impressions", "impr."},
    "clicks": {"clicks", "link clicks"},
    "conversions": {"conversions", "results", "purchases"},
    "video_views": {"video views", "video plays", "views"},
    "views_25": {"25% views", "video watches at 25%", "views_25"},
    "views_50": {"50% views", "video watches at 50%", "views_50"},
    "views_75": {"75% views", "video watches at 75%", "views_75"},
    "views_100": {"100% views", "completions", "video watches at 100%", "views_100"},
    "client": {"client", "client name", "account", "account name", "advertiser"},
    "project": {"project", "project name"},
    "vertical": {"vertical", "industry", "category"},
    "market": {"market", "market name", "country", "region", "geo"},
    "objective": {"objective", "campaign objective", "optimization goal",
                  "optimisation goal"},
    "funnel_stage": {"funnel stage", "funnel_stage", "funnel", "stage"},
    "date": {"date", "day", "reporting date", "report date"},
    "revenue": {"revenue", "purchase value", "purchase conversion value",
                "conversion value", "total revenue", "total purchase value",
                "shop revenue"},
}

_NUMERIC = {"spend": float, "impressions": int, "clicks": int,
            "conversions": float, "video_views": int, "views_25": int,
            "views_50": int, "views_75": int, "views_100": int,
            "revenue": float}


def _norm(header):
    return " ".join(header.strip().lower().split())


class _BadValue(ValueError):
    pass


def _to_number(raw, kind):
    """Legacy lenient coercion: blanks and garbage become zero."""
    try:
        cleaned = str(raw).replace(",", "").replace("$", "").replace("%", "").strip()
        if cleaned in ("", "-", "n/a"):
            return kind(0)
        return kind(float(cleaned))
    except (ValueError, TypeError, OverflowError):
        return kind(0)


def _to_number_strict(raw, kind):
    """Strict coercion: blanks become zero, but garbage and non-finite
    values raise _BadValue so the row lands in quarantine with a reason."""
    cleaned = str(raw).replace(",", "").replace("$", "").replace("%", "").strip()
    if cleaned in ("", "-", "n/a"):
        return kind(0)
    try:
        value = kind(float(cleaned))
    except (ValueError, TypeError, OverflowError):
        raise _BadValue("not numeric: %r" % (raw,))
    if isinstance(value, float) and not math.isfinite(value):
        raise _BadValue("non-finite: %r" % (raw,))
    return value


def _rows_from_dicts(fieldnames, dicts, platform, source):
    """Shared strict pipeline: header aliases, quarantine, key fallback."""
    rows, quarantined = [], []
    col_map = {}
    for col in fieldnames:
        for field, aliases in _ALIASES.items():
            if _norm(str(col)) in aliases and field not in col_map:
                col_map[field] = col
    for lineno, raw in enumerate(dicts, start=2):
        if not any(str(v or "").strip() for v in raw.values()):
            continue
        row = {"platform": platform, "source": source}
        bad = None
        for field in CANONICAL_FIELDS:
            if field == "platform":
                continue
            raw_val = raw.get(col_map.get(field, ""), "") if field in col_map else ""
            if raw_val is None:
                raw_val = ""
            if field in _NUMERIC:
                try:
                    row[field] = _to_number_strict(raw_val, _NUMERIC[field])
                except _BadValue as exc:
                    bad = "%s %s" % (field, exc)
                    break
            else:
                row[field] = str(raw_val or "").strip()
        if bad is not None:
            quarantined.append({"source_row": lineno, "reason": bad})
            continue
        if not row["creative_key"]:
            row["creative_key"] = row["ad_name"] or "uncategorised"
        rows.append(row)
    return rows, quarantined


def parse_csv_report(csv_text, platform, source="upload"):
    """Return (rows, quarantined). Quarantined entries carry the 1-based
    source row number (header is row 1) plus a reason. Nothing is silently
    coerced: one bad cell quarantines its row, the rest of the file loads."""
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames or not any(c.strip() for c in reader.fieldnames):
        raise ValueError("empty CSV: no header row found")
    return _rows_from_dicts(reader.fieldnames, list(reader), platform, source)


def parse_xlsx_report(blob, platform, source="upload"):
    """Same contract as parse_csv_report for true .xlsx bytes (stdlib)."""
    from creative_intel import ooxml
    dicts = ooxml.parse_xlsx(blob)
    if not dicts:
        raise ValueError("empty workbook: no data rows found")
    headers = list(dicts[0].keys())
    if not any(str(h or "").strip() for h in headers):
        raise ValueError("empty workbook: no header row found")
    return _rows_from_dicts(headers, dicts, platform, source)


def parse_csv(csv_text, platform, source="upload"):
    """Return a list of canonical ad-row dicts (quarantined rows skipped)."""
    rows, _ = parse_csv_report(csv_text, platform, source)
    return rows


def parse_workbook(path, platform, source="upload"):
    """Parse an .xlsx file when openpyxl is available; else clear error."""
    try:
        import openpyxl
    except ImportError:
        raise ValueError("Excel (.xlsx) needs openpyxl installed, or save-as-CSV "
                         "and upload the CSV text instead") from None
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_vals = next(rows_iter)
    except StopIteration:
        raise ValueError("empty workbook: no header row found")
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["" if c is None else c for c in header_vals])
    for vals in rows_iter:
        writer.writerow(["" if c is None else c for c in vals])
    return parse_csv(buf.getvalue(), platform, source)


def insert_rows(conn, rows):
    defaults = {"client": "", "project": "", "vertical": "", "market": "",
                "objective": "", "funnel_stage": "", "date": "",
                "revenue": 0.0}
    normalised = [dict(defaults, **row) for row in rows]
    conn.executemany(
        "INSERT INTO ads (platform, source, campaign, adset, ad_name, creative_key,"
        " spend, impressions, clicks, conversions, video_views,"
        " views_25, views_50, views_75, views_100,"
        " client, project, vertical, market, objective, funnel_stage,"
        " date, revenue)"
        " VALUES (:platform, :source, :campaign, :adset, :ad_name, :creative_key,"
        " :spend, :impressions, :clicks, :conversions, :video_views,"
        " :views_25, :views_50, :views_75, :views_100,"
        " :client, :project, :vertical, :market, :objective, :funnel_stage,"
        " :date, :revenue)", normalised)
    rows = normalised
    for row in rows:
        conn.execute(
            "INSERT OR IGNORE INTO creatives (creative_key, platform, name)"
            " VALUES (?, ?, ?)",
            (row["creative_key"], row["platform"], row["ad_name"]))
    conn.commit()
    return len(rows)
