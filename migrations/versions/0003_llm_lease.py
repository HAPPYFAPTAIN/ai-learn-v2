"""模型并发租约表。

Revision ID: 0003_llm_lease
Revises: 0002_ktem_tables
Create Date: 2026-11-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlmodel import SQLModel

import learn_core.db.models  # noqa: F401

revision = "0003_llm_lease"
down_revision = "0002_ktem_tables"
branch_labels = None
depends_on = None

APP_ROLE = "learn_app"
TABLE = "llm_lease"


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind, tables=[SQLModel.metadata.tables[TABLE]])

    op.execute(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{TABLE}" FORCE ROW LEVEL SECURITY')
    op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{TABLE}"')
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON "{TABLE}"
          USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
          WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )
    op.create_index("ix_llm_lease_expires", TABLE, ["expires_at"])
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {TABLE} CASCADE")
