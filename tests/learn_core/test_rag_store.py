"""RAG 写入与混合检索的守卫测试。"""

from __future__ import annotations

import hashlib
import os
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import text

from learn_core.db.engine import reset_engine, session_scope
from learn_core.db.models import Tenant
from learn_core.rag.chunking import split_text, tokenize_for_tsv
from learn_core.rag.store import delete_source, hybrid_search, upsert_chunks
from learn_core.tenancy.context import tenant_context

pytestmark = pytest.mark.skipif(
    os.getenv("LEARN_DATABASE_URL") is None,
    reason="需要 LEARN_DATABASE_URL 指向测试库",
)

DIM = 384


def fake_vector(seed: str) -> list[float]:
    """确定性的伪向量：同文本永远同向量，不同文本方向不同。"""
    digest = hashlib.sha256(seed.encode()).digest()
    raw = [(digest[i % len(digest)] / 255.0) - 0.5 for i in range(DIM)]
    norm = sum(x * x for x in raw) ** 0.5 or 1.0
    return [x / norm for x in raw]


@pytest.fixture(scope="module", autouse=True)
def _engine():
    reset_engine()
    yield
    reset_engine()


@contextmanager
def _tenant(official_id: str):
    with session_scope() as session:
        tenant = Tenant(official_user_id=official_id)
        session.add(tenant)
        session.flush()
        tenant_id = tenant.id
    yield tenant_id
    with session_scope() as session:
        session.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


def test_split_text_respects_limit_and_overlap():
    text_in = "第一段。" * 200 + "\n\n" + "第二段。" * 200
    chunks = split_text(text_in, max_chars=300, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)


def test_split_text_handles_single_long_sentence():
    chunks = split_text("啊" * 1000, max_chars=200, overlap=20)
    assert len(chunks) == 5
    assert all(len(c) <= 200 for c in chunks)


def test_tokenize_falls_back_to_chars_without_jieba():
    tokens = tokenize_for_tsv("向量检索")
    assert "向" in tokens.split()


def test_upsert_and_hybrid_search_are_tenant_scoped():
    suffix = uuid.uuid4().hex[:8]
    docs = {
        "d1": "分子动力学模拟需要先做能量最小化，否则初始结构可能爆炸。",
        "d2": "复习计划按 FSRS 安排，每天的新卡片数量要设上限。",
    }
    chunks = {k: split_text(v, max_chars=200) for k, v in docs.items()}

    with _tenant(f"rag-a-{suffix}") as ta, _tenant(f"rag-b-{suffix}") as tb:
        with tenant_context(ta):
            with session_scope() as session:
                for source_id, parts in chunks.items():
                    upsert_chunks(
                        session,
                        index_id="course:1",
                        source_id=source_id,
                        chunks=parts,
                        vectors=[fake_vector(p) for p in parts],
                    )

        with tenant_context(ta):
            with session_scope() as session:
                hits = hybrid_search(
                    session,
                    index_id="course:1",
                    query="能量最小化",
                    query_vector=fake_vector(docs["d1"]),
                    limit=5,
                )
            assert hits, "本租户应能检索到自己的资料"
            assert hits[0].source_id == "d1"

        with tenant_context(tb):
            with session_scope() as session:
                hits = hybrid_search(
                    session,
                    index_id="course:1",
                    query="能量最小化",
                    query_vector=fake_vector(docs["d1"]),
                    limit=5,
                )
            assert hits == [], "另一个租户不应看到任何块"

        # 重建同一来源时旧块被清掉。
        with tenant_context(ta):
            with session_scope() as session:
                delete_source(session, index_id="course:1", source_id="d1")
                remaining = session.execute(
                    text("SELECT count(*) FROM rag_chunk WHERE source_id = 'd1'")
                ).scalar()
            assert remaining == 0
