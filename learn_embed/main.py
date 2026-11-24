"""本机嵌入服务。

OpenAI 兼容的最小实现：POST /v1/embeddings。
不鉴权，只监听 127.0.0.1，由 hpc/网关侧的内网调用；对外不可见。

启动：
    PYTHONPATH=. .venv/bin/python -m learn_embed --port 18090
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from learn_core.config import get_settings
from learn_embed.constants import DIM, MODEL_NAME
from learn_embed.gate import EmbeddingBusy, EmbeddingGate

MAX_BATCH = 64
MAX_CHARS = 8_000


def error(
    code: str,
    message: str,
    status: int = 400,
    *,
    retryable: bool = False,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "retryable": retryable}},
        headers=headers,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    from learn_embed.model import get_embedder

    settings = get_settings()
    app.state.embedding_gate = EmbeddingGate(
        settings.embed_concurrency, settings.embed_queue_size
    )
    app.state.embedder = await asyncio.to_thread(get_embedder)
    yield


app = FastAPI(title="learn-embed", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    embedder = getattr(app.state, "embedder", None)
    gate = getattr(app.state, "embedding_gate", None)
    return {
        "status": "ok" if embedder else "loading",
        "model": MODEL_NAME,
        "dim": DIM,
        "queue": await gate.snapshot() if gate else None,
    }


@app.post("/v1/embeddings")
async def embeddings(request: Request) -> Any:
    try:
        payload = await request.json()
    except Exception:
        return error("INVALID_JSON", "request body is not valid JSON")

    model = payload.get("model") or MODEL_NAME
    if model not in (MODEL_NAME, "all-MiniLM-L6-v2"):
        return error("MODEL_NOT_FOUND", f"only {MODEL_NAME} is supported", 404)

    raw = payload.get("input")
    if isinstance(raw, str):
        texts = [raw]
    elif isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        texts = raw
    else:
        return error("INVALID_INPUT", "input must be a string or a list of strings")

    if not texts:
        return error("INVALID_INPUT", "input must not be empty")
    if len(texts) > MAX_BATCH:
        return error("TOO_MANY_INPUTS", f"at most {MAX_BATCH} inputs per request")
    if any(len(t) > MAX_CHARS for t in texts):
        return error("INPUT_TOO_LONG", f"each input must be at most {MAX_CHARS} characters")

    embedder = app.state.embedder
    try:
        async with app.state.embedding_gate.slot():
            vectors = await asyncio.to_thread(embedder.encode, texts)
    except EmbeddingBusy:
        return error(
            "EMBEDDING_BUSY",
            "嵌入服务正忙，请稍后重试",
            429,
            retryable=True,
            headers={"Retry-After": "2"},
        )

    return {
        "object": "list",
        "model": MODEL_NAME,
        "data": [
            {"object": "embedding", "index": i, "embedding": vec}
            for i, vec in enumerate(vectors)
        ],
        "usage": {"prompt_tokens": sum(len(t) for t in texts), "total_tokens": sum(len(t) for t in texts)},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18090)
    parser.add_argument("--log-level", default="warning")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        "learn_embed.main:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        workers=1,
    )


if __name__ == "__main__":
    main()
