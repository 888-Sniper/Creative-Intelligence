"""Google OAuth for private Drive/Sheets (item 31).

Server-side flow only: the browser never sees the client secret or any
token. Short-lived access tokens live in the oauth_tokens table;
long-lived refresh tokens live in the OS keychain. The pending-state
machinery (single-use, expiring) is shared with the WorkOS flow.
"""

from __future__ import annotations

import datetime
import secrets
import urllib.parse
from typing import Any

import httpx
from sqlalchemy.orm import Session

from ci_backend import credentials as secrets_mod
from ci_backend import employees as emp
from ci_backend import workos as workos_mod
from ci_backend.config import Settings
from ci_backend.db import OAuthToken

PROVIDER = "google"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
# Read-only: listing/downloading files the employee can already see.
SCOPES = ("https://www.googleapis.com/auth/drive.readonly",)


class GoogleError(Exception):
    pass


def keyring_account(employee_id: str) -> str:
    return "%s-%s" % (secrets_mod.GOOGLE_ACCOUNT, employee_id)


def google_configured(settings=None) -> bool:
    client_id = (getattr(settings, "google_client_id", "") or "").strip()
    redirect = (getattr(settings, "google_redirect_uri", "") or "").strip()
    return bool(client_id and redirect
                and secrets_mod.google_client_secret(settings))


def start_google(db: Session, settings=None) -> dict[str, str]:
    """Begin Google OAuth: returns {url} for a top-level navigation."""
    if not google_configured(settings):
        raise emp.StoreError("Google Drive is not configured.")
    emp.sweep_pending(db)
    verifier, challenge = workos_mod.pkce_pair()
    state = secrets.token_urlsafe(16)
    emp.pending_put(db, state, "google-drive", verifier)
    query = urllib.parse.urlencode({
        "client_id": settings.google_client_id.strip(),
        "redirect_uri": settings.google_redirect_uri.strip(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    })
    return {"url": "%s?%s" % (GOOGLE_AUTH_URL, query), "state": state}


def _exchange(payload: dict[str, str], settings=None) -> dict[str, Any]:
    settings = settings or Settings()
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(GOOGLE_TOKEN_URL, data={
                "client_id": settings.google_client_id.strip(),
                "client_secret": secrets_mod.google_client_secret(settings),
                **payload,
            })
    except Exception as exc:
        raise GoogleError("Google token request failed.") from exc
    if resp.status_code != 200:
        raise GoogleError("Google refused the token request.")
    try:
        body = resp.json()
    except ValueError as exc:
        raise GoogleError("Google returned an unreadable token.") from exc
    if not isinstance(body, dict) or not body.get("access_token"):
        raise GoogleError("Google returned no access token.")
    return body


def finish_google(db: Session, code: str, state: str, employee_id: str,
                  settings=None) -> dict[str, str]:
    """Redeem a callback code and store tokens for one employee.

    Single-use state: replays fail closed. Returns safe status fields
    only — never tokens.
    """
    if not google_configured(settings):
        raise emp.StoreError("Google Drive is not configured.")
    row = emp.pending_pop(db, state or "")
    if row is None or row.provider != "google-drive" \
            or not emp.pending_valid(row):
        raise emp.StoreError("That Google sign-in expired. Try again.")
    body = _exchange({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.google_redirect_uri.strip(),
        "code_verifier": row.verifier,
    }, settings)
    _store(db, employee_id, body)
    return {"ok": "connected", "scope": " ".join(SCOPES)}


def _store(db: Session, employee_id: str, body: dict[str, Any]) -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    lifetime = body.get("expires_in")
    try:
        seconds = int(lifetime) if lifetime is not None else 3600
    except (TypeError, ValueError):
        seconds = 3600
    row = db.get(OAuthToken, (PROVIDER, employee_id))
    if row is None:
        row = OAuthToken(provider=PROVIDER, owner_employee_id=employee_id)
        db.add(row)
    row.access_token = str(body.get("access_token") or "")
    row.expires_at = (now + datetime.timedelta(
        seconds=max(seconds, 60))).isoformat(timespec="seconds")
    row.scope = " ".join(SCOPES)
    row.updated_at = now.isoformat(timespec="seconds")
    db.commit()
    refresh = body.get("refresh_token")
    if refresh:
        # Long-lived secret: OS keychain only, never the database.
        try:
            import keyring
            keyring.set_password(secrets_mod.SERVICE,
                                 keyring_account(employee_id), str(refresh))
        except Exception:
            pass


def _refresh_token_for(employee_id: str) -> str:
    try:
        import keyring
        return keyring.get_password(
            secrets_mod.SERVICE, keyring_account(employee_id)) or ""
    except Exception:
        return ""


def forget(db: Session, employee_id: str) -> None:
    """Disconnect Google: drop the access row and the keychain refresh."""
    row = db.get(OAuthToken, (PROVIDER, employee_id))
    if row is not None:
        db.delete(row)
        db.commit()
    try:
        import keyring
        keyring.delete_password(secrets_mod.SERVICE,
                                keyring_account(employee_id))
    except Exception:
        pass


def status(db: Session, employee_id: str) -> dict[str, Any]:
    row = db.get(OAuthToken, (PROVIDER, employee_id))
    if row is None:
        return {"connected": False}
    return {"connected": True, "expires_at": row.expires_at or "",
            "scope": row.scope or ""}


def access_token_for(db: Session, employee_id: str,
                     settings=None) -> str:
    """Valid access token, refreshing transparently when expired."""
    row = db.get(OAuthToken, (PROVIDER, employee_id))
    if row is None or not row.access_token:
        raise emp.StoreError(
            "Google Drive is not connected. Connect it in Settings.")
    try:
        expired = datetime.datetime.fromisoformat(row.expires_at).replace(
            tzinfo=datetime.timezone.utc) <= datetime.datetime.now(
                datetime.timezone.utc)
    except ValueError:
        expired = True
    if not expired:
        return row.access_token
    refresh = _refresh_token_for(employee_id)
    if not refresh:
        raise emp.StoreError(
            "Google session expired. Reconnect it in Settings.")
    body = _exchange({"grant_type": "refresh_token",
                      "refresh_token": refresh}, settings)
    _store(db, employee_id, body)
    return str(body.get("access_token") or "")


def bearer_headers(db: Session, employee_id: str, settings=None) -> dict:
    return {"Authorization": "Bearer %s" % access_token_for(
        db, employee_id, settings)}
