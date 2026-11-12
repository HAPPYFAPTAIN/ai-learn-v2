"""阶段 0 的探针任务。

只用于验证队列语义（去重、串行、心跳回收），不承载业务逻辑；
业务任务在阶段 1 随各 service 一起落地。
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from sqlalchemy import text

from learn_core.db.engine import get_engine, session_scope
from learn_core.tenancy.context import tenant_context
from learn_core.jobs.app import app, channel_lock


def _record(kind: str, tenant: str, event: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO phase0_trace (kind, tenant, event, ts) "
                "VALUES (:kind, :tenant, :event, :ts)"
            ),
            {"kind": kind, "tenant": tenant, "event": event, "ts": datetime.now(timezone.utc)},
        )


@app.task(name="learn_core.jobs.tasks.probe", queue="phase0", retry=1)
def probe(tenant: str, tag: str, seconds: float = 0.4) -> str:
    _record("probe", tenant, f"start:{tag}")
    time.sleep(seconds)
    _record("probe", tenant, f"end:{tag}")
    return tag


@app.task(name="learn_core.jobs.tasks.tenant_probe", queue="cpu")
def tenant_probe(tenant: str, channel: str, tag: str, seconds: float = 0.4) -> str:
    """带 lock=租户:通道 的任务，同一租户同一通道必须串行。"""
    _record("tenant_probe", tenant, f"start:{tag}")
    time.sleep(seconds)
    _record("tenant_probe", tenant, f"end:{tag}")
    return tag


__all__ = ["probe", "tenant_probe", "channel_lock"]


def _set_job(tenant_id: "UUID", job_id: str, **fields) -> None:
    """更新 job_progress；worker 里没有请求上下文，得自己建租户上下文。"""
    from uuid import UUID  # noqa: F401

    from sqlalchemy import text as sql_text

    from learn_core.db.engine import session_scope
    from learn_core.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        with session_scope() as session:
            session.execute(
                sql_text(
                    """
                    UPDATE job_progress
                       SET state = COALESCE(:state, state),
                           progress = COALESCE(CAST(:progress AS jsonb), progress),
                           error = :error,
                           updated_at = now()
                     WHERE job_id = :job_id
                    """
                ),
                {
                    "job_id": job_id,
                    "state": fields.get("state"),
                    "progress": json.dumps(fields["progress"]) if "progress" in fields else None,
                    "error": fields.get("error"),
                },
            )


@app.task(name="learn_core.jobs.tasks.index_source", queue="io", retry=0)
def index_source_task(
    tenant: str,
    job_id: str,
    source_id: str,
    text: str,
    index_id: str = "material",
) -> int:
    """把一份资料索引成块。同一租户的索引任务串行，避免一起抢嵌入服务。"""
    from uuid import UUID

    from learn_core.rag.embedding import EmbeddingClient
    from learn_core.rag.index import index_source

    tenant_id = UUID(tenant)
    _set_job(tenant_id, job_id, state="running", progress={"done": 0, "total": 0})

    def on_progress(done: int, total: int) -> None:
        _set_job(tenant_id, job_id, progress={"done": done, "total": total})

    try:
        with tenant_context(tenant_id):
            with session_scope() as session:
                count = index_source(
                    session,
                    source_id=source_id,
                    text=text,
                    embedder=EmbeddingClient(),
                    index_id=index_id,
                    progress=on_progress,
                )
    except Exception as exc:  # noqa: BLE001 - 失败也要让前端看到原因
        _set_job(tenant_id, job_id, state="failed", error=f"{exc.__class__.__name__}: {exc}"[:500])
        raise

    _set_job(tenant_id, job_id, state="done", progress={"done": count, "total": count})
    return count


__all__ = ["probe", "tenant_probe", "index_source_task", "channel_lock"]
