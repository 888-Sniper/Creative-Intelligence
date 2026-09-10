"""WorkOS identity client over httpx (Nextly workos.py architecture).

Same provider map, PKCE, endpoints and payload shapes as Nextly's
workos.py; Creative Intelligence keeps its own ``CREATIVE_INTEL_*``
environment names and adds no licensing calls.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

from ci_backend import credentials as secrets_mod

PROVIDERS = {
    "google": "GoogleOAuth",
    "github": "GitHubOAuth",
    "microsoft": "MicrosoftOAuth",
    "apple": "AppleOAuth",
}

TIMEOUT_S = 20


class WorkOSError(RuntimeError):
    def __init__(self, message: str, *, code: str = "") -> None:
        super().__init__(message)
        self.code = code


def api_base(settings=None) -> str:
    base = ""
    if settings is not None:
        base = (getattr(settings, "workos_api_url", "") or "").strip()
    return (base or "https://api.workos.com").rstrip("/")


def client_id(settings=None) -> str:
    if settings is not None and getattr(settings, "workos_client_id", ""):
        return settings.workos_client_id
    return secrets_mod.env_value("CREATIVE_INTEL_WORKOS_CLIENT_ID")


def _api_key(settings=None) -> str:
    key = secrets_mod.workos_api_key(settings=settings)
    if not key:
        raise WorkOSError("WorkOS is not configured.")
    return key


def workos_configured(settings=None) -> bool:
    """Presence probe only: never reads the secret value into memory."""
    if not client_id(settings):
        return False
    return secrets_mod.workos_key_present(settings)


def redirect_uri(settings=None, *, default_host: str = "127.0.0.1", default_port: int = 4321) -> str:
    override = ""
    if settings is not None:
        override = (getattr(settings, "workos_redirect_uri", "") or "").strip()
    override = override or secrets_mod.env_value("CREATIVE_INTEL_WORKOS_REDIRECT_URI")
    if override:
        return override
    return f"http://{default_host}:{default_port}/api/auth/callback"


def _headers(settings=None) -> dict[str, str]:
    return {"Authorization": f"Bearer {_api_key(settings)}", "Content-Type": "application/json"}


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def authorization_url(*, provider: str, state: str, code_challenge: str,
                      redirect: str = "", settings=None) -> str:
    workos_provider = PROVIDERS.get(provider)
    if not workos_provider:
        raise WorkOSError("Unknown sign-in provider.")
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id(settings),
            "redirect_uri": redirect or redirect_uri(settings),
            "provider": workos_provider,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{api_base(settings)}/user_management/authorize?{query}"


def public_identity(raw: dict[str, Any], *, provider: str = "email") -> dict[str, Any]:
    user = raw.get("user") if isinstance(raw.get("user"), dict) else raw
    if not isinstance(user, dict):
        raise WorkOSError("WorkOS returned an unexpected user payload.")
    email = str(user.get("email") or "").strip().lower()
    verified = bool(
        user.get("email_verified") if "email_verified" in user else user.get("verified")
    )
    return {
        "workos_user_id": str(user.get("workos_user_id") or user.get("id") or ""),
        "email": email,
        "first_name": str(user.get("first_name") or "").strip(),
        "last_name": str(user.get("last_name") or "").strip(),
        "avatar_url": str(user.get("avatar_url") or user.get("profile_picture_url") or ""),
        "verified": verified,
        "provider": provider,
    }


def _error_detail(payload: Any, fallback: str) -> tuple[str, str]:
    if not isinstance(payload, dict):
        return fallback, ""
    code = str(payload.get("code") or "")
    for key in ("message", "error_description", "error"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), code
    return fallback, code


def _raise_http(response: httpx.Response, fallback: str) -> None:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    message, code = _error_detail(payload, fallback)
    raise WorkOSError(message, code=code)


def _post(path: str, payload: dict[str, Any], *, settings=None) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=TIMEOUT_S) as client:
            response = client.post(
                f"{api_base(settings)}{path}",
                headers=_headers(settings),
                json=payload,
            )
            if response.status_code >= 400:
                _raise_http(response, "Could not sign in.")
            data = response.json()
    except httpx.RequestError as exc:
        raise WorkOSError("Could not reach WorkOS.") from exc
    if not isinstance(data, dict):
        raise WorkOSError("WorkOS returned an unexpected session payload.")
    return data


def authenticate_code(code: str, code_verifier: str, *, settings=None) -> dict[str, Any]:
    return _post(
        "/user_management/authenticate",
        {
            "client_id": client_id(settings),
            "client_secret": _api_key(settings),
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
        },
        settings=settings,
    )


def authenticate_password(email: str, password: str, *, settings=None) -> dict[str, Any]:
    return _post(
        "/user_management/authenticate",
        {
            "client_id": client_id(settings),
            "client_secret": _api_key(settings),
            "grant_type": "password",
            "email": email,
            "password": password,
        },
        settings=settings,
    )


def send_magic_code(email: str, *, settings=None) -> None:
    _post("/user_management/magic_auth", {"email": email}, settings=settings)


def authenticate_magic_code(email: str, code: str, *, settings=None) -> dict[str, Any]:
    return _post(
        "/user_management/authenticate",
        {
            "client_id": client_id(settings),
            "client_secret": _api_key(settings),
            "grant_type": "urn:workos:oauth:grant-type:magic-auth:code",
            "email": email,
            "code": code,
        },
        settings=settings,
    )


def send_password_reset(email: str, *, settings=None) -> None:
    _post("/user_management/password_reset", {"email": email}, settings=settings)


def reset_password(token: str, password: str, *, settings=None) -> dict[str, Any]:
    if len(password or "") < 8:
        raise WorkOSError("Use a password with at least 8 characters.")
    return _post(
        "/user_management/password_reset/confirm",
        {"token": token, "new_password": password},
        settings=settings,
    )
