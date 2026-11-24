from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager


class EmbeddingBusy(RuntimeError):
    pass


class EmbeddingGate:
    def __init__(self, concurrency: int, queue_size: int) -> None:
        if concurrency < 1 or queue_size < 0:
            raise ValueError("invalid embedding admission limits")
        self.concurrency = concurrency
        self.queue_size = queue_size
        self._condition = asyncio.Condition()
        self._active = 0
        self._waiting = 0

    @asynccontextmanager
    async def slot(self):
        queued = False
        async with self._condition:
            if self._active >= self.concurrency:
                if self._waiting >= self.queue_size:
                    raise EmbeddingBusy("embedding queue is full")
                self._waiting += 1
                queued = True
            else:
                self._active += 1
        if queued:
            try:
                async with self._condition:
                    await self._condition.wait_for(
                        lambda: self._active < self.concurrency
                    )
                    self._waiting -= 1
                    self._active += 1
            except BaseException:
                async with self._condition:
                    self._waiting -= 1
                    self._condition.notify()
                raise
        try:
            yield
        finally:
            async with self._condition:
                self._active -= 1
                self._condition.notify()

    async def snapshot(self) -> dict[str, int]:
        async with self._condition:
            return {
                "active": self._active,
                "waiting": self._waiting,
                "concurrency": self.concurrency,
                "queueSize": self.queue_size,
            }
