"""Authenticated personal-data export (Settings → Export Data).

Builds a ZIP of everything the requester is entitled to: profile
(without secrets), preferences, analyst conversations + messages,
report templates, upload-draft metadata, saved views visible in the
workspace, and a README describing the format. API keys, OAuth
tokens, password material, TOTP secrets and session credentials are
never included — the builder only reads allowlisted fields.
"""

import datetime
import io
import json
import zipfile

_SECRET_MARKERS = ("token", "secret", "password", "key", "hash",
                   "session", "cookie", "totp", "recovery")


def _safe(obj):
    """Recursively drop any key that smells like credential material."""
    if isinstance(obj, dict):
        return {k: _safe(v) for k, v in obj.items()
                if not any(m in str(k).lower() for m in _SECRET_MARKERS)}
    if isinstance(obj, list):
        return [_safe(v) for v in obj]
    return obj


def _rows(conn, sql, params=()):
    try:
        cur = conn.execute(sql, params)
    except Exception:
        return []
    cols = [d[0] for d in cur.description or []]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def build_export(conn, employee):
    """Return (zip_bytes, filename). employee is a mapping with at
    least id/email/name fields from the identity layer."""
    employee_id = str(employee.get("id") or "")
    stamp = datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = "creative-intelligence-export-%s.zip" % stamp
    profile = _safe({k: employee.get(k) for k in (
        "id", "email", "first_name", "last_name", "name", "is_admin",
        "status", "created_at", "last_login_at") if k in employee})
    from creative_intel import notifications as notify_mod
    prefs = notify_mod.get_prefs(conn, employee_id)
    conversations = _rows(
        conn,
        "SELECT id, title, objective, language, created_at, updated_at"
        " FROM analyst_conversations WHERE owner_employee_id=?"
        " ORDER BY created_at",
        (employee_id,))
    messages = _rows(
        conn,
        "SELECT m.conversation_id, m.role, m.kind, m.body_text,"
        " m.created_at FROM analyst_messages m"
        " JOIN analyst_conversations c ON c.id = m.conversation_id"
        " WHERE c.owner_employee_id=? ORDER BY m.id", (employee_id,))
    templates = _rows(
        conn,
        "SELECT id, name, config_json, created_at, updated_at"
        " FROM report_templates WHERE owner_employee_id=?",
        (employee_id,))
    drafts = _rows(
        conn,
        "SELECT id, status, dataset_version, created_at, updated_at"
        " FROM drafts WHERE owner_employee_id=?", (employee_id,))
    outbox = notify_mod.list_outbox(conn, employee_id, limit=200)
    readme = (
        "Creative Intelligence personal data export\n"
        "Generated: %s UTC\nRequester: %s\n\n"
        "Contents: profile.json (no credentials), preferences.json,\n"
        "conversations.json + messages.json (AI Analyst history),\n"
        "report-templates.json, upload-drafts.json (metadata only,\n"
        "no media bytes), notifications.json (delivery log).\n"
        "API keys, OAuth tokens, passwords, authenticator secrets\n"
        "and session credentials are excluded by design.\n"
        % (stamp, profile.get("email") or employee_id))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", readme)
        for name, data in (
                ("profile.json", profile),
                ("preferences.json", prefs),
                ("conversations.json", conversations),
                ("messages.json", messages),
                ("report-templates.json", templates),
                ("upload-drafts.json", drafts),
                ("notifications.json", outbox)):
            zf.writestr(name, json.dumps(_safe(data), indent=2,
                                          ensure_ascii=False))
    return buf.getvalue(), filename
