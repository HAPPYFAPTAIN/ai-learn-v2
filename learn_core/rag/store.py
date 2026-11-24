"""RAG 的写入与混合检索。

检索用两路打分后做 RRF（Reciprocal Rank Fusion）：
向量一路、全文一路，各自排名倒数相加。选 RRF 而不是分数加权，
是因为余弦相似度和 ts_rank 的量纲没法直接比，调权重会变成玄学。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from learn_core.rag.chunking import tokenize_for_tsv
from learn_core.rag.settings import apply_ann_settings

_RRF_K = 60


@dataclass(frozen=True)
class SearchHit:
    chunk_id: str
    source_id: str
    text: str
    metadata: dict
    score: float


def _vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(f"{float(x):.6f}" for x in vector) + "]"


def upsert_chunks(
    session: Session,
    *,
    index_id: str,
    source_id: str,
    chunks: list[str],
    vectors: list[Sequence[float]],
    metadata: dict | None = None,
) -> int:
    """按 ``chunk_id = f"{source_id}:{i}"`` 写入或覆盖。

    覆盖而不是跳过，是因为重新切块时块数可能变少，
    旧块要靠 :func:`delete_source` 清干净。
    """
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors must have the same length")
    if not chunks:
        return 0

    # RAG 表按租户 LIST 分区：写之前确保这个租户有分区。
    # 函数是 SECURITY DEFINER，应用角色只拿到 EXECUTE。
    session.execute(
        text("SELECT ensure_rag_partition(NULLIF(current_setting('app.tenant_id', true), '')::uuid)")
    )

    rows = [
        {
            "index_id": index_id,
            "chunk_id": f"{source_id}:{i}",
            "source_id": source_id,
            "text": chunk,
            "tok": tokenize_for_tsv(chunk),
            "metadata": json.dumps(metadata or {}, ensure_ascii=False),
        }
        for i, chunk in enumerate(chunks)
    ]
    session.execute(
        text(
            """
            INSERT INTO rag_chunk (tenant_id, index_id, chunk_id, source_id, text, metadata, tsv)
            VALUES (current_setting('app.tenant_id')::uuid, :index_id, :chunk_id, :source_id,
                    :text, CAST(:metadata AS jsonb), to_tsvector('simple', :tok))
            ON CONFLICT (tenant_id, index_id, chunk_id) DO UPDATE
               SET source_id = excluded.source_id,
                   text = excluded.text,
                   metadata = excluded.metadata,
                   tsv = excluded.tsv
            """
        ),
        rows,
    )
    session.execute(
        text(
            """
            INSERT INTO rag_embedding (tenant_id, index_id, chunk_id, source_id, embedding)
            VALUES (current_setting('app.tenant_id')::uuid, :index_id, :chunk_id, :source_id,
                    CAST(:embedding AS vector))
            ON CONFLICT (tenant_id, index_id, chunk_id) DO UPDATE
               SET source_id = excluded.source_id,
                   embedding = excluded.embedding
            """
        ),
        [
            {
                "index_id": index_id,
                "chunk_id": row["chunk_id"],
                "source_id": source_id,
                "embedding": _vector_literal(vector),
            }
            for row, vector in zip(rows, vectors)
        ],
    )
    return len(rows)


def delete_source(session: Session, *, index_id: str, source_id: str) -> int:
    result = session.execute(
        text(
            "DELETE FROM rag_embedding WHERE index_id = :index_id AND source_id = :source_id"
        ),
        {"index_id": index_id, "source_id": source_id},
    )
    removed = result.rowcount or 0
    session.execute(
        text("DELETE FROM rag_chunk WHERE index_id = :index_id AND source_id = :source_id"),
        {"index_id": index_id, "source_id": source_id},
    )
    return removed


def hybrid_search(
    session: Session,
    *,
    index_id: str,
    query: str,
    query_vector: Sequence[float] | None = None,
    limit: int = 10,
    pool: int = 40,
    source_ids: list[str] | None = None,
) -> list[SearchHit]:
    query = query.strip()
    if not query and query_vector is None:
        return []

    if query_vector is None:
        sql = """
            WITH txt AS (
                SELECT chunk_id,
                       row_number() OVER (
                           ORDER BY ts_rank_cd(tsv, plainto_tsquery('simple', :qtok)) DESC
                       ) AS rnk
                  FROM rag_chunk
                 WHERE index_id = :index_id
                   AND (NOT :filter_sources OR source_id = ANY(CAST(:source_ids AS text[])))
                   AND tsv @@ plainto_tsquery('simple', :qtok)
                 ORDER BY ts_rank_cd(tsv, plainto_tsquery('simple', :qtok)) DESC
                 LIMIT :pool
            )
            SELECT c.chunk_id, c.source_id, c.text, c.metadata,
                   1.0 / (%(rrf)s + t.rnk) AS score
              FROM txt t
              JOIN rag_chunk c ON c.chunk_id = t.chunk_id AND c.index_id = :index_id
             ORDER BY score DESC
             LIMIT :limit
        """ % {"rrf": _RRF_K}
        rows = session.execute(
            text(sql),
            {
                "index_id": index_id,
                "qtok": tokenize_for_tsv(query),
                "pool": pool,
                "limit": limit,
                "filter_sources": source_ids is not None,
                "source_ids": source_ids or [],
            },
        ).mappings()
        return [
            SearchHit(
                chunk_id=row["chunk_id"],
                source_id=row["source_id"],
                text=row["text"],
                metadata=row["metadata"] or {},
                score=float(row["score"]),
            )
            for row in rows
        ]

    apply_ann_settings(session)
    sql = """
        WITH vec AS (
            SELECT chunk_id,
                   row_number() OVER (ORDER BY embedding <=> CAST(:qvec AS vector)) AS rnk
              FROM rag_embedding
             WHERE index_id = :index_id
               AND (NOT :filter_sources OR source_id = ANY(CAST(:source_ids AS text[])))
               AND embedding IS NOT NULL
             ORDER BY embedding <=> CAST(:qvec AS vector)
             LIMIT :pool
        ), txt AS (
            SELECT chunk_id,
                   row_number() OVER (
                       ORDER BY ts_rank_cd(tsv, plainto_tsquery('simple', :qtok)) DESC
                   ) AS rnk
              FROM rag_chunk
             WHERE index_id = :index_id
               AND (NOT :filter_sources OR source_id = ANY(CAST(:source_ids AS text[])))
               AND tsv @@ plainto_tsquery('simple', :qtok)
             ORDER BY ts_rank_cd(tsv, plainto_tsquery('simple', :qtok)) DESC
             LIMIT :pool
        )
        SELECT c.chunk_id, c.source_id, c.text, c.metadata,
               COALESCE(1.0 / (%(rrf)s + v.rnk), 0) + COALESCE(1.0 / (%(rrf)s + t.rnk), 0) AS score
          FROM rag_chunk c
          LEFT JOIN vec v USING (chunk_id)
          LEFT JOIN txt t USING (chunk_id)
         WHERE c.index_id = :index_id
           AND (v.rnk IS NOT NULL OR t.rnk IS NOT NULL)
         ORDER BY score DESC
         LIMIT :limit
    """ % {"rrf": _RRF_K}

    rows = session.execute(
        text(sql),
        {
            "index_id": index_id,
            "qvec": _vector_literal(query_vector) if query_vector is not None else None,
            "qtok": tokenize_for_tsv(query),
            "pool": pool,
            "limit": limit,
            "filter_sources": source_ids is not None,
            "source_ids": source_ids or [],
        },
    ).mappings()
    return [
        SearchHit(
            chunk_id=row["chunk_id"],
            source_id=row["source_id"],
            text=row["text"],
            metadata=row["metadata"] or {},
            score=float(row["score"]),
        )
        for row in rows
    ]
