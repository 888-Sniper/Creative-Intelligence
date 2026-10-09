"""OAuth for Meta Ads, TikTok Ads, and Google Analytics 4.

Server-side only: the browser is sent to the provider and back. Access
and refresh tokens stay encrypted in oauth_tokens. A missing app
configuration refuses to start instead of pretending the account is
connected.
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
from ci_backend.db import OAuthToken

PROVIDERS = ("meta", "tiktok", "ga4")
LABELS = {
    "meta": "Meta Ads",
    "tiktok": "TikTok Ads",
    "ga4": "Google Analytics 4",
}
_META_AUTH = "https://www.facebook.com/v21.0/dialog/oauth"
_META_TOKEN = "https://graph.facebook.com/v21.0/oauth/access_token"
_META_ACCOUNTS = "https://graph.facebook.com/v21.0/me/adaccounts"
_TIKTOK_AUTH = "https://business-api.tiktok.com/portal/auth"
_TIKTOK_TOKEN = ("https://business-api.tiktok.com/open_api/v1.3/"
                 "oauth2/access_token/")
_TIKTOK_REFRESH = ("https://business-api.tiktok.com/open_api/v1.3/"
                   "oauth2/refresh_token/")
_GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_GOOGLE_REVOKE = "https://oauth2.googleapis.com/revoke"
_GA4_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
_GA4_SUMMARY = ("https://analyticsadmin.googleapis.com/v1beta/"
                "accountSummaries")


class IntegrationError(Exception):
    pass


def label(provider: str) -> str:
    return LABELS.get(provider, "Integration")


def _pending_name(provider: str) -> str:
    return "integration-%s" % provider


def _bind_owner(employee_id: str, verifier: str) -> str:
    """Keep the PKCE verifier and the employee who started the flow.

    The state cookie travels with the browser. The callback must not
    store tokens for whoever happens to be signed in later.
    """
    return "%s %s" % ((employee_id or "").strip(), verifier or "")


def _unbind_owner(packed: str) -> tuple[str, str]:
    owner, sep, verifier = (packed or "").partition(" ")
    if not sep:
        return "", packed or ""
    return owner, verifier


def configured(provider: str, settings=None) -> bool:
    if provider == "meta":
        return bool(_clean(settings, "meta_client_id")
                    and _clean(settings, "meta_redirect_uri")
                    and secrets_mod.meta_client_secret(settings))
    if provider == "tiktok":
        return bool(_clean(settings, "tiktok_client_id")
                    and _clean(settings, "tiktok_redirect_uri")
                    and secrets_mod.tiktok_client_secret(settings))
    if provider == "ga4":
        return bool(_clean(settings, "google_client_id")
                    and _clean(settings, "ga4_redirect_uri")
                    and secrets_mod.google_client_secret(settings))
    return False


def _clean(settings, attr: str) -> str:
    return (getattr(settings, attr, "") or "").strip()


def _require(provider: str, settings) -> None:
    if provider not in PROVIDERS:
        raise emp.StoreError("Unknown integration.")
    if not configured(provider, settings):
        raise emp.StoreError("%s is not configured." % label(provider))


def start(db: Session, provider: str, settings=None,
          employee_id: str = "") -> dict[str, str]:
    """Begin OAuth. Returns {url, state} for a top-level navigation."""
    _require(provider, settings)
    if not (employee_id or "").strip():
        raise emp.StoreError("Sign in to connect %s." % label(provider))
    emp.sweep_pending(db)
    verifier, challenge = workos_mod.pkce_pair()
    state = secrets.token_urlsafe(16)
    emp.pending_put(db, state, _pending_name(provider),
                    _bind_owner(employee_id, verifier))
    if provider == "meta":
        query = urllib.parse.urlencode({
            "client_id": _clean(settings, "meta_client_id"),
            "redirect_uri": _clean(settings, "meta_redirect_uri"),
            "state": state,
            "response_type": "code",
            "scope": "ads_read",
        })
        url = "%s?%s" % (_META_AUTH, query)
    elif provider == "tiktok":
        query = urllib.parse.urlencode({
            "app_id": _clean(settings, "tiktok_client_id"),
            "redirect_uri": _clean(settings, "tiktok_redirect_uri"),
            "state": state,
        })
        url = "%s?%s" % (_TIKTOK_AUTH, query)
    else:
        query = urllib.parse.urlencode({
            "client_id": _clean(settings, "google_client_id"),
            "redirect_uri": _clean(settings, "ga4_redirect_uri"),
            "response_type": "code",
            "scope": _GA4_SCOPE,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        })
        url = "%s?%s" % (_GOOGLE_AUTH, query)
    return {"url": url, "state": state}


def _client() -> httpx.Client:
    return httpx.Client(timeout=20)


def _normalize(provider: str, body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise IntegrationError("%s returned an unreadable token." % label(provider))
    code = body.get("code")
    if code not in (None, 0, "0"):
        raise IntegrationError("%s refused the connection." % label(provider))
    data = body.get("data") if isinstance(body.get("data"), dict) else body
    access = str(data.get("access_token") or "")
    if not access:
        raise IntegrationError("%s returned no access token." % label(provider))
    refresh = str(data.get("refresh_token") or "")
    lifetime = data.get("expires_in", data.get("access_token_expire_in"))
    try:
        seconds = int(lifetime) if lifetime is not None else 3600
    except (TypeError, ValueError):
        seconds = 3600
    scope = data.get("scope") or ""
    if isinstance(scope, list):
        scope = " ".join(str(item) for item in scope)
    account = ""
    ids = data.get("advertiser_ids")
    if isinstance(ids, list) and ids:
        account = str(ids[0])
    return {"access_token": access, "refresh_token": refresh,
            "expires_in": max(seconds, 60), "scope": str(scope),
            "account": account}


def _exchange(provider: str, code: str, verifier: str, settings) -> dict[str, Any]:
    try:
        with _client() as client:
            if provider == "meta":
                resp = client.get(_META_TOKEN, params={
                    "client_id": _clean(settings, "meta_client_id"),
                    "client_secret": secrets_mod.meta_client_secret(settings),
                    "redirect_uri": _clean(settings, "meta_redirect_uri"),
                    "code": code,
                })
            elif provider == "tiktok":
                resp = client.post(_TIKTOK_TOKEN, json={
                    "app_id": _clean(settings, "tiktok_client_id"),
                    "secret": secrets_mod.tiktok_client_secret(settings),
                    "auth_code": code,
                })
            else:
                resp = client.post(_GOOGLE_TOKEN, data={
                    "client_id": _clean(settings, "google_client_id"),
                    "client_secret": secrets_mod.google_client_secret(settings),
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _clean(settings, "ga4_redirect_uri"),
                    "code_verifier": verifier,
                })
    except IntegrationError:
        raise
    except Exception as exc:
        raise IntegrationError(
            "%s token request failed." % label(provider)) from exc
    if resp.status_code != 200:
        raise IntegrationError("%s refused the connection." % label(provider))
    try:
        body = resp.json()
    except ValueError as exc:
        raise IntegrationError(
            "%s returned an unreadable token." % label(provider)) from exc
    token = _normalize(provider, body)
    if provider == "meta":
        longer = _meta_long_lived(token["access_token"], settings)
        if longer is not None:
            token = longer
    if provider == "ga4":
        granted = token["scope"]
        if granted and _GA4_SCOPE not in granted.split():
            raise IntegrationError(
                "Google did not grant Analytics access.")
    return token


def _meta_long_lived(access: str, settings) -> dict[str, Any] | None:
    try:
        with _client() as client:
            resp = client.get(_META_TOKEN, params={
                "grant_type": "fb_exchange_token",
                "client_id": _clean(settings, "meta_client_id"),
                "client_secret": secrets_mod.meta_client_secret(settings),
                "fb_exchange_token": access,
            })
        if resp.status_code != 200:
            return None
        return _normalize("meta", resp.json())
    except Exception:
        return None


def _discover(provider: str, access: str) -> str:
    """Best-effort account id. A lookup failure still leaves the token stored."""
    try:
        with _client() as client:
            if provider == "meta":
                resp = client.get(_META_ACCOUNTS, params={
                    "fields": "account_id,name", "limit": 1,
                    "access_token": access,
                })
                if resp.status_code != 200:
                    return ""
                data = (resp.json() or {}).get("data") or []
                if data and isinstance(data, list):
                    return str(data[0].get("account_id") or "")[:120]
            elif provider == "ga4":
                resp = client.get(_GA4_SUMMARY, headers={
                    "Authorization": "Bearer %s" % access})
                if resp.status_code != 200:
                    return ""
                summaries = (resp.json() or {}).get("accountSummaries") or []
                for account in summaries:
                    props = account.get("propertySummaries") or []
                    if props:
                        return str(props[0].get("property") or "")[:120]
    except Exception:
        return ""
    return ""


def _store(db: Session, provider: str, employee_id: str, token: dict,
           settings=None, account: str = "") -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    row = db.get(OAuthToken, (provider, employee_id))
    if row is None:
        row = OAuthToken(provider=provider, owner_employee_id=employee_id)
        db.add(row)
    access = token.get("access_token") or ""
    row.access_token_enc = token_crypto.encrypt_secret(access, settings) \
        if access else ""
    row.access_token = ""
    row.expires_at = (now + datetime.timedelta(
        seconds=int(token.get("expires_in") or 3600))).isoformat(
            timespec="seconds")
    row.scope = token.get("scope") or ""
    row.updated_at = now.isoformat(timespec="seconds")
    refresh = token.get("refresh_token") or ""
    if refresh:
        row.refresh_token_enc = token_crypto.encrypt_secret(refresh, settings)
    elif provider == "meta" and access and not row.refresh_token_enc:
        # Meta refresh re-exchanges the current user token.
        row.refresh_token_enc = token_crypto.encrypt_secret(access, settings)
    if account:
        row.account_ref = account[:120]
    db.commit()


def finish(db: Session, provider: str, code: str, state: str,
           employee_id: str, settings=None) -> dict[str, str]:
    """Redeem one callback code. Replays fail closed. Returns no tokens."""
    _require(provider, settings)
    row = emp.pending_pop(db, state or "")
    if row is None or row.provider != _pending_name(provider) \
            or not emp.pending_valid(row):
        raise emp.StoreError("That connection expired. Try again.")
    owner, verifier = _unbind_owner(row.verifier)
    if not owner or owner != employee_id:
        raise emp.StoreError("That connection expired. Try again.")
    # TikTok's callback names the code auth_code; callers pass whichever
    # query value they found.
    token = _exchange(provider, code, verifier, settings)
    account = token.get("account") or _discover(provider, token["access_token"])
    _store(db, provider, employee_id, token, settings, account=account)
    return {"ok": "connected", "account": account}


def _plain(row: OAuthToken, field: str, settings=None) -> str:
    enc = getattr(row, field, "") or ""
    if not enc:
        return ""
    return token_crypto.decrypt_secret(enc, settings)


def _expired(row: OAuthToken) -> bool:
    try:
        when = datetime.datetime.fromisoformat(row.expires_at)
        if when.tzinfo is None:
            when = when.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return True
    return when <= datetime.datetime.now(datetime.timezone.utc)


def _refresh(provider: str, refresh: str, settings) -> dict[str, Any]:
    try:
        with _client() as client:
            if provider == "meta":
                resp = client.get(_META_TOKEN, params={
                    "grant_type": "fb_exchange_token",
                    "client_id": _clean(settings, "meta_client_id"),
                    "client_secret": secrets_mod.meta_client_secret(settings),
                    "fb_exchange_token": refresh,
                })
            elif provider == "tiktok":
                resp = client.post(_TIKTOK_REFRESH, json={
                    "app_id": _clean(settings, "tiktok_client_id"),
                    "secret": secrets_mod.tiktok_client_secret(settings),
                    "refresh_token": refresh,
                })
            else:
                resp = client.post(_GOOGLE_TOKEN, data={
                    "client_id": _clean(settings, "google_client_id"),
                    "client_secret": secrets_mod.google_client_secret(settings),
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                })
    except Exception as exc:
        raise emp.StoreError(
            "%s session expired. Reconnect it in Settings."
            % label(provider)) from exc
    if resp.status_code != 200:
        raise emp.StoreError(
            "%s session expired. Reconnect it in Settings." % label(provider))
    try:
        return _normalize(provider, resp.json())
    except IntegrationError as exc:
        raise emp.StoreError(str(exc)) from exc


def access_token_for(db: Session, provider: str, employee_id: str,
                     settings=None) -> str:
    """Valid access token, refreshing when the stored one has expired."""
    row = db.get(OAuthToken, (provider, employee_id))
    if row is None:
        raise emp.StoreError(
            "%s is not connected. Connect it in Settings." % label(provider))
    try:
        access = _plain(row, "access_token_enc", settings)
    except token_crypto.CryptoError as exc:
        raise emp.StoreError(
            "Cannot decrypt the stored %s token. Fix "
            "CREATIVE_INTEL_MASTER_KEY, then reconnect."
            % label(provider)) from exc
    if access and not _expired(row):
        return access
    try:
        refresh = _plain(row, "refresh_token_enc", settings)
    except token_crypto.CryptoError as exc:
        raise emp.StoreError(
            "Cannot decrypt the stored %s token. Fix "
            "CREATIVE_INTEL_MASTER_KEY, then reconnect."
            % label(provider)) from exc
    if not refresh:
        raise emp.StoreError(
            "%s session expired. Reconnect it in Settings." % label(provider))
    token = _refresh(provider, refresh, settings)
    if not token.get("refresh_token"):
        token["refresh_token"] = refresh
    _store(db, provider, employee_id, token, settings,
           account=row.account_ref or "")
    return str(token.get("access_token") or "")


def account_ref(db: Session, provider: str, employee_id: str) -> str:
    row = db.get(OAuthToken, (provider, employee_id))
    if row is None:
        return ""
    return row.account_ref or ""


def status(db: Session, provider: str, employee_id: str) -> dict[str, Any]:
    row = db.get(OAuthToken, (provider, employee_id))
    if row is None or not (row.access_token_enc or row.refresh_token_enc):
        return {"connected": False}
    return {"connected": True, "account": row.account_ref or "",
            "scope": row.scope or ""}


def forget(db: Session, provider: str, employee_id: str, settings=None) -> None:
    row = db.get(OAuthToken, (provider, employee_id))
    if row is None:
        return
    try:
        access = _plain(row, "access_token_enc", settings)
    except token_crypto.CryptoError:
        access = ""
    _revoke(provider, access, settings)
    db.delete(row)
    db.commit()


def _revoke(provider: str, access: str, settings=None) -> None:
    if not access:
        return
    try:
        with _client() as client:
            if provider == "meta":
                client.delete(
                    "https://graph.facebook.com/v21.0/me/permissions",
                    params={"access_token": access})
            elif provider == "ga4":
                client.post(_GOOGLE_REVOKE, data={"token": access})
    except Exception:
        pass
