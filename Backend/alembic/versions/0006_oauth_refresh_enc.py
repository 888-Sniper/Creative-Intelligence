"""Encrypted refresh-token column on oauth_tokens.

Refresh tokens move from the OS keychain (unavailable on servers)
into this table encrypted under the server master key, so private
Drive/Sheets sync survives restarts and deploys.
"""

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import sqlalchemy as sa
    from alembic import op
    cols = {c["name"] for c in op.get_bind().dialect.get_columns(
        op.get_bind(), "oauth_tokens")}
    if "refresh_token_enc" not in cols:
        op.add_column("oauth_tokens",
                      sa.Column("refresh_token_enc", sa.String(),
                                server_default="", nullable=False))


def downgrade() -> None:
    from alembic import op
    cols = {c["name"] for c in op.get_bind().dialect.get_columns(
        op.get_bind(), "oauth_tokens")}
    if "refresh_token_enc" in cols:
        op.drop_column("oauth_tokens", "refresh_token_enc")
