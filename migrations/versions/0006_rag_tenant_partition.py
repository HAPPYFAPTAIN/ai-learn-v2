"""把 RAG 两张表改成按租户 LIST 分区。

pgvector 官方文档说得直白：多租户共享一个 HNSW 索引，别人的向量会挤占你的
召回和查询时间。改成 ``PARTITION BY LIST (tenant_id)`` 后，每个租户一个分区，
各自一份 HNSW，查询按 tenant_id 裁剪到单分区。

分区由 ``ensure_rag_partition(uuid)`` 按需创建：应用角色没有 DDL 权限，
所以函数以 learn_owner 的身份执行（SECURITY DEFINER），只做建分区这一件事。

Revision ID: 0006_rag_tenant_partition
Revises: 0005_stored_file_name
Create Date: 2026-11-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0006_rag_tenant_partition"
down_revision = "0005_stored_file_name"
branch_labels = None
depends_on = None

APP_ROLE = "learn_app"

FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION ensure_rag_partition(tid uuid) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    chunk_name text := 'rag_chunk_t_' || replace(tid::text, '-', '');
    emb_name   text := 'rag_embedding_t_' || replace(tid::text, '-', '');
BEGIN
    -- 同一租户并发建分区时只让一个进来。
    PERFORM pg_advisory_xact_lock(hashtext('rag_partition:' || tid::text));

    IF to_regclass(chunk_name) IS NULL THEN
        EXECUTE format('CREATE TABLE %I PARTITION OF rag_chunk FOR VALUES IN (%L)', chunk_name, tid);
    END IF;
    IF to_regclass(emb_name) IS NULL THEN
        EXECUTE format('CREATE TABLE %I PARTITION OF rag_embedding FOR VALUES IN (%L)', emb_name, tid);
    END IF;
END;
$$;
"""


def upgrade() -> None:
    columns_chunk = """
        tenant_id uuid NOT NULL,
        index_id varchar(64) NOT NULL,
        chunk_id varchar(64) NOT NULL,
        source_id varchar(64) NOT NULL,
        text text NOT NULL,
        metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
        tsv tsvector,
        PRIMARY KEY (tenant_id, index_id, chunk_id)
    """
    columns_emb = """
        tenant_id uuid NOT NULL,
        index_id varchar(64) NOT NULL,
        chunk_id varchar(64) NOT NULL,
        source_id varchar(64) NOT NULL,
        embedding vector(384),
        PRIMARY KEY (tenant_id, index_id, chunk_id)
    """

    # 先留一份旧数据，建好分区表再搬回来。
    op.execute("ALTER TABLE rag_chunk RENAME TO rag_chunk_legacy")
    op.execute("ALTER TABLE rag_embedding RENAME TO rag_embedding_legacy")

    # 改表名不会改索引/约束名，先给旧对象让位，新表才能用同样的名字。
    for table, old, new in (
        ("rag_chunk_legacy", "rag_chunk_pkey", "rag_chunk_legacy_pkey"),
        ("rag_chunk_legacy", "rag_chunk_tenant_id_fkey", "rag_chunk_legacy_tenant_fkey"),
        ("rag_embedding_legacy", "rag_embedding_pkey", "rag_embedding_legacy_pkey"),
        ("rag_embedding_legacy", "rag_embedding_tenant_id_fkey", "rag_embedding_legacy_tenant_fkey"),
    ):
        op.execute(f"ALTER TABLE {table} RENAME CONSTRAINT {old} TO {new}")

    for old, new in (
        ("ix_rag_chunk_source_id", "ix_rag_chunk_legacy_source_id"),
        ("ix_rag_chunk_tsv", "ix_rag_chunk_legacy_tsv"),
        ("ix_rag_embedding_source_id", "ix_rag_embedding_legacy_source_id"),
        ("ix_rag_embedding_hnsw", "ix_rag_embedding_legacy_hnsw"),
        ("ix_rag_embedding_tenant_source", "ix_rag_embedding_legacy_tenant_source"),
    ):
        op.execute(f"ALTER INDEX {old} RENAME TO {new}")

    op.execute(f"CREATE TABLE rag_chunk ({columns_chunk}) PARTITION BY LIST (tenant_id)")
    op.execute(f"CREATE TABLE rag_embedding ({columns_emb}) PARTITION BY LIST (tenant_id)")

    op.execute("CREATE INDEX ix_rag_chunk_tsv ON rag_chunk USING gin (tsv)")
    op.execute(
        "CREATE INDEX ix_rag_embedding_hnsw ON rag_embedding "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX ix_rag_embedding_tenant_source ON rag_embedding (tenant_id, source_id)"
    )

    # 应用角色只有 DML；建分区走 SECURITY DEFINER 函数。
    op.execute(FUNCTION_SQL)
    op.execute(f"REVOKE ALL ON FUNCTION ensure_rag_partition(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION ensure_rag_partition(uuid) TO {APP_ROLE}")

    op.execute("ALTER TABLE rag_chunk ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rag_chunk FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON rag_chunk
          USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
          WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )
    op.execute("ALTER TABLE rag_embedding ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE rag_embedding FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON rag_embedding
          USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
          WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        """
    )

    # 已有租户先建分区，再把数据搬过来。
    bind = op.get_bind()
    tenants = bind.execute(
        text(
            """
            SELECT DISTINCT tenant_id FROM rag_chunk_legacy
            UNION SELECT DISTINCT tenant_id FROM rag_embedding_legacy
            """
        )
    ).scalars().all()
    for tid in tenants:
        bind.execute(text("SELECT ensure_rag_partition(:tid)"), {"tid": tid})

    # 父表是分区表，直接 INSERT 会按 tenant_id 路由到对应分区。
    op.execute(
        """
        INSERT INTO rag_chunk (tenant_id, index_id, chunk_id, source_id, text, metadata, tsv)
        SELECT tenant_id, index_id, chunk_id, source_id, text, metadata, tsv FROM rag_chunk_legacy
        """
    )
    op.execute(
        """
        INSERT INTO rag_embedding (tenant_id, index_id, chunk_id, source_id, embedding)
        SELECT tenant_id, index_id, chunk_id, source_id, embedding FROM rag_embedding_legacy
        """
    )

    op.execute("DROP TABLE rag_chunk_legacy")
    op.execute("DROP TABLE rag_embedding_legacy")

    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON rag_chunk TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON rag_embedding TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rag_chunk CASCADE")
    op.execute("DROP TABLE IF EXISTS rag_embedding CASCADE")
    op.execute("DROP FUNCTION IF EXISTS ensure_rag_partition(uuid)")
    # 回滚时按旧结构重建空表（分区里的数据不迁回，属于破坏性回滚）。
    op.execute(
        """
        CREATE TABLE rag_chunk (
            tenant_id uuid NOT NULL,
            index_id varchar(64) NOT NULL,
            chunk_id varchar(64) NOT NULL,
            source_id varchar(64) NOT NULL,
            text text NOT NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            tsv tsvector,
            PRIMARY KEY (tenant_id, index_id, chunk_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE rag_embedding (
            tenant_id uuid NOT NULL,
            index_id varchar(64) NOT NULL,
            chunk_id varchar(64) NOT NULL,
            source_id varchar(64) NOT NULL,
            embedding vector(384),
            PRIMARY KEY (tenant_id, index_id, chunk_id)
        )
        """
    )

    for table in ('rag_chunk', 'rag_embedding'):
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f"""CREATE POLICY tenant_isolation ON {table}
          USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
          WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)""")
        op.execute(f'ALTER TABLE {table} ADD CONSTRAINT {table}_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES tenant(id) ON DELETE CASCADE')
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO learn_app, learn_ops')
    op.execute('CREATE INDEX ix_rag_chunk_source_id ON rag_chunk (source_id)')
    op.execute('CREATE INDEX ix_rag_embedding_source_id ON rag_embedding (source_id)')
    op.execute('CREATE INDEX ix_rag_chunk_tsv ON rag_chunk USING gin (tsv)')
    op.execute('CREATE INDEX ix_rag_embedding_hnsw ON rag_embedding USING hnsw (embedding vector_cosine_ops)')
    op.execute('CREATE INDEX ix_rag_embedding_tenant_source ON rag_embedding (tenant_id, source_id)')
