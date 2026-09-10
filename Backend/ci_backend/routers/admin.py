"""Admin routes (FastAPI port of the legacy /api/admin/* surface)."""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request

from ci_backend import employees as emp
from ci_backend.deps import get_current_admin, get_db, json_payload

router = APIRouter(prefix="/api/admin", tags=["admin"])

_MOVES = {
    "approve": ("active", "EMPLOYEE_APPROVED"),
    "suspend": ("suspended", "EMPLOYEE_SUSPENDED"),
    "reactivate": ("active", "EMPLOYEE_REACTIVATED"),
    "revoke": ("revoked", "EMPLOYEE_REVOKED"),
}


def _employee_payload(employee) -> dict:
    return {"employee": emp.public_employee(employee).model_dump()}


@router.get("/employees")
def list_employees(request: Request, db=Depends(get_db),
                   admin=Depends(get_current_admin)):
    search = request.query_params.get("search", "")
    filt = request.query_params.get("filter", "")
    return {"employees": [e.model_dump() for e in
                          emp.admin_list(db, search, filt)]}


@router.post("/employees")
async def create_employee(request: Request, db=Depends(get_db),
                          admin=Depends(get_current_admin)):
    body = await json_payload(request)
    try:
        employee = emp.admin_create(
            db, admin.id, body.get("email", ""),
            body.get("first_name", ""), body.get("last_name", ""),
            body.get("role", "employee"))
    except emp.StoreError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return _employee_payload(employee)


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
                          admin=Depends(get_current_admin)):
    body = await json_payload(request)
    target = unquote(employee_id)
    try:
        if verb in _MOVES:
            status, action = _MOVES[verb]
            employee = emp.admin_set_status(
                db, admin.id, target, status, action)
        elif verb == "role":
            employee = emp.admin_set_role(
                db, admin.id, target, body.get("role", ""))
        else:
            raise HTTPException(status_code=404,
                                detail={"error": "not found"})
    except emp.StoreError as exc:
        raise HTTPException(status_code=409, detail={"error": str(exc)})
    return _employee_payload(employee)
