"""Secret resolution: environment first, OS keychain second (Nextly secrets.py pattern).

No secret is ever logged, returned in API payloads, or written to the repo.
"""

from __future__ import annotations

import os

SERVICE = "CreativeIntelligence"
WORKOS_ACCOUNT = "creative-intel-workos"


def env_value(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def keyring_get(account: str) -> str:
    try:
        import keyring
    except ImportError:
        return ""
    try:
        return keyring.get_password(SERVICE, account) or ""
    except Exception:
        return ""


def keyring_has(account: str) -> bool:
    return bool(keyring_get(account))


def workos_api_key(client_env: str = "", settings=None) -> str:
    """Resolve the WorkOS API key without ever logging it."""
    if settings is not None and getattr(settings, "key_workos", ""):
        return settings.key_workos
    if client_env:
        return client_env
    if env_value("CREATIVE_INTEL_KEY_WORKOS"):
        return env_value("CREATIVE_INTEL_KEY_WORKOS")
    return keyring_get(WORKOS_ACCOUNT)


def workos_key_present(settings=None) -> bool:
    if settings is not None and getattr(settings, "key_workos", ""):
        return True
    if env_value("CREATIVE_INTEL_KEY_WORKOS"):
        return True
    return keyring_has(WORKOS_ACCOUNT)
