"""Google OAuth routes for private Drive/Sheets (item 31).

Secrets and tokens never reach the browser: the client only ever sees
{url}/{state} to navigate to, and safe status fields back.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ci_backend import employees as emp
from ci_backend import google_oauth as goog
from ci_backend import product_audit as paudit
from ci_backend import security_log
from ci_backend.config import Settings
from ci_backend.deps import get_db, get_settings
from ci_backend.routers.auth import bearer_token

router = APIRouter(prefix="/api/auth/google", tags=["google"])

GOOGLE_STATE_COOKIE = "ci_google_state"


def _actor(request: Request, db: Session) -> emp.Employee:
    """Active-employee gate: suspended/revoked staff cannot operate
    Google integrations even with a live session token."""
    try:
        employee, _gate = emp.authorize(db, bearer_token(request))
    except emp.Denied as exc:
        raise HTTPException(
            status_code=401 if exc.gate == "login" else 403,
            detail={"error": str(exc), "gate": exc.gate})
    return employee


@router.post("/start")
def google_start(request: Request, db: Session = Depends(get_db),
                 settings: Settings = Depends(get_settings)):
    employee = _actor(request, db)
    try:
        flow = goog.start_google(db, settings)
    except emp.StoreError as exc:
        raise HTTPException(status_code=409,
                            detail={"error": str(exc)})
    response = JSONResponse({"url": flow["url"]})
    response.set_cookie(GOOGLE_STATE_COOKIE, flow["state"], max_age=600,
                        path="/", httponly=True, samesite="lax",
                        secure=settings.cookie_secure)
    security_log.event("google_oauth_start", actor=employee.id)
    return response


@router.get("/callback")
def google_callback(request: Request, db: Session = Depends(get_db),
                    settings: Settings = Depends(get_settings)):
    # Top-level navigation from Google sends the session cookie
    # (SameSite=Lax), identifying the employee who started the flow.
    # The pending state row + state cookie still bind and expire it.
    # Status is rechecked: staff suspended mid-flow land on expired.
    try:
        employee, _gate = emp.authorize(db, bearer_token(request))
    except emp.Denied:
        employee = None
    state = request.query_params.get("state", "")
    if employee is None or not state \
            or request.cookies.get(GOOGLE_STATE_COOKIE) != state:
        return RedirectResponse("/settings?google=expired", status_code=302)
    try:
        goog.finish_google(db, request.query_params.get("code", ""),
                           state, employee.id, settings)
    except (emp.StoreError, goog.GoogleError):
        return RedirectResponse("/settings?google=failed", status_code=302)
    security_log.event("google_connected", actor=employee.id)
    paudit.audit_request(request, employee_id=employee.id,
                         action="connector_changed", target="connect-google")
    response = RedirectResponse("/settings?google=connected", status_code=302)
    response.delete_cookie(GOOGLE_STATE_COOKIE, path="/")
    return response


@router.get("/status")
def google_status(request: Request, db: Session = Depends(get_db)):
    employee = _actor(request, db)
    return goog.status(db, employee.id)


@router.post("/disconnect")
def google_disconnect(request: Request, db: Session = Depends(get_db),
                      settings: Settings = Depends(get_settings)):
    employee = _actor(request, db)
    goog.forget(db, employee.id, settings)
    security_log.event("google_disconnected", actor=employee.id)
    paudit.audit_request(request, employee_id=employee.id,
                         action="connector_changed",
                         target="disconnect-google")
    return {"ok": True}
