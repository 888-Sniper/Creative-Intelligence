"""Record the authentication provider per employee (item 21).

Adds employees.provider so Settings can show how the employee signed in
(google/microsoft/apple/github/email). Existing rows stay "" (unknown);
new logins persist the verified identity's provider.
"""

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import sqlalchemy as sa
    from alembic import op
    existing = {c["name"] for c in
                op.get_bind().dialect.get_columns(
                    op.get_bind(), "employees")}
    if "provider" in existing:
        return
    with op.batch_alter_table("employees") as batch:
        batch.add_column(sa.Column("provider", sa.String(),
                                   server_default="", nullable=False))


def downgrade() -> None:
    from alembic import op
    with op.batch_alter_table("employees") as batch:
        batch.drop_column("provider")
