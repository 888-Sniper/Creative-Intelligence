"""Encrypted access-token column on oauth_tokens.

Access tokens move from plaintext into access_token_enc (server
master key), matching the refresh-token treatment: a database or
WAL disclosure must not yield a usable token. Readers upgrade
legacy plaintext rows on first use; writers always clear the
legacy column.
"""

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import sqlalchemy as sa
    from alembic import op
    cols = {c["name"] for c in op.get_bind().dialect.get_columns(
        op.get_bind(), "oauth_tokens")}
    if "access_token_enc" not in cols:
        op.add_column("oauth_tokens",
                      sa.Column("access_token_enc", sa.String(),
                                server_default="", nullable=False))


def downgrade() -> None:
    from alembic import op
    cols = {c["name"] for c in op.get_bind().dialect.get_columns(
        op.get_bind(), "oauth_tokens")}
    if "access_token_enc" in cols:
        op.drop_column("oauth_tokens", "access_token_enc")
