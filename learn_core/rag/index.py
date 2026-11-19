"""把一段文本变成可检索的块。

API 和 worker 都走这里，区别只是谁提供嵌入向量：
worker 用本机嵌入服务，测试用假实现。切成小块再逐批嵌入，
是因为 800 字一块、64 块一批时单次请求的耗时和内存都可控。
"""

from __future__ import annotations

from typing import Callable, Protocol, Sequence

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from learn_core.rag.chunking import split_text
from learn_core.rag.store import delete_source, upsert_chunks

ProgressFn = Callable[[int, int], None]


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


def index_source(
    session: Session,
    *,
    source_id: str,
    text: str,
    embedder: Embedder,
    index_id: str = "material",
    metadata: dict | None = None,
    progress: ProgressFn | None = None,
    chunk_chars: int = 800,
    overlap: int = 80,
) -> int:
    """切块、嵌入、写入；返回块数。文本为空时清掉旧块。"""
    chunks = split_text(text, max_chars=chunk_chars, overlap=overlap)
    if not chunks:
        delete_source(session, index_id=index_id, source_id=source_id)
        return 0

    vectors: list[Sequence[float]] = []
    total = len(chunks)
    batch = 16
    for start in range(0, total, batch):
        part = chunks[start : start + batch]
        vectors.extend(embedder.embed(part))
        if progress is not None:
            progress(min(start + batch, total), total)

    upsert_chunks(
        session,
        index_id=index_id,
        source_id=source_id,
        chunks=chunks,
        vectors=vectors,
        metadata=metadata,
    )
    # 上次切块可能更长，多出来的旧块要删掉。
    session.execute(
        sql_text(
            """
            DELETE FROM rag_chunk
             WHERE index_id = :index_id AND source_id = :source_id
               AND chunk_id NOT IN (
                   SELECT :source_id || ':' || i::text
                     FROM generate_series(0, :last) AS i
               )
            """
        ),
        {"index_id": index_id, "source_id": source_id, "last": total - 1},
    )
    return total
