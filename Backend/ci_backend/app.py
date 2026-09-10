"""FastAPI application factory (Nextly main.py/api.py pattern)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from ci_backend.config import Settings  # noqa: E402
from ci_backend.deps import bind_database  # noqa: E402
from ci_backend.routers import admin, auth, product  # noqa: E402


async def _http_error_body(_request, exc: HTTPException) -> JSONResponse:
    # Legacy wire contract: error objects sit at the top level, not
    # under FastAPI's {"detail"} envelope.
    body = exc.detail if isinstance(exc.detail, dict) else {"error": exc.detail}
    return JSONResponse(status_code=exc.status_code, content=body)


def create_app(db_path: str = "", settings: Settings | None = None,
               providers=None) -> FastAPI:
    """Build the app bound to one sqlite file (auth + product facts)."""
    settings = settings or Settings()
    db_path = db_path or str(settings.database_path)
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

    app = FastAPI(title="Creative Intelligence")
    app.add_exception_handler(HTTPException, _http_error_body)
    app.state.ci_settings = settings
    bind_database(app, db_path)
    if providers is not None:
        app.state.ci_providers = providers

    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(product.router)
    return app
