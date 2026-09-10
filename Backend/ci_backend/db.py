"""SQLAlchemy models + engine (Nextly db.py pattern).

Auth tables mirror the legacy sqlite3 schema exactly (same table and
column names) so existing databases open unchanged: ``employees``,
``auth_sessions``, ``auth_pending``, ``employee_audit``.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    workos_user_id: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    email: Mapped[str] = mapped_column(String, default="")
    first_name: Mapped[str] = mapped_column(String, default="")
    last_name: Mapped[str] = mapped_column(String, default="")
    avatar_url: Mapped[str] = mapped_column(String, default="")
    role: Mapped[str] = mapped_column(String, default="employee")
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[str] = mapped_column(String, default="")
    approved_at: Mapped[str] = mapped_column(String, default="")
    approved_by: Mapped[str] = mapped_column(String, default="")
    last_login_at: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[str] = mapped_column(String, default="")

    __table_args__ = (
        Index("employees_workos_uid", "workos_user_id", unique=True),
        Index("employees_email", "email", unique=True),
        CheckConstraint("role IN ('admin', 'employee')",
                        name="ck_employees_role"),
        CheckConstraint(
            "status IN ('pending', 'active', 'suspended', 'revoked')",
            name="ck_employees_status"),
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    employee_id: Mapped[str] = mapped_column(
        String, ForeignKey("employees.id"), default="")
    workos_user_id: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String, default="")
    last_seen_at: Mapped[str] = mapped_column(String, default="")
    expires_at: Mapped[str] = mapped_column(String, default="")


class AuthPending(Base):
    __tablename__ = "auth_pending"

    state: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String, default="")
    verifier: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String, default="")


class EmployeeAudit(Base):
    __tablename__ = "employee_audit"

    # target_id references employees (history is never rewritten); note
    # there is deliberately NO foreign key on admin_id, which also
    # carries bootstrap/test markers such as "root" by design.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    target_id: Mapped[str] = mapped_column(
        String, ForeignKey("employees.id"), default="")
    admin_id: Mapped[str] = mapped_column(String, default="")
    action: Mapped[str] = mapped_column(String, default="")
    prev_value: Mapped[str] = mapped_column(String, default="")
    new_value: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(Text, default="")


def make_engine(database_path: str | Path):
    path = Path(database_path)
    if str(path) != ":memory:" and path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", future=True)

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    return engine


def make_session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False, future=True)


def init_db(engine) -> None:
    """Create missing auth tables. Safe to call repeatedly (tests + boot)."""
    Base.metadata.create_all(engine)


def alembic_script_location() -> str:
    from pathlib import Path as _Path
    return str(_Path(__file__).resolve().parent.parent / "alembic")


def ensure_migrated(engine) -> None:
    """Bring identity tables to Alembic head (authoritative path).

    Fresh databases upgrade from scratch. Databases created by the
    legacy create_all path carry the 0001 shape, so they are stamped
    0001 first and then upgraded — never rebuilt, never wiped.
    """
    from alembic import command as _command
    from alembic.config import Config as _Config
    from alembic.migration import MigrationContext as _MigrationContext
    from sqlalchemy import inspect as _inspect
    cfg = _Config()
    cfg.set_main_option("script_location", alembic_script_location())
    with engine.connect() as conn:
        ctx = _MigrationContext.configure(conn)
        heads = ctx.get_current_heads()
        legacy = _inspect(conn).has_table("employees")
    if heads:
        return
    # Migrations run on a disposable engine: the FK enforcement
    # window in env.py must never touch pooled connections, and the
    # explicit commit persists DML (pysqlite autocommits DDL but
    # would roll back an uncommitted version stamp on close).
    from sqlalchemy import create_engine as _create_engine
    migrant = _create_engine("sqlite:///%s" % engine.url.database,
                             future=True)
    try:
        with migrant.connect() as conn:
            cfg.attributes["connection"] = conn
            if legacy:
                _command.stamp(cfg, "0001")
            _command.upgrade(cfg, "head")
            conn.commit()
    finally:
        migrant.dispose()


def migrate(engine, revision: str) -> None:
    """Move identity tables to an explicit revision (tests/ops).

    Same disposable-connection discipline as ensure_migrated.
    """
    from alembic import command as _command
    from alembic.config import Config as _Config
    from sqlalchemy import create_engine as _create_engine
    cfg = _Config()
    cfg.set_main_option("script_location", alembic_script_location())
    migrant = _create_engine("sqlite:///%s" % engine.url.database,
                             future=True)
    try:
        with migrant.connect() as conn:
            cfg.attributes["connection"] = conn
            if revision == "base":
                _command.downgrade(cfg, "base")
            elif revision.startswith("-") or ":" in revision:
                raise ValueError("unsupported revision %r" % (revision,))
            elif _is_downgrade(engine, revision):
                _command.downgrade(cfg, revision)
            else:
                _command.upgrade(cfg, revision)
            conn.commit()
    finally:
        migrant.dispose()


def _is_downgrade(engine, revision: str) -> bool:
    from alembic.config import Config as _Config
    from alembic.migration import MigrationContext as _MigrationContext
    from alembic.script import ScriptDirectory as _ScriptDirectory
    cfg = _Config()
    cfg.set_main_option("script_location", alembic_script_location())
    script = _ScriptDirectory.from_config(cfg)
    order = [r.revision for r in script.walk_revisions()]
    with engine.connect() as conn:
        ctx = _MigrationContext.configure(conn)
        heads = ctx.get_current_heads()
    if not heads:
        return False
    try:
        # walk_revisions() yields head-first, so a downgrade target
        # sits LATER in the order than the current head.
        return order.index(revision) > order.index(heads[0])
    except ValueError:
        return False


def session_scope(factory) -> Session:
    return factory()
