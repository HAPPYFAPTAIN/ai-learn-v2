"""Kotaemon 核心表的租户化版本。

Revision ID: 0002_ktem_tables
Revises: 0001_tenant_baseline
Create Date: 2026-11-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlmodel import SQLModel

import learn_core.db.ktem  # noqa: F401

revision = "0002_ktem_tables"
down_revision = "0001_tenant_baseline"
branch_labels = None
depends_on = None

APP_ROLE = "learn_app"

TABLES = ("ktem_conversation", "ktem_settings", "ktem_issue_report")


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind)

    for table in TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON "{table}"
              USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
              WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
            """
        )

    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(TABLES)} TO {APP_ROLE}"
    )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
