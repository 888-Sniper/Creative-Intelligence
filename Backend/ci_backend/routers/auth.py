"""Authentication routes (FastAPI port of the legacy /api/auth/* surface).

Response shapes are unchanged so the existing UI keeps working:
login always answers 200 with a gate envelope; OAuth failures on the
finish/callback path answer 409 (retryable) and never leak secrets.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.datastructures import UploadFile

from ci_backend import employees as emp
from ci_backend.actions import _media_dir
from ci_backend import oauth as oauth_mod
from ci_backend import workos as workos_mod
from ci_backend.config import Settings
from ci_backend.deps import (
    bearer_token,
    get_db,
    get_settings,
    json_payload,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue(body: dict, token: str = "", clear: bool = False) -> JSONResponse:
    response = JSONResponse(body)
    if clear:
        response.set_cookie(emp.COOKIE_NAME, "", max_age=0,
                            path="/", httponly=True, samesite="lax")
    elif token:
        response.set_cookie(emp.COOKIE_NAME, token,
                            max_age=emp.SESSION_TTL_S,
                            path="/", httponly=True, samesite="lax")
    return response


def _apply_cookie(response, header: str) -> None:
    value = header.split(";", 1)[0]
    name, _, val = value.partition("=")
    response.set_cookie(name.strip(), val.strip(),
                        max_age=emp.SESSION_TTL_S,
                        path="/", httponly=True, samesite="lax")


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
    body = await json_payload(request)
    try:
        updated = emp.update_profile(
            db, employee.id, first_name=body.get("first_name"),
            last_name=body.get("last_name"),
            avatar_url=body.get("avatar_url"))
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
    content = await upload.read(emp.MAX_AVATAR_BYTES + 1)
    try:
        updated = emp.save_avatar(db, employee.id,
                                  upload.filename or "avatar",
                                  content, _media_dir())
    except emp.StoreError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
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
    if emp.valid_session(db, bearer_token(request)) is None:
        raise HTTPException(status_code=401, detail={
            "error": "Sign in to continue.", "gate": "login"})
    return {"accounts": emp.list_accounts(db)}


@router.get("/callback")
def callback(request: Request, db=Depends(get_db),
             settings: Settings = Depends(get_settings)):
    code = request.query_params.get("code", "")
    state = request.query_params.get("state", "")
    try:
        identity = oauth_mod.finish_oauth(db, code, state, settings)
        token, _employee, _created = emp.login_identity(
            db, identity, settings)
    except (emp.StoreError, emp.Denied) as exc:
        from urllib.parse import quote
        return RedirectResponse("/?auth_error=" + quote(str(exc)[:200]),
                                status_code=302)
    response = RedirectResponse("/", status_code=302)
    _apply_cookie(response, emp.session_cookie(token))
    return response


@router.post("/oauth/start")
async def oauth_start(request: Request, db=Depends(get_db),
                      settings: Settings = Depends(get_settings)):
    body = await json_payload(request)
    try:
        out = oauth_mod.start_oauth(
            db, body.get("provider", ""),
            body.get("redirect_uri", ""), settings)
        return out
    except (emp.StoreError, workos_mod.WorkOSError) as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})


@router.post("/oauth/finish")
async def oauth_finish(request: Request, db=Depends(get_db),
                       settings: Settings = Depends(get_settings)):
    body = await json_payload(request)
    try:
        identity = oauth_mod.finish_oauth(
            db, body.get("code", ""), body.get("state", ""), settings)
        token, employee, _created = emp.login_identity(
            db, identity, settings)
    except (emp.StoreError, emp.Denied,
            workos_mod.WorkOSError) as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    gate = "app" if employee.status == "active" else employee.status
    return _issue({"ok": True, "gate": gate,
                   "employee": emp.public_employee(employee).model_dump()},
                  token)


@router.post("/email/signin")
async def email_signin(request: Request, db=Depends(get_db),
                       settings: Settings = Depends(get_settings)):
    body = await json_payload(request)
    try:
        raw = workos_mod.authenticate_password(
            body.get("email", ""), body.get("password", ""),
            settings=settings)
        identity = workos_mod.public_identity(raw, provider="email")
        token, employee, gate = oauth_mod.login_verified(
            db, identity, settings)
    except (emp.StoreError, workos_mod.WorkOSError) as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return _issue({"ok": True, "gate": gate,
                   "employee": emp.public_employee(employee).model_dump()},
                  token)


@router.post("/email/code")
async def email_code(request: Request, settings: Settings = Depends(get_settings)):
    body = await json_payload(request)
    try:
        workos_mod.send_magic_code(body.get("email", ""), settings=settings)
    except workos_mod.WorkOSError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return {"ok": True}


@router.post("/email/code/signin")
async def email_code_signin(request: Request, db=Depends(get_db),
                            settings: Settings = Depends(get_settings)):
    body = await json_payload(request)
    try:
        raw = workos_mod.authenticate_magic_code(
            body.get("email", ""), body.get("code", ""), settings=settings)
        identity = workos_mod.public_identity(raw, provider="email")
        token, employee, gate = oauth_mod.login_verified(
            db, identity, settings)
    except (emp.StoreError, workos_mod.WorkOSError) as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return _issue({"ok": True, "gate": gate,
                   "employee": emp.public_employee(employee).model_dump()},
                  token)


@router.post("/email/reset")
async def email_reset(request: Request, settings: Settings = Depends(get_settings)):
    body = await json_payload(request)
    try:
        workos_mod.send_password_reset(body.get("email", ""),
                                       settings=settings)
    except workos_mod.WorkOSError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return {"ok": True}


@router.post("/password/reset")
async def password_reset(request: Request, settings: Settings = Depends(get_settings)):
    body = await json_payload(request)
    try:
        workos_mod.reset_password(body.get("token", ""),
                                  body.get("password", ""),
                                  settings=settings)
    except workos_mod.WorkOSError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, db=Depends(get_db)):
    emp.destroy_session(db, bearer_token(request))
    return _issue({"ok": True}, clear=True)


@router.post("/switch")
async def switch(request: Request, db=Depends(get_db)):
    body = await json_payload(request)
    if emp.valid_session(db, bearer_token(request)) is None:
        raise HTTPException(status_code=401, detail={
            "error": "Sign in to continue.", "gate": "login"})
    target = emp.get_employee(db, body.get("employee_id", ""))
    if target is None or not emp.has_live_session(db, target.id):
        raise HTTPException(status_code=404, detail={
            "error": "Sign in with that account first."})
    fresh = emp.create_session(db, target.id, target.workos_user_id or "")
    return _issue({"ok": True,
                   "employee": emp.public_employee(target).model_dump()},
                  fresh)
