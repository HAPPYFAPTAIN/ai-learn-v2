"""把任务丢进队列的统一入口。

API 只负责建 job_progress 行和 defer，执行细节在 tasks 里；
这样测试可以 monkeypatch 这一个函数，不用起 worker。
"""

from __future__ import annotations

from uuid import UUID
import json

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session


def enqueue_index(
    session: Session,
    *,
    tenant_id: UUID,
    job_id: str,
    source_id: str,
    text: str,
    index_id: str = "material",
) -> str:
    job = session.scalar(sql_text("""
        SELECT procrastinate_defer_jobs_v1(ARRAY[
          ROW('io', 'learn_core.jobs.tasks.index_source', 0,
              :lock, :dedupe, CAST(:args AS jsonb), NULL::timestamptz)
        ]::procrastinate_job_to_defer_v1[])
    """), {
        "lock": f"{tenant_id}:io",
        "dedupe": f"{tenant_id}:index:{index_id}:{source_id}",
        "args": json.dumps({"tenant": str(tenant_id), "job_id": job_id,
                            "source_id": source_id, "text": text, "index_id": index_id}),
    })
    return str(job)
