"""Application settings (pydantic-settings, Nextly config.py pattern).

Every value comes from a ``CREATIVE_INTEL_*`` environment variable;
nothing is read from ad-hoc files. Tests override via constructor kwargs
or monkeypatched env vars — never via hidden global state.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_data_dir() -> Path:
    raw = os.environ.get("CREATIVE_INTEL_DATA_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path(__file__).resolve().parents[2] / "Data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CREATIVE_INTEL_", extra="ignore")

    data_dir: Path = Field(default_factory=default_data_dir)
    db_filename: str = "creative_intel.db"

    workos_client_id: str = ""
    key_workos: str = ""
    workos_redirect_uri: str = ""
    workos_api_url: str = "https://api.workos.com"

    google_client_id: str = ""
    """Google OAuth client id (public identifier, safe for the browser).

    The client SECRET stays server-side: keychain account
    ``creative-intel-google`` or CREATIVE_INTEL_GOOGLE_CLIENT_SECRET.
    """
    google_redirect_uri: str = ""
    """Exact redirect registered in Google Cloud console, e.g.
    http://127.0.0.1:4321/api/auth/google/callback."""

    admin_email: str = ""

    master_key: str = ""
    """Master key for stored OAuth secret encryption (Fernet).

    Set CREATIVE_INTEL_MASTER_KEY on servers. On developer Macs an
    OS-keychain key is auto-provisioned when this is empty.
    """

    max_json_bytes: int = 25 * 1024 * 1024
    """Largest accepted JSON body (ingest payloads ride inside JSON).

    Creative media uploads travel multipart (their own 100MB cap);
    this caps csv/xlsx-in-JSON imports against memory exhaustion.
    """

    cookie_secure: bool = False
    """Set CREATIVE_INTEL_COOKIE_SECURE=true behind HTTPS in production.

    Local development over plain HTTP keeps this false so the browser
    still sends the session cookie; production HTTPS must set it so
    the session cookie is never transmitted over cleartext.
    """

    environment: str = "local"
    """Deployment environment: local, demo, or production."""

    provider_mode: str = "mock"
    """AI provider mode: mock or live (CREATIVE_INTEL_PROVIDER_MODE)."""

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.db_filename

    def require_public_safety(self) -> None:
        """Fail closed for public demo/production environments.

        A public deployment must never silently run mock AI analysis,
        cleartext cookies, or missing auth identity. Raises ConfigError
        with secret-free messages; local development is unaffected.
        """
        if self.environment.strip().lower() not in ("demo", "production"):
            return
        problems = []
        if self.provider_mode.strip().lower() != "live":
            problems.append(
                "CREATIVE_INTEL_PROVIDER_MODE must be 'live' in environment "
                "'%s' (refusing to serve mock AI analysis publicly)."
                % self.environment.strip())
        if not self.cookie_secure:
            problems.append(
                "CREATIVE_INTEL_COOKIE_SECURE must be true in environment "
                "'%s'." % self.environment.strip())
        required = (
            ("CREATIVE_INTEL_ADMIN_EMAIL", self.admin_email),
            ("CREATIVE_INTEL_WORKOS_CLIENT_ID", self.workos_client_id),
            ("CREATIVE_INTEL_KEY_WORKOS", self.key_workos),
            ("CREATIVE_INTEL_WORKOS_REDIRECT_URI",
             self.workos_redirect_uri),
        )
        for label, value in required:
            if not str(value or "").strip():
                problems.append("%s is not configured." % label)
        if problems:
            raise ConfigError("; ".join(problems))


class ConfigError(ValueError):
    """Startup configuration failure (messages never carry secrets)."""


@lru_cache
def get_settings() -> Settings:
    return Settings()
