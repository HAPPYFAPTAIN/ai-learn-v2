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
    op.add_column(
        "stored_file",
        sa.Column("original_name", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("stored_file", "original_name")
