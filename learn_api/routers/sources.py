"""资料索引：提交文本 → 202 + jobId，进度走 /jobs/{id}/events。"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from learn_api.deps import get_session, get_tenant_id
from learn_api.errors import ApiError
from learn_core.db.models import JobProgress
from learn_core.jobs import enqueue
from learn_core.learning import projects as project_service

router = APIRouter(prefix="/projects", tags=["sources"])


class SourceCreate(BaseModel):
    source_id: str = Field(min_length=1, max_length=64, alias="sourceId")
    text: str = Field(min_length=1)
    index_id: str = Field(default="material", max_length=64, alias="indexId")

    model_config = {"populate_by_name": True}


@router.post("/{project_id}/sources", status_code=status.HTTP_202_ACCEPTED)
def create_source(
    project_id: int,
    payload: SourceCreate,
    response: Response,
    tenant_id=Depends(get_tenant_id),
    session: Session = Depends(get_session),
) -> dict:
    project_service.get_project(session, project_id)  # 不存在直接 404，不建无主任务

    job_id = f"idx-{uuid4().hex[:12]}"
    session.add(
        JobProgress(
            job_id=job_id,
            kind="index",
            subject=payload.source_id,
            state="queued",
            progress={"done": 0, "total": 0},
        )
    )
    session.flush()

    try:
        enqueue.enqueue_index(
            tenant_id=tenant_id,
            job_id=job_id,
            source_id=payload.source_id,
            text=payload.text,
            index_id=payload.index_id,
        )
    except Exception as exc:  # noqa: BLE001 - 队列不可用时不能留下假任务
        session.rollback()
        raise ApiError("INTERNAL", f"queue unavailable: {exc.__class__.__name__}") from exc

    response.headers["Location"] = f"/official/learn-everything/api/v2/jobs/{job_id}"
    return {"jobId": job_id, "state": "queued"}
