"""Employee access store over SQLAlchemy (Nextly db.py pattern).

Identical semantics to the legacy sqlite3 implementation it replaces:
verified WorkOS identities link by immutable ``workos_user_id`` (or by
verified email for pre-added staff — never a duplicate); unknown
identities become ``pending``; only the configured bootstrap email can
mint the first admin; suspend/revoke destroy sessions immediately; no
operation may leave zero active admins; enforcement is unconditional
(no setup bypass).
"""

from __future__ import annotations

import datetime
import hashlib
import secrets
import uuid

from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ci_backend.db import AuthPending, AuthSession, Employee, EmployeeAudit

COOKIE_NAME = "ci_session"
SESSION_TTL_S = 30 * 24 * 3600
PENDING_TTL_S = 10 * 60

STATUSES = ("pending", "active", "suspended", "revoked")
ROLES = ("admin", "employee")

# Allowed status moves; role changes are independent. Revoked is
# terminal: re-entry needs a fresh pending record approved by admin.
TRANSITIONS = {
    "pending": ("active", "revoked"),
    "active": ("suspended", "revoked"),
    "suspended": ("active", "revoked"),
    "revoked": (),
}


class StoreError(Exception):
    """User-safe authentication failure. Never carries secrets."""

    def __init__(self, message: str, code: str = "") -> None:
        super().__init__(message)
        self.code = code or ""


class Denied(Exception):
    """Protected access refused. gate names the frontend screen."""

    def __init__(self, gate: str, message: str = "") -> None:
        super().__init__(message or gate)
        self.gate = gate


# ---------------------------------------------------------------------------
# Pydantic schemas (request/response contracts for the FastAPI layer)
# ---------------------------------------------------------------------------


class OAuthStartRequest(BaseModel):
    provider: str = ""
    redirect_uri: str = ""


class OAuthFinishRequest(BaseModel):
    code: str = ""
    state: str = ""


class EmailLoginRequest(BaseModel):
    email: str = ""
    password: str = ""


class MagicSendRequest(BaseModel):
    email: str = ""


class MagicVerifyRequest(BaseModel):
    email: str = ""
    code: str = ""


class PasswordResetRequest(BaseModel):
    email: str = ""


class PasswordResetConfirm(BaseModel):
    token: str = ""
    password: str = ""


class EmployeeCreate(BaseModel):
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    role: str = "employee"


class RoleChange(BaseModel):
    role: str = ""


class SwitchRequest(BaseModel):
    employee_id: str = ""


class ProfileUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None


class PublicEmployee(BaseModel):
    id: str = ""
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    avatar_url: str = ""
    role: str = "employee"
    status: str = "pending"
    created_at: str = ""
    approved_at: str = ""
    approved_by: str = ""
    last_login_at: str = ""
    updated_at: str = ""


class AuditEvent(BaseModel):
    id: str = ""
    target_id: str = ""
    admin_id: str = ""
    action: str = ""
    prev_value: str = ""
    new_value: str = ""
    created_at: str = ""


class MeResponse(BaseModel):
    authenticated: bool = False
    gate: str = "login"
    employee: PublicEmployee | None = None
    is_admin: bool = False
    message: str = ""
    workos_configured: bool = False


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def public_employee(emp: Employee | None) -> PublicEmployee | None:
    if emp is None:
        return None
    return PublicEmployee(
        id=emp.id, email=emp.email, first_name=emp.first_name,
        last_name=emp.last_name, avatar_url=emp.avatar_url, role=emp.role,
        status=emp.status, created_at=emp.created_at,
        approved_at=emp.approved_at, approved_by=emp.approved_by,
        last_login_at=emp.last_login_at, updated_at=emp.updated_at,
    )


def get_employee(db: Session, employee_id: str) -> Employee | None:
    if not employee_id:
        return None
    return db.get(Employee, employee_id)


def find_employee(db: Session, workos_user_id: str = "", email: str = "") -> Employee | None:
    if workos_user_id:
        emp = db.scalars(select(Employee).where(
            Employee.workos_user_id == workos_user_id)).first()
        if emp is not None:
            return emp
    if email:
        return db.scalars(select(Employee).where(
            Employee.email == email.strip().lower())).first()
    return None


def bootstrap_admin_email(settings=None) -> str:
    if settings is not None and getattr(settings, "admin_email", ""):
        return settings.admin_email.strip().lower()
    import os
    return os.environ.get("CREATIVE_INTEL_ADMIN_EMAIL", "").strip().lower()


def ensure_identity(db: Session, identity: dict, settings=None) -> tuple[Employee, bool]:
    """Link a verified WorkOS identity to an employee record.

    Returns (employee, created). Unknown identities become pending
    requests, except the configured bootstrap admin email, which
    becomes the first admin when no admin exists yet.
    """
    email = (identity.get("email") or "").strip().lower()
    wid = identity.get("workos_user_id") or ""
    if not wid and not email:
        raise StoreError("WorkOS did not return a user.")
    emp = find_employee(db, wid, email if identity.get("verified") else "")
    now = utcnow()
    if emp is None:
        n_admins = db.scalar(select(func.count()).select_from(Employee).where(
            Employee.role == "admin")) or 0
        bootstrapped = bool(n_admins == 0 and email
                            and email == bootstrap_admin_email(settings))
        emp = Employee(
            id=uuid.uuid4().hex, workos_user_id=wid or None, email=email,
            first_name=identity.get("first_name") or "",
            last_name=identity.get("last_name") or "",
            avatar_url=identity.get("avatar_url") or "",
            role="admin" if bootstrapped else "employee",
            status="active" if bootstrapped else "pending",
            created_at=now, approved_at=now if bootstrapped else "",
            approved_by="bootstrap" if bootstrapped else "",
            last_login_at="", updated_at=now)
        db.add(emp)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise StoreError(
                "An account with that email is already registered.") from exc
        if bootstrapped:
            _audit(db, emp.id, emp.id, "EMPLOYEE_CREATED", "", "admin/active")
        db.commit()
        return emp, True
    changed = False
    if wid and not emp.workos_user_id:
        emp.workos_user_id = wid
        changed = True
    for field in ("first_name", "last_name"):
        if identity.get(field) and not getattr(emp, field):
            setattr(emp, field, identity[field])
            changed = True
    if identity.get("avatar_url") and not emp.avatar_url:
        emp.avatar_url = identity["avatar_url"]
        changed = True
    if changed:
        emp.updated_at = now
        db.commit()
    return emp, False


# ---------------------------------------------------------------------------
# OAuth pending states (server-side, expiring, single-use)
# ---------------------------------------------------------------------------


def pending_put(db: Session, state: str, provider: str, verifier: str) -> None:
    db.add(AuthPending(state=state, provider=provider, verifier=verifier,
                       created_at=utcnow()))
    db.commit()


def pending_pop(db: Session, state: str) -> AuthPending | None:
    row = db.get(AuthPending, state or "")
    if row is None:
        return None
    db.delete(row)
    db.commit()
    return row


def pending_valid(row: AuthPending) -> bool:
    try:
        born = datetime.datetime.fromisoformat(row.created_at)
        if born.tzinfo is None:
            born = born.replace(tzinfo=datetime.timezone.utc)
        age = (datetime.datetime.now(datetime.timezone.utc) - born).total_seconds()
    except (ValueError, OverflowError):
        return False
    return bool(row.verifier) and age <= PENDING_TTL_S


def sweep_pending(db: Session) -> None:
    """Drop expired OAuth states only (concurrent flows keep theirs)."""
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(seconds=PENDING_TTL_S)).isoformat()
    db.execute(delete(AuthPending).where(AuthPending.created_at < cutoff))
    db.commit()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


MAX_CONTAINER_CHARS = 64


def valid_container_id(value: object) -> str:
    """Validate an installation container id (item 18).

    "" means unbound (legacy clients). Otherwise 1-64 chars of
    letters, digits, "-" and "_". Anything else raises StoreError so
    login endpoints answer 409 instead of storing attacker-shaped data.
    """
    text = value if isinstance(value, str) else ""
    if text == "":
        return ""
    if len(text) > MAX_CONTAINER_CHARS or any(
            not (ch.isalnum() or ch in "-_") for ch in text):
        raise StoreError("Invalid container id.")
    return text


def create_session(db: Session, employee_id: str, workos_user_id: str,
                   container_id: str = "") -> str:
    """Issue a session token. Only the hash is stored; the raw token is
    shown once (Set-Cookie) and never logged."""
    token = secrets.token_urlsafe(32)
    now = datetime.datetime.now(datetime.timezone.utc)
    db.add(AuthSession(
        token_hash=_token_hash(token), employee_id=employee_id,
        workos_user_id=workos_user_id,
        container_id=valid_container_id(container_id),
        created_at=now.isoformat(timespec="seconds"),
        last_seen_at=now.isoformat(timespec="seconds"),
        expires_at=(now + datetime.timedelta(
            seconds=SESSION_TTL_S)).isoformat(timespec="seconds")))
    db.commit()
    return token


def session_container(db: Session, token: str) -> str | None:
    """Container bound to a live session token, or None when unknown."""
    row = _session_row(db, token)
    if row is None or _expired(row):
        return None
    return row.container_id or ""


def bind_session_container(db: Session, token: str,
                           container_id: str) -> str:
    """Adopt an unbound session into a container (first write wins).

    Used after OAuth logins, whose server-side redirect cannot carry the
    browser's container id. Rebinding an already-bound session is refused
    so a session observed elsewhere cannot be pulled into a foreign
    container. Returns the session's (possibly unchanged) container.
    """
    wanted = valid_container_id(container_id)
    if not wanted:
        raise StoreError("Invalid container id.")
    row = _session_row(db, token)
    if row is None or _expired(row):
        raise Denied("login", "Sign in to continue.")
    current = row.container_id or ""
    if not current:
        row.container_id = wanted
        db.commit()
        return wanted
    if current != wanted:
        raise Denied("login", "This session belongs to another "
                              "installation. Sign in again.")
    return current


def destroy_session(db: Session, token: str) -> None:
    if token:
        db.execute(delete(AuthSession).where(
            AuthSession.token_hash == _token_hash(token)))
        db.commit()


def destroy_employee_sessions(db: Session, employee_id: str) -> None:
    db.execute(delete(AuthSession).where(
        AuthSession.employee_id == employee_id))
    db.commit()


def revoke_all_sessions(db: Session, actor_id: str,
                        employee_id: str) -> int:
    """Destroy every session of an employee; audit SESSIONS_REVOKED.

    Returns the number of sessions destroyed. Used both for
    self-service "log out everywhere" (actor == employee) and for
    admin invalidation of another employee's sessions.
    """
    target = get_employee(db, employee_id)
    if target is None:
        raise StoreError("Employee not found.")
    doomed = db.scalars(select(AuthSession).where(
        AuthSession.employee_id == employee_id)).all()
    count = len(doomed)
    destroy_employee_sessions(db, employee_id)
    _audit(db, employee_id, actor_id, "SESSIONS_REVOKED",
           "%d active session(s)" % count, "0 active sessions")
    return count


def _session_row(db: Session, token: str) -> AuthSession | None:
    if not token:
        return None
    return db.get(AuthSession, _token_hash(token))


def _expired(row: AuthSession) -> bool:
    try:
        return (datetime.datetime.now(datetime.timezone.utc)
                > datetime.datetime.fromisoformat(row.expires_at))
    except (ValueError, TypeError):
        return True


def authorize(db: Session, token: str) -> tuple[Employee, str]:
    """Validate a session AND recheck employee status right now.

    Returns (employee, gate) with gate "app" for active staff.
    Anything else raises Denied — revocation takes effect immediately.
    """
    row = _session_row(db, token)
    if row is None:
        raise Denied("login", "Sign in to continue.")
    if _expired(row):
        destroy_session(db, token)
        raise Denied("login", "Your session expired. Sign in again.")
    emp = get_employee(db, row.employee_id)
    if emp is None:
        destroy_session(db, token)
        raise Denied("login", "Sign in to continue.")
    row.last_seen_at = utcnow()
    db.commit()
    status = emp.status or "pending"
    if status == "active":
        return emp, "app"
    raise Denied(status, {
        "pending": "Your access is pending approval.",
        "suspended": "Your access has been suspended.",
        "revoked": "Your access has been revoked.",
    }.get(status, "Your access is pending approval."))


def login_identity(db: Session, identity: dict, settings=None,
                   container_id: str = "") -> tuple[str, Employee, bool]:
    """Complete a verified WorkOS login: link employee, open session."""
    emp, created = ensure_identity(db, identity, settings)
    token = create_session(db, emp.id, emp.workos_user_id or "",
                           valid_container_id(container_id))
    emp.last_login_at = utcnow()
    db.commit()
    return token, emp, created


def me(db: Session, token: str, settings=None) -> MeResponse:
    """Session envelope for app boot: never raises, always describes."""
    from ci_backend import workos as workos_mod
    try:
        emp, _gate = authorize(db, token)
        return MeResponse(authenticated=True, gate="app",
                          employee=public_employee(emp),
                          is_admin=emp.role == "admin",
                          workos_configured=workos_mod.workos_configured(settings))
    except Denied as exc:
        emp = None
        row = _session_row(db, token)
        if row is not None:
            emp = public_employee(get_employee(db, row.employee_id))
        return MeResponse(
            authenticated=emp is not None, gate=exc.gate, employee=emp,
            is_admin=bool(emp) and emp.role == "admin" and exc.gate == "app",
            message=str(exc),
            workos_configured=workos_mod.workos_configured(settings))


def valid_session(db: Session, token: str) -> Employee | None:
    """Employee behind a live session token, or None (no status gate)."""
    row = _session_row(db, token)
    if row is None:
        return None
    if _expired(row):
        destroy_session(db, token)
        return None
    return get_employee(db, row.employee_id)


def has_live_session_in(db: Session, employee_id: str,
                        container_id: str) -> bool:
    """Item 18: live session for employee inside one container only."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return db.scalar(select(func.count()).select_from(AuthSession).where(
        AuthSession.employee_id == employee_id,
        AuthSession.container_id == (container_id or ""),
        AuthSession.expires_at > now)) not in (None, 0)


def list_accounts(db: Session, container_id: str = "") -> list[dict]:
    """Stored account identities visible inside one container.

    Only accounts with a live session bound to the caller's container
    are returned, so one installation can never enumerate accounts from
    another. Unbound ("") callers see unbound sessions (legacy parity).
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    rows = db.execute(
        select(AuthSession, Employee)
        .outerjoin(Employee, Employee.id == AuthSession.employee_id)
        .where(AuthSession.container_id == (container_id or ""),
               AuthSession.expires_at > now)
        .order_by(AuthSession.last_seen_at.desc())).all()
    out = []
    for sess, emp in rows:
        out.append({
            "employee_id": sess.employee_id,
            "last_seen_at": sess.last_seen_at,
            "email": (emp.email if emp else "") or "",
            "first_name": (emp.first_name if emp else "") or "",
            "last_name": (emp.last_name if emp else "") or "",
            "avatar_url": (emp.avatar_url if emp else "") or "",
            "role": (emp.role if emp else "") or "",
            "status": (emp.status if emp else "") or "",
        })
    return out


MAX_NAME_CHARS = 120
MAX_AVATAR_URL_CHARS = 2048
MAX_AVATAR_BYTES = 2 * 1024 * 1024
AVATAR_TYPES = {".jpg", ".jpeg", ".png", ".webp"}


def _clean_name(value, field: str) -> str:
    text = (value or "").strip()
    if len(text) > MAX_NAME_CHARS:
        raise StoreError("%s must be %d characters or fewer."
                         % (field, MAX_NAME_CHARS))
    return text


def _clean_avatar_url(value) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) > MAX_AVATAR_URL_CHARS:
        raise StoreError("Avatar URL is too long.")
    lowered = text.lower()
    if lowered.startswith(("http://", "https://")):
        return text
    if text.startswith("/api/auth/avatar/"):
        return text
    raise StoreError("Avatar must be an http(s) URL or an uploaded avatar."
                     )


def update_profile(db: Session, employee_id: str, first_name=None,
                   last_name=None, avatar_url=None) -> Employee:
    """Self-service profile edit for an active employee.

    None means "leave unchanged"; empty avatar_url clears the avatar.
    Every change is audit-logged as PROFILE_UPDATED (admin_id=self).
    """
    emp = get_employee(db, employee_id)
    if emp is None:
        raise StoreError("Employee not found.")
    if (emp.status or "") != "active":
        raise StoreError("Only active employees can edit their profile.")
    changes = []
    if first_name is not None:
        cleaned = _clean_name(first_name, "First name")
        if cleaned != (emp.first_name or ""):
            changes.append(("first_name", emp.first_name or "", cleaned))
            emp.first_name = cleaned
    if last_name is not None:
        cleaned = _clean_name(last_name, "Last name")
        if cleaned != (emp.last_name or ""):
            changes.append(("last_name", emp.last_name or "", cleaned))
            emp.last_name = cleaned
    if avatar_url is not None:
        cleaned = _clean_avatar_url(avatar_url)
        if cleaned != (emp.avatar_url or ""):
            changes.append(("avatar_url", emp.avatar_url or "", cleaned))
            emp.avatar_url = cleaned
    if changes:
        emp.updated_at = utcnow()
        db.commit()
        _audit(db, emp.id, emp.id, "PROFILE_UPDATED",
               "; ".join("%s: %s" % (field, prev)
                           for field, prev, _new in changes),
               "; ".join("%s: %s" % (field, new)
                           for field, _prev, new in changes))
    return emp


def _avatar_dir(store_dir: str) -> str:
    import os
    path = os.path.join(store_dir, "avatars")
    os.makedirs(path, exist_ok=True)
    return path


def save_avatar(db: Session, employee_id: str, filename: str,
                content: bytes, store_dir: str) -> Employee:
    """Store a manually uploaded avatar image for an active employee.

    Validates type (jpeg/png/webp) and size (<=2MB) before writing;
    replaces any previous upload and points avatar_url at the
    authenticated avatar route. Raises StoreError on any rejection.
    """
    import os
    emp = get_employee(db, employee_id)
    if emp is None:
        raise StoreError("Employee not found.")
    if (emp.status or "") != "active":
        raise StoreError("Only active employees can edit their profile.")
    if not isinstance(content, (bytes, bytearray)) or not content:
        raise StoreError("Empty avatar upload.")
    if len(content) > MAX_AVATAR_BYTES:
        raise StoreError("Avatar exceeds 2 MB.")
    from creative_intel import media as media_mod
    try:
        ext, mime = media_mod.check_upload(filename, bytes(content))
    except ValueError as exc:
        raise StoreError(str(exc))
    if ext not in AVATAR_TYPES:
        raise StoreError("Avatar must be a JPEG, PNG or WebP image.")
    if ext == ".jpeg":
        ext = ".jpg"
    directory = _avatar_dir(store_dir)
    dest = os.path.join(directory, employee_id + ext)
    if os.path.basename(dest) != employee_id + ext:
        raise StoreError("Invalid avatar filename.")
    for old in os.listdir(directory):
        if old.startswith(employee_id + ".") and old != employee_id + ext:
            try:
                os.remove(os.path.join(directory, old))
            except OSError:
                pass
    with open(dest, "wb") as fh:
        fh.write(bytes(content))
    prev = emp.avatar_url or ""
    emp.avatar_url = "/api/auth/avatar/" + employee_id
    emp.updated_at = utcnow()
    db.commit()
    _audit(db, emp.id, emp.id, "PROFILE_UPDATED",
           "avatar_url: %s" % prev, "avatar_url: %s" % emp.avatar_url)
    return emp


def load_avatar(employee_id: str, store_dir: str):
    """(path, mime) for an employee's uploaded avatar, or None."""
    import os

    from creative_intel import media as media_mod
    if not isinstance(employee_id, str) or not employee_id \
            or "/" in employee_id or "\\\\" in employee_id:
        return None
    try:
        names = os.listdir(os.path.join(store_dir, "avatars"))
    except OSError:
        return None
    for name in sorted(names):
        if name.startswith(employee_id + "."):
            ext = name[name.rfind("."):].lower()
            if ext in AVATAR_TYPES and media_mod.TYPES.get(ext):
                return (os.path.join(store_dir, "avatars", name),
                        media_mod.TYPES[ext][0])
    return None


def session_cookie(token: str, max_age: int = SESSION_TTL_S,
                   secure: bool = False) -> str:
    return ("%s=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Lax%s"
            % (COOKIE_NAME, token, max_age,
               "; Secure" if secure else ""))


def clear_cookie(secure: bool = False) -> str:
    return ("%s=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax%s"
            % (COOKIE_NAME, "; Secure" if secure else ""))


def token_from_cookie_header(raw: str) -> str:
    """Extract the session token from a Cookie header (never logs it)."""
    for part in (raw or "").split(";"):
        name, _, value = part.partition("=")
        if name.strip() == COOKIE_NAME:
            return value.strip()
    return ""


# ---------------------------------------------------------------------------
# Admin operations (every route re-checks active+admin server-side)
# ---------------------------------------------------------------------------


def _audit(db: Session, target_id: str, admin_id: str, action: str,
           prev: str, new: str) -> None:
    db.add(EmployeeAudit(
        id=uuid.uuid4().hex, target_id=target_id or "",
        admin_id=admin_id or "", action=action, prev_value=prev or "",
        new_value=new or "", created_at=utcnow()))
    db.commit()


def audit_event(row: EmployeeAudit) -> AuditEvent:
    return AuditEvent(
        id=row.id, target_id=row.target_id, admin_id=row.admin_id,
        action=row.action, prev_value=row.prev_value,
        new_value=row.new_value, created_at=row.created_at)


def admin_list(db: Session, search: str = "", filt: str = "") -> list[PublicEmployee]:
    """Employees with optional search (name/email) and status/role filter."""
    filt = (filt or "").strip().lower()
    needle = (search or "").strip().lower()
    query = select(Employee).order_by(Employee.updated_at.desc())
    if filt in ("active", "pending", "suspended", "revoked"):
        query = query.where(Employee.status == filt)
    elif filt in ("admin", "employee"):
        query = query.where(Employee.role == filt)
    out = []
    for emp in db.scalars(query).all():
        if needle and needle not in ("%s %s" % (
                emp.first_name or "", emp.last_name or "")).lower() \
                and needle not in (emp.email or ""):
            continue
        out.append(public_employee(emp))
    return out


def admin_create(db: Session, admin_id: str, email: str, first_name: str = "",
                 last_name: str = "", role: str = "employee") -> Employee:
    """Pre-add staff (default Active). Links on first verified login."""
    email = (email or "").strip().lower()
    if "@" not in email:
        raise StoreError("Enter a valid email address.")
    if role not in ROLES:
        raise StoreError("Role must be admin or employee.")
    if find_employee(db, "", email) is not None:
        raise StoreError("That email is already registered.")
    now = utcnow()
    emp = Employee(
        id=uuid.uuid4().hex, workos_user_id=None, email=email,
        first_name=(first_name or "").strip(),
        last_name=(last_name or "").strip(), avatar_url="", role=role,
        status="active", created_at=now, approved_at=now,
        approved_by=admin_id, last_login_at="", updated_at=now)
    db.add(emp)
    db.flush()
    _audit(db, emp.id, admin_id, "EMPLOYEE_CREATED", "", "%s/active" % role)
    db.commit()
    return emp


def _active_admins(db: Session, exclude_id: str = "") -> list[str]:
    query = select(Employee.id).where(
        Employee.role == "admin", Employee.status == "active")
    if exclude_id:
        query = query.where(Employee.id != exclude_id)
    return list(db.scalars(query).all())


def _refuse_last_admin(db: Session, employee_id: str) -> None:
    """Forbid an operation that would leave zero active admins."""
    emp = get_employee(db, employee_id)
    if emp and emp.role == "admin" and emp.status == "active" \
            and not _active_admins(db, employee_id):
        raise StoreError("Refused: at least one active admin must remain.")


def admin_set_status(db: Session, admin_id: str, employee_id: str,
                     new_status: str, action: str) -> Employee:
    """Approve/suspend/reactivate/revoke with transition validation."""
    emp = get_employee(db, employee_id)
    if emp is None:
        raise StoreError("Employee not found.")
    if new_status not in STATUSES:
        raise StoreError("Unknown status.")
    if new_status not in TRANSITIONS.get(emp.status or "", ()):
        raise StoreError("Cannot move %s to %s." % (emp.status, new_status))
    if new_status in ("suspended", "revoked"):
        _refuse_last_admin(db, employee_id)
    prev = emp.status
    now = utcnow()
    if action == "EMPLOYEE_APPROVED":
        emp.approved_at, emp.approved_by = now, admin_id
    emp.status = new_status
    emp.updated_at = now
    db.flush()
    _audit(db, employee_id, admin_id, action, "%s" % prev, "%s" % new_status)
    if new_status in ("suspended", "revoked"):
        destroy_employee_sessions(db, employee_id)
    else:
        db.commit()
    return emp


def admin_set_role(db: Session, admin_id: str, employee_id: str,
                   role: str) -> Employee:
    if role not in ROLES:
        raise StoreError("Role must be admin or employee.")
    emp = get_employee(db, employee_id)
    if emp is None:
        raise StoreError("Employee not found.")
    if emp.role == role:
        return emp
    if role != "admin" and (emp.status or "") == "active":
        _refuse_last_admin(db, employee_id)
    prev = emp.role
    emp.role = role
    emp.updated_at = utcnow()
    db.flush()
    _audit(db, employee_id, admin_id, "ROLE_CHANGED",
           "%s" % prev, "%s" % role)
    db.commit()
    return emp


def admin_audit_list(db: Session, limit: int = 100) -> list[AuditEvent]:
    try:
        limit = max(1, min(500, int(limit)))
    except (TypeError, ValueError):
        limit = 100
    rows = db.scalars(select(EmployeeAudit).order_by(
        EmployeeAudit.created_at.desc(),
        EmployeeAudit.id.desc()).limit(limit)).all()
    return [audit_event(r) for r in rows]


def admin_search(db: Session, needle: str) -> list[PublicEmployee]:
    needle = (needle or "").strip().lower()
    if not needle:
        return admin_list(db)
    like = "%%%s%%" % needle.replace("%", "").replace("_", "")
    rows = db.scalars(select(Employee).where(or_(
        func.lower(Employee.email).like(like),
        func.lower(Employee.first_name).like(like),
        func.lower(Employee.last_name).like(like),
    )).order_by(Employee.updated_at.desc())).all()
    return [public_employee(e) for e in rows]
