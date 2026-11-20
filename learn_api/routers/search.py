"""RAG 检索接口。

嵌入服务不可用时退化成纯全文检索，而不是整条链路失败——
检索质量差一点，总比页面报错好；降级原因写在响应里。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from learn_api.deps import SessionDep
from learn_core.config import get_settings
from learn_core.rag.embedding import EmbeddingClient, EmbeddingError
from learn_core.rag.store import hybrid_search

router = APIRouter(tags=["rag"])


class SearchRequest(BaseModel):
    index_id: str = Field(alias="indexId", min_length=1, max_length=64)
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=10, ge=1, le=50)

    model_config = {"populate_by_name": True}




@router.post("/search")
def search(payload: SearchRequest, session: SessionDep) -> dict:
    settings = get_settings()
    vector = None
    degraded = None
    try:
        with EmbeddingClient(settings.embed_url) as client:
            vector = client.embed([payload.query])[0]
    except EmbeddingError as exc:
        degraded = f"vector search unavailable: {exc.__class__.__name__}"

    hits = hybrid_search(
        session,
        index_id=payload.index_id,
        query=payload.query,
        query_vector=vector,
        limit=payload.limit,
    )
    return {
        "hits": [
            {
                "chunkId": h.chunk_id,
                "sourceId": h.source_id,
                "text": h.text,
                "metadata": h.metadata,
                "score": round(h.score, 6),
            }
            for h in hits
        ],
        "degraded": degraded,
    }
