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

    admin_email: str = ""

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

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.db_filename


@lru_cache
def get_settings() -> Settings:
    return Settings()
