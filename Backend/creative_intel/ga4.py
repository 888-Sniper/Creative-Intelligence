"""Google Analytics 4 read-only retrieval.

Uses the connected employee's GA4 OAuth token (analytics.readonly)
against the Data API runReport endpoint. Rows land in ga4_rows —
kept apart from ad facts. Website sessions are never presented as
ad-level creative metrics; any join to campaigns needs explicit,
defensible attribution, which this module does not perform.
"""

import datetime
import json
import urllib.request

DATA_API = "https://analyticsdata.googleapis.com/v1beta"
ADMIN_API = "https://analyticsadmin.googleapis.com/v1beta"


class Ga4Unavailable(Exception):
    pass


def _get(url, token):
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except Exception as exc:
        raise Ga4Unavailable("GA4 request failed: %s" % exc)


def _post(url, token, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except Exception as exc:
        raise Ga4Unavailable("GA4 request failed: %s" % exc)


def list_properties(token):
    """Authorised GA4 properties for the connected account."""
    if not token:
        raise Ga4Unavailable("Google Analytics 4 is not connected.")
    got = _get(ADMIN_API + "/accountSummaries?pageSize=200", token)
    out = []
    for account in got.get("accountSummaries") or []:
        for prop in account.get("propertySummaries") or []:
            name = str(prop.get("property") or "")
            out.append({
                "property_id": name.replace("properties/", ""),
                "display_name": prop.get("displayName") or name,
                "account": account.get("displayName") or ""})
    return out


def fetch_rows(token, property_id, start_date, end_date):
    """Daily source/medium rows. Validates ids and dates strictly."""
    if not token:
        raise Ga4Unavailable("Google Analytics 4 is not connected.")
    pid = str(property_id or "").replace("properties/", "").strip()
    if not pid.isdigit():
        raise Ga4Unavailable("GA4 property id must be numeric.")
    for value in (start_date, end_date):
        try:
            datetime.date.fromisoformat(str(value))
        except ValueError:
            raise Ga4Unavailable("GA4 dates must be YYYY-MM-DD.")
    if str(start_date) > str(end_date):
        raise Ga4Unavailable("GA4 start date is after end date.")
    # Page through runReport with offset until rowCount is covered:
    # a single capped page must never masquerade as a complete import.
    page_size = 10000
    raw_rows = []
    timezone = ""
    offset = 0
    while True:
        payload = {
            "dateRanges": [{"startDate": str(start_date),
                            "endDate": str(end_date)}],
            "dimensions": [{"name": "date"}, {"name": "sessionSource"},
                           {"name": "sessionMedium"},
                           {"name": "sessionCampaignName"}],
            "metrics": [{"name": "sessions"}, {"name": "totalUsers"},
                        {"name": "conversions"}],
            "limit": page_size,
            "offset": offset,
        }
        got = _post("%s/properties/%s:runReport" % (DATA_API, pid),
                    token, payload)
        if not timezone:
            timezone = ((got.get("metadata") or {}).get("timeZone") or "")
        batch = got.get("rows") or []
        raw_rows.extend(batch)
        total = got.get("rowCount")
        try:
            total = int(total) if total is not None else None
        except (TypeError, ValueError):
            total = None
        if not batch or len(batch) < page_size:
            break
        if total is not None and len(raw_rows) >= total:
            break
        offset += len(batch)
        if offset > 250000:  # hard stop: never loop unbounded
            raise Ga4Unavailable(
                "GA4 result exceeds the 250000-row import cap; "
                "narrow the date range.")
    rows = []
    for row in raw_rows:
        dims = [d.get("value", "") for d in row.get("dimensionValues") or []]
        mets = [m.get("value", "0") for m in row.get("metricValues") or []]
        raw_date = dims[0] if dims else ""
        iso = ("%s-%s-%s" % (raw_date[:4], raw_date[4:6], raw_date[6:8])
               if len(raw_date) == 8 else raw_date)
        rows.append({
            "date": iso,
            "session_source": dims[1] if len(dims) > 1 else "",
            "session_medium": dims[2] if len(dims) > 2 else "",
            "session_campaign": dims[3] if len(dims) > 3 else "",
            "sessions": int(float(mets[0])) if mets else 0,
            "total_users": int(float(mets[1])) if len(mets) > 1 else 0,
            "conversions": float(mets[2]) if len(mets) > 2 else 0.0,
            "timezone": timezone})
    return rows


def import_rows(conn, token, property_id, start_date, end_date,
                imported_by):
    """Fetch + upsert. Repeat imports update in place (no duplicates)."""
    rows = fetch_rows(token, property_id, start_date, end_date)
    pid = str(property_id).replace("properties/", "")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for row in rows:
        conn.execute(
            "INSERT INTO ga4_rows (property_id, date, session_source,"
            " session_medium, session_campaign, sessions, total_users,"
            " conversions, timezone, imported_by, imported_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (property_id, date, session_source,"
            " session_medium, session_campaign) DO UPDATE SET"
            " sessions=excluded.sessions,"
            " total_users=excluded.total_users,"
            " conversions=excluded.conversions,"
            " timezone=excluded.timezone,"
            " imported_by=excluded.imported_by,"
            " imported_at=excluded.imported_at",
            (pid, row["date"], row["session_source"],
             row["session_medium"], row["session_campaign"],
             row["sessions"], row["total_users"], row["conversions"],
             row["timezone"], imported_by, now))
    conn.commit()
    return {"property_id": pid, "rows": len(rows),
            "note": "GA4 website analytics only — not ad-level "
                    "creative metrics. No campaign attribution was "
                    "applied."}
