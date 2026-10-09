"""Two-factor secrets and an account id on oauth tokens.

employee_totp holds the encrypted authenticator secret. totp_challenges
holds short-lived sign-in challenges (hash only). oauth_tokens gains
account_ref for the linked Meta, TikTok, or GA4 account id. No secret
is written by this migration.
"""

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def _tables(bind):
    return set(bind.dialect.get_table_names(bind))


def _cols(bind, table):
    return {c["name"] for c in bind.dialect.get_columns(bind, table)}


def upgrade() -> None:
    import sqlalchemy as sa
    from alembic import op

    bind = op.get_bind()
    names = _tables(bind)
    if "oauth_tokens" in names and "account_ref" not in _cols(
            bind, "oauth_tokens"):
        op.add_column("oauth_tokens",
                      sa.Column("account_ref", sa.String(),
                                server_default="", nullable=False))
    if "employee_totp" not in names:
        op.create_table(
            "employee_totp",
            sa.Column("employee_id", sa.String(), nullable=False),
            sa.Column("secret_enc", sa.String(), server_default="",
                      nullable=False),
            sa.Column("enabled", sa.Integer(), server_default="0",
                      nullable=False),
            sa.Column("recovery_hashes", sa.Text(), server_default="",
                      nullable=False),
            sa.Column("last_step", sa.Integer(), server_default="0",
                      nullable=False),
            sa.Column("updated_at", sa.String(), server_default="",
                      nullable=False),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
            sa.PrimaryKeyConstraint("employee_id"),
        )
    if "totp_challenges" not in names:
        op.create_table(
            "totp_challenges",
            sa.Column("token_hash", sa.String(), nullable=False),
            sa.Column("employee_id", sa.String(), server_default="",
                      nullable=False),
            sa.Column("attempts", sa.Integer(), server_default="0",
                      nullable=False),
            sa.Column("expires_at", sa.String(), server_default="",
                      nullable=False),
            sa.Column("created_at", sa.String(), server_default="",
                      nullable=False),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
            sa.PrimaryKeyConstraint("token_hash"),
        )


def downgrade() -> None:
    from alembic import op

    bind = op.get_bind()
    names = _tables(bind)
    if "totp_challenges" in names:
        op.drop_table("totp_challenges")
    if "employee_totp" in names:
        op.drop_table("employee_totp")
    if "oauth_tokens" in names and "account_ref" in _cols(
            bind, "oauth_tokens"):
        op.drop_column("oauth_tokens", "account_ref")
