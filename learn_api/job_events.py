"""One PostgreSQL listener per API process, shared by all job event streams."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from typing import Awaitable, Callable

import psycopg

from learn_core.db.engine import JOB_NOTIFY_CHANNEL

log = logging.getLogger("learn_api.job_events")

Connect = Callable[..., Awaitable[object]]


class JobEventBroker:
    def __init__(
        self,
        dsn: str,
        *,
        connect: Connect | None = None,
        retry_max: float = 5.0,
    ) -> None:
        self._dsn = dsn
        self._connect = connect or psycopg.AsyncConnection.connect
        self._retry_max = retry_max
        self._subscribers: dict[tuple[str, str], set[asyncio.Queue[None]]] = {}
        self._task: asyncio.Task | None = None
        self._closed = False

    async def subscribe(self, tenant_id, job_id: str) -> asyncio.Queue[None]:
        if self._closed:
            raise RuntimeError("job event broker is closed")
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._listen(), name="learn-job-events")
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._subscribers.setdefault((str(tenant_id), str(job_id)), set()).add(queue)
        return queue

    def unsubscribe(self, tenant_id, job_id: str, queue: asyncio.Queue[None]) -> None:
        key = (str(tenant_id), str(job_id))
        queues = self._subscribers.get(key)
        if not queues:
            return
        queues.discard(queue)
        if not queues:
            self._subscribers.pop(key, None)

    def snapshot(self) -> dict:
        return {
            "listenerActive": bool(self._task and not self._task.done()),
            "subscribers": sum(len(queues) for queues in self._subscribers.values()),
            "jobs": len(self._subscribers),
        }

    async def close(self) -> None:
        self._closed = True
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._subscribers.clear()

    def _publish(self, payload: str) -> None:
        try:
            data = json.loads(payload)
            tenant_id = data["tenantId"]
            job_id = data["jobId"]
        except (TypeError, ValueError, KeyError):
            return
        if not isinstance(tenant_id, str) or not isinstance(job_id, str):
            return
        for queue in self._subscribers.get((tenant_id, job_id), ()):
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    async def _listen(self) -> None:
        retry = 0.5
        while not self._closed:
            try:
                async with await self._connect(self._dsn, autocommit=True) as connection:
                    await connection.execute(f"LISTEN {JOB_NOTIFY_CHANNEL}")
                    retry = 0.5
                    async for notification in connection.notifies():
                        if self._closed:
                            return
                        self._publish(notification.payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._closed:
                    return
                log.warning(
                    "job_event_listener_reconnecting error=%s",
                    exc.__class__.__name__,
                )
                await asyncio.sleep(retry)
                retry = min(self._retry_max, retry * 2)
