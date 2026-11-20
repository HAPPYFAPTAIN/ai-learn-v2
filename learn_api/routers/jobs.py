"""任务进度与事件流。

长操作返回 202 + jobId，前端订阅 ``/jobs/{id}/events``。
事件源是 ``job_progress`` 表，所以多进程部署不需要粘性会话；
代价是每个订阅者 1 秒轮询一次，等规模起来再换 LISTEN/NOTIFY。
"""

from __future__ import annotations

import asyncio
import anyio
import json
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from learn_api.deps import SessionDep
from learn_api.errors import ApiError
from learn_core.db.engine import session_scope
from learn_core.db.models import JobProgress
from learn_core.tenancy.context import tenant_context

from learn_api.schemas import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])

TERMINAL_STATES = {"done", "failed", "cancelled"}
POLL_SECONDS = 1.0


def _serialize(row: JobProgress) -> dict:
    return {
        "jobId": row.job_id,
        "kind": row.kind,
        "subject": row.subject,
        "state": row.state,
        "progress": {key: value for key, value in row.progress.items()
                     if key not in {"prepared", "gatewayCallPending"}},
        "error": row.error,
        "updatedAt": row.updated_at,
    }




@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, session: SessionDep) -> dict:
    row = session.scalars(
        select(JobProgress).where(JobProgress.job_id == job_id)
    ).first()
    if row is None:
        raise ApiError("NOT_FOUND", "job not found")
    return _serialize(row)


@router.get("/{job_id}/events")
def job_events(job_id: str, session: SessionDep) -> StreamingResponse:
    row = session.scalars(
        select(JobProgress).where(JobProgress.job_id == job_id)
    ).first()
    if row is None:
        raise ApiError("NOT_FOUND", "job not found")
    snapshot = _serialize(row)
    tenant_id = row.tenant_id

    def poll():
        with tenant_context(tenant_id), session_scope() as scoped:
            current = scoped.scalar(select(JobProgress).where(JobProgress.job_id == job_id))
            return _serialize(current) if current else None

    async def stream() -> AsyncIterator[bytes]:
        last = snapshot
        if snapshot["state"] in TERMINAL_STATES:
            yield b"event: end\ndata: {}\n\n"
            return
        while True:
            payload = await anyio.to_thread.run_sync(poll)
            if payload is None:
                yield b"event: gone\ndata: {}\n\n"
                return
            if payload != last:
                yield (
                    "event: progress\ndata: "
                    + json.dumps(payload, ensure_ascii=False, default=str)
                    + "\n\n"
                ).encode()
                last = payload
                if payload["state"] in TERMINAL_STATES:
                    yield b"event: end\ndata: {}\n\n"
                    return
            await asyncio.sleep(POLL_SECONDS)

    yield_snapshot = (
        "event: progress\ndata: " + json.dumps(snapshot, ensure_ascii=False, default=str) + "\n\n"
    ).encode()
    return StreamingResponse(
        _prepend(yield_snapshot, stream()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _prepend(first: bytes, rest: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    yield first
    async for chunk in rest:
        yield chunk
