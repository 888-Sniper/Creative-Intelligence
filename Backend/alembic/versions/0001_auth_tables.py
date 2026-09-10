"""Initial schema: employee access tables (mirrors legacy DDL)."""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workos_user_id", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=False, server_default=""),
        sa.Column("first_name", sa.String(), nullable=False, server_default=""),
        sa.Column("last_name", sa.String(), nullable=False, server_default=""),
        sa.Column("avatar_url", sa.String(), nullable=False, server_default=""),
        sa.Column("role", sa.String(), nullable=False, server_default="employee"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.String(), nullable=False, server_default=""),
        sa.Column("approved_at", sa.String(), nullable=False, server_default=""),
        sa.Column("approved_by", sa.String(), nullable=False, server_default=""),
        sa.Column("last_login_at", sa.String(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("employees_workos_uid", "employees", ["workos_user_id"],
                    unique=True)
    op.create_index("employees_email", "employees", ["email"], unique=True)
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("employee_id", sa.String(), nullable=False, server_default=""),
        sa.Column("workos_user_id", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(), nullable=False, server_default=""),
        sa.Column("last_seen_at", sa.String(), nullable=False, server_default=""),
        sa.Column("expires_at", sa.String(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_table(
        "auth_pending",
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False, server_default=""),
        sa.Column("verifier", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("state"),
    )
    op.create_table(
        "employee_audit",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False, server_default=""),
        sa.Column("admin_id", sa.String(), nullable=False, server_default=""),
        sa.Column("action", sa.String(), nullable=False, server_default=""),
        sa.Column("prev_value", sa.String(), nullable=False, server_default=""),
        sa.Column("new_value", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    # Constraints drop with their table on sqlite; batch mode is not
    # needed since no other migration depends on these tables yet.
    op.drop_index("employees_email", table_name="employees")
    op.drop_index("employees_workos_uid", table_name="employees")
    op.drop_table("employee_audit")
    op.drop_table("auth_pending")
    op.drop_table("auth_sessions")
    op.drop_table("employees")
