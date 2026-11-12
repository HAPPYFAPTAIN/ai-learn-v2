"""RAG 表按租户分区的验证：各写各的分区，互不可见。"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text

from learn_core.db.engine import reset_engine, session_scope
from learn_core.db.models import Tenant
from learn_core.rag.store import hybrid_search, upsert_chunks
from learn_core.tenancy.context import tenant_context

pytestmark = pytest.mark.skipif(
    os.getenv("LEARN_DATABASE_URL") is None,
    reason="需要 LEARN_DATABASE_URL 指向测试库",
)


@pytest.fixture(scope="module", autouse=True)
def _engine():
    reset_engine()
    yield
    reset_engine()


def _make_tenant(prefix: str) -> uuid.UUID:
    with session_scope() as session:
        tenant = Tenant(official_user_id=f"{prefix}-{uuid.uuid4().hex[:8]}")
        session.add(tenant)
        session.flush()
        return tenant.id


def _partition_of(tid: uuid.UUID) -> str:
    return "rag_chunk_t_" + str(tid).replace("-", "")


def test_each_tenant_gets_its_own_partition():
    tid = _make_tenant("part")
    with tenant_context(tid):
        with session_scope() as session:
            upsert_chunks(
                session,
                index_id="material",
                source_id="doc",
                chunks=["向量空间里的第一段"],
                vectors=[[0.1] * 384],
            )

    with session_scope() as session:
        exists = session.execute(
            text("SELECT to_regclass(:name)"), {"name": _partition_of(tid)}
        ).scalar_one()
    assert exists is not None, "写入时应自动建出该租户的分区"

    with session_scope() as session:
        session.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tid})


def test_same_source_id_across_tenants_does_not_collide():
    a = _make_tenant("parta")
    b = _make_tenant("partb")

    for tid, text_ in ((a, "甲租户的原文"), (b, "乙租户的原文")):
        with tenant_context(tid):
            with session_scope() as session:
                upsert_chunks(
                    session,
                    index_id="material",
                    source_id="same",
                    chunks=[text_],
                    vectors=[[0.2] * 384],
                )

    with tenant_context(a):
        with session_scope() as session:
            hits = hybrid_search(
                session, index_id="material", query="原文", query_vector=[0.2] * 384, limit=10
            )
    assert [h.text for h in hits] == ["甲租户的原文"]

    with session_scope() as session:
        session.execute(text("DELETE FROM tenant WHERE id = ANY(:ids)"), {"ids": [str(a), str(b)]})
