"""僵死任务回收。

Procrastinate 只提供查询接口：worker 进程被 kill 后，它名下的 `doing`
任务不会自动回到队列。这里补上回收逻辑，由运维定时器每分钟调用一次，
或者由独立 maintenance 进程轮询。

判定依据是 worker 心跳：心跳超过 `seconds_since_heartbeat` 的 worker
视为已死，其名下 doing 任务整体重排。
"""

from __future__ import annotations

import asyncio

from learn_core.jobs.app import app


async def _reap(seconds_since_heartbeat: float, queue: str | None) -> list[int]:
    async with app.open_async():
        stalled = list(
            await app.job_manager.get_stalled_jobs(
                seconds_since_heartbeat=seconds_since_heartbeat, queue=queue
            )
        )
        reaped: list[int] = []
        for job in stalled:
            await app.job_manager.retry_job(job)
            reaped.append(job.id)
        return reaped


def reap_stalled_jobs(seconds_since_heartbeat: float = 60.0, queue: str | None = None) -> list[int]:
    """同步入口，返回被重排的任务 id。"""
    return asyncio.run(_reap(seconds_since_heartbeat, queue))
