"""Durable note/card creation receipts and ordered daily report lookups."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_creation_receipts"
down_revision = "0006_rag_tenant_partition"
branch_labels = None
depends_on = None


def upgrade():
    # Historical 0001/0002 load current model metadata. On a fresh database
    # they may already have created this table; existing 0006 databases have not.
    op.create_table(
        "creation_request",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False,
                  server_default=sa.text("NULLIF(current_setting('app.tenant_id', true), '')::uuid")),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.BigInteger(), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "operation", "request_id", name="uq_creation_request_intent"),
        if_not_exists=True,
    )
    op.create_index("ix_creation_request_tenant_id", "creation_request", ["tenant_id"], if_not_exists=True)
    op.execute("ALTER TABLE creation_request ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE creation_request FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON creation_request")
    op.execute("""CREATE POLICY tenant_isolation ON creation_request
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON creation_request TO learn_app, learn_ops")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE creation_request_id_seq TO learn_app, learn_ops")
    op.execute("CREATE INDEX ix_daily_report_latest ON le_daily_report (tenant_id, project_id, report_date DESC, id DESC)")


def downgrade():
    op.drop_index("ix_daily_report_latest", table_name="le_daily_report")
    op.drop_table("creation_request")
