"""Server-persisted employee preferences + notification delivery.

Preferences live server-side (employee_prefs) so defaults and
notification opt-ins follow the account, not one browser. Email
delivery goes through an outbox: every notification is recorded
with a truthful status. Without SMTP configuration the status is
"blocked" with the exact missing setting named — delivery is never
reported as sent when it was not.

SMTP settings (env): CREATIVE_INTEL_SMTP_HOST, _PORT (default 587),
_USER, _PASSWORD (or Keychain creative-intel-smtp), _FROM.
Triggers: report_generated (Email Reports), campaign_import
(Campaign Updates), analysis_ready (AI Insights). Product Updates
has no automatic trigger in this build; it is recorded as such.
"""

import datetime
import json
import os
import uuid

PREF_KEYS = {
    "workspace", "default_view", "default_currency", "default_date_range",
    "default_campaign_view", "theme", "accent", "density", "language",
    "timezone", "email_reports", "campaign_updates", "ai_insights",
    "product_updates", "data_usage", "share_analytics", "retention",
}

NOTIFY_KINDS = {
    "report_generated": "email_reports",
    "campaign_import": "campaign_updates",
    "analysis_ready": "ai_insights",
    "product_update": "product_updates",
}


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def get_prefs(conn, employee_id):
    row = conn.execute(
        "SELECT prefs_json FROM employee_prefs WHERE employee_id=?",
        (employee_id,)).fetchone()
    if not row:
        return {}
    try:
        data = json.loads(row[0] or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


class StalePreferenceRevision(ValueError):
    """A save whose base version is older than the stored version.

    Carries the CURRENT stored prefs so the API can return them
    with the 409 and the client can reconcile (re-apply its own
    changed keys on the fresh base) instead of silently losing
    the edit while reporting success."""

    def __init__(self, current):
        super().__init__("preferences changed since they were loaded")
        self.current = current


def save_prefs(conn, employee_id, prefs, base_revision=None):
    """Merge-save preferences with a SERVER-ISSUED version.

    The server owns `_rev`: every accepted save increments it and
    returns the new value. Clients echo the version of the
    snapshot they edited as `base_revision`. A write whose base
    is older than the current version is stale (another tab or a
    pre-reset edit landed first): it raises
    StalePreferenceRevision — an explicit conflict the caller
    must reconcile, never a silent drop reported as success.
    Unknown base (None) accepts — first contact after a GET is
    the normal bootstrap path."""
    if not employee_id:
        raise ValueError("preferences need an employee")
    if not isinstance(prefs, dict):
        raise ValueError("preferences must be an object")
    clean = {k: prefs[k] for k in prefs if k in PREF_KEYS}
    existing = get_prefs(conn, employee_id)
    current = existing.get("_rev")
    current = current if isinstance(current, int) else 0
    if base_revision is not None:
        try:
            base_revision = int(base_revision)
        except (TypeError, ValueError):
            raise ValueError("base_revision must be an integer")
        if base_revision < current:
            raise StalePreferenceRevision(existing)
    clean["_rev"] = current + 1
    merged = {**existing, **clean}
    conn.execute(
        "INSERT INTO employee_prefs (employee_id, prefs_json, updated_at)"
        " VALUES (?, ?, ?) ON CONFLICT (employee_id) DO UPDATE SET"
        " prefs_json=excluded.prefs_json, updated_at=excluded.updated_at",
        (employee_id, json.dumps(merged, sort_keys=True), _now()))
    conn.commit()
    return merged


def smtp_blocker():
    """None when SMTP delivery is configured, else the exact gap."""
    if not os.environ.get("CREATIVE_INTEL_SMTP_HOST"):
        return "CREATIVE_INTEL_SMTP_HOST is not configured"
    if not os.environ.get("CREATIVE_INTEL_SMTP_FROM"):
        return "CREATIVE_INTEL_SMTP_FROM is not configured"
    return None


def _send_smtp(to_addr, subject, body):
    import smtplib
    from email.message import EmailMessage

    from creative_intel.providers import live_secret
    host = os.environ["CREATIVE_INTEL_SMTP_HOST"]
    port = int(os.environ.get("CREATIVE_INTEL_SMTP_PORT") or 587)
    user = os.environ.get("CREATIVE_INTEL_SMTP_USER") or ""
    password = (os.environ.get("CREATIVE_INTEL_SMTP_PASSWORD")
                or live_secret("creative-intel-smtp") or "")
    msg = EmailMessage()
    msg["From"] = os.environ["CREATIVE_INTEL_SMTP_FROM"]
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(host, port, timeout=20) as server:
        server.starttls()
        if user:
            server.login(user, password)
        server.send_message(msg)


def enqueue(conn, employee_id, kind, subject, body, dedup_key="",
            recipient="", sender=None):
    """Record + attempt one notification, honouring the opt-in.

    Returns the outbox row dict. Opted-out kinds are recorded as
    skipped (visible, never sent). sender is injectable for tests.
    """
    if kind not in NOTIFY_KINDS:
        raise ValueError("unknown notification kind %r" % (kind,))
    if dedup_key:
        existing = conn.execute(
            "SELECT id, status FROM notification_outbox WHERE dedup_key=?",
            (dedup_key,)).fetchone()
        if existing:
            return {"id": existing[0], "status": existing[1],
                    "duplicate": True}
    prefs = get_prefs(conn, employee_id)
    opt_in = prefs.get(NOTIFY_KINDS[kind])
    nid = uuid.uuid4().hex
    now = _now()
    # Claim the dedup slot BEFORE any send: the unique index is the
    # lock, so two concurrent calls with the same key cannot both
    # deliver. The loser returns as a duplicate without sending.
    try:
        conn.execute(
            "INSERT INTO notification_outbox (id, employee_id, kind,"
            " subject, body, status, detail, dedup_key, created_at,"
            " sent_at) VALUES (?, ?, ?, ?, ?, 'queued', '', ?, ?, '')",
            (nid, employee_id, kind, subject[:300], body[:5000],
             dedup_key, now))
        conn.commit()
    except Exception:
        conn.rollback()
        if dedup_key:
            row = conn.execute(
                "SELECT id, status FROM notification_outbox"
                " WHERE dedup_key=?", (dedup_key,)).fetchone()
            if row:
                return {"id": row[0], "status": row[1], "duplicate": True}
        raise
    if opt_in is False:
        status, detail, sent_at = "skipped", "opted out", ""
    elif kind == "product_update":
        status = "blocked"
        detail = "no product-update trigger is wired in this build"
        sent_at = ""
    else:
        blocker = smtp_blocker()
        if blocker and sender is None:
            status, detail, sent_at = "blocked", blocker, ""
        elif not recipient:
            status, detail, sent_at = "blocked", "no recipient address", ""
        else:
            try:
                (sender or _send_smtp)(recipient, subject, body)
                status, detail, sent_at = "sent", "", now
            except Exception as exc:
                status, detail, sent_at = "failed", str(exc)[:300], ""
    conn.execute(
        "UPDATE notification_outbox SET status=?, detail=?, sent_at=?"
        " WHERE id=?", (status, detail, sent_at, nid))
    conn.commit()
    return {"id": nid, "status": status, "detail": detail}


def notify_employee(conn, employee_id, kind, subject, body,
                    dedup_key=""):
    """Event trigger entry point: resolve the employee's own email
    and enqueue. Best-effort by design — notification problems must
    never fail the underlying report/import/analysis."""
    try:
        row = conn.execute(
            "SELECT email FROM employees WHERE id=?",
            (employee_id,)).fetchone()
        recipient = (row[0] or "") if row else ""
        return enqueue(conn, employee_id, kind, subject, body,
                       dedup_key=dedup_key, recipient=recipient)
    except Exception:
        return None


def list_outbox(conn, employee_id, limit=50):
    cols = ("id", "kind", "subject", "status", "detail", "created_at",
            "sent_at")
    return [dict(zip(cols, r)) for r in conn.execute(
        "SELECT id, kind, subject, status, detail, created_at, sent_at"
        " FROM notification_outbox WHERE employee_id=?"
        " ORDER BY created_at DESC LIMIT ?",
        (employee_id, int(limit))).fetchall()]
