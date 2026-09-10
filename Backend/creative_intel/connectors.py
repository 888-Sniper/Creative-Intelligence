"""External data connectors: Sheets/Drive links, Meta/TikTok APIs.

Everything here degrades honestly:

- Public Google Sheets / Drive links need no auth and are fetched
  over plain HTTPS (stdlib urllib). Private files need OAuth, which is
  parked: the connector says so instead of failing cryptically.
- Meta Marketing API and TikTok Business API need tokens. Tokens come
  from CREATIVE_INTEL_KEY_META / CREATIVE_INTEL_KEY_TIKTOK env vars or
  macOS Keychain (creative-intel-meta / creative-intel-tiktok) and are
  never logged, stored, or returned. Without a token the connector
  raises instead of returning invented rows.
- API rows are converted to CSV text with canonical headers and flow
  through the normal strict ingest pipeline (aliases, quarantine).

ConnectorUnavailable subclasses ValueError so the HTTP layer maps it
to a 409 product message, matching every other failed action.
"""

import json
import os
import re
import urllib.parse
import urllib.request

MAX_FETCH_BYTES = 10 * 1024 * 1024
FETCH_TIMEOUT_S = 30.0
MAX_API_PAGES = 50


class ConnectorUnavailable(ValueError):
    pass


def _https_only(url):
    try:
        scheme = urllib.parse.urlparse(url).scheme.lower()
    except Exception:
        scheme = ""
    if scheme not in ("http", "https"):
        raise ConnectorUnavailable("only http(s) URLs can be fetched")
    return url


def fetch_bytes(url, timeout=FETCH_TIMEOUT_S, headers=None):
    _https_only(url)
    merged = {"User-Agent": "FoapCI/1.0"}
    merged.update(headers or {})
    req = urllib.request.Request(url, headers=merged)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            chunks, total = [], 0
            while True:
                part = resp.read(65536)
                if not part:
                    break
                total += len(part)
                if total > MAX_FETCH_BYTES:
                    raise ConnectorUnavailable("remote file exceeds %d MB"
                                               % (MAX_FETCH_BYTES // (1024 * 1024)))
                chunks.append(part)
            return b"".join(chunks)
    except ConnectorUnavailable:
        raise
    except Exception as e:
        raise ConnectorUnavailable("fetch failed for %s: %s"
                                   % (_host_of(url), e))


def fetch_text(url, timeout=FETCH_TIMEOUT_S, headers=None):
    raw = fetch_bytes(url, timeout, headers)
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except ValueError:
            continue
    raise ConnectorUnavailable("could not decode remote file as text")


def _host_of(url):
    try:
        return urllib.parse.urlparse(url).netloc or "remote host"
    except Exception:
        return "remote host"


def sheets_csv_url(url):
    """Normalise any Google Sheets link to its CSV export URL."""
    _https_only(url)
    if "docs.google.com/spreadsheets" not in url:
        # Plain CSV link (published Sheets output=csv included): as-is.
        return url
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", url)
    if not match:
        raise ConnectorUnavailable("not a recognisable Sheets URL")
    sheet_id = match.group(1)
    parts = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parts.query)
    if "gid" not in query:
        # Real Sheets links carry the tab in the fragment (#gid=…).
        query = urllib.parse.parse_qs(parts.fragment)
    gid = (query.get("gid") or ["0"])[0]
    return ("https://docs.google.com/spreadsheets/d/%s/export"
            "?format=csv&gid=%s" % (sheet_id, gid))


def drive_file_url(url):
    """Normalise a Drive share link to its direct-download URL."""
    _https_only(url)
    if "drive.google.com" not in url:
        return url
    match = re.search(r"/file/d/([A-Za-z0-9_-]+)", url)
    if match:
        return ("https://drive.google.com/uc?export=download&id=%s"
                % match.group(1))
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if query.get("id"):
        return ("https://drive.google.com/uc?export=download&id=%s"
                % query["id"][0])
    return url


def fetch_sheet_csv(url, bearer=None):
    """Fetch a Sheets/CSV URL; refuses login pages and binaries.

    Pass bearer="..." for private sheets (Google OAuth, item 31).
    Without it a private file raises ConnectorUnavailable pointing at
    Settings > Google Drive instead of a parked-OAuth dead end.
    """
    text = fetch_text(sheets_csv_url(url),
                      headers={"Authorization": "Bearer %s" % bearer}
                      if bearer else None)
    stripped = text.lstrip()
    if stripped[:15].lower().startswith("<!doctype html") or \
            stripped[:5].lower().startswith("<html"):
        hint = ("Connect Google Drive in Settings and retry with "
                "Google auth enabled." if bearer is None else
                "Revoke and reconnect Google Drive in Settings.")
        raise ConnectorUnavailable(
            "Google returned a login/confirm page: the file is private "
            "or needs virus-scan confirmation. %s Publish the sheet "
            "(File > Share > Publish to web, CSV) also works." % hint)
    if "," not in text and "\n" not in text.strip():
        raise ConnectorUnavailable("remote file does not look like CSV")
    return text


def token_for(name):
    """Platform token: env override else Keychain. Never logs the value."""
    from . import providers
    service = "creative-intel-" + name
    env = os.environ.get(
        "CREATIVE_INTEL_KEY_" + name.upper().replace("-", "_"))
    if env:
        return env
    secret = providers.live_secret(service)
    if not secret:
        raise ConnectorUnavailable(
            "no %s token: set %s or store it in Keychain service %s" % (
                name, "CREATIVE_INTEL_KEY_" + name.upper(), service))
    return secret


def api_base(name, default):
    return (os.environ.get("CREATIVE_INTEL_API_" + name.upper()) or default)


def _api_json(url, token=None, payload=None, headers=None):
    heads = dict(headers or {})
    if token:
        heads["Authorization"] = "Bearer " + token
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=heads,
                                 method="POST" if data else "GET")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except Exception as e:
        code = getattr(e, "code", "?")
        raise ConnectorUnavailable("platform API error (HTTP %s)" % code)


META_VERSION = "v21.0"
META_FIELDS = ("campaign_name,adset_name,ad_name,spend,impressions,"
               "clicks,actions,action_values,video_play_actions")
# Purchase-flavoured action types counted as conversions; the same set
# is summed from action_values as revenue (purchase value).
META_PURCHASE_TYPES = ("purchase", "offsite_conversion",
                       "onsite_conversion.purchase")


def meta_insights_csv(ad_account_id, since, until):
    """Meta Marketing API -> canonical CSV text. ad_account_id without act_."""
    token = token_for("meta")
    if not ad_account_id or not str(ad_account_id).strip():
        raise ConnectorUnavailable("meta needs an ad account id")
    base = api_base("meta", "https://graph.facebook.com").rstrip("/")
    params = urllib.parse.urlencode({
        "fields": META_FIELDS,
        "time_range": json.dumps({"since": since, "until": until}),
        # Daily breakdown: without time_increment the API returns one
        # aggregate row per ad with no date, which makes period analysis
        # from direct API data impossible.
        "time_increment": 1,
        "limit": 500,
        "access_token": token,
    })
    url = "%s/%s/act_%s/insights?%s" % (
        base, META_VERSION, str(ad_account_id).strip(), params)
    data_rows = []
    seen_pages = 0
    while url and seen_pages < MAX_API_PAGES:
        got = _api_json(url)
        if isinstance(got.get("error"), dict):
            raise ConnectorUnavailable("meta: %s" % got["error"].get("message"))
        data_rows.extend(got.get("data", []) or [])
        # Follow Graph paging cursors so accounts with more than one
        # results page are never silently truncated.
        nxt = (got.get("paging") or {}).get("next")
        if nxt and not str(nxt).startswith("http"):
            nxt = urllib.parse.urljoin(url, str(nxt))
        url = nxt
        seen_pages += 1
    lines = ["Campaign,Ad Set,Ad Name,Spend,Impressions,Clicks,"
             "Conversions,Video Views,Date,Revenue"]
    for row in data_rows:
        conv = 0.0
        for action in row.get("actions", []) or []:
            if action.get("action_type") in META_PURCHASE_TYPES:
                try:
                    conv += float(action.get("value", 0))
                except (TypeError, ValueError):
                    continue
        # Revenue only when the API actually returned action_values;
        # otherwise the cell stays blank (unavailable, never invented).
        if "action_values" in row:
            revenue = 0.0
            for action in row.get("action_values", []) or []:
                if action.get("action_type") in META_PURCHASE_TYPES:
                    try:
                        revenue += float(action.get("value", 0))
                    except (TypeError, ValueError):
                        continue
            revenue_cell = _num(revenue)
        else:
            revenue_cell = ""
        lines.append(",".join(_csv_cell(row.get(k, "")) for k in
                              ("campaign_name", "adset_name", "ad_name",
                               "spend", "impressions", "clicks")) +
                     ",%s,%s,%s,%s" % (_num(conv), _num(_views(row)),
                                       _csv_cell(row.get("date_start", "")),
                                       revenue_cell))
    return "\n".join(lines) + "\n"


def _views(row):
    plays = row.get("video_play_actions")
    if isinstance(plays, list) and plays:
        try:
            return float(plays[0].get("value", 0))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _num(value):
    try:
        return repr(float(value))
    except (TypeError, ValueError):
        return "0"


def _csv_cell(value):
    text = "" if value is None else str(value)
    if any(c in text for c in (",", '"', "\n")):
        return '"%s"' % text.replace('"', '""')
    return text


TIKTOK_FIELDS = ("campaign_id", "adgroup_id", "ad_id", "spend",
                 "impressions", "clicks", "conversion", "video_views")
# Value metric requested alongside the base set so Revenue is genuine
# API data, not an assumption. If the API ever rejects it, the fetch
# retries once with the base metrics and revenue stays unavailable.
TIKTOK_VALUE_METRICS = ("roas",)


def tiktok_report_csv(advertiser_id, start_date, end_date):
    """TikTok Business API integrated report -> canonical CSV text."""
    token = token_for("tiktok")
    if not advertiser_id or not str(advertiser_id).strip():
        raise ConnectorUnavailable("tiktok needs an advertiser id")
    base = api_base("tiktok", "https://business-api.tiktok.com").rstrip("/")
    url = base + "/open_api/v1.3/report/integrated/get/"
    dims = ["campaign_id", "adgroup_id", "ad_id", "stat_time_day"]
    metrics = list(TIKTOK_FIELDS[3:]) + list(TIKTOK_VALUE_METRICS)
    try:
        rows = _tiktok_pages(url, token, advertiser_id, start_date,
                             end_date, dims, metrics)
    except _MetricRejected:
        # The value metric is not accepted by this API version:
        # fall back to base metrics; revenue stays unavailable.
        rows = _tiktok_pages(url, token, advertiser_id, start_date,
                             end_date, dims, list(TIKTOK_FIELDS[3:]))
    # Revenue is genuine API data only: an explicit purchase-value
    # metric when the API returns one, else roas x spend (both TikTok
    # figures, so the implied revenue matches TikTok's own ROAS).
    # Otherwise the cell stays blank, which ingest records as
    # revenue_reported=False (unavailable, never invented).
    lines = ["Campaign,Ad Set,Ad Name,Spend,Impressions,Clicks,"
             "Conversions,Video Views,Date,Revenue"]
    for row in rows:
        dims = row.get("dimensions") or {}
        mets = row.get("metrics") or {}
        value = mets.get("purchase_value", mets.get("total_purchase_value",
                         mets.get("shop_revenue", "")))
        if value == "":
            value = _roas_revenue(mets)
        cells = [dims.get("campaign_id", ""), dims.get("adgroup_id", ""),
                 dims.get("ad_id", ""), _num(mets.get("spend")),
                 _num(mets.get("impressions")), _num(mets.get("clicks")),
                 _num(mets.get("conversion")), _num(mets.get("video_views")),
                 _csv_cell(dims.get("stat_time_day", "")),
                 _num(value) if value != "" else ""]
        lines.append(",".join(_csv_cell(c) for c in cells))
    return "\n".join(lines) + "\n"


class _MetricRejected(Exception):
    """The API refused the requested value metric (retry with base)."""


def _tiktok_pages(url, token, advertiser_id, start_date, end_date,
                  dimensions, metrics):
    rows = []
    page = 1
    while page <= MAX_API_PAGES:
        payload = {
            "advertiser_id": str(advertiser_id).strip(),
            "report_type": "BASIC",
            # stat_time_day gives the daily breakdown backing the Date
            # column; without it every row is range-aggregate and period
            # analysis is impossible.
            "dimensions": dimensions,
            "metrics": metrics,
            "start_date": start_date,
            "end_date": end_date,
            "page": page,
            "page_size": 500,
        }
        got = _api_json(url, token=None, payload=payload,
                        headers={"Access-Token": token})
        if got.get("code", 0) != 0:
            message = str(got.get("message") or "")
            lowered = message.lower()
            if ("metric" in lowered or "field" in lowered
                    or "invalid" in lowered or "param" in lowered):
                raise _MetricRejected(message)
            raise ConnectorUnavailable("tiktok: %s" % got.get("message"))
        data = got.get("data") or {}
        chunk = data.get("list") or []
        rows.extend(chunk)
        # Keep requesting pages until the report is complete: stop on
        # a short page, or once total_number is covered.
        info = data.get("page_info") or {}
        total = info.get("total_number")
        size = info.get("page_size") or 500
        if total is not None:
            if page * size >= total:
                break
        elif len(chunk) < size:
            break
        page += 1
    return rows


def _roas_revenue(mets):
    """Implied revenue from the API's own roas x spend, or ''."""
    try:
        roas = float(mets.get("roas", ""))
        spend = float(mets.get("spend", ""))
    except (TypeError, ValueError):
        return ""
    if spend > 0 and roas >= 0:
        return repr(round(roas * spend, 2))
    return ""
