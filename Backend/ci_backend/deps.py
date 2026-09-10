"""FastAPI dependencies: settings, databases, guards (Nextly api.py pattern).

One sqlite file serves both layers: SQLAlchemy owns the identity /
access tables, the analytics library keeps its sqlite3 access for
product facts. Guards are default-deny from the first launch.
"""

from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from fastapi import Depends, HTTPException, Request  # noqa: E402

from ci_backend import employees as emp  # noqa: E402
from ci_backend.config import Settings  # noqa: E402
from ci_backend.db import init_db, make_engine, make_session_factory  # noqa: E402


def bind_database(app, db_path: str):
    """Attach engine + factories to the app. Called once at startup."""
    engine = make_engine(db_path)
    init_db(engine)
    app.state.ci_engine = engine
    app.state.ci_sessions = make_session_factory(engine)
    app.state.ci_db_path = str(db_path)
    return engine


def get_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "ci_settings", None)
    if settings is not None:
        return settings
    from ci_backend.config import get_settings as cached
    return cached()


def get_db(request: Request):
    with request.app.state.ci_sessions() as sess:
        yield sess


def get_product_conn(request: Request):
    from creative_intel import schema
    # One connection per request (never shared), so thread affinity is
    # disabled: servers and TestClient serve requests off-thread.
    conn = sqlite3.connect(request.app.state.ci_db_path,
                           check_same_thread=False)
    schema.init_db(conn)
    try:
        yield conn
    finally:
        conn.close()


def get_providers(request: Request):
    prov = getattr(request.app.state, "ci_providers", None)
    if prov is not None:
        return prov
    from creative_intel import providers as providers_mod
    return providers_mod.Providers()


def bearer_token(request: Request) -> str:
    return emp.token_from_cookie_header(request.headers.get("cookie", ""))


def _deny(exc: emp.Denied) -> HTTPException:
    return HTTPException(status_code=401 if exc.gate == "login" else 403,
                         detail={"error": str(exc), "gate": exc.gate})


def get_current_employee(request: Request, db=Depends(get_db)):
    """Default-deny guard: live session for an active employee or 401/403."""
    try:
        employee, _gate = emp.authorize(db, bearer_token(request))
        return employee
    except emp.Denied as exc:
        raise _deny(exc)


def get_current_admin(request: Request, db=Depends(get_db)):
    """Admin guard: active employee with the admin role or 401/403."""
    try:
        employee, _gate = emp.authorize(db, bearer_token(request))
    except emp.Denied as exc:
        raise _deny(exc)
    if employee.role != "admin":
        raise HTTPException(status_code=403, detail={
            "error": "Administrator access required.", "gate": "forbidden"})
    return employee


def query_multidict(request: Request) -> dict[str, list[str]]:
    """parse_qs-shaped query map for the analytics library."""
    out: dict[str, list[str]] = {}
    for key in request.query_params:
        out[key] = request.query_params.getlist(key)
    return out


# In-memory per-IP sliding-window rate limits (process-local).
#
# This is a local-first single-process app: buckets live on app.state
# so every test app (and every server start) gets a fresh table.
# Limits are deliberately generous — they exist to blunt automated
# credential-stuffing and callback-replay floods, not to punish
# legitimate employees. A distributed deployment would replace this
# with a shared store, but must keep the same 429 contract.
AUTH_RATE_LIMIT = (30, 60.0)    # 30 calls / 60s per IP, auth-sensitive
ADMIN_RATE_LIMIT = (120, 60.0)  # 120 calls / 60s per IP, admin actions


def _buckets(request: Request) -> dict:
    buckets = getattr(request.app.state, "ci_ratelimits", None)
    if buckets is None:
        buckets = {}
        request.app.state.ci_ratelimits = buckets
    return buckets


def rate_limiter(calls: int, per_seconds: float, group: str):
    """Dependency factory: 429 when an IP exceeds calls/per_seconds."""
    import time

    async def guard(request: Request):
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        key = (group, ip)
        buckets = _buckets(request)
        window = [t for t in buckets.get(key, []) if now - t < per_seconds]
        if len(window) >= calls:
            raise HTTPException(
                status_code=429,
                detail={"error": "Too many requests. Try again shortly.",
                        "gate": "rate_limited"})
        buckets[key] = window + [now]

    return guard


auth_rate_limit = rate_limiter(*AUTH_RATE_LIMIT, "auth")
admin_rate_limit = rate_limiter(*ADMIN_RATE_LIMIT, "admin")


async def json_payload(request: Request) -> dict:
    """Tolerant JSON body (empty/invalid bodies become {}, like before)."""
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
