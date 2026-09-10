"""SQLAlchemy models + engine (Nextly db.py pattern).

Auth tables mirror the legacy sqlite3 schema exactly (same table and
column names) so existing databases open unchanged: ``employees``,
``auth_sessions``, ``auth_pending``, ``employee_audit``.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Index, String, Text, create_engine, event
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
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    employee_id: Mapped[str] = mapped_column(String, default="")
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

    id: Mapped[str] = mapped_column(String, primary_key=True)
    target_id: Mapped[str] = mapped_column(String, default="")
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


def session_scope(factory) -> Session:
    return factory()
