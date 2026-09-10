"""Per-employee third-party OAuth token storage (item 31).

Creates oauth_tokens for short-lived access tokens. Refresh tokens stay
in the OS keychain and never touch this table.
"""

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import sqlalchemy as sa
    from alembic import op
    if "oauth_tokens" in op.get_bind().dialect.get_table_names(
            op.get_bind()):
        return
    op.create_table(
        "oauth_tokens",
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("owner_employee_id", sa.String(), nullable=False),
        sa.Column("access_token", sa.String(), server_default="",
                  nullable=False),
        sa.Column("expires_at", sa.String(), server_default="",
                  nullable=False),
        sa.Column("scope", sa.String(), server_default="", nullable=False),
        sa.Column("updated_at", sa.String(), server_default="",
                  nullable=False),
        sa.ForeignKeyConstraint(["owner_employee_id"], ["employees.id"]),
        sa.PrimaryKeyConstraint("provider", "owner_employee_id"),
    )


def downgrade() -> None:
    from alembic import op
    op.drop_table("oauth_tokens")
