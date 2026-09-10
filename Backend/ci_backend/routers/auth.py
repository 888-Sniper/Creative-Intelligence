"""Authentication routes (FastAPI port of the legacy /api/auth/* surface).

Response shapes are unchanged so the existing UI keeps working:
login always answers 200 with a gate envelope; OAuth failures on the
finish/callback path answer 409 (retryable) and never leak secrets.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile

from ci_backend import employees as emp
from ci_backend import oauth as oauth_mod
from ci_backend import security_log
from ci_backend import workos as workos_mod
from ci_backend.actions import _media_dir
from ci_backend.config import Settings
from ci_backend.deps import (
    auth_rate_limit,
    bearer_token,
    get_db,
    get_settings,
    json_payload,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue(body: dict, token: str = "", clear: bool = False,
           secure: bool = False) -> JSONResponse:
    response = JSONResponse(body)
    if clear:
        response.set_cookie(emp.COOKIE_NAME, "", max_age=0,
                            path="/", httponly=True, samesite="lax",
                            secure=secure)
    elif token:
        response.set_cookie(emp.COOKIE_NAME, token,
                            max_age=emp.SESSION_TTL_S,
                            path="/", httponly=True, samesite="lax",
                            secure=secure)
    return response


def _apply_cookie(response, header: str, secure: bool = False) -> None:
    value = header.split(";", 1)[0]
    name, _, val = value.partition("=")
    response.set_cookie(name.strip(), val.strip(),
                        max_age=emp.SESSION_TTL_S,
                        path="/", httponly=True, samesite="lax",
                        secure=secure)


@router.get("/me")
def me(request: Request, db=Depends(get_db),
       settings: Settings = Depends(get_settings)):
    envelope = emp.me(db, bearer_token(request), settings)
    return envelope.model_dump(exclude_none=False)


@router.patch("/me")
async def update_me(request: Request, db=Depends(get_db)):
    try:
        employee, _gate = emp.authorize(db, bearer_token(request))
    except emp.Denied as exc:
        raise HTTPException(
            status_code=401 if exc.gate == "login" else 403,
            detail={"error": str(exc), "gate": exc.gate})
    raw = await json_payload(request)
    try:
        body = emp.ProfileUpdate.model_validate(raw or {})
    except Exception as exc:
        raise HTTPException(status_code=409,
                            detail={"error": "Invalid profile: %s" % exc})
    try:
        updated = emp.update_profile(
            db, employee.id, first_name=body.first_name,
            last_name=body.last_name, avatar_url=body.avatar_url)
    except emp.StoreError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return {"ok": True,
            "employee": emp.public_employee(updated).model_dump()}


@router.post("/me/avatar")
async def upload_avatar(request: Request, db=Depends(get_db)):
    try:
        employee, _gate = emp.authorize(db, bearer_token(request))
    except emp.Denied as exc:
        raise HTTPException(
            status_code=401 if exc.gate == "login" else 403,
            detail={"error": str(exc), "gate": exc.gate})
    form = await request.form()
    upload = form.get("avatar")
    if not isinstance(upload, UploadFile):
        raise HTTPException(status_code=409,
                            detail={"error": "Attach an avatar file."})
    try:
        content = await upload.read(emp.MAX_AVATAR_BYTES + 1)
        try:
            updated = emp.save_avatar(db, employee.id,
                                      upload.filename or "avatar",
                                      content, _media_dir())
        except emp.StoreError as exc:
            raise HTTPException(status_code=409, detail={"error": str(exc)})
    finally:
        # Starlette parks the part in a SpooledTemporaryFile that
        # nothing else closes.
        try:
            await upload.close()
        except Exception:
            pass
    return {"ok": True,
            "employee": emp.public_employee(updated).model_dump()}


@router.get("/avatar/{employee_id}")
def serve_avatar(employee_id: str, request: Request, db=Depends(get_db)):
    from urllib.parse import unquote
    if emp.valid_session(db, bearer_token(request)) is None:
        raise HTTPException(status_code=401, detail={
            "error": "Sign in to continue.", "gate": "login"})
    target = unquote(employee_id)
    found = emp.load_avatar(target, _media_dir())
    if found is None:
        raise HTTPException(status_code=404,
                            detail={"error": "No avatar."})
    path, mime = found
    return FileResponse(path, media_type=mime,
                        headers={"Cache-Control": "private, max-age=3600"})


@router.get("/accounts")
def accounts(request: Request, db=Depends(get_db)):
    token = bearer_token(request)
    if emp.valid_session(db, token) is None:
        raise HTTPException(status_code=401, detail={
            "error": "Sign in to continue.", "gate": "login"})
    # Item 18: the switcher only sees the caller's own container.
    container = emp.session_container(db, token) or ""
    return {"accounts": emp.list_accounts(db, container)}


class ContainerBind(BaseModel):
    container_id: str = Field(default="", max_length=64)


@router.post("/container")
def bind_container(body: ContainerBind, request: Request,
                   db=Depends(get_db)):
    """Adopt the caller's session into its installation container.

    First write wins; a session already bound elsewhere is refused.
    Container-aware clients call this on boot after OAuth logins, whose
    server-side redirect cannot carry the container id.
    """
    token = bearer_token(request)
    if emp.valid_session(db, token) is None:
        raise HTTPException(status_code=401, detail={
            "error": "Sign in to continue.", "gate": "login"})
    try:
        container = emp.bind_session_container(
            db, token, body.container_id)
    except emp.Denied as exc:
        raise HTTPException(status_code=401, detail={
            "error": str(exc), "gate": exc.gate})
    except emp.StoreError as exc:
        raise HTTPException(status_code=409,
                            detail={"error": str(exc)})
    return {"ok": True, "container_id": container}


# CSRF threat model (documented, not assumed away).
#
# The UI is same-origin and the session cookie is SameSite=Lax, so a
# foreign site cannot drive authenticated cross-site POST/PATCH/DELETE
# requests: the browser simply withholds the cookie on cross-site
# POSTs. Two endpoints deliberately accept cross-site top-level
# navigation and need their own protection:
#
# * GET /api/auth/callback is reached from WorkOS (cross-site). It
#   consumes a single-use server-side OAuth state AND requires the
#   browser to present the matching state cookie set by
#   POST /api/auth/oauth/start. Without that binding, an attacker
#   could complete their own provider flow and trick a victim's
#   browser into finishing it (login CSRF).
# * POST /api/auth/oauth/finish is same-origin fetch, but enforces
#   the same binding for defence in depth.
OAUTH_STATE_COOKIE = "ci_oauth_state"


def _check_state_binding(request: Request, state: str) -> None:
    if not state or request.cookies.get(OAUTH_STATE_COOKIE) != state:
        raise HTTPException(status_code=409, detail={
            "error": "OAuth session mismatch. Restart sign-in."})


def _bind_state_cookie(response, state: str, secure: bool) -> None:
    response.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600,
                        path="/", httponly=True, samesite="lax",
                        secure=secure)


def _clear_state_cookie(response) -> None:
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/")


@router.get("/callback")
def callback(request: Request, db=Depends(get_db),
             settings: Settings = Depends(get_settings)):
    code = request.query_params.get("code", "")
    state = request.query_params.get("state", "")
    try:
        _check_state_binding(request, state)
        identity = oauth_mod.finish_oauth(db, code, state, settings)
        token, _employee, _created = emp.login_identity(
            db, identity, settings)
        security_log.event("login_success", target=_employee.id,
                           detail="oauth callback gate=%s" % (
                               "app" if _employee.status == "active"
                               else _employee.status))
    except (emp.StoreError, emp.Denied, HTTPException) as exc:
        from urllib.parse import quote
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        if isinstance(detail, dict):
            detail = detail.get("error", "Sign-in failed.")
        return RedirectResponse("/?auth_error=" + quote(str(detail)[:200]),
                                status_code=302)
    response = RedirectResponse("/", status_code=302)
    _apply_cookie(response, emp.session_cookie(token),
                  settings.cookie_secure)
    _clear_state_cookie(response)
    return response


@router.post("/oauth/start")
async def oauth_start(request: Request, db=Depends(get_db),
                      settings: Settings = Depends(get_settings),
                     _rl=Depends(auth_rate_limit)):
    body = await json_payload(request)
    try:
        out = oauth_mod.start_oauth(
            db, body.get("provider", ""),
            body.get("redirect_uri", ""), settings)
    except (emp.StoreError, workos_mod.WorkOSError) as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    response = JSONResponse(out)
    _bind_state_cookie(response, out["state"], settings.cookie_secure)
    return response


@router.post("/oauth/finish")
async def oauth_finish(request: Request, db=Depends(get_db),
                       settings: Settings = Depends(get_settings),
                     _rl=Depends(auth_rate_limit)):
    body = await json_payload(request)
    _check_state_binding(request, body.get("state", ""))
    try:
        identity = oauth_mod.finish_oauth(
            db, body.get("code", ""), body.get("state", ""), settings)
        token, employee, _created = emp.login_identity(
            db, identity, settings,
            emp.valid_container_id(body.get("container_id", "")))
        security_log.event("login_success", target=employee.id,
                           detail="oauth finish")
    except (emp.StoreError, emp.Denied,
            workos_mod.WorkOSError) as exc:
        security_log.event("login_failure", detail="oauth finish")
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    gate = "app" if employee.status == "active" else employee.status
    response = _issue({"ok": True, "gate": gate,
                       "employee": emp.public_employee(employee).model_dump()},
                      token, secure=settings.cookie_secure)
    _clear_state_cookie(response)
    return response


@router.post("/email/signin")
async def email_signin(request: Request, db=Depends(get_db),
                       settings: Settings = Depends(get_settings),
                     _rl=Depends(auth_rate_limit)):
    body = await json_payload(request)
    try:
        raw = workos_mod.authenticate_password(
            body.get("email", ""), body.get("password", ""),
            settings=settings)
        identity = workos_mod.public_identity(raw, provider="email")
        token, employee, gate = oauth_mod.login_verified(
            db, identity, settings,
            emp.valid_container_id(body.get("container_id", "")))
    except (emp.StoreError, workos_mod.WorkOSError) as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return _issue({"ok": True, "gate": gate,
                   "employee": emp.public_employee(employee).model_dump()},
                  token, secure=settings.cookie_secure)


@router.post("/email/code")
async def email_code(request: Request, settings: Settings = Depends(get_settings),
                     _rl=Depends(auth_rate_limit)):
    body = await json_payload(request)
    try:
        workos_mod.send_magic_code(body.get("email", ""), settings=settings)
    except workos_mod.WorkOSError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return {"ok": True}


@router.post("/email/code/signin")
async def email_code_signin(request: Request, db=Depends(get_db),
                            settings: Settings = Depends(get_settings),
                     _rl=Depends(auth_rate_limit)):
    body = await json_payload(request)
    try:
        raw = workos_mod.authenticate_magic_code(
            body.get("email", ""), body.get("code", ""), settings=settings)
        identity = workos_mod.public_identity(raw, provider="email")
        token, employee, gate = oauth_mod.login_verified(
            db, identity, settings,
            emp.valid_container_id(body.get("container_id", "")))
    except (emp.StoreError, workos_mod.WorkOSError) as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return _issue({"ok": True, "gate": gate,
                   "employee": emp.public_employee(employee).model_dump()},
                  token, secure=settings.cookie_secure)


@router.post("/email/reset")
async def email_reset(request: Request, settings: Settings = Depends(get_settings),
                     _rl=Depends(auth_rate_limit)):
    body = await json_payload(request)
    try:
        workos_mod.send_password_reset(body.get("email", ""),
                                       settings=settings)
    except workos_mod.WorkOSError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return {"ok": True}


@router.post("/password/reset")
async def password_reset(request: Request, settings: Settings = Depends(get_settings),
                     _rl=Depends(auth_rate_limit)):
    body = await json_payload(request)
    try:
        workos_mod.reset_password(body.get("token", ""),
                                  body.get("password", ""),
                                  settings=settings)
    except workos_mod.WorkOSError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, db=Depends(get_db),
           settings: Settings = Depends(get_settings)):
    token = bearer_token(request)
    known = emp.valid_session(db, token) is not None
    emp.destroy_session(db, token)
    if known:
        security_log.event("logout")
    return _issue({"ok": True}, clear=True,
                  secure=settings.cookie_secure)


@router.post("/sessions/revoke-all")
def revoke_own_sessions(request: Request, db=Depends(get_db),
                        settings: Settings = Depends(get_settings)):
    """Log out everywhere: destroy all of the caller's sessions."""
    caller = emp.valid_session(db, bearer_token(request))
    if caller is None:
        raise HTTPException(status_code=401, detail={
            "error": "Sign in to continue.", "gate": "login"})
    count = emp.revoke_all_sessions(db, caller.id, caller.id)
    security_log.event("session_revocation", actor=caller.id,
                       target=caller.id,
                       detail="%d session(s) self-revoked" % count)
    return _issue({"ok": True, "revoked": count}, clear=True,
                  secure=settings.cookie_secure)


@router.post("/switch")
async def switch(request: Request, db=Depends(get_db),
                 settings: Settings = Depends(get_settings)):
    body = await json_payload(request)
    token = bearer_token(request)
    if emp.valid_session(db, token) is None:
        raise HTTPException(status_code=401, detail={
            "error": "Sign in to continue.", "gate": "login"})
    # Item 18: the target needs a live session in the CALLER's container.
    # A live session anywhere else no longer authorizes the switch, and
    # the fresh session inherits the caller's container.
    container = emp.session_container(db, token) or ""
    target = emp.get_employee(db, body.get("employee_id", ""))
    if target is None or not emp.has_live_session_in(
            db, target.id, container):
        raise HTTPException(status_code=404, detail={
            "error": "Sign in with that account first."})
    fresh = emp.create_session(db, target.id, target.workos_user_id or "",
                               container)
    return _issue({"ok": True,
                   "employee": emp.public_employee(target).model_dump()},
                  fresh, secure=settings.cookie_secure)
