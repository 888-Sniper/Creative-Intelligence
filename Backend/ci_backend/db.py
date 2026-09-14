"""SQLAlchemy models + engine (Nextly db.py pattern).

Auth tables mirror the legacy sqlite3 schema exactly (same table and
column names) so existing databases open unchanged: ``employees``,
``auth_sessions``, ``auth_pending``, ``employee_audit``.
"""

from __future__ import annotations

import atexit
import weakref
from pathlib import Path

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

# Every engine ever made (weak refs): dispose_all_engines() closes the
# pooled handles of engines tests have already dropped.
_ENGINES: weakref.WeakSet = weakref.WeakSet()


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
    # "1" when the employee deliberately cleared their avatar: later
    # provider photos must not silently restore it. Any explicit new
    # photo (upload or URL) resets this to "".
    avatar_removed: Mapped[str] = mapped_column(String, default="")
    # Short readable display number (EMP-001…). Assigned once by the
    # server, never derived from a count, stable across status changes.
    # The uuid id stays the relational/authorization identity.
    emp_no: Mapped[str] = mapped_column(String, default="")
    role: Mapped[str] = mapped_column(String, default="employee")
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[str] = mapped_column(String, default="")
    approved_at: Mapped[str] = mapped_column(String, default="")
    approved_by: Mapped[str] = mapped_column(String, default="")
    last_login_at: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[str] = mapped_column(String, default="")
    provider: Mapped[str] = mapped_column(String, default="")

    __table_args__ = (
        Index("employees_workos_uid", "workos_user_id", unique=True),
        Index("employees_email", "email", unique=True),
        Index("employees_emp_no", "emp_no", unique=True),
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
    # Item 18: installation/account container binding. Sessions created
    # by container-aware clients carry the local container id; the
    # account switcher only ever sees same-container sessions, so one
    # installation can never enumerate or hop into accounts from another
    # device/database-sharer. "" means unbound (legacy clients).
    container_id: Mapped[str] = mapped_column(String, default="")


class AuthPending(Base):
    __tablename__ = "auth_pending"

    state: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String, default="")
    verifier: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String, default="")


class OAuthToken(Base):
    """Per-employee third-party OAuth tokens (item 31: Google).

    Both the SHORT-LIVED access token and the long-lived REFRESH
    token are encrypted under the server master key (never in logs
    or the browser). The legacy plaintext access_token column stays
    readable for one-time upgrade and is cleared on write. Composite
    PK stops duplicate rows per owner.
    """

    __tablename__ = "oauth_tokens"

    provider: Mapped[str] = mapped_column(String, primary_key=True)
    owner_employee_id: Mapped[str] = mapped_column(
        String, ForeignKey("employees.id"), primary_key=True)
    access_token: Mapped[str] = mapped_column(String, default="")
    access_token_enc: Mapped[str] = mapped_column(String, default="")
    expires_at: Mapped[str] = mapped_column(String, default="")
    scope: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[str] = mapped_column(String, default="")
    refresh_token_enc: Mapped[str] = mapped_column(String, default="")


class ProviderConfig(Base):
    """Admin-managed secret + endpoint per canonical provider.

    secret_enc is a Fernet token under the server master key (see
    ci_backend.token_crypto); NULL means unconfigured. Plaintext
    secrets never touch this table. Rows are seeded by migration
    0012; the admin providers router owns all writes.
    """

    __tablename__ = "provider_configs"

    provider_id: Mapped[str] = mapped_column(String, primary_key=True)
    display: Mapped[str] = mapped_column(String, default="")
    kind: Mapped[str] = mapped_column(String, default="")
    base_url: Mapped[str | None] = mapped_column(String, nullable=True,
                                                default=None)
    secret_enc: Mapped[str | None] = mapped_column(String, nullable=True,
                                                  default=None)
    secret_updated_at: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None)
    created_at: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[str] = mapped_column(String, default="")


class ProviderModelCache(Base):
    """Last-known offered-model catalog per provider.

    Replaced wholesale on every successful refresh (merge = live
    discovery intersected with the static inventory filter); a failed
    refresh leaves rows untouched so inference keeps the last good
    catalog until its 24h TTL lapses.
    """

    __tablename__ = "provider_model_cache"

    provider_id: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(String, primary_key=True)
    display: Mapped[str] = mapped_column(String, default="")
    offered: Mapped[int] = mapped_column(default=1)
    fetched_at: Mapped[str] = mapped_column(String, default="")


class ActiveProviderSelection(Base):
    """Singleton (id=1) single-active-provider selection.

    NULL provider_id/model_id (or a missing row) means paused: live
    inference fails closed with an honest "not configured" error.
    revision is optimistic concurrency for activate/deactivate: the
    writer's UPDATE filters on the revision it read, so a concurrent
    change collides with 0 affected rows instead of silently winning.
    """

    __tablename__ = "active_provider_selection"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[str | None] = mapped_column(String, nullable=True,
                                                   default=None)
    model_id: Mapped[str | None] = mapped_column(String, nullable=True,
                                                default=None)
    revision: Mapped[int] = mapped_column(default=1)
    updated_by: Mapped[str] = mapped_column(String, default="")
    updated_at: Mapped[str] = mapped_column(String, default="")

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_active_provider_singleton"),
    )


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

    _ENGINES.add(engine)
    return engine


def dispose_all_engines() -> None:
    """Close pooled connections of every live engine.

    Test hygiene only: engines dropped by tests would otherwise leave
    pooled SQLite handles to the garbage collector (ResourceWarnings).
    Production lifetimes are process-scoped and unaffected.
    """
    for engine in list(_ENGINES):
        try:
            engine.dispose()
        except Exception:
            pass


def _dispose_at_exit() -> None:
    """Best-effort pool close at interpreter shutdown.

    Runners without the pytest teardown hook (stdlib unittest) drop
    engines without disposing them; without this, their pooled SQLite
    handles surface as ResourceWarnings during shutdown GC. Production
    lifetimes are process-scoped, so closing idle handles at exit is
    a no-op there — it only makes shutdown deterministic.
    """
    dispose_all_engines()


atexit.register(_dispose_at_exit)


def make_session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False, future=True)


def init_db(engine) -> None:
    """Create missing auth tables. Safe to call repeatedly (tests + boot)."""
    Base.metadata.create_all(engine)


def alembic_script_location() -> str:
    from pathlib import Path as _Path
    return str(_Path(__file__).resolve().parent.parent / "alembic")


def script_head() -> str:
    """Single expected Alembic head; fails closed on script branches."""
    from alembic.config import Config as _Config
    from alembic.script import ScriptDirectory as _ScriptDirectory
    cfg = _Config()
    cfg.set_main_option("script_location", alembic_script_location())
    heads = _ScriptDirectory.from_config(cfg).get_heads()
    if len(heads) != 1:
        raise RuntimeError(
            "migrations must have exactly one head, found %r" % (heads,))
    return heads[0]


def ensure_migrated(engine) -> None:
    """Bring identity tables to Alembic head (authoritative path).

    Fresh databases upgrade from scratch. Databases created by the
    legacy create_all path carry the 0001 shape, so they are stamped
    0001 first and then upgraded — never rebuilt, never wiped.
    Databases on an older revision upgrade forward; multiple heads
    or a post-upgrade mismatch fail closed instead of booting stale.
    """
    from alembic import command as _command
    from alembic.config import Config as _Config
    from alembic.migration import MigrationContext as _MigrationContext
    from sqlalchemy import inspect as _inspect
    cfg = _Config()
    cfg.set_main_option("script_location", alembic_script_location())
    expected = script_head()
    with engine.connect() as conn:
        ctx = _MigrationContext.configure(conn)
        heads = ctx.get_current_heads()
        legacy = _inspect(conn).has_table("employees")
    if len(heads) > 1:
        raise RuntimeError(
            "database has multiple migration heads %r: refusing to boot"
            % (heads,))
    if list(heads) == [expected]:
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
            if legacy and not heads:
                _command.stamp(cfg, "0001")
            _command.upgrade(cfg, "head")
            conn.commit()
        with migrant.connect() as conn:
            ctx = _MigrationContext.configure(conn)
            landed = list(ctx.get_current_heads())
        if landed != [expected]:
            raise RuntimeError(
                "migration landed on %r, expected head %r"
                % (landed, expected))
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
