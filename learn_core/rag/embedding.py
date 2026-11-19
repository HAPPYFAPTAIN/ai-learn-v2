"""嵌入服务客户端。

服务本身在 ``learn_embed/``，走 OpenAI 兼容的 ``/v1/embeddings``。
这里只负责批量、重试和错误翻译，不做缓存——缓存放在调用方，
因为同一段文本在不同租户下可以复用，但配额要分开算。
"""

from __future__ import annotations

import time

import httpx

MAX_BATCH = 64


class EmbeddingError(RuntimeError):
    pass


class EmbeddingClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 60.0,
        retries: int = 2,
    ) -> None:
        if base_url is None:
            from learn_core.config import get_settings

            base_url = get_settings().embed_url
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
        )
        self._retries = retries

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "EmbeddingClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), MAX_BATCH):
            out.extend(self._embed_batch(texts[start : start + MAX_BATCH]))
        return out

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        if not batch:
            return []
        payload = {"model": "all-MiniLM-L6-v2", "input": batch}
        last_error: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                response = self._client.post("/v1/embeddings", json=payload)
                if response.status_code >= 400:
                    raise EmbeddingError(
                        f"embedding service returned {response.status_code}: {response.text[:200]}"
                    )
                data = response.json()
                items = sorted(data["data"], key=lambda item: item["index"])
                vectors = [item["embedding"] for item in items]
                if len(vectors) != len(batch):
                    raise EmbeddingError(
                        f"expected {len(batch)} vectors, got {len(vectors)}"
                    )
                return vectors
            except (httpx.HTTPError, KeyError, ValueError, EmbeddingError) as exc:
                last_error = exc
                if attempt < self._retries:
                    time.sleep(0.2 * (attempt + 1))
        raise EmbeddingError(str(last_error))
