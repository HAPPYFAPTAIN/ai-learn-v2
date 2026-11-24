import asyncio
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from learn_api.job_events import JobEventBroker
from learn_api.routers import jobs


def test_shared_listener_dispatches_by_tenant_with_bounded_queues():
    async def exercise():
        ready = asyncio.Event()
        stopped = asyncio.Event()
        commands = []
        payloads = [
            "not-json",
            json.dumps({"tenantId": "other", "jobId": "job-1"}),
            json.dumps({"tenantId": "tenant-1", "jobId": "job-1"}),
            json.dumps({"tenantId": "tenant-1", "jobId": "job-1"}),
        ]

        class FakeConnection:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def execute(self, command):
                commands.append(command)

            async def notifies(self):
                ready.set()
                for payload in payloads:
                    yield SimpleNamespace(payload=payload)
                await stopped.wait()

        async def connect(dsn, **kwargs):
            assert dsn == "postgresql://test/learn"
            assert kwargs == {"autocommit": True}
            return FakeConnection()

        broker = JobEventBroker("postgresql://test/learn", connect=connect)
        matching = await broker.subscribe("tenant-1", "job-1")
        other = await broker.subscribe("other-tenant", "job-1")
        try:
            assert broker.snapshot() == {"listenerActive": True, "subscribers": 2, "jobs": 2}
            await asyncio.wait_for(ready.wait(), 1)
            assert commands == ["LISTEN learn_job_progress"]
            assert await asyncio.wait_for(matching.get(), 1) is None
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(other.get(), 0.05)
        finally:
            stopped.set()
            await broker.close()
        assert broker.snapshot() == {"listenerActive": False, "subscribers": 0, "jobs": 0}

    asyncio.run(exercise())


def test_sse_route_wakes_on_notification_and_closes_subscription(monkeypatch):
    def row(state):
        return SimpleNamespace(
            tenant_id="tenant-1",
            job_id="job-1",
            kind="lesson",
            subject="node:1",
            state=state,
            progress={"phase": state},
            error=None,
            updated_at="2026-11-23T00:00:00Z",
        )

    current = {"row": row("running")}

    class FakeSession:
        def scalars(self, query):
            return SimpleNamespace(first=lambda: current["row"])

        def scalar(self, query):
            return current["row"]

    @contextmanager
    def fake_scope():
        yield FakeSession()

    class FakeBroker:
        def __init__(self):
            self.queue = None
            self.subscribed = asyncio.Event()
            self.unsubscribed = False

        async def subscribe(self, tenant_id, job_id):
            assert (str(tenant_id), job_id) == ("tenant-1", "job-1")
            self.queue = asyncio.Queue(maxsize=1)
            self.subscribed.set()
            return self.queue

        def unsubscribe(self, tenant_id, job_id, queue):
            assert queue is self.queue
            self.unsubscribed = True

    async def exercise():
        broker = FakeBroker()
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(job_event_broker=broker))
        )
        monkeypatch.setattr(jobs, "session_scope", fake_scope)
        response = jobs.job_events(
            "job-1",
            request,
            SimpleNamespace(
                scalars=lambda query: SimpleNamespace(first=lambda: current["row"])
            ),
        )
        iterator = response.body_iterator
        try:
            first = await anext(iterator)
            waiting = asyncio.create_task(anext(iterator))
            await asyncio.wait_for(broker.subscribed.wait(), 1)
            current["row"] = row("done")
            await broker.queue.put(None)
            progress = await asyncio.wait_for(waiting, 1)
            end = await asyncio.wait_for(anext(iterator), 1)
        finally:
            await iterator.aclose()

        assert first.startswith(b"event: progress")
        assert b'"state": "running"' in first
        assert progress.startswith(b"event: progress")
        assert b'"state": "done"' in progress
        assert end == b"event: end\ndata: {}\n\n"
        assert broker.unsubscribed

    asyncio.run(exercise())
