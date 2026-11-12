"""把任务丢进队列的统一入口。

API 只负责建 job_progress 行和 defer，执行细节在 tasks 里；
这样测试可以 monkeypatch 这一个函数，不用起 worker。
"""

from __future__ import annotations

from uuid import UUID


def enqueue_index(
    *,
    tenant_id: UUID,
    job_id: str,
    source_id: str,
    text: str,
    index_id: str = "material",
) -> str:
    from learn_core.jobs.app import app, channel_lock
    from learn_core.jobs.tasks import index_source_task

    with app.open():
        task = index_source_task.configure(
            lock=channel_lock(str(tenant_id), "io"),
            queueing_lock=f"index:{source_id}",
            queue="io",
        )
        job = task.defer(
            tenant=str(tenant_id),
            job_id=job_id,
            source_id=source_id,
            text=text,
            index_id=index_id,
        )
    return str(job)
