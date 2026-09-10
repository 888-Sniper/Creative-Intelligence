"""Product audit log: who did what, without sensitive payloads.

Admin identity actions already live in ``employee_audit``. This table
covers product writes instead: creative uploads, analyses, annotation
verifications, sync starts, report generation/exports and connector
changes. Each row carries the request ID, the acting employee, the
action name, a short non-sensitive target (IDs, keys, counts) and the
result (``ok`` or ``error``).

Never recorded here: API keys, OAuth codes, tokens, passwords,
question text, annotation bodies, uploaded bytes or filenames.
"""

from __future__ import annotations

import time
import uuid

TABLE_DDL = """CREATE TABLE IF NOT EXISTS product_audit (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL DEFAULT '',
    employee_id TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_product_audit_created
    ON product_audit (created_at);
CREATE INDEX IF NOT EXISTS idx_product_audit_employee
    ON product_audit (employee_id);
"""

# Short safety caps: targets/results stay metadata, never payloads.
TARGET_MAX = 200
RESULT_MAX = 120


def ensure(conn) -> None:
    """Create the table/indexes when missing (idempotent)."""
    conn.executescript(TABLE_DDL)
    conn.commit()


def _utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def record(conn, *, request_id: str = "", employee_id: str = "",
           action: str, target: str = "", result: str = "ok") -> str:
    """Append one audit row and return its id. Raises on DB errors."""
    row_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO product_audit"
        " (id, request_id, employee_id, action, target, result,"
        " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (row_id, (request_id or "")[:64], (employee_id or "")[:128],
         (action or "")[:64], (target or "")[:TARGET_MAX],
         (result or "")[:RESULT_MAX], _utcnow()))
    conn.commit()
    return row_id


def audit_request(request, conn=None, *, employee_id: str = "",
                  action: str, target: str = "",
                  result: str = "ok") -> str:
    """Best-effort audit from a request handler.

    Resolves the request ID from ``request.state`` and opens a short
    sqlite handle when the caller has no product connection (auth-layer
    routers). Audit failures never break the product write itself, so
    every error is swallowed here; the success path still persists.
    """
    try:
        rid = getattr(getattr(request, "state", None),
                      "request_id", "") or ""
        if conn is None:
            import sqlite3
            owned = sqlite3.connect(
                request.app.state.ci_db_path, check_same_thread=False)
            try:
                ensure(owned)
                return record(owned, request_id=rid,
                              employee_id=employee_id, action=action,
                              target=target, result=result)
            finally:
                owned.close()
        return record(conn, request_id=rid, employee_id=employee_id,
                      action=action, target=target, result=result)
    except Exception:
        return ""


def recent(conn, limit: int = 100) -> list:
    """Newest-first audit rows as plain dicts."""
    try:
        count = int(limit)
    except (TypeError, ValueError):
        count = 100
    count = max(1, min(count, 500))
    rows = conn.execute(
        "SELECT id, request_id, employee_id, action, target, result,"
        " created_at FROM product_audit"
        " ORDER BY created_at DESC, rowid DESC LIMIT ?", (count,))
    return [{"id": r[0], "request_id": r[1], "employee_id": r[2],
             "action": r[3], "target": r[4], "result": r[5],
             "created_at": r[6]} for r in rows.fetchall()]
