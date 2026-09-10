"""Product audit table for production writes.

Records who uploaded a creative, ran analysis, verified annotations,
started syncs, generated/exported reports and changed connectors,
with request ID, employee, action, target, result and timestamp.
Payloads (question text, annotations, bytes, tokens) are never stored.
"""

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op
    op.execute("""CREATE TABLE IF NOT EXISTS product_audit (
        id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL DEFAULT '',
        employee_id TEXT NOT NULL DEFAULT '',
        action TEXT NOT NULL DEFAULT '',
        target TEXT NOT NULL DEFAULT '',
        result TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT ''
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_product_audit_created"
               " ON product_audit (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_product_audit_employee"
               " ON product_audit (employee_id)")


def downgrade() -> None:
    from alembic import op
    op.execute("DROP INDEX IF EXISTS idx_product_audit_employee")
    op.execute("DROP INDEX IF EXISTS idx_product_audit_created")
    op.execute("DROP TABLE IF EXISTS product_audit")
