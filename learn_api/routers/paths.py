"""学习路径接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from learn_api.deps import get_session
from learn_api.errors import ApiError
from learn_core.learning import paths as service
from learn_core.learning import projects as project_service

from learn_api.schemas import PlanOut

router = APIRouter(prefix="/projects", tags=["paths"])

SessionDep = Annotated[Session, Depends(get_session)]


class PlanRequest(BaseModel):
    model_config = {"extra": "forbid", "populate_by_name": True}

    weeks: int = Field(default=8, ge=1, le=52)
    hours_per_week: float = Field(default=10.0, gt=0, le=80, alias="hoursPerWeek")


@router.post("/{project_id}/path", response_model=PlanOut)
def build_path(project_id: int, payload: PlanRequest, session: SessionDep) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    return service.build_plan(
        session,
        project_id=project_id,
        weeks=payload.weeks,
        hours_per_week=payload.hours_per_week,
    )
