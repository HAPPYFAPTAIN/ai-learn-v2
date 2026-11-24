import asyncio
import threading

import httpx
import pytest

from learn_embed.gate import EmbeddingGate
from learn_embed.main import app


def test_health_reports_bounded_queue_state():
    async def exercise():
        app.state.embedder = object()
        app.state.embedding_gate = EmbeddingGate(1, 2)
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://embed.test") as client:
            response = await client.get("/healthz")
        assert response.json() == {
            "status": "ok",
            "model": "sentence-transformers/all-MiniLM-L6-v2",
            "dim": 384,
            "queue": {"active": 0, "waiting": 0, "concurrency": 1, "queueSize": 2},
        }

    asyncio.run(exercise())


def test_embedding_requests_execute_queue_and_reject_when_full():
    async def exercise():
        gate = EmbeddingGate(concurrency=1, queue_size=1)
        started = threading.Event()
        release = threading.Event()
        calls = 0

        class FakeEmbedder:
            def encode(self, texts):
                nonlocal calls
                calls += 1
                started.set()
                if not release.wait(2):
                    raise RuntimeError("test embedder was not released")
                return [[0.0] * 384 for _ in texts]

        app.state.embedder = FakeEmbedder()
        app.state.embedding_gate = gate
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://embed.test") as client:
            tasks = []
            try:
                tasks.append(asyncio.create_task(client.post("/v1/embeddings", json={"input": "first"})))
                assert await asyncio.to_thread(started.wait, 1)
                tasks.append(asyncio.create_task(client.post("/v1/embeddings", json={"input": "second"})))
                for _ in range(100):
                    snapshot = await gate.snapshot()
                    if snapshot["waiting"] == 1:
                        break
                    await asyncio.sleep(0.01)
                assert snapshot == {"active": 1, "waiting": 1, "concurrency": 1, "queueSize": 1}
                busy = await client.post("/v1/embeddings", json={"input": "third"})
            finally:
                release.set()
                results = await asyncio.gather(*tasks, return_exceptions=True)

        assert busy.status_code == 429
        assert busy.headers["Retry-After"] == "2"
        assert busy.json()["error"] == {
            "code": "EMBEDDING_BUSY",
            "message": "嵌入服务正忙，请稍后重试",
            "retryable": True,
        }
        assert [response.status_code for response in results] == [200, 200]
        assert calls == 2
        assert await gate.snapshot() == {"active": 0, "waiting": 0, "concurrency": 1, "queueSize": 1}

    asyncio.run(exercise())


def test_cancelled_waiter_releases_queue_slot():
    async def exercise():
        gate = EmbeddingGate(concurrency=1, queue_size=1)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def occupy():
            async with gate.slot():
                entered.set()
                await release.wait()

        async def wait_for_slot():
            async with gate.slot():
                pass

        first = asyncio.create_task(occupy())
        await asyncio.wait_for(entered.wait(), 1)
        waiter = asyncio.create_task(wait_for_slot())
        for _ in range(100):
            snapshot = await gate.snapshot()
            if snapshot["waiting"] == 1:
                break
            await asyncio.sleep(0.01)
        assert snapshot["waiting"] == 1
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert await gate.snapshot() == {"active": 1, "waiting": 0, "concurrency": 1, "queueSize": 1}
        release.set()
        await first
        async with gate.slot():
            pass
        assert (await gate.snapshot())["active"] == 0

    asyncio.run(exercise())
