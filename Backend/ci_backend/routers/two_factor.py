"""Authenticator-app two-factor routes.

Setup and disable need a live session. The sign-in verify route uses
the short-lived challenge cookie instead, and only then issues a
session.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ci_backend import employees as emp
from ci_backend import security_log
from ci_backend import totp as totp_mod
from ci_backend import workos as workos_mod
from ci_backend.config import Settings
from ci_backend.deps import auth_rate_limit, bearer_token, get_db, get_settings
from ci_backend.routers.auth import _issue

router = APIRouter(prefix="/api/auth/2fa", tags=["two-factor"])


class CodeBody(BaseModel):
    code: str = Field(default="", max_length=64)
    container_id: str = Field(default="", max_length=64)


def _actor(request: Request, db):
    try:
        employee, _gate = emp.authorize(db, bearer_token(request))
    except emp.Denied as exc:
        raise HTTPException(
            status_code=401 if exc.gate == "login" else 403,
            detail={"error": str(exc), "gate": exc.gate})
    return employee


def _reject(exc: emp.StoreError) -> HTTPException:
    return HTTPException(status_code=409, detail={"error": str(exc)})


@router.get("/status")
def two_factor_status(request: Request, db=Depends(get_db)):
    employee = _actor(request, db)
    return totp_mod.status(db, employee.id)


@router.post("/setup", dependencies=[Depends(auth_rate_limit)])
def two_factor_setup(request: Request, db=Depends(get_db),
                     settings: Settings = Depends(get_settings)):
    employee = _actor(request, db)
    try:
        out = totp_mod.begin_setup(db, employee, settings)
    except emp.StoreError as exc:
        raise _reject(exc)
    security_log.event("two_factor_setup", actor=employee.id)
    return out


@router.post("/confirm", dependencies=[Depends(auth_rate_limit)])
def two_factor_confirm(body: CodeBody, request: Request, db=Depends(get_db),
                       settings: Settings = Depends(get_settings)):
    employee = _actor(request, db)
    try:
        out = totp_mod.confirm_setup(db, employee, body.code, settings)
    except emp.StoreError as exc:
        raise _reject(exc)
    security_log.event("two_factor_enabled", actor=employee.id)
    return out


@router.post("/cancel")
def two_factor_cancel(request: Request, db=Depends(get_db)):
    employee = _actor(request, db)
    return totp_mod.cancel_setup(db, employee.id)


@router.post("/disable", dependencies=[Depends(auth_rate_limit)])
def two_factor_disable(body: CodeBody, request: Request, db=Depends(get_db),
                       settings: Settings = Depends(get_settings)):
    employee = _actor(request, db)
    try:
        out = totp_mod.disable(db, employee, body.code, settings)
    except emp.StoreError as exc:
        raise _reject(exc)
    security_log.event("two_factor_disabled", actor=employee.id)
    return out


@router.post("/verify", dependencies=[Depends(auth_rate_limit)])
def two_factor_verify(body: CodeBody, request: Request, db=Depends(get_db),
                      settings: Settings = Depends(get_settings)):
    """Turn a challenge cookie plus a valid code into a session."""
    try:
        employee = totp_mod.take_challenge(
            db, request.cookies.get(totp_mod.CHALLENGE_COOKIE, ""), body.code,
        settings)
        container = emp.valid_container_id(body.container_id)
        token = emp.create_session(
            db, employee.id, employee.workos_user_id or "", container)
        employee.last_login_at = emp.utcnow()
        db.commit()
    except emp.StoreError as exc:
        security_log.event("login_failure", detail="two-factor")
        raise _reject(exc)
    security_log.event("login_success", target=employee.id,
                       detail="two-factor")
    gate = "app" if employee.status == "active" else employee.status
    response = _issue({
        "ok": True,
        "authenticated": True,
        "gate": gate,
        "employee": emp.public_employee(employee).model_dump(),
        "is_admin": employee.role == "admin",
        "message": "",
        "workos_configured": workos_mod.workos_configured(settings),
    }, token, secure=settings.cookie_secure)
    response.delete_cookie(totp_mod.CHALLENGE_COOKIE, path="/")
    return response
