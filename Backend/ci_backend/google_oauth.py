"""Google OAuth for private Drive/Sheets (item 31).

Server-side flow only: the browser never sees the client secret or any
token. Access tokens (short-lived) and refresh tokens (long-lived,
encrypted under the server master key) live in the oauth_tokens table,
so private sync survives restarts and deploys with no desktop keychain.
The pending-state machinery (single-use, expiring) is shared with the
WorkOS flow.
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
from ci_backend import token_crypto
from ci_backend import workos as workos_mod
from ci_backend.config import Settings
from ci_backend.db import OAuthToken

PROVIDER = "google"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
# Read-only: listing/downloading files the employee can already see.
SCOPES = ("https://www.googleapis.com/auth/drive.readonly",)


class GoogleError(Exception):
    pass


def keyring_account(employee_id: str) -> str:
    """Legacy OS-keychain account (pre-encryption storage)."""
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
    granted = body.get("scope") or ""
    if granted and SCOPES[0] not in str(granted).split():
        raise GoogleError(
            "Google did not grant read-only Drive access.")
    _store(db, employee_id, body, settings,
           scope=str(granted) or " ".join(SCOPES))
    return {"ok": "connected", "scope": str(granted) or " ".join(SCOPES)}


def _store(db: Session, employee_id: str, body: dict[str, Any],
           settings=None, scope: str = "") -> None:
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
    access = str(body.get("access_token") or "")
    # Usable token: encrypted at rest, never plaintext in the row.
    row.access_token_enc = token_crypto.encrypt_secret(access, settings) \
        if access else ""
    row.access_token = ""
    row.expires_at = (now + datetime.timedelta(
        seconds=max(seconds, 60))).isoformat(timespec="seconds")
    row.scope = scope or " ".join(SCOPES)
    row.updated_at = now.isoformat(timespec="seconds")
    refresh = body.get("refresh_token")
    if refresh:
        # Long-lived secret: encrypted in this row, never in logs.
        row.refresh_token_enc = token_crypto.encrypt_secret(
            str(refresh), settings)
    db.commit()


def _refresh_token_for(db: Session, employee_id: str,
                       settings=None) -> str:
    """Decrypt the stored refresh token, upgrading legacy keychain rows."""
    row = db.get(OAuthToken, (PROVIDER, employee_id))
    if row is not None and getattr(row, "refresh_token_enc", ""):
        return token_crypto.decrypt_secret(row.refresh_token_enc, settings)
    # One-time upgrade: rows stored before encryption kept the secret
    # in the OS keychain. Move it into the database, then drop it.
    legacy = ""
    try:
        import keyring
        legacy = keyring.get_password(
            secrets_mod.SERVICE, keyring_account(employee_id)) or ""
    except Exception:
        legacy = ""
    if legacy and row is not None:
        row.refresh_token_enc = token_crypto.encrypt_secret(
            legacy, settings)
        db.commit()
        try:
            import keyring
            keyring.delete_password(secrets_mod.SERVICE,
                                    keyring_account(employee_id))
        except Exception:
            pass
    return legacy


def forget(db: Session, employee_id: str, settings=None) -> None:
    """Disconnect Google: revoke at Google, then drop the stored row."""
    row = db.get(OAuthToken, (PROVIDER, employee_id))
    if row is not None:
        # Disconnect must never strand a row: an undecryptable access
        # token (wrong master key) still gets wiped locally.
        try:
            access = _plain_access_token(db, row, settings)
        except token_crypto.CryptoError:
            access = ""
        _revoke(getattr(row, "refresh_token_enc", ""), access,
                settings)
        db.delete(row)
        db.commit()
    _forget_legacy_keychain(employee_id)


def _forget_legacy_keychain(employee_id: str) -> None:
    try:
        import keyring
        keyring.delete_password(secrets_mod.SERVICE,
                                keyring_account(employee_id))
    except Exception:
        pass


def _revoke(refresh_enc: str, access_token: str, settings=None) -> None:
    """Best-effort server-side revocation; local wipe happens regardless."""
    token = ""
    if refresh_enc:
        try:
            token = token_crypto.decrypt_secret(refresh_enc, settings)
        except token_crypto.CryptoError:
            token = ""
    try:
        with httpx.Client(timeout=20) as client:
            if token:
                client.post(GOOGLE_REVOKE_URL, data={"token": token})
            if access_token:
                client.post(GOOGLE_REVOKE_URL,
                            data={"token": access_token})
    except Exception:
        pass


def status(db: Session, employee_id: str) -> dict[str, Any]:
    row = db.get(OAuthToken, (PROVIDER, employee_id))
    if row is None:
        return {"connected": False}
    return {"connected": True, "expires_at": row.expires_at or "",
            "scope": row.scope or ""}


def _plain_access_token(db: Session, row: OAuthToken,
                          settings=None) -> str:
    """Decrypt the stored access token, upgrading legacy rows.

    New rows keep it in access_token_enc only; rows written before
    encryption carry plaintext in access_token and are moved into the
    encrypted column on first use. Decryption failures propagate as
    CryptoError: both tokens share the master key, so a wrong key
    cannot be recovered through the refresh flow either.
    """
    enc = getattr(row, "access_token_enc", "") or ""
    if enc:
        return token_crypto.decrypt_secret(enc, settings)
    legacy = row.access_token or ""
    if legacy:
        row.access_token_enc = token_crypto.encrypt_secret(
            legacy, settings)
        row.access_token = ""
        db.commit()
    return legacy


def access_token_for(db: Session, employee_id: str,
                     settings=None) -> str:
    """Valid access token, refreshing transparently when expired."""
    row = db.get(OAuthToken, (PROVIDER, employee_id))
    if row is None:
        raise emp.StoreError(
            "Google Drive is not connected. Connect it in Settings.")
    try:
        access = _plain_access_token(db, row, settings)
    except token_crypto.CryptoError as exc:
        raise emp.StoreError(
            "Cannot decrypt the stored Google token: wrong master "
            "key. Fix CREATIVE_INTEL_MASTER_KEY, then reconnect.") \
            from exc
    if not access:
        raise emp.StoreError(
            "Google Drive is not connected. Connect it in Settings.")
    try:
        expired = datetime.datetime.fromisoformat(row.expires_at).replace(
            tzinfo=datetime.timezone.utc) <= datetime.datetime.now(
                datetime.timezone.utc)
    except ValueError:
        expired = True
    if not expired:
        return access
    try:
        refresh = _refresh_token_for(db, employee_id, settings)
    except token_crypto.CryptoError as exc:
        raise emp.StoreError(str(exc))
    if not refresh:
        raise emp.StoreError(
            "Google session expired. Reconnect it in Settings.")
    body = _exchange({"grant_type": "refresh_token",
                      "refresh_token": refresh}, settings)
    _store(db, employee_id, body, settings, scope=row.scope)
    return str(body.get("access_token") or "")


def bearer_headers(db: Session, employee_id: str, settings=None) -> dict:
    return {"Authorization": "Bearer %s" % access_token_for(
        db, employee_id, settings)}
