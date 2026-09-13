"""Avatar-removal preference on employees.

Databases created before this change gain ``avatar_removed``
(default '') via this migration; fresh databases get it from the
static DDL. Old code ignores the extra column, so downgrade-safe.
"""

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def _employee_columns():
    from alembic import op
    bind = op.get_bind()
    if "employees" not in bind.dialect.get_table_names(bind):
        return None
    return {c["name"] for c in bind.dialect.get_columns(bind, "employees")}


def upgrade() -> None:
    cols = _employee_columns()
    if cols is not None and "avatar_removed" not in cols:
        import sqlalchemy as sa
        from alembic import op
        op.add_column("employees",
                      sa.Column("avatar_removed", sa.String(),
                                server_default="", nullable=False))


def downgrade() -> None:
    cols = _employee_columns()
    if cols is not None and "avatar_removed" in cols:
        from alembic import op
        op.drop_column("employees", "avatar_removed")
