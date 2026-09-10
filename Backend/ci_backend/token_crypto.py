"""Master-key envelope encryption for stored OAuth secrets.

Refresh tokens are long-lived credentials: they must survive server
restarts and deploys (durable) without depending on a desktop keychain
(server-safe). They live in the oauth_tokens table encrypted with
Fernet under a single master key, which itself comes from the
environment on servers (CREATIVE_INTEL_MASTER_KEY) or the OS keychain
on developer Macs. No plaintext secret is ever logged or returned.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from ci_backend import credentials as secrets_mod

MASTER_ACCOUNT = "creative-intel-master"


class CryptoError(Exception):
    """Master key missing/invalid or stored secret undecryptable."""


def generate_master_key() -> str:
    """New random master key, encoded for CREATIVE_INTEL_MASTER_KEY."""
    return Fernet.generate_key().decode("ascii")


def master_key_value(settings=None) -> bytes:
    """Resolve the Fernet master key, provisioning into the keychain.

    Order: explicit setting/env, then OS keychain (auto-provisioned on
    first use where a keychain backend works), else fail closed with a
    message telling the operator how to set one.
    """
    raw = ""
    if settings is not None:
        raw = (getattr(settings, "master_key", "") or "").strip()
    if not raw:
        raw = secrets_mod.env_value("CREATIVE_INTEL_MASTER_KEY").strip()
    if not raw:
        raw = secrets_mod.keyring_get(MASTER_ACCOUNT)
        if not raw:
            raw = _provision_keychain_key()
    if not raw:
        raise CryptoError(
            "Google token encryption needs a master key: set "
            "CREATIVE_INTEL_MASTER_KEY (generate one with "
            "python3 -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\").")
    try:
        Fernet(raw.encode("ascii"))
    except Exception as exc:
        raise CryptoError(
            "CREATIVE_INTEL_MASTER_KEY is not a valid Fernet key.") from exc
    return raw.encode("ascii")


def _provision_keychain_key() -> str:
    """Generate and store a master key where a keychain backend works."""
    try:
        import keyring
    except ImportError:
        return ""
    try:
        key = generate_master_key()
        keyring.set_password(secrets_mod.SERVICE, MASTER_ACCOUNT, key)
        return keyring.get_password(secrets_mod.SERVICE,
                                    MASTER_ACCOUNT) or ""
    except Exception:
        return ""


def encrypt_secret(plaintext: str, settings=None) -> str:
    """Encrypt one secret value; returns the Fernet token string."""
    fernet = Fernet(master_key_value(settings))
    return fernet.encrypt((plaintext or "").encode("utf-8")).decode("ascii")


def decrypt_secret(token_enc: str, settings=None) -> str:
    """Decrypt a Fernet token string; fails closed on any mismatch."""
    if not token_enc:
        raise CryptoError("No encrypted secret stored.")
    fernet = Fernet(master_key_value(settings))
    try:
        return fernet.decrypt(token_enc.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise CryptoError(
            "Stored Google secret cannot be decrypted with this master "
            "key. Reconnect Google Drive in Settings.") from exc
