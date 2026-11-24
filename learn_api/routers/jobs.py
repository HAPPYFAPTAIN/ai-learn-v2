"""任务进度与事件流。

长操作返回 202 + jobId，前端订阅 ``/jobs/{id}/events``。
每个 API 进程通过一个 PostgreSQL LISTEN 连接接收入口共享通知，
收到通知后再按租户读取最新任务；15 秒轮询仅用于监听断线兜底。
"""

from __future__ import annotations

import asyncio
import anyio
import json
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, Request
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
FALLBACK_SECONDS = 15.0


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
def job_events(job_id: str, request: Request, session: SessionDep) -> StreamingResponse:
    row = session.scalars(
        select(JobProgress).where(JobProgress.job_id == job_id)
    ).first()
    if row is None:
        raise ApiError("NOT_FOUND", "job not found")
    snapshot = _serialize(row)
    tenant_id = row.tenant_id
    broker = request.app.state.job_event_broker

    def poll():
        with tenant_context(tenant_id), session_scope() as scoped:
            current = scoped.scalar(select(JobProgress).where(JobProgress.job_id == job_id))
            return _serialize(current) if current else None

    def event(name: str, payload: dict | None = None) -> bytes:
        data = "{}" if payload is None else json.dumps(payload, ensure_ascii=False, default=str)
        return f"event: {name}\ndata: {data}\n\n".encode()

    async def stream() -> AsyncIterator[bytes]:
        last = snapshot
        yield event("progress", snapshot)
        if snapshot["state"] in TERMINAL_STATES:
            yield event("end")
            return
        queue = await broker.subscribe(tenant_id, job_id)
        try:
            while True:
                payload = await anyio.to_thread.run_sync(poll)
                if payload is None:
                    yield event("gone")
                    return
                if payload != last:
                    yield event("progress", payload)
                    last = payload
                    if payload["state"] in TERMINAL_STATES:
                        yield event("end")
                        return
                try:
                    await asyncio.wait_for(queue.get(), timeout=FALLBACK_SECONDS)
                except TimeoutError:
                    yield b": keep-alive\n\n"
        finally:
            broker.unsubscribe(tenant_id, job_id, queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
