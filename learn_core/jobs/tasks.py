"""持久化学习、问答、润色与资料任务，以及独立的队列语义探针。"""

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


@app.task(name='learn_core.jobs.tasks.index_material', queue='io', retry=0)
def index_material_task(tenant: str, job_id: str, file_id: str):
    from uuid import UUID
    from sqlalchemy import select
    from learn_core.db.models import StoredFile, JobProgress
    from learn_core.storage import files as storage
    from learn_core.storage.parsing import extract_text
    from learn_core.rag.chunking import split_text
    from learn_core.rag.embedding import EmbeddingClient
    from learn_core.rag.store import delete_source, upsert_chunks
    from learn_core.learning.materials import storage_lock
    tid = UUID(tenant)
    with tenant_context(tid):
        try:
            with session_scope() as session:
                row = session.get(StoredFile, UUID(file_id))
                job = session.scalar(select(JobProgress).where(JobProgress.job_id == job_id).with_for_update())
                if row is None or job is None or job.state in {'cancelled','done'}:
                    return
                storage_key, name = row.storage_key, row.original_name
                job.state, job.error = 'running', None
            with storage.open_file(storage_key) as source:
                data = source.read(50 * 1024 * 1024 + 1)
            if len(data) > 50 * 1024 * 1024:
                raise ValueError('文件过大，请拆分后上传')
            parts = split_text(extract_text(data, name))
            vectors = []
            # Neither parsing nor embedding keeps a business DB connection open.
            with EmbeddingClient() as embedder:
                for start in range(0, len(parts), 16):
                    vectors.extend(embedder.embed(parts[start:start+16]))
                    _set_job(tid, job_id, progress={'done':min(start+16,len(parts)), 'total':len(parts)})
            with session_scope() as session:
                storage_lock(session)
                row = session.get(StoredFile, UUID(file_id))
                job = session.scalar(select(JobProgress).where(JobProgress.job_id == job_id).with_for_update())
                if row is None or job is None or job.state == 'cancelled':
                    return
                delete_source(session, index_id='material', source_id=file_id)
                count = upsert_chunks(session, index_id='material', source_id=file_id, chunks=parts, vectors=vectors, metadata={'name':name})
                job.state, job.error = 'done', None
                job.progress = {'done':count,'total':count}
                job.updated_at = datetime.now(timezone.utc)
        except Exception as exc:
            with session_scope() as session:
                job = session.scalar(select(JobProgress).where(JobProgress.job_id == job_id).with_for_update())
                if job and job.state not in {'cancelled','done'}:
                    job.state = 'failed'
                    job.error = str(exc) if isinstance(exc, ValueError) else '资料处理失败，请重试；若持续失败，请联系管理员检查解析和索引服务'
                    job.updated_at = datetime.now(timezone.utc)


@app.task(name='learn_core.jobs.tasks.purge_material', queue='io', retry=3)
def purge_material_task(tenant: str, storage_key: str):
    from uuid import UUID
    from sqlalchemy import select
    from learn_core.db.models import StoredFile
    from learn_core.storage import files as storage
    from learn_core.learning.materials import storage_lock
    with tenant_context(UUID(tenant)), session_scope() as session:
        storage_lock(session)
        # A same-content reupload may reuse the key before cleanup runs.
        if session.scalar(select(StoredFile.id).where(StoredFile.storage_key == storage_key)) is None:
            storage.delete(storage_key)


@app.task(name='learn_core.jobs.tasks.answer_question',queue='llm',retry=0)
def answer_question_task(tenant:str,job_id:str):
    from learn_core.learning.conversations import run_answer
    run_answer(tenant=tenant,job_id=job_id)


@app.task(name='learn_core.jobs.tasks.polish_text',queue='llm',retry=0)
def polish_text_task(tenant:str,job_id:str):
    from learn_core.learning.polish import run_polish
    run_polish(tenant=tenant,job_id=job_id)


from procrastinate.retry import BaseRetryStrategy, RetryDecision
from learn_core.learning.generation import RetryableGenerationError, run_generation


class LearningGenerationRetry(BaseRetryStrategy):
    def get_retry_decision(self, *, exception, job):
        if isinstance(exception, RetryableGenerationError) and job.attempts < 2:
            return RetryDecision(retry_in={"seconds": exception.delay})
        return None


@app.task(name="learn_core.jobs.tasks.generate_learning", queue="llm",
          pass_context=True, retry=LearningGenerationRetry())
def generate_learning_task(context, tenant: str, job_id: str) -> None:
    run_generation(tenant=tenant, job_id=job_id, attempt=context.job.attempts)
