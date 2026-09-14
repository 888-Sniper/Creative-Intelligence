"""Readable employee numbers (EMP-001…).

Databases created before this change gain ``emp_no`` (default '')
via this migration; fresh databases get it from the static DDL.
Existing rows are backfilled deterministically by (created_at, id)
before the UNIQUE index is created, so relationships are preserved
and numbering is stable. New employees are numbered at creation
time by the server (never from a live count). Old code ignores the
extra column, so downgrade-safe.
"""

import re

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_EMP_NO_RE = re.compile(r"EMP-(\d+)")


def _employee_columns():
    from alembic import op
    bind = op.get_bind()
    if "employees" not in bind.dialect.get_table_names(bind):
        return None
    return {c["name"] for c in bind.dialect.get_columns(bind, "employees")}


def _backfill():
    from alembic import op
    bind = op.get_bind()
    rows = bind.exec_driver_sql(
        "SELECT id, COALESCE(emp_no, '') FROM employees "
        "ORDER BY COALESCE(created_at, ''), id").fetchall()
    top = 0
    for _id, raw in rows:
        m = _EMP_NO_RE.fullmatch((raw or "").strip().upper())
        if m:
            top = max(top, int(m.group(1)))
    next_no = top + 1
    for _id, raw in rows:
        if not (raw or "").strip():
            bind.exec_driver_sql(
                "UPDATE employees SET emp_no = ? WHERE id = ?",
                ("EMP-%03d" % next_no, _id))
            next_no += 1


def upgrade() -> None:
    import sqlalchemy as sa
    from alembic import op
    cols = _employee_columns()
    if cols is not None and "emp_no" not in cols:
        op.add_column("employees",
                      sa.Column("emp_no", sa.String(),
                                server_default="", nullable=False))
    _backfill()
    bind = op.get_bind()
    indexes = {i["name"] for i in bind.dialect.get_indexes(bind, "employees")}
    if "employees_emp_no" not in indexes:
        op.create_index("employees_emp_no", "employees", ["emp_no"],
                        unique=True)


def downgrade() -> None:
    from alembic import op
    cols = _employee_columns()
    bind = op.get_bind()
    indexes = {i["name"] for i in bind.dialect.get_indexes(bind, "employees")}
    if "employees_emp_no" in indexes:
        op.drop_index("employees_emp_no", table_name="employees")
    if cols is not None and "emp_no" in cols:
        op.drop_column("employees", "emp_no")
