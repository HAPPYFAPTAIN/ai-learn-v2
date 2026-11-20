"""Encrypted personal model providers, isolated by the existing tenant RLS."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_model_providers"
down_revision = "0007_creation_receipts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "model_provider",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenant.id", ondelete="CASCADE"),
                  nullable=False, server_default=sa.text("NULLIF(current_setting('app.tenant_id', true), '')::uuid")),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "name", name="uq_model_provider_name"),
        if_not_exists=True,
    )
    op.create_index("ix_model_provider_tenant_id", "model_provider", ["tenant_id"], if_not_exists=True)
    op.execute("ALTER TABLE model_provider ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE model_provider FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON model_provider")
    op.execute("""CREATE POLICY tenant_isolation ON model_provider
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON model_provider TO learn_app, learn_ops")


def downgrade():
    op.drop_table("model_provider")
