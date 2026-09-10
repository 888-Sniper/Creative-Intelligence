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


def _run_on(connection) -> None:
    import sqlalchemy as sa
    # SQLite cannot rebuild a referenced parent table while
    # enforcement is on. Migrations run unenforced; each migration
    # that adds references must verify no orphans itself (fail
    # closed, never silently rewrite history). AUTOCOMMIT makes both
    # toggles take effect deterministically: inside a transaction
    # these PRAGMAs would be silent no-ops and pooled connections
    # could leak back with enforcement off.
    # First statement on a fresh connection: autocommit, takes effect.
    # Callers must run migrations on a disposable connection (see
    # ensure_migrated) so no pooled connection can leak enforcement
    # state; OFF is still restored below for hygiene.
    connection.execute(sa.text("PRAGMA foreign_keys=OFF"))
    try:
        context.configure(connection=connection,
                          target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    finally:
        connection.execute(sa.text("PRAGMA foreign_keys=ON"))


def run_migrations_online() -> None:
    # Programmatic use (boot/tests) injects a connection via
    # config.attributes so migrations hit the intended database file;
    # the `alembic` CLI falls back to the configured URL.
    injected = config.attributes.get("connection", None)
    if injected is not None:
        _run_on(injected)
        return
    engine = create_engine(database_url(), future=True)
    with engine.connect() as connection:
        _run_on(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
