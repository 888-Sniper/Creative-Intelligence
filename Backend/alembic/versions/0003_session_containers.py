"""Bind sessions to installation containers (item 18).

Adds auth_sessions.container_id so the account switcher only sees
same-container sessions. Unbound ("") legacy sessions keep working among
themselves; container-aware clients bind on login or adopt on boot.
"""

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import sqlalchemy as sa
    from alembic import op
    existing = {c["name"] for c in
                op.get_bind().dialect.get_columns(
                    op.get_bind(), "auth_sessions")}
    if "container_id" in existing:
        # Databases built by create_all already carry the column (the
        # model is the same); stamping through must not rebuild.
        return
    with op.batch_alter_table("auth_sessions") as batch:
        batch.add_column(sa.Column("container_id", sa.String(),
                                   server_default="", nullable=False))


def downgrade() -> None:
    from alembic import op
    with op.batch_alter_table("auth_sessions") as batch:
        batch.drop_column("container_id")
