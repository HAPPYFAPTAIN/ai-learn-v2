"""嵌入模型封装。

只用 CPU：50–200 人同时在线的场景下，一次批量编码 32 条短文本，
单条延迟在 10–30 ms 量级，没必要占用 GPU。

模型固定 all-MiniLM-L6-v2（384 维），向量归一化后用余弦距离，
与 pgvector 的 vector_cosine_ops 对齐。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# 国内访问 HuggingFace 经常超时；国内镜像可用时优先走镜像。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from fastembed import TextEmbedding  # noqa: E402

from learn_embed.constants import DIM, MODEL_NAME  # noqa: E402


class Embedder:
    def __init__(self, cache_dir: str | None = None, threads: int = 2) -> None:
        cache = Path(cache_dir or os.getenv("LEARN_EMBED_CACHE", "~/.cache/learn-embed")).expanduser()
        cache.mkdir(parents=True, exist_ok=True)
        self.model = TextEmbedding(
            model_name=MODEL_NAME,
            cache_dir=str(cache),
            threads=threads,
            providers=["CPUExecutionProvider"],
        )

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = []
        for vec in self.model.embed(texts, batch_size=32):
            norm = float((vec * vec).sum()) ** 0.5 or 1.0
            vectors.append([float(x) / norm for x in vec])
        return vectors

    @property
    def dim(self) -> int:
        return DIM


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return Embedder()
