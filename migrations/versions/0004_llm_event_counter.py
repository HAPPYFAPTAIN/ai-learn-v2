"""模型事件 id 的自增计数器。

Revision ID: 0004_llm_event_counter
Revises: 0003_llm_lease
Create Date: 2026-11-12
"""

from __future__ import annotations

from alembic import op
from sqlmodel import SQLModel

import learn_core.db.models  # noqa: F401

revision = "0004_llm_event_counter"
down_revision = "0003_llm_lease"
branch_labels = None
depends_on = None

APP_ROLE = "learn_app"
TABLE = "llm_event_counter"


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
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {TABLE} TO {APP_ROLE}")


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {TABLE} CASCADE")
