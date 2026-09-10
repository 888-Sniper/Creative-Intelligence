"""FastAPI application factory (Nextly main.py/api.py pattern)."""

from __future__ import annotations

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from ci_backend.config import Settings  # noqa: E402
from ci_backend.deps import bind_database  # noqa: E402
from ci_backend.observability import access_log_middleware  # noqa: E402
from ci_backend.routers import admin, auth, google, product  # noqa: E402


def _requeue_interrupted_jobs(db_path: str) -> None:
    """Boot recovery: work left running by a dead process waits again."""
    import sqlite3

    from creative_intel import jobs as jobs_mod

    conn = sqlite3.connect(db_path, timeout=30.0)
    try:
        jobs_mod.requeue_interrupted(conn)
    finally:
        conn.close()


async def _http_error_body(_request, exc: HTTPException) -> JSONResponse:
    # Legacy wire contract: error objects sit at the top level, not
    # under FastAPI's {"detail"} envelope.
    body = exc.detail if isinstance(exc.detail, dict) else {"error": exc.detail}
    return JSONResponse(status_code=exc.status_code, content=body)


async def _internal_error_body(_request, _exc: Exception) -> JSONResponse:
    # Production error handling: never leak tracebacks, SQL errors,
    # paths or provider details. Detailed diagnostics belong in server
    # logs, not in the response body.
    return JSONResponse(status_code=500,
                        content={"error": "Something went wrong."})


async def _csrf_origin_guard(request: Request, call_next):
    # Cookie-based CSRF defence: credentialed browser writes (the ones
    # carrying the ci_session cookie) must come from our own origin.
    # Requests without an Origin/Referer header (same-origin form
    # posts, non-browser API clients, TestClient) still pass.
    if request.method in ("POST", "PATCH", "PUT", "DELETE"):
        if "ci_session" in request.headers.get("cookie", ""):
            presented = (request.headers.get("origin")
                         or request.headers.get("referer"))
            if presented:
                from urllib.parse import urlparse
                if urlparse(presented).hostname != request.url.hostname:
                    return JSONResponse(
                        status_code=403,
                        content={"error": "Cross-origin request refused.",
                                 "gate": "csrf"})
    return await call_next(request)


async def _request_id(request: Request, call_next):
    # Observability without sensitive data: every request gets a short
    # random ID (also echoed as X-Request-ID) that product audit rows
    # reference. Nothing about the caller or payload is encoded in it.
    request.state.request_id = uuid.uuid4().hex[:16]
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


async def _security_headers(request: Request, call_next):
    # Baseline hardening. No CORS middleware is installed on purpose:
    # the UI is same-origin, so cross-origin credentialed access is
    # simply never granted (no Access-Control-Allow-Origin at all).
    # HSTS is HTTPS-only and follows the same environment switch as
    # the Secure cookie flag so local HTTP development keeps working.
    # A strict Content-Security-Policy is intentionally deferred until
    # the frontend ships external scripts: the current page still uses
    # inline scripts, which a default-src 'self' policy would break.
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=()")
    settings = getattr(request.app.state, "ci_settings", None)
    if settings is not None and getattr(settings, "cookie_secure", False):
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains")
    return response


def create_app(db_path: str = "", settings: Settings | None = None,
               providers=None) -> FastAPI:
    """Build the app bound to one sqlite file (auth + product facts)."""
    settings = settings or Settings()
    # Fail startup (never serve) when a public environment is misconfigured.
    settings.require_public_safety()
    db_path = db_path or str(settings.database_path)
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    app = FastAPI(title="Creative Intelligence")
    app.add_exception_handler(HTTPException, _http_error_body)
    app.add_exception_handler(Exception, _internal_error_body)
    app.middleware("http")(_csrf_origin_guard)
    app.middleware("http")(_security_headers)
    app.middleware("http")(_request_id)
    # Outermost: the duration covers every inner layer. The request ID
    # is read after the inner chain ran, so it is always populated.
    app.middleware("http")(access_log_middleware)
    app.state.ci_settings = settings
    bind_database(app, db_path)
    if providers is not None:
        app.state.ci_providers = providers
    _requeue_interrupted_jobs(db_path)

    # Liveness/readiness register BEFORE the product router: its
    # explicit SPA fallback (/{spa_path}) matches single-segment paths
    # in registration order and must never shadow these endpoints.
    @app.get("/health")
    def health():
        """Liveness only: the process is alive. No secrets, no checks."""
        return {"ok": True}

    @app.get("/readiness")
    def readiness():
        """Ready to serve: database reachable with identity tables."""
        try:
            engine = app.state.ci_engine
            from sqlalchemy import inspect as sa_inspect
            tables = set(sa_inspect(engine).get_table_names())
            missing = {"employees", "auth_sessions"} - tables
            if missing:
                return JSONResponse(
                    status_code=503,
                    content={"ready": False,
                             "error": "database not migrated"})
            return {"ready": True}
        except Exception:
            return JSONResponse(status_code=503,
                                content={"ready": False,
                                         "error": "database unavailable"})

    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(google.router)
    app.include_router(product.router)

    return app
