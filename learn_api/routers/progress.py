"""进度记录与项目概览接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from learn_api.deps import SessionDep
from learn_api.errors import ApiError
from learn_core.learning import progress as service
from learn_core.learning import projects as project_service

from learn_api.schemas import SummaryOut

router = APIRouter(tags=["progress"])



class ProgressCreate(BaseModel):
    model_config = {"extra": "forbid", "populate_by_name": True, "allow_inf_nan": False}

    node_id: int | None = Field(default=None, alias="nodeId")
    metric: str
    value: float


@router.post("/projects/{project_id}/progress", status_code=status.HTTP_201_CREATED)
def record_progress(project_id: int, payload: ProgressCreate, session: SessionDep) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    try:
        row = service.record_progress(
            session,
            project_id=project_id,
            node_id=payload.node_id,
            metric=payload.metric,
            value=payload.value,
        )
    except ValueError as exc:
        raise ApiError("INVALID_ARGUMENT", str(exc)) from exc
    return {
        "id": row.id,
        "projectId": row.project_id,
        "nodeId": row.node_id,
        "metric": row.metric,
        "value": row.value,
        "recordedAt": row.recorded_at,
    }


@router.get("/projects/{project_id}/progress")
def list_progress(
    project_id: int,
    session: SessionDep,
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    rows = service.list_progress(session, project_id=project_id, limit=limit)
    return {
        "items": [
            {
                "id": r.id,
                "nodeId": r.node_id,
                "metric": r.metric,
                "value": r.value,
                "recordedAt": r.recorded_at,
            }
            for r in rows
        ]
    }


@router.get("/projects/{project_id}/summary", response_model=SummaryOut)
def summary(project_id: int, session: SessionDep) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    return service.project_summary(session, project_id=project_id)
