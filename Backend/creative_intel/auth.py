"""WorkOS authentication + admin-controlled employee access (stdlib port).

Port of Nextly AI's authentication architecture (mac-backend workos.py
plus the AccountStore OAuth/session/activation flow), adapted to
Creative Intelligence's stdlib stack:

* urllib instead of httpx for WorkOS HTTPS (same endpoints/params),
* sqlite3 tables + schema.migrate() instead of SQLAlchemy/Alembic,
* plain functions instead of Pydantic models,
* unittest instead of pytest.

Deliberately NOT ported: the third-party license bridge
(keys/seats/plans/device caps/entitlement checks), mock-auth
placeholders, and the single-account restriction (Creative
Intelligence is multi-account: every stored account passes employee
authorization independently). There is no licensing system here;
access is decided by administrator approval of employee records.

Security model: WorkOS proves identity; the employees table decides
access (default deny). Protected routes re-validate session +
active-employee on every call, so suspend/revoke take effect
immediately. Secrets live in Keychain/env via providers.live_secret
and never enter logs, errors, URLs, or the repo.
"""

import base64
import datetime
import hashlib
import json
import os
import secrets
import sqlite3
import time
import urllib.parse
import urllib.request
import uuid

HTTP_TIMEOUT_S = 20.0
PENDING_TTL_S = 600
SESSION_TTL_S = 30 * 24 * 3600
COOKIE_NAME = "ci_session"

PROVIDERS = {
    "google": "GoogleOAuth",
    "github": "GitHubOAuth",
    "microsoft": "MicrosoftOAuth",
    "apple": "AppleOAuth",
}

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


class AuthError(Exception):
    """User-safe authentication failure. Never carries secrets."""

    def __init__(self, message, code=""):
        super().__init__(message)
        self.code = code or ""


def _env(name, default=""):
    return os.environ.get(name, default)


def workos_base():
    """Endpoint base: env override (tests/stubs) else WorkOS default."""
    from creative_intel import providers as providers_mod
    return providers_mod.live_base(
        "workos", "https://api.workos.com").rstrip("/")


def _api_key():
    from creative_intel import providers as providers_mod
    key = providers_mod.live_secret("creative-intel-workos")
    if not key:
        raise AuthError("WorkOS is not configured.")
    return key


def client_id():
    return _env("CREATIVE_INTEL_WORKOS_CLIENT_ID")


def workos_configured():
    """Presence probe only: never reads the secret value into memory."""
    if not client_id():
        return False
    if _env("CREATIVE_INTEL_KEY_WORKOS"):
        return True
    return _keychain_has_workos()


def _keychain_has_workos():
    from creative_intel import providers as providers_mod
    return providers_mod.keychain_has("creative-intel-workos")


def redirect_uri(port=None):
    """OAuth callback URI. Env override wins (must be allowlisted in
    the WorkOS dashboard); otherwise the local server address."""
    override = _env("CREATIVE_INTEL_WORKOS_REDIRECT_URI")
    if override:
        return override
    return "http://127.0.0.1:%s/api/auth/callback" % (port or 4321)


def _workos_post(path, payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        workos_base() + path, data=body, method="POST",
        headers={"Authorization": "Bearer %s" % _api_key(),
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise _http_error(exc, "Could not sign in.")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise AuthError("Could not reach WorkOS.") from exc


def _workos_get(path):
    req = urllib.request.Request(
        workos_base() + path, method="GET",
        headers={"Authorization": "Bearer %s" % _api_key()})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise _http_error(exc, "Could not reach WorkOS.")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise AuthError("Could not reach WorkOS.") from exc


def _error_detail(payload, fallback):
    if not isinstance(payload, dict):
        return fallback, ""
    code = str(payload.get("code") or "")
    for key in ("message", "error_description", "error"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), code
    return fallback, code


def _http_error(exc, fallback):
    try:
        payload = json.loads(exc.read() or b"{}")
    except (OSError, ValueError):
        payload = {}
    message, code = _error_detail(payload, fallback)
    return AuthError(message, code=code)


def pkce_pair():
    """S256 PKCE verifier/challenge (Nextly workos.pkce_pair)."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def authorization_url(provider, state, code_challenge, redir=None):
    """WorkOS authorize URL for one of the four OAuth providers."""
    mapped = PROVIDERS.get(provider)
    if not mapped:
        raise AuthError("Unknown sign-in provider.")
    query = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id(),
        "redirect_uri": redir or redirect_uri(),
        "provider": mapped,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })
    return "%s/user_management/authorize?%s" % (workos_base(), query)


def authenticate_code(code, code_verifier):
    return _workos_post("/user_management/authenticate", {
        "client_id": client_id(),
        "client_secret": _api_key(),
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
    })


def authenticate_password(email, password):
    return _workos_post("/user_management/authenticate", {
        "client_id": client_id(),
        "client_secret": _api_key(),
        "grant_type": "password",
        "email": email,
        "password": password,
    })


def send_magic_code(email):
    _workos_post("/user_management/magic_auth", {"email": email})


def authenticate_magic_code(email, code):
    return _workos_post("/user_management/authenticate", {
        "client_id": client_id(),
        "client_secret": _api_key(),
        "grant_type": "urn:workos:oauth:grant-type:magic-auth:code",
        "email": email,
        "code": code,
    })


def send_password_reset(email):
    _workos_post("/user_management/password_reset", {"email": email})


def reset_password(token, password):
    if len(password or "") < 8:
        raise AuthError("Use a password with at least 8 characters.")
    return _workos_post("/user_management/password_reset/confirm", {
        "token": token,
        "new_password": password,
    })


def public_identity(raw, provider="email"):
    """Normalized verified identity (Nextly workos.public_user)."""
    user = raw.get("user") if isinstance(raw.get("user"), dict) else raw
    if not isinstance(user, dict):
        raise AuthError("WorkOS returned an unexpected user payload.")
    email = str(user.get("email") or "").strip().lower()
    verified = bool(user.get("email_verified")
                    if "email_verified" in user else user.get("verified"))
    return {
        "workos_user_id": str(user.get("workos_user_id")
                               or user.get("id") or ""),
        "email": email,
        "first_name": str(user.get("first_name") or "").strip(),
        "last_name": str(user.get("last_name") or "").strip(),
        "avatar_url": str(user.get("avatar_url")
                           or user.get("profile_picture_url") or ""),
        "verified": verified,
        "provider": provider,
    }


def utcnow():
    return datetime.datetime.now(
        datetime.timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# OAuth pending states (CSRF protection, Nextly oauth_pending pattern)
# ---------------------------------------------------------------------------

def start_oauth(conn, provider, redir=None):
    """Begin an OAuth flow: returns {url, state} for the browser.

    Stores verifier + provider server-side under a random state so the
    callback can verify code/state/PKCE without trusting the client.
    """
    if provider not in PROVIDERS:
        raise AuthError("Unknown sign-in provider.")
    if not workos_configured():
        raise AuthError("WorkOS is not configured.")
    sweep_pending(conn)
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)
    conn.execute(
        "INSERT INTO auth_pending (state, provider, verifier, created_at)"
        " VALUES (?, ?, ?, ?)", (state, provider, verifier, utcnow()))
    conn.commit()
    url = authorization_url(provider, state, challenge, redir)
    return {"url": url, "state": state}


def finish_oauth(conn, code, state):
    """Exchange a callback code for a verified identity.

    Single-use state: a replayed or expired callback fails closed and
    creates no employee and no session (duplicate-callback safe).
    """
    if not workos_configured():
        raise AuthError("WorkOS is not configured.")
    row = conn.execute(
        "SELECT provider, verifier, created_at FROM auth_pending"
        " WHERE state=?", (state or "",)).fetchone()
    conn.execute("DELETE FROM auth_pending WHERE state=?", (state or "",))
    conn.commit()
    if row is None:
        raise AuthError("That sign-in expired. Try again.")
    provider, verifier, created_at = row
    try:
        born = datetime.datetime.fromisoformat(created_at)
        if born.tzinfo is None:
            born = born.replace(tzinfo=datetime.timezone.utc)
        age = (datetime.datetime.now(datetime.timezone.utc)
               - born).total_seconds()
    except (ValueError, OverflowError):
        age = PENDING_TTL_S + 1
    if not verifier or age > PENDING_TTL_S:
        raise AuthError("That sign-in expired. Try again.")
    try:
        raw = authenticate_code(code, verifier)
    except AuthError as exc:
        raise AuthError(str(exc), code=exc.code)
    identity = public_identity(raw, provider=provider)
    if not identity["workos_user_id"] or not identity["verified"]:
        raise AuthError("WorkOS did not return a verified identity.")
    return identity


def sweep_pending(conn):
    """Drop expired OAuth states only (concurrent flows keep theirs)."""
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(seconds=PENDING_TTL_S)).isoformat()
    conn.execute("DELETE FROM auth_pending WHERE created_at < ?", (cutoff,))
    conn.commit()


# ---------------------------------------------------------------------------
# Sessions (server-side bearer tokens, HttpOnly cookies)
# ---------------------------------------------------------------------------

def _token_hash(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def create_session(conn, employee_id, workos_user_id):
    """Issue a session token. Only the hash is stored; the raw token
    is shown once (Set-Cookie) and never logged."""
    token = secrets.token_urlsafe(32)
    now = datetime.datetime.now(datetime.timezone.utc)
    conn.execute(
        "INSERT INTO auth_sessions (token_hash, employee_id,"
        " workos_user_id, created_at, last_seen_at, expires_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (_token_hash(token), employee_id, workos_user_id,
         now.isoformat(timespec="seconds"), now.isoformat(timespec="seconds"),
         (now + datetime.timedelta(seconds=SESSION_TTL_S)).isoformat(
             timespec="seconds")))
    conn.commit()
    return token


def destroy_session(conn, token):
    """Logout: the token stops working immediately."""
    if token:
        conn.execute("DELETE FROM auth_sessions WHERE token_hash=?",
                     (_token_hash(token),))
        conn.commit()


def destroy_employee_sessions(conn, employee_id):
    """Revoke every session of one employee (used on suspend/revoke)."""
    conn.execute("DELETE FROM auth_sessions WHERE employee_id=?",
                 (employee_id,))
    conn.commit()


def _employee_columns():
    return ("id, workos_user_id, email, first_name, last_name,"
            " avatar_url, role, status, created_at, approved_at,"
            " approved_by, last_login_at, updated_at")


def _row_employee(row):
    keys = ("id", "workos_user_id", "email", "first_name", "last_name",
            "avatar_url", "role", "status", "created_at", "approved_at",
            "approved_by", "last_login_at", "updated_at")
    return dict(zip(keys, row))


def get_employee(conn, employee_id):
    row = conn.execute(
        "SELECT %s FROM employees WHERE id=?" % _employee_columns(),
        (employee_id,)).fetchone()
    return _row_employee(row) if row else None


def find_employee(conn, workos_user_id="", email=""):
    if workos_user_id:
        row = conn.execute(
            "SELECT %s FROM employees WHERE workos_user_id=?"
            % _employee_columns(), (workos_user_id,)).fetchone()
        if row:
            return _row_employee(row)
    if email:
        row = conn.execute(
            "SELECT %s FROM employees WHERE email=?" % _employee_columns(),
            (email.strip().lower(),)).fetchone()
        if row:
            return _row_employee(row)
    return None


def public_employee(emp):
    """Safe employee shape for the frontend (no internal notes)."""
    if not emp:
        return None
    return {k: emp.get(k) for k in
            ("id", "email", "first_name", "last_name", "avatar_url",
             "role", "status", "last_login_at")}


def bootstrap_admin_email():
    return _env("CREATIVE_INTEL_ADMIN_EMAIL", "").strip().lower()


def ensure_identity(conn, identity):
    """Link a verified WorkOS identity to an employee record.

    Find by immutable workos_user_id, else by verified email (pre-added
    staff link here — never a duplicate). Unknown identities become
    pending requests, except the configured bootstrap admin email,
    which becomes the first admin. Returns (employee, created).
    """
    email = (identity.get("email") or "").strip().lower()
    wid = identity.get("workos_user_id") or ""
    if not wid and not email:
        raise AuthError("WorkOS did not return a user.")
    emp = find_employee(conn, wid, email if identity.get("verified") else "")
    now = utcnow()
    if emp is None:
        emp = {
            "id": uuid.uuid4().hex,
            "workos_user_id": wid or None,
            "email": email,
            "first_name": identity.get("first_name") or "",
            "last_name": identity.get("last_name") or "",
            "avatar_url": identity.get("avatar_url") or "",
            "role": "employee",
            "status": "pending",
            "created_at": now,
            "approved_at": "",
            "approved_by": "",
            "last_login_at": "",
            "updated_at": now,
        }
        admins = conn.execute(
            "SELECT COUNT(*) FROM employees WHERE role='admin'").fetchone()
        bootstrapped = bool(admins and admins[0] == 0 and email
                            and email == bootstrap_admin_email())
        if bootstrapped:
            emp["role"] = "admin"
            emp["status"] = "active"
            emp["approved_at"] = now
            emp["approved_by"] = "bootstrap"
        try:
            conn.execute(
                "INSERT INTO employees (id, workos_user_id, email,"
                " first_name, last_name, avatar_url, role, status,"
                " created_at, approved_at, approved_by, last_login_at,"
                " updated_at)"
                " VALUES (:id, :workos_user_id, :email, :first_name,"
                " :last_name, :avatar_url, :role, :status, :created_at,"
                " :approved_at, :approved_by, :last_login_at,"
                " :updated_at)", emp)
        except sqlite3.IntegrityError as exc:
            raise AuthError(
                "An account with that email is already registered.") from exc
        if bootstrapped:
            audit(conn, emp["id"], emp["id"], "EMPLOYEE_CREATED",
                  "", "admin/active")
        conn.commit()
        return emp, True
    changed = False
    if wid and not emp.get("workos_user_id"):
        emp["workos_user_id"] = wid
        changed = True
    for field in ("first_name", "last_name"):
        if identity.get(field) and not emp.get(field):
            emp[field] = identity[field]
            changed = True
    if identity.get("avatar_url") and not emp.get("avatar_url"):
        emp["avatar_url"] = identity["avatar_url"]
        changed = True
    if changed:
        emp["updated_at"] = now
        conn.execute(
            "UPDATE employees SET workos_user_id=?, first_name=?,"
            " last_name=?, avatar_url=?, updated_at=? WHERE id=?",
            (emp["workos_user_id"], emp["first_name"], emp["last_name"],
             emp["avatar_url"], now, emp["id"]))
        conn.commit()
    return emp, False


class Denied(Exception):
    """Protected access refused. gate names the frontend screen."""

    def __init__(self, gate, message=""):
        super().__init__(message or gate)
        self.gate = gate


def _session_row(conn, token):
    if not token:
        return None
    return conn.execute(
        "SELECT employee_id, workos_user_id, expires_at FROM auth_sessions"
        " WHERE token_hash=?", (_token_hash(token),)).fetchone()


def authorize(conn, token):
    """Validate a session AND recheck employee status right now.

    Returns (employee, gate) with gate "app" for active staff.
    Suspended/revoked/expired/unknown sessions raise Denied with the
    frontend screen to show — revocation takes effect immediately.
    """
    row = _session_row(conn, token)
    if row is None:
        raise Denied("login", "Sign in to continue.")
    employee_id = row[0]
    try:
        expired = (datetime.datetime.now(datetime.timezone.utc)
                   > datetime.datetime.fromisoformat(row[2]))
    except (ValueError, TypeError):
        expired = True
    if expired:
        destroy_session(conn, token)
        raise Denied("login", "Your session expired. Sign in again.")
    emp = get_employee(conn, employee_id)
    if emp is None:
        destroy_session(conn, token)
        raise Denied("login", "Sign in to continue.")
    conn.execute("UPDATE auth_sessions SET last_seen_at=? WHERE token_hash=?",
                 (utcnow(), _token_hash(token)))
    conn.commit()
    status = emp.get("status") or "pending"
    if status == "active":
        return emp, "app"
    if status in ("pending", "suspended", "revoked"):
        raise Denied(status if status != "pending" else "pending",
                     {"pending": "Your access is pending approval.",
                      "suspended": "Your access has been suspended.",
                      "revoked": "Your access has been revoked."}[status])
    raise Denied("pending", "Your access is pending approval.")


def login_identity(conn, identity):
    """Complete a verified WorkOS login: link employee, open session.

    Returns (token, employee, created). The session works for /me and
    account screens; data APIs additionally require active status.
    """
    emp, created = ensure_identity(conn, identity)
    token = create_session(conn, emp["id"], emp.get("workos_user_id") or "")
    conn.execute("UPDATE employees SET last_login_at=? WHERE id=?",
                 (utcnow(), emp["id"]))
    conn.commit()
    emp["last_login_at"] = utcnow()
    return token, emp, created


def me(conn, token):
    """Session envelope for app boot: never raises, always describes."""
    try:
        emp, _gate = authorize(conn, token)
        return {"authenticated": True, "gate": "app",
                "employee": public_employee(emp),
                "is_admin": emp.get("role") == "admin",
                "workos_configured": workos_configured()}
    except Denied as exc:
        emp = None
        row = _session_row(conn, token)
        if row is not None:
            emp = public_employee(get_employee(conn, row[0]))
        return {"authenticated": emp is not None, "gate": exc.gate,
                "employee": emp,
                "is_admin": bool(emp) and emp.get("role") == "admin"
                and exc.gate == "app",
                "message": str(exc),
                "workos_configured": workos_configured()}


def enforced(conn):
    """Access control is live once any employee record exists.

    A pristine database (no identities at all) runs in setup mode so
    first-run and the pre-auth test suite keep working; the moment
    the first login or pre-add creates an employee, every protected
    route requires a live session for an active employee. There is no
    override flag — enforcement is purely a function of DB state.
    """
    row = conn.execute("SELECT COUNT(*) FROM employees").fetchone()
    return bool(row and row[0])


def valid_session(conn, token):
    """Employee behind a live session token, or None.

    Checks session validity only (row + expiry + known employee) —
    no status gate. Used by account screens (logout/switch/accounts),
    which pending users must also reach.
    """
    row = _session_row(conn, token)
    if row is None:
        return None
    try:
        expired = (datetime.datetime.now(datetime.timezone.utc)
                   > datetime.datetime.fromisoformat(row[2]))
    except (ValueError, TypeError):
        return None
    if expired:
        destroy_session(conn, token)
        return None
    return get_employee(conn, row[0])


def has_live_session(conn, employee_id):
    """True when the employee holds at least one unexpired session.

    Account switching mints a FRESH token only for identities already
    authenticated on this device — never for strangers.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    row = conn.execute(
        "SELECT 1 FROM auth_sessions WHERE employee_id=?"
        " AND expires_at > ? LIMIT 1", (employee_id, now)).fetchone()
    return row is not None


def list_accounts(conn):
    """Every stored account identity (for the account menu/switcher)."""
    out = []
    for row in conn.execute(
            "SELECT s.token_hash, s.employee_id, s.last_seen_at,"
            " e.email, e.first_name, e.last_name, e.avatar_url,"
            " e.role, e.status FROM auth_sessions s"
            " LEFT JOIN employees e ON e.id=s.employee_id"
            " ORDER BY s.last_seen_at DESC").fetchall():
        out.append({"employee_id": row[1], "last_seen_at": row[2],
                    "email": row[3] or "", "first_name": row[4] or "",
                    "last_name": row[5] or "", "avatar_url": row[6] or "",
                    "role": row[7] or "", "status": row[8] or ""})
    return out


# ---------------------------------------------------------------------------
# Admin operations (every route re-checks active+admin server-side)
# ---------------------------------------------------------------------------

def audit(conn, target_id, admin_id, action, prev, new):
    conn.execute(
        "INSERT INTO employee_audit (id, target_id, admin_id, action,"
        " prev_value, new_value, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (uuid.uuid4().hex, target_id or "", admin_id or "", action,
         prev or "", new or "", utcnow()))
    conn.commit()


def admin_list(conn, search="", filt=""):
    """Employees with optional search (name/email) and status/role filter."""
    filt = (filt or "").strip().lower()
    rows = conn.execute(
        "SELECT %s FROM employees ORDER BY updated_at DESC"
        % _employee_columns()).fetchall()
    out = []
    needle = (search or "").strip().lower()
    for row in rows:
        emp = _row_employee(row)
        if needle and needle not in ("%s %s" % (
                emp.get("first_name") or "", emp.get("last_name") or "")
                ).lower() and needle not in (emp.get("email") or ""):
            continue
        if filt in ("active", "pending", "suspended", "revoked"):
            if emp.get("status") != filt:
                continue
        elif filt in ("admin", "employee"):
            if emp.get("role") != filt:
                continue
        out.append(public_employee(emp))
    return out


def admin_create(conn, admin_id, email, first_name="", last_name="",
                 role="employee"):
    """Pre-add staff (default Active). Links on first verified login."""
    email = (email or "").strip().lower()
    if "@" not in email:
        raise AuthError("Enter a valid email address.")
    if role not in ROLES:
        raise AuthError("Role must be admin or employee.")
    if find_employee(conn, "", email) is not None:
        raise AuthError("That email is already registered.")
    now = utcnow()
    emp_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO employees (id, workos_user_id, email, first_name,"
        " last_name, avatar_url, role, status, created_at, approved_at,"
        " approved_by, last_login_at, updated_at)"
        " VALUES (?, NULL, ?, ?, ?, '', ?, 'active', ?, ?, ?, '', ?)",
        (emp_id, email, (first_name or "").strip(),
         (last_name or "").strip(), role, now, now, admin_id, now))
    audit(conn, emp_id, admin_id, "EMPLOYEE_CREATED", "", "%s/active" % role)
    conn.commit()
    return get_employee(conn, emp_id)


def admin_set_status(conn, admin_id, employee_id, new_status, action):
    """Approve/suspend/reactivate/revoke with transition validation."""
    emp = get_employee(conn, employee_id)
    if emp is None:
        raise AuthError("Employee not found.")
    if new_status not in STATUSES:
        raise AuthError("Unknown status.")
    if new_status not in TRANSITIONS.get(emp.get("status") or "", ()):
        raise AuthError("Cannot move %s to %s."
                        % (emp.get("status"), new_status))
    now = utcnow()
    approved_at = emp.get("approved_at") or ""
    approved_by = emp.get("approved_by") or ""
    if action == "EMPLOYEE_APPROVED":
        approved_at, approved_by = now, admin_id
    conn.execute("UPDATE employees SET status=?, approved_at=?,"
                 " approved_by=?, updated_at=? WHERE id=?",
                 (new_status, approved_at, approved_by, now, employee_id))
    audit(conn, employee_id, admin_id, action,
          "%s" % emp.get("status"), "%s" % new_status)
    if new_status in ("suspended", "revoked"):
        destroy_employee_sessions(conn, employee_id)
    else:
        conn.commit()
    return get_employee(conn, employee_id)


def admin_set_role(conn, admin_id, employee_id, role):
    if role not in ROLES:
        raise AuthError("Role must be admin or employee.")
    emp = get_employee(conn, employee_id)
    if emp is None:
        raise AuthError("Employee not found.")
    if emp.get("role") == role:
        return emp
    conn.execute("UPDATE employees SET role=?, updated_at=? WHERE id=?",
                 (role, utcnow(), employee_id))
    audit(conn, employee_id, admin_id, "ROLE_CHANGED",
          "%s" % emp.get("role"), "%s" % role)
    conn.commit()
    return get_employee(conn, employee_id)


def admin_audit_list(conn, limit=100):
    try:
        limit = max(1, min(500, int(limit)))
    except (TypeError, ValueError):
        limit = 100
    return [{"id": r[0], "target_id": r[1], "admin_id": r[2],
             "action": r[3], "prev_value": r[4], "new_value": r[5],
             "created_at": r[6]}
            for r in conn.execute(
                "SELECT id, target_id, admin_id, action, prev_value,"
                " new_value, created_at FROM employee_audit"
                " ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,)).fetchall()]


# ---------------------------------------------------------------------------
# Cookies (HttpOnly session bearer; media tags ride cookies, not headers)
# ---------------------------------------------------------------------------

def session_cookie(token, max_age=SESSION_TTL_S):
    return ("%s=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Lax"
            % (COOKIE_NAME, token, max_age))


def clear_cookie():
    return ("%s=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax" % COOKIE_NAME)


def token_from_headers(headers):
    """Extract the session token from a Cookie header (never logs it)."""
    try:
        raw = headers.get("Cookie") or headers.get("cookie") or ""
    except AttributeError:
        return ""
    for part in raw.split(";"):
        name, _, value = part.partition("=")
        if name.strip() == COOKIE_NAME:
            return value.strip()
    return ""
