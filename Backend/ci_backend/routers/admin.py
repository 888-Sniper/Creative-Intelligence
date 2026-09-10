"""Admin routes (FastAPI port of the legacy /api/admin/* surface)."""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ci_backend import employees as emp
from ci_backend.deps import (
    admin_rate_limit,
    get_current_admin,
    get_db,
    json_payload,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

_MOVES = {
    "approve": ("active", "EMPLOYEE_APPROVED"),
    "suspend": ("suspended", "EMPLOYEE_SUSPENDED"),
    "reactivate": ("active", "EMPLOYEE_REACTIVATED"),
    "revoke": ("revoked", "EMPLOYEE_REVOKED"),
}


def _employee_payload(employee) -> dict:
    return {"employee": emp.public_employee(employee).model_dump()}


class EmployeeCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    first_name: str = Field(default="", max_length=120)
    last_name: str = Field(default="", max_length=120)
    role: str = Field(default="employee", pattern="^(admin|employee)$")


class RoleChange(BaseModel):
    role: str = Field(pattern="^(admin|employee)$")


class EmployeeSearch(BaseModel):
    search: str = Field(default="", max_length=120)
    filter: str = Field(
        default="", pattern="^(|all|pending|active|suspended|revoked"
        "|admin|employee)$")


def _validated(model, body: dict):
    try:
        return model.model_validate(body or {})
    except Exception as exc:
        raise HTTPException(status_code=409,
                            detail={"error": "Invalid request: %s" % exc})


@router.get("/employees")
def list_employees(request: Request, db=Depends(get_db),
                   admin=Depends(get_current_admin)):
    params = _validated(EmployeeSearch, {
        "search": request.query_params.get("search", ""),
        "filter": request.query_params.get("filter", "")})
    return {"employees": [e.model_dump() for e in
                          emp.admin_list(db, params.search, params.filter)]}


@router.post("/employees")
async def create_employee(request: Request, db=Depends(get_db),
                          admin=Depends(get_current_admin),
                          _rl=Depends(admin_rate_limit)):
    body = _validated(EmployeeCreate, await json_payload(request))
    try:
        employee = emp.admin_create(
            db, admin.id, body.email,
            body.first_name, body.last_name, body.role)
    except emp.StoreError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return _employee_payload(employee)


@router.post("/employees/{employee_id}/sessions/revoke")
def revoke_employee_sessions(employee_id: str, request: Request,
                             db=Depends(get_db),
                             admin=Depends(get_current_admin),
                             _rl=Depends(admin_rate_limit)):
    """Admin: invalidate every session of one employee (audited)."""
    try:
        count = emp.revoke_all_sessions(db, admin.id, unquote(employee_id))
    except emp.StoreError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    return {"ok": True, "revoked": count}


@router.get("/audit")
def audit(request: Request, db=Depends(get_db),
          admin=Depends(get_current_admin)):
    return {"events": [e.model_dump() for e in emp.admin_audit_list(
        db, request.query_params.get("limit", "100"))]}


@router.get("/employees/{employee_id}")
def get_employee(employee_id: str, db=Depends(get_db),
                 admin=Depends(get_current_admin)):
    employee = emp.get_employee(db, unquote(employee_id))
    if employee is None:
        raise HTTPException(status_code=404,
                            detail={"error": "Employee not found."})
    return _employee_payload(employee)


@router.post("/employees/{employee_id}/{verb}")
async def employee_action(employee_id: str, verb: str, request: Request,
                          db=Depends(get_db),
                          admin=Depends(get_current_admin),
                          _rl=Depends(admin_rate_limit)):
    raw = await json_payload(request)
    target = unquote(employee_id)
    try:
        if verb in _MOVES:
            status, action = _MOVES[verb]
            employee = emp.admin_set_status(
                db, admin.id, target, status, action)
        elif verb == "role":
            body = _validated(RoleChange, raw)
            employee = emp.admin_set_role(
                db, admin.id, target, body.role)
        else:
            raise HTTPException(status_code=404,
                                detail={"error": "not found"})
    except emp.StoreError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return _employee_payload(employee)
