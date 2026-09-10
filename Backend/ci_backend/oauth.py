"""OAuth/email login flows (Nextly AccountStore.start_oauth pattern).

Pure flow logic over the SQLAlchemy store; the FastAPI router only
translates HTTP. Every WorkOS identity is verified before any
employee record is touched.
"""

from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy.orm import Session

from ci_backend import employees as emp
from ci_backend import workos as workos_mod

OAUTH_PROVIDERS = ("google", "microsoft", "apple", "github")


def start_oauth(db: Session, provider: str, redirect: str = "",
                settings=None) -> dict[str, str]:
    """Begin an OAuth flow: returns {url, state} for the browser."""
    if provider not in OAUTH_PROVIDERS:
        raise emp.StoreError("Unknown sign-in provider.")
    if not workos_mod.workos_configured(settings):
        raise emp.StoreError("WorkOS is not configured.")
    emp.sweep_pending(db)
    verifier, challenge = workos_mod.pkce_pair()
    state = secrets.token_urlsafe(16)
    emp.pending_put(db, state, provider, verifier)
    url = workos_mod.authorization_url(
        provider=provider, state=state, code_challenge=challenge,
        redirect=redirect, settings=settings)
    return {"url": url, "state": state}


def finish_oauth(db: Session, code: str, state: str,
                 settings=None) -> dict[str, Any]:
    """Exchange a callback code for a verified identity.

    Single-use state: a replayed or expired callback fails closed and
    creates no employee and no session (duplicate-callback safe).
    """
    if not workos_mod.workos_configured(settings):
        raise emp.StoreError("WorkOS is not configured.")
    row = emp.pending_pop(db, state or "")
    if row is None or not emp.pending_valid(row):
        raise emp.StoreError("That sign-in expired. Try again.")
    try:
        raw = workos_mod.authenticate_code(code, row.verifier,
                                           settings=settings)
    except workos_mod.WorkOSError as exc:
        raise emp.StoreError(str(exc), code=exc.code)
    identity = workos_mod.public_identity(raw, provider=row.provider)
    if not identity["workos_user_id"] or not identity["verified"]:
        raise emp.StoreError("WorkOS did not return a verified identity.")
    return identity


def login_verified(db: Session, identity: dict[str, Any],
                   settings=None) -> tuple[str, Any, str]:
    """Email-grant login: verified WorkOS identity only, then session.

    Returns (token, employee, gate) where gate mirrors /me so the
    frontend lands on app/pending/suspended without a second call.
    """
    if not identity.get("workos_user_id") or not identity.get("verified"):
        raise emp.StoreError("WorkOS did not return a verified identity.")
    token, employee, _created = emp.login_identity(db, identity, settings)
    gate = "app" if employee.status == "active" else employee.status
    return token, employee, gate
