"""Settings connections for Meta Ads, TikTok Ads, and GA4.

The client only receives an authorize URL and a safe status. Tokens
never leave the server.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ci_backend import employees as emp
from ci_backend import integrations_oauth as integ
from ci_backend import product_audit as paudit
from ci_backend import security_log
from ci_backend.config import Settings
from ci_backend.deps import bearer_token, get_db, get_settings

router = APIRouter(prefix="/api/auth/integrations", tags=["integrations"])

STATE_COOKIE = "ci_integration_state"


def _actor(request: Request, db):
    try:
        employee, _gate = emp.authorize(db, bearer_token(request))
    except emp.Denied as exc:
        raise HTTPException(
            status_code=401 if exc.gate == "login" else 403,
            detail={"error": str(exc), "gate": exc.gate})
    return employee


def _known(provider: str) -> str:
    if provider not in integ.PROVIDERS:
        raise HTTPException(status_code=404,
                            detail={"error": "Unknown integration."})
    return provider


@router.post("/{provider}/start")
def integration_start(provider: str, request: Request, db=Depends(get_db),
                      settings: Settings = Depends(get_settings)):
    provider = _known(provider)
    employee = _actor(request, db)
    try:
        flow = integ.start(db, provider, settings, employee.id)
    except emp.StoreError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    response = JSONResponse({"url": flow["url"]})
    response.set_cookie(STATE_COOKIE, flow["state"], max_age=600,
                        path="/", httponly=True, samesite="lax",
                        secure=settings.cookie_secure)
    security_log.event("integration_oauth_start", actor=employee.id,
                       detail=provider)
    return response


@router.get("/{provider}/callback")
def integration_callback(provider: str, request: Request, db=Depends(get_db),
                         settings: Settings = Depends(get_settings)):
    provider = provider if provider in integ.PROVIDERS else ""
    try:
        employee, _gate = emp.authorize(db, bearer_token(request))
    except emp.Denied:
        employee = None
    state = request.query_params.get("state", "")
    code = request.query_params.get("code", "") \
        or request.query_params.get("auth_code", "")
    if not provider or employee is None or not state \
            or request.cookies.get(STATE_COOKIE) != state:
        target = "/settings?integration=%s&result=expired" % (
            provider or "unknown")
        return RedirectResponse(target, status_code=302)
    try:
        integ.finish(db, provider, code, state, employee.id, settings)
    except (emp.StoreError, integ.IntegrationError):
        response = RedirectResponse(
            "/settings?integration=%s&result=failed" % provider,
            status_code=302)
        response.delete_cookie(STATE_COOKIE, path="/")
        return response
    security_log.event("integration_connected", actor=employee.id,
                       detail=provider)
    paudit.audit_request(request, employee_id=employee.id,
                         action="connector_changed",
                         target="connect-%s" % provider)
    response = RedirectResponse(
        "/settings?integration=%s&result=connected" % provider,
        status_code=302)
    response.delete_cookie(STATE_COOKIE, path="/")
    return response


@router.get("/{provider}/status")
def integration_status(provider: str, request: Request, db=Depends(get_db)):
    provider = _known(provider)
    employee = _actor(request, db)
    return integ.status(db, provider, employee.id)


@router.post("/{provider}/disconnect")
def integration_disconnect(provider: str, request: Request, db=Depends(get_db),
                           settings: Settings = Depends(get_settings)):
    provider = _known(provider)
    employee = _actor(request, db)
    integ.forget(db, provider, employee.id, settings)
    security_log.event("integration_disconnected", actor=employee.id,
                       detail=provider)
    paudit.audit_request(request, employee_id=employee.id,
                         action="connector_changed",
                         target="disconnect-%s" % provider)
    return {"ok": True}
