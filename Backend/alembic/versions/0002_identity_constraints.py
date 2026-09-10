"""Identity hardening: role/status checks plus session/audit references.

Application validation stays first, but core identity relationships are
now also defended at the database level: roles and statuses outside the
known enums are rejected, sessions cannot dangle off unknown
employees, and audit rows always point at a real target employee.
There is deliberately NO foreign key on employee_audit.admin_id,
which also carries bootstrap markers such as "root" by design.
"""

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _orphans(table: str, column: str) -> int:
    from alembic import op
    import sqlalchemy as sa
    return op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM %s LEFT JOIN employees"
        " ON employees.id = %s.%s WHERE employees.id IS NULL"
        % (table, table, column))).scalar()


def upgrade() -> None:
    from alembic import op
    # Fail closed: existing rows that would violate the new
    # references abort the migration instead of being dropped.
    dangling = (_orphans("auth_sessions", "employee_id")
                + _orphans("employee_audit", "target_id"))
    if dangling:
        raise RuntimeError(
            "%d session/audit row(s) reference unknown employees;"
            " resolve them before migrating" % dangling)
    with op.batch_alter_table("employees") as batch:
        batch.create_check_constraint(
            "ck_employees_role", "role IN ('admin', 'employee')")
        batch.create_check_constraint(
            "ck_employees_status",
            "status IN ('pending', 'active', 'suspended', 'revoked')")
    with op.batch_alter_table("auth_sessions") as batch:
        batch.create_foreign_key("fk_sessions_employee", "employees",
                                 ["employee_id"], ["id"])
    with op.batch_alter_table("employee_audit") as batch:
        batch.create_foreign_key("fk_audit_target", "employees",
                                 ["target_id"], ["id"])


def downgrade() -> None:
    from alembic import op
    with op.batch_alter_table("employee_audit") as batch:
        batch.drop_constraint("fk_audit_target", type_="foreignkey")
    with op.batch_alter_table("auth_sessions") as batch:
        batch.drop_constraint("fk_sessions_employee", type_="foreignkey")
    with op.batch_alter_table("employees") as batch:
        batch.drop_constraint("ck_employees_status", type_="check")
        batch.drop_constraint("ck_employees_role", type_="check")
