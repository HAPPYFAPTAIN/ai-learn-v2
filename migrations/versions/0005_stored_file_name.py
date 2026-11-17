"""stored_file 记录原始文件名，便于列表展示。

Revision ID: 0005_stored_file_name
Revises: 0004_llm_event_counter
Create Date: 2026-11-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_stored_file_name"
down_revision = "0004_llm_event_counter"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 builds from current metadata on a fresh database, which already
    # includes this column. Existing installations still need the expansion.
    op.execute("ALTER TABLE stored_file ADD COLUMN IF NOT EXISTS original_name TEXT NOT NULL DEFAULT ''")


def downgrade() -> None:
    op.drop_column("stored_file", "original_name")
