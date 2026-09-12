"""Team attribution column on ads.

Team filtering needs a real row-level dimension: databases created
before this change gain ``team`` (default '') via this migration,
fresh databases get it from the static DDL, and schema.migrate()
backfills anything in between. Old code ignores the extra column
(it names its INSERT columns explicitly), so this is downgrade-safe.
"""

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def _ads_columns():
    from alembic import op
    bind = op.get_bind()
    if "ads" not in bind.dialect.get_table_names(bind):
        # Product tables are created lazily per request (schema.init_db),
        # which already includes team for fresh databases; nothing to do.
        return None
    return {c["name"] for c in bind.dialect.get_columns(bind, "ads")}


def upgrade() -> None:
    cols = _ads_columns()
    if cols is not None and "team" not in cols:
        import sqlalchemy as sa
        from alembic import op
        op.add_column("ads",
                      sa.Column("team", sa.String(),
                                server_default="", nullable=False))


def downgrade() -> None:
    cols = _ads_columns()
    if cols is not None and "team" in cols:
        from alembic import op
        op.drop_column("ads", "team")
