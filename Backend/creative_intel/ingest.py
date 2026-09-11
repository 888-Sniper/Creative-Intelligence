"""Upload ingest: Meta / TikTok / Excel / Sheets -> canonical ads rows.

- CSV text accepted for every source (Sheets = paste CSV export or URL
  whose text is fetched upstream; Excel = .xlsx when openpyxl is
  installed, otherwise save-as-CSV and upload the text).
- Header matching is case/space-insensitive with common Meta and TikTok
  Ads Manager export aliases.
"""

import csv
import hashlib
import io
import math
import re
import unicodedata

#: Media-safe creative-key alphabet (mirrors media.KEY_RE; kept local
#: so ingest never imports the media layer).
_SAFE_KEY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


def safe_creative_key(name):
    """Deterministic media-safe asset id for a human ad/creative name.

    Names already in the safe alphabet (plus "uncategorised") pass
    through unchanged, so every existing key keeps working. Anything
    else — spaces, accents, non-Latin scripts — is slugified with a
    content-hash suffix, so "Summer Hook 01" becomes an uploadable key
    instead of an analytics-only ghost, and distinct names can never
    share one key.
    """
    text = (name or "").strip() or "uncategorised"
    if _SAFE_KEY_RE.fullmatch(text):
        return text
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-",
                  unicodedata.normalize("NFKD", text).encode(
                      "ascii", "ignore").decode("ascii")).strip("-_")
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return "%s-%s" % (slug[:60] or "creative", digest)

CANONICAL_FIELDS = ("platform", "campaign", "adset", "ad_name",
                    "creative_key", "spend", "impressions", "clicks",
                    "conversions", "video_views", "views_25", "views_50",
                    "views_75", "views_100", "client", "project",
                    "vertical", "market", "objective", "funnel_stage",
                    "date", "revenue",
                    # Foap Analyst measurement families (spec section 4).
                    "account_id", "campaign_id", "ad_id", "reach",
                    "frequency", "currency", "video_starts", "views_2s",
                    "views_3s", "views_6s", "watch_time_total_s",
                    "watch_time_basis", "avg_watch_per_view_s",
                    "avg_watch_per_user_s", "link_clicks",
                    "conversion_event", "attribution", "likes",
                    "comments", "shares", "saves", "creator", "concept",
                    "format", "message_class", "promotion", "placement",
                    "audience")

_ALIASES = {
    "platform": {"platform"},
    "campaign": {"campaign", "campaign name", "kampania"},
    "adset": {"ad set", "adset", "ad set name", "adgroup", "ad group",
              "grupa reklam", "zestaw reklam"},
    "ad_name": {"ad", "ad name", "reklama", "nazwa reklamy"},
    "creative_key": {"creative", "creative key", "creative name",
                     "video name", "kreacja", "nazwa kreacji"},
    "spend": {"spend", "amount spent", "cost", "spend (usd)",
              "wydatek", "wydatki", "koszt", "kwota wydana"},
    "impressions": {"impressions", "impr.", "wyswietlenia"},
    "clicks": {"clicks", "link clicks", "klikniecia"},
    "conversions": {"conversions", "results", "purchases", "konwersje"},
    "video_views": {"video views", "video plays", "views", "odtworzenia",
                    "odtworzenia wideo"},
    "views_25": {"25% views", "video watches at 25%", "views_25"},
    "views_50": {"50% views", "video watches at 50%", "views_50"},
    "views_75": {"75% views", "video watches at 75%", "views_75"},
    "views_100": {"100% views", "completions", "video watches at 100%", "views_100"},
    "client": {"client", "client name", "account", "account name",
               "advertiser", "klient"},
    "project": {"project", "project name"},
    "vertical": {"vertical", "industry", "category"},
    "market": {"market", "market name", "country", "region", "geo",
               "rynek", "kraj"},
    "objective": {"objective", "campaign objective", "optimization goal",
                  "optimisation goal", "cel", "cel kampanii"},
    "funnel_stage": {"funnel stage", "funnel_stage", "funnel", "stage"},
    "date": {"date", "day", "reporting date", "report date", "data",
             "dzien"},
    "revenue": {"revenue", "purchase value", "purchase conversion value",
                "conversion value", "total revenue", "total purchase value",
                "shop revenue", "przychod", "wartosc konwersji"},
    "currency": {"currency", "waluta"},
    "account_id": {"account id", "account_id", "ad account", "advertiser id"},
    "campaign_id": {"campaign id", "campaign_id", "id kampanii"},
    "ad_id": {"ad id", "ad_id", "id reklamy"},
    "reach": {"reach", "unique reach", "zasieg"},
    "frequency": {"frequency", "avg frequency", "czestotliwosc"},
    "video_starts": {"video starts", "starts", "video plays (start)",
                     "rozpoczecia", "starty wideo",
                     "odtworzenia (rozpoczecie)"},
    "views_2s": {"2s views", "2-second views", "2 second views",
                 "wyswietlenia 2s", "wyswietlenia 2 s", "odtworzenia 2 s",
                 "odslony 2 s", "odslony 2s", "2s video views"},
    "views_3s": {"3s views", "3-second views", "3 second views",
                 "wyswietlenia 3s", "wyswietlenia 3 s", "odtworzenia 3 s",
                 "odslony 3 s", "odslony 3s", "3s video views"},
    "views_6s": {"6s views", "6-second views", "6 second views",
                 "wyswietlenia 6s", "wyswietlenia 6 s", "odtworzenia 6 s",
                 "odslony 6 s", "odslony 6s", "6s video views"},
    "watch_time_total_s": {"watch time", "total watch time",
                           "total watch time (s)", "czas ogladania",
                           "calkowity czas ogladania"},
    "watch_time_basis": {"watch time basis", "podstawa czasu ogladania"},
    "avg_watch_per_view_s": {"avg watch time", "average watch time",
                             "average play time per video view",
                             "sr czas ogladania",
                             "sredni czas odtworzenia"},
    "avg_watch_per_user_s": {"average play time per user",
                             "avg watch per user",
                             "sr czas na uzytkownika"},
    "link_clicks": {"link clicks", "destination clicks", "outbound clicks",
                    "klikniecia linku", "klikniecia w link"},
    "conversion_event": {"conversion event", "conversion name",
                         "zdarzenie konwersji"},
    "attribution": {"attribution", "attribution window", "atrybucja"},
    "likes": {"likes", "polubienia"},
    "comments": {"comments", "komentarze"},
    "shares": {"shares", "udostepnienia"},
    "saves": {"saves", "zapisania"},
    "creator": {"creator", "tworca", "autor"},
    "concept": {"concept", "angle", "koncept", "koncepcja"},
    "format": {"creative format", "format kreacji"},
    "message_class": {"message", "message class", "message type",
                      "rodzaj przekazu", "typ komunikatu",
                      "klasa przekazu"},
    "promotion": {"promotion", "promocja", "promo"},
    "placement": {"placement", "umiejscowienie"},
    "audience": {"audience", "odbiorcy", "grupa docelowa"},
}

_NUMERIC = {"spend": float, "impressions": int, "clicks": int,
            "conversions": float, "video_views": int, "views_25": int,
            "views_50": int, "views_75": int, "views_100": int,
            "revenue": float, "reach": int, "frequency": float,
            "video_starts": int, "views_2s": int, "views_3s": int,
            "views_6s": int, "watch_time_total_s": float,
            "avg_watch_per_view_s": float, "avg_watch_per_user_s": float,
            "link_clicks": int, "likes": int, "comments": int,
            "shares": int, "saves": int}


def _norm(header):
    """Lowercase/whitespace/diacritics-insensitive header key."""
    text = " ".join(str(header).strip().lower().split())
    # ł/Ł have no NFKD decomposition; fold them explicitly first.
    text = text.replace("ł", "l").replace("Ł", "l")
    folded = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


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


_CURRENCY_TOKENS = ("zł", "pln", "$", "€", "eur", "usd", "£", "gbp")

_AMBIGUOUS_COMMA = re.compile(r"^[+-]?\d+,\d{1,2}$")


def detect_locale(fieldnames, sample_dicts, delimiter=""):
    """Detect (locale, delimiter) for a report.

    Polish signals: semicolon delimiter, Polish header words, or
    decimal-comma values (``1,18``). Defaults to ("en", delimiter or
    ","). Detection never raises; ambiguity is resolved per value
    below, never by silent guessing.
    """
    heads = [_norm(c) for c in (fieldnames or [])]
    pl_heads = {"kampania", "kreacja", "wyswietlenia", "wydatek", "wydatki",
                "koszt", "zasieg", "data", "dzien", "rynek", "klient",
                "cel", "przychod", "waluta", "tworca", "koncept"}
    score = sum(1 for h in heads if h in pl_heads)
    if delimiter == ";" or score >= 2:
        return "pl", delimiter or ";"
    for row in (sample_dicts or [])[:20]:
        for value in row.values():
            text = str(value or "").strip()
            if _AMBIGUOUS_COMMA.match(text):
                return "pl", delimiter or ","
    return "en", delimiter or ","


def _strip_number_affixes(text):
    cleaned = str(text).replace("\u00a0", " ").strip()
    low = cleaned.lower()
    for token in _CURRENCY_TOKENS:
        low = low.replace(token, "")
    return low.strip()


def _to_number_locale(raw, kind, locale):
    """Locale-aware strict coercion.

    Polish: ``1,18`` is 1.18, ``1 000,50`` and ``1.000,50`` are
    1000.50. English keeps thousands commas (``1,000`` → 1000).
    A comma decimal with 1–2 fraction digits under the English
    locale (``1,18``) is ambiguous — quarantined, never silently
    chosen. Returns (value, was_blank).
    """
    text = _strip_number_affixes(raw).replace(" ", "")
    if text.endswith("%"):
        text = text[:-1]
    if text in ("", "-", "n/a", "brak"):
        return kind(0), True
    if locale == "pl":
        if _AMBIGUOUS_COMMA.match(text):
            text = text.replace(",", ".")
        elif re.match(r"^[+-]?[\d.]+,\d{3}$", text):
            # 1,000 under a Polish file: thousands or decimal?
            # Ambiguous — quarantine rather than guess.
            raise _BadValue("ambiguous number format: %r" % (raw,))
        else:
            text = text.replace(".", "").replace(",", ".") \
                if "," in text else text
    else:
        text = text.replace(",", "")
        # A comma the English path just stripped may have been a
        # decimal comma: re-check the raw shape before accepting.
        raw_text = _strip_number_affixes(raw).replace(" ", "")
        if "," in str(raw) and _AMBIGUOUS_COMMA.match(raw_text):
            raise _BadValue("ambiguous number format: %r (decimal comma"
                            " under English locale?)" % (raw,))
    try:
        value = kind(float(text))
    except (ValueError, TypeError, OverflowError):
        raise _BadValue("not numeric: %r" % (raw,))
    if isinstance(value, float) and not math.isfinite(value):
        raise _BadValue("non-finite: %r" % (raw,))
    return value, False


def _to_number_strict(raw, kind, locale="en"):
    """Strict coercion with locale-aware commas; blanks become zero.

    Blank-ness is reported separately by the caller (missing-data
    tracking), so this keeps its historical (value,) contract.
    """
    value, _ = _to_number_locale(raw, kind, locale)
    return value


def _to_date(raw):
    """Normalize unambiguous localized dates to ISO.

    ISO and dotted day.month.year shapes normalize directly. Slashed
    dates normalize only when the first part exceeds 12 (unambiguous
    day-first); ``01/02/2024`` could be US or EU, so it passes through
    stripped rather than silently choosing. Unknown shapes are labels,
    never quarantine reasons.
    """
    import datetime as _dt
    text = str(raw or "").strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return _dt.datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{2}|\d{4})$", text)
    if m:
        day, mon, year = int(m.group(1)), int(m.group(2)), m.group(3)
        year = int(year) + (2000 if int(year) < 70 else 1900) \
            if len(year) == 2 else int(year)
        if day > 12 >= mon:
            try:
                return _dt.date(year, mon, day).isoformat()
            except ValueError:
                pass
        elif "." in text:
            try:
                return _dt.date(year, mon, day).isoformat()
            except ValueError:
                pass
    return text


def _rows_from_dicts(fieldnames, dicts, platform, source, locale="en"):
    """Shared strict pipeline: header aliases, quarantine, key fallback.

    Blank numerics and unmapped numeric fields land in the row's
    missing list (stored as missing_json) instead of silently
    becoming measured zeros. Returns (rows, quarantined, meta) where
    meta carries locale, the header mapping and unmapped columns.
    """
    rows, quarantined = [], []
    col_map = {}
    normed = {_norm(str(col)): col for col in (fieldnames or [])}
    for field, aliases in _ALIASES.items():
        for alias in aliases:
            for head, col in normed.items():
                if head == alias and field not in col_map:
                    col_map[field] = col
                    break
            if field in col_map:
                break
    mapped_cols = set(col_map.values())
    unmapped = [str(c) for c in (fieldnames or [])
                if str(c).strip() and c not in mapped_cols]
    for lineno, raw in enumerate(dicts, start=2):
        if not any(str(v or "").strip() for v in raw.values()):
            continue
        row = {"platform": platform, "source": source}
        missing = []
        bad = None
        for field in CANONICAL_FIELDS:
            if field == "platform":
                continue
            raw_val = raw.get(col_map.get(field, ""), "") if field in col_map else ""
            if raw_val is None:
                raw_val = ""
            if field in _NUMERIC:
                if field not in col_map:
                    row[field] = _NUMERIC[field](0)
                    missing.append(field)
                    if field == "revenue":
                        row["revenue_reported"] = False
                    continue
                try:
                    value, blank = _to_number_locale(
                        raw_val, _NUMERIC[field], locale)
                    row[field] = value
                    if blank:
                        missing.append(field)
                except _BadValue as exc:
                    bad = "%s %s" % (field, exc)
                    break
                if field == "revenue":
                    row["revenue_reported"] = bool(
                        field in col_map and
                        str(raw_val).strip() not in ("", "-", "n/a"))
            elif field == "date":
                row[field] = _to_date(raw_val)
            else:
                row[field] = str(raw_val or "").strip()
        if bad is not None:
            quarantined.append({"source_row": lineno, "reason": bad})
            continue
        # The stored key is always the safe asset id; the original
        # human name stays in ad_name for display.
        row["creative_key"] = safe_creative_key(
            row["creative_key"] or row["ad_name"])
        import json as _json
        row["missing_json"] = _json.dumps(sorted(set(missing)))
        rows.append(row)
    meta = {"locale": locale,
            "mapping": {field: col_map[field] for field in sorted(col_map)},
            "unmapped": unmapped}
    return rows, quarantined, meta


def _rows_and_quarantine(fieldnames, dicts, platform, source, locale="en"):
    """Two-tuple wrapper preserving the historical parse_* contract."""
    rows, quarantined, _ = _rows_from_dicts(
        fieldnames, dicts, platform, source, locale)
    return rows, quarantined


def _sniff_delimiter(csv_text):
    """Semicolon-delimited Polish exports use ``;``; sniff the header."""
    first = (csv_text or "").splitlines()
    head = first[0] if first else ""
    if head.count(";") > head.count(","):
        return ";"
    return ","


def parse_csv_report(csv_text, platform, source="upload"):
    """Return (rows, quarantined). Quarantined entries carry the 1-based
    source row number (header is row 1) plus a reason. Nothing is silently
    coerced: one bad cell quarantines its row, the rest of the file loads."""
    rows, quarantined, _ = parse_csv_report_ex(csv_text, platform, source)
    return rows, quarantined


def _split_csv(csv_text):
    delimiter = _sniff_delimiter(csv_text)
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)
    if not reader.fieldnames or not any(c.strip() for c in reader.fieldnames):
        raise ValueError("empty CSV: no header row found")
    return reader.fieldnames, list(reader)


def _detect_for_csv(csv_text):
    try:
        fieldnames, dicts = _split_csv(csv_text)
    except ValueError:
        return "en"
    locale, _ = detect_locale(fieldnames, dicts,
                              delimiter=_sniff_delimiter(csv_text))
    return locale


def parse_csv_report_ex(csv_text, platform, source="upload"):
    """Extended contract: (rows, quarantined, meta) with locale,
    header mapping and unmapped columns for import provenance."""
    fieldnames, dicts = _split_csv(csv_text)
    locale, delimiter = detect_locale(fieldnames, dicts,
                                      delimiter=_sniff_delimiter(csv_text))
    rows, quarantined, meta = _rows_from_dicts(
        fieldnames, dicts, platform, source, locale)
    meta["delimiter"] = delimiter
    return rows, quarantined, meta


#: Largest accepted .xlsx payload (decoded bytes).
MAX_XLSX_BYTES = 20 * 1024 * 1024

#: An .xlsx file is a ZIP archive: reject anything else up front.
XLSX_MAGIC = b"PK\x03\x04"


def check_xlsx_blob(blob):
    """Fail-closed gate for uploaded workbooks (size + ZIP magic)."""
    if not isinstance(blob, (bytes, bytearray)) or not blob:
        raise ValueError("empty workbook upload")
    if len(blob) > MAX_XLSX_BYTES:
        raise ValueError("workbook exceeds %d MB"
                         % (MAX_XLSX_BYTES // (1024 * 1024)))
    if not bytes(blob).startswith(XLSX_MAGIC):
        raise ValueError("upload is not an .xlsx workbook")
    return bytes(blob)


def parse_xlsx_report(blob, platform, source="upload"):
    """Same contract as parse_csv_report for true .xlsx bytes (stdlib)."""
    blob = check_xlsx_blob(blob)
    from creative_intel import ooxml
    dicts = ooxml.parse_xlsx(blob)
    if not dicts:
        raise ValueError("empty workbook: no data rows found")
    headers = list(dicts[0].keys())
    if not any(str(h or "").strip() for h in headers):
        raise ValueError("empty workbook: no header row found")
    locale, _ = detect_locale(headers, dicts)
    return _rows_and_quarantine(headers, dicts, platform, source, locale)


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


#: Every ads column the store writes (sync key excluded from
#: updates but included in inserts via explicit SQL below).
STORED_COLUMNS = (
    "platform", "source", "campaign", "adset", "ad_name",
    "creative_key", "spend", "impressions", "clicks", "conversions",
    "video_views", "views_25", "views_50", "views_75", "views_100",
    "client", "project", "vertical", "market", "objective",
    "funnel_stage", "date", "revenue", "revenue_reported",
    "account_id", "campaign_id", "ad_id", "import_id", "reach",
    "frequency", "currency", "video_starts", "views_2s", "views_3s",
    "views_6s", "watch_time_total_s", "watch_time_basis",
    "avg_watch_per_view_s", "avg_watch_per_user_s", "link_clicks",
    "conversion_event", "attribution", "likes", "comments", "shares",
    "saves", "creator", "concept", "format", "message_class",
    "promotion", "placement", "audience", "missing_json")


def _normalise(rows):
    defaults = {"client": "", "project": "", "vertical": "", "market": "",
                "objective": "", "funnel_stage": "", "date": "",
                "revenue": 0.0, "revenue_reported": False,
                "account_id": "", "campaign_id": "", "ad_id": "",
                "import_id": "", "reach": 0, "frequency": 0.0,
                "currency": "", "video_starts": 0, "views_2s": 0,
                "views_3s": 0, "views_6s": 0, "watch_time_total_s": 0.0,
                "watch_time_basis": "", "avg_watch_per_view_s": 0.0,
                "avg_watch_per_user_s": 0.0, "link_clicks": 0,
                "conversion_event": "", "attribution": "", "likes": 0,
                "comments": 0, "shares": 0, "saves": 0, "creator": "",
                "concept": "", "format": "", "message_class": "",
                "promotion": "", "placement": "", "audience": "",
                "missing_json": "[]"}
    return [dict(defaults, **row) for row in rows]


def _insert_sql():
    cols = ", ".join(STORED_COLUMNS)
    vals = ", ".join(":%s" % col for col in STORED_COLUMNS)
    return "INSERT INTO ads (%s) VALUES (%s)" % (cols, vals)


def _store_tail(conn, rows):
    for row in rows:
        conn.execute(
            "INSERT OR IGNORE INTO creatives (creative_key, platform, name)"
            " VALUES (?, ?, ?)",
            (row["creative_key"], row["platform"], row["ad_name"]))
    from creative_intel import retention as retention_mod
    retention_mod.synthesize_from_quartiles(conn)
    conn.commit()


def insert_rows(conn, rows):
    normalised = _normalise(rows)
    conn.executemany(_insert_sql(), normalised)
    _store_tail(conn, normalised)
    return len(normalised)


# Columns refreshed when a re-import hits an existing fact: every
# stored column except the sync key itself, which is the row identity
# and is never overwritten. The exclusion mirrors
# schema.SYNC_KEY_COLUMNS (kept literal here so the constant stays
# import-cycle free).
UPSERT_VALUE_COLUMNS = tuple(
    col for col in STORED_COLUMNS
    if col not in ("source", "platform", "campaign", "adset",
                   "ad_name", "date", "client", "account_id",
                   "campaign_id", "ad_id"))


def upsert_rows(conn, rows):
    """Dedup-aware store for every product import surface.

    Rows matching an existing fact on the sync key update that row's
    metrics (last write wins); genuinely new facts insert. Returns
    {"inserted": n, "updated": m}. insert_rows() stays the raw append
    primitive (refuses exact duplicates via the sync-key index).
    """
    from creative_intel import schema as schema_mod
    key_cols = schema_mod.SYNC_KEY_COLUMNS
    # DROP first (same reason as schema.migrate): a stale narrow
    # index would keep enforcing the old identity.
    conn.execute("DROP INDEX IF EXISTS ads_sync_key")
    conn.execute(
        "CREATE UNIQUE INDEX ads_sync_key ON ads (%s)"
        % ", ".join(key_cols))
    where = " AND ".join("%s=?" % col for col in key_cols)
    update_sql = ("UPDATE ads SET %s WHERE %s" % (
        ", ".join("%s=?" % col for col in UPSERT_VALUE_COLUMNS), where))
    insert_sql = _insert_sql()
    inserted = updated = 0
    normalised = _normalise(rows)
    for row in normalised:
        key_vals = tuple(row[col] for col in key_cols)
        hit = conn.execute(
            "SELECT id FROM ads WHERE %s" % where, key_vals).fetchone()
        if hit is None:
            conn.execute(insert_sql, row)
            inserted += 1
        else:
            conn.execute(
                update_sql,
                tuple(row[col] for col in UPSERT_VALUE_COLUMNS) + key_vals)
            updated += 1
    _store_tail(conn, normalised)
    return {"inserted": inserted, "updated": updated}


def record_import(conn, meta, platform, source="upload", filename="",
                  imported_by="", counts=None):
    """Persist import provenance; stamp + return an import id.

    The id links every stored ads row (import_id) to its original
    column names (mapping_json), unmapped columns, locale and row
    counts — the evidence trail behind every analyst number.
    """
    import datetime as _dt
    import json as _json
    import uuid as _uuid
    import_id = _uuid.uuid4().hex
    counts = counts or {}
    conn.execute(
        "INSERT INTO analyst_imports (id, filename, platform, source,"
        " locale, delimiter, mapping_json, unmapped_json, rows_imported,"
        " rows_quarantined, imported_by, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (import_id, filename, platform, source, meta.get("locale", ""),
         meta.get("delimiter", ""), _json.dumps(meta.get("mapping", {})),
         _json.dumps(meta.get("unmapped", [])),
         counts.get("imported", 0), counts.get("quarantined", 0),
         imported_by,
         _dt.datetime.now(_dt.timezone.utc).isoformat()))
    conn.commit()
    return import_id


def import_report(conn, csv_text, platform, source="upload", filename="",
                  imported_by=""):
    """Full path: parse (locale-aware) -> provenance -> upsert.

    Returns {"import_id", "inserted", "updated", "quarantined",
    "quarantine", "locale", "mapping", "unmapped"}. Re-imports update
    facts instead of duplicating them; quarantined rows never load.
    """
    rows, quarantined, meta = parse_csv_report_ex(
        csv_text, platform, source)
    counts = {"imported": 0, "quarantined": len(quarantined)}
    import_id = record_import(conn, meta, platform, source, filename,
                              imported_by, counts)
    for row in rows:
        row["import_id"] = import_id
    stored = upsert_rows(conn, rows)
    counts["imported"] = stored["inserted"] + stored["updated"]
    conn.execute("UPDATE analyst_imports SET rows_imported=?,"
                 " rows_quarantined=? WHERE id=?",
                 (counts["imported"], counts["quarantined"], import_id))
    conn.commit()
    return {"import_id": import_id, "inserted": stored["inserted"],
            "updated": stored["updated"], "quarantined": len(quarantined),
            "quarantine": quarantined, "locale": meta["locale"],
            "mapping": meta["mapping"], "unmapped": meta["unmapped"]}
