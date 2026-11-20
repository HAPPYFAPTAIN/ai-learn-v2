"""学习项目 CRUD。"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from learn_api.deps import SessionDep
from learn_api.errors import ApiError
from learn_core.db.models import Project
from learn_core.learning import projects as service
from learn_core.learning.creation import create_once, lookup_creation

from learn_api.schemas import NonNullPatch, ProjectCreated, ProjectList, ProjectOut
from learn_core.learning.generation import submit_generation, GenerationConflict

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    model_config = {"allow_inf_nan": False}
    title: str = Field(min_length=1, max_length=200)
    topic: str = Field(default="", max_length=200)
    background: str = Field(default="", max_length=5000)
    goal: str = Field(default="", max_length=5000)
    weekly_hours: float = Field(default=10.0, gt=0, le=168, alias="weeklyHours")
    generate_roadmap: bool = Field(default=False, alias="generateRoadmap")
    request_id: UUID | None = Field(default=None, alias="requestId")


class ProjectUpdate(NonNullPatch):
    model_config = {"allow_inf_nan": False}
    title: str | None = Field(default=None, min_length=1, max_length=200)
    topic: str | None = Field(default=None, max_length=200)
    background: str | None = Field(default=None, max_length=5000)
    goal: str | None = Field(default=None, max_length=5000)
    weekly_hours: float | None = Field(default=None, gt=0, le=168, alias="weeklyHours")
    status: Literal["active", "paused", "completed", "archived"] | None = None


def _serialize(project: Project) -> dict:
    return {
        "id": project.id,
        "title": project.title,
        "topic": project.topic,
        "background": project.background,
        "goal": project.goal,
        "weeklyHours": project.weekly_hours,
        "status": project.status,
        "createdAt": project.created_at,
        "updatedAt": project.updated_at,
    }




@router.get("", response_model=ProjectList)
def list_projects(
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    items = service.list_projects(session, limit=limit, offset=offset)
    return {"items": [_serialize(p) for p in items], "limit": limit, "offset": offset}


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProjectCreated)
def create_project(payload: ProjectCreate, session: SessionDep) -> dict:
    def create() -> dict:
        project = service.create_project(
            session,
            title=payload.title,
            topic=payload.topic,
            background=payload.background,
            goal=payload.goal,
            weekly_hours=payload.weekly_hours,
        )
        result = _serialize(project)
        if payload.generate_roadmap:
            try:
                job = submit_generation(session, project_id=project.id, kind="roadmap")
            except GenerationConflict as exc:
                raise ApiError("CONFLICT", str(exc)) from exc
            result["generation"] = {"jobId": job.job_id, "state": job.state}
        return result

    return create_once(session, operation="project", request_id=payload.request_id,
        payload=payload.model_dump(mode="json", exclude={"request_id"}), create=create)


@router.get("/creation-requests/{request_id}", response_model=ProjectCreated | None)
def get_project_creation(request_id: UUID, session: SessionDep) -> dict | None:
    return lookup_creation(session, operation="project", request_id=request_id)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, session: SessionDep) -> dict:
    project = service.get_project(session, project_id)
    if project is None:
        raise ApiError("NOT_FOUND", "project not found")
    return _serialize(project)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, payload: ProjectUpdate, session: SessionDep) -> dict:
    fields = payload.model_dump(exclude_unset=True)
    try:
        project = service.update_project(session, project_id, **fields)
    except ValueError as exc:
        raise ApiError("INVALID_ARGUMENT", str(exc)) from exc
    if project is None:
        raise ApiError("NOT_FOUND", "project not found")
    return _serialize(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, session: SessionDep) -> Response:
    if not service.delete_project(session, project_id):
        raise ApiError("NOT_FOUND", "project not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{project_id}/roadmap", status_code=status.HTTP_204_NO_CONTENT)
def delete_roadmap(project_id: int, session: SessionDep) -> Response:
    from learn_core.learning.nodes import delete_roadmap as clear_roadmap

    try:
        found = clear_roadmap(session, project_id)
    except GenerationConflict as exc:
        raise ApiError("JOB_RUNNING", str(exc)) from exc
    if not found:
        raise ApiError("NOT_FOUND", "学习计划不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
