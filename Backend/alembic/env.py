"""Alembic environment (Nextly migration pattern)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alembic import context
from sqlalchemy import create_engine

from ci_backend.config import Settings
from ci_backend.db import Base

config = context.config


def database_url() -> str:
    override = os.environ.get("CREATIVE_INTEL_DB_URL", "").strip()
    if override:
        return override
    configured = config.get_main_option("sqlalchemy.url", "").strip()
    if configured:
        return configured
    settings = Settings()
    return f"sqlite:///{settings.database_path}"


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(), target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), future=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
