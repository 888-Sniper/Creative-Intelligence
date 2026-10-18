"""Owner-scoped reusable report templates.

A template is the Reports screen configuration (campaigns, KPIs,
benchmark, format) saved under a name. Templates belong to one
employee; another account never sees them. Applying a template is a
visible UI step that re-checks the saved values against what still
exists — generation itself is unchanged.
"""

import datetime
import json
import uuid

_FORMATS = ("pptx", "xlsx", "one-pager")
_MAX_NAME = 80
_MAX_ITEMS = 200


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def clean_config(config):
    if not isinstance(config, dict):
        raise ValueError("template config must be an object")
    out = {}
    for key in ("campaigns", "kpis"):
        value = config.get(key) or []
        if not isinstance(value, list):
            raise ValueError("template %s must be a list" % key)
        out[key] = [str(v)[:200] for v in value[:_MAX_ITEMS]]
    out["benchmark"] = str(config.get("benchmark") or "")[:64]
    fmt = str(config.get("format") or "pptx").lower()
    if fmt not in _FORMATS:
        raise ValueError("template format must be one of %s"
                         % (list(_FORMATS),))
    out["format"] = fmt
    return out


def _row(row):
    return {"id": row[0], "name": row[1],
            "config": json.loads(row[2] or "{}"),
            "created_at": row[3], "updated_at": row[4]}


def save(conn, owner_id, name, config, template_id=None):
    name = str(name or "").strip()
    if not name or len(name) > _MAX_NAME:
        raise ValueError("template needs a name of 1-80 characters")
    if not owner_id:
        raise ValueError("template needs an owner")
    clean = clean_config(config)
    now = _now()
    tid = template_id or uuid.uuid4().hex
    existing = conn.execute(
        "SELECT id FROM report_templates WHERE id=? AND owner_employee_id=?",
        (tid, owner_id)).fetchone() if template_id else None
    if template_id and existing is None:
        raise ValueError("template not found")
    if existing:
        conn.execute(
            "UPDATE report_templates SET name=?, config_json=?, updated_at=?"
            " WHERE id=? AND owner_employee_id=?",
            (name, json.dumps(clean, sort_keys=True), now, tid, owner_id))
    else:
        conn.execute(
            "INSERT INTO report_templates (id, owner_employee_id, name,"
            " config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (tid, owner_id, name, json.dumps(clean, sort_keys=True),
             now, now))
    conn.commit()
    return get(conn, owner_id, tid)


def get(conn, owner_id, template_id):
    row = conn.execute(
        "SELECT id, name, config_json, created_at, updated_at"
        " FROM report_templates WHERE id=? AND owner_employee_id=?",
        (template_id, owner_id)).fetchone()
    return _row(row) if row else None


def list_mine(conn, owner_id):
    return [_row(r) for r in conn.execute(
        "SELECT id, name, config_json, created_at, updated_at"
        " FROM report_templates WHERE owner_employee_id=?"
        " ORDER BY updated_at DESC, name", (owner_id,)).fetchall()]


def delete(conn, owner_id, template_id):
    cur = conn.execute(
        "DELETE FROM report_templates WHERE id=? AND owner_employee_id=?",
        (template_id, owner_id))
    conn.commit()
    return cur.rowcount > 0
