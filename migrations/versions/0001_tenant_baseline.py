"""基线：全部表、行级安全与角色授权。

Revision ID: 0001_tenant_baseline
Revises:
Create Date: 2026-11-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlmodel import SQLModel

import learn_core.db.models  # noqa: F401  注册全部模型

revision = "0001_tenant_baseline"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = "learn_app"
OPS_ROLE = "learn_ops"


def _tenant_tables(bind) -> list[str]:
    rows = bind.execute(
        sa.text(
            """
            SELECT c.table_name
            FROM information_schema.columns c
            JOIN information_schema.tables t
              ON t.table_schema = c.table_schema AND t.table_name = c.table_name
            WHERE c.table_schema = 'public'
              AND c.column_name = 'tenant_id'
              AND t.table_type = 'BASE TABLE'
            ORDER BY 1
            """
        )
    ).fetchall()
    return [r[0] for r in rows]


def upgrade() -> None:
    bind = op.get_bind()

    # 基线版本由模型元数据一次性建表；后续版本改为显式 op.create_table。
    SQLModel.metadata.create_all(bind)

    # 每张租户表：强制行级安全 + 统一策略。
    for table in _tenant_tables(bind):
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

    # 应用角色只拿到增删改查，没有建表权限；运维角色可以绕过行级安全。
    op.execute(
        f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}, {OPS_ROLE}"
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"
    )
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {OPS_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {OPS_ROLE}")

    # 向量与全文检索索引。
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rag_embedding_hnsw ON rag_embedding "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rag_embedding_tenant_source ON rag_embedding (tenant_id, source_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rag_chunk_tsv ON rag_chunk USING gin (tsv)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(SQLModel.metadata.sorted_tables):
        bind.execute(sa.text(f'DROP TABLE IF EXISTS "{table.name}" CASCADE'))
