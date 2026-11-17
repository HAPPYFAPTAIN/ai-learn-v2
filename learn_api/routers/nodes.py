"""学习节点接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from learn_api.deps import get_session
from learn_api.errors import ApiError
from learn_core.db.models import Knode
from learn_core.learning import nodes as service
from learn_core.learning import projects as project_service

from learn_api.schemas import Items, NodeOut

router = APIRouter(tags=["nodes"])

SessionDep = Annotated[Session, Depends(get_session)]


class NodeCreate(BaseModel):
    # 宁可 422 也不要静默忽略拼错的字段。
    model_config = {"extra": "forbid", "populate_by_name": True}

    code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    stage: str = ""
    est_hours: float = Field(default=1.0, gt=0, le=1000, alias="estHours")
    difficulty: float = Field(default=1.0, gt=0, le=10)


class NodeUpdate(BaseModel):
    model_config = {"extra": "forbid", "populate_by_name": True}

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    stage: str | None = None
    est_hours: float | None = Field(default=None, gt=0, le=1000, alias="estHours")
    difficulty: float | None = Field(default=None, gt=0, le=10)
    mastery: float | None = Field(default=None, ge=0, le=1)
    status: str | None = None


def _serialize(node: Knode) -> dict:
    return {
        "id": node.id,
        "projectId": node.project_id,
        "code": node.code,
        "title": node.title,
        "description": node.description,
        "stage": node.stage,
        "estHours": node.est_hours,
        "difficulty": node.difficulty,
        "mastery": node.mastery,
        "status": node.status,
        "contentVersion": node.content_version,
        "createdAt": node.created_at,
    }


@router.get("/projects/{project_id}/nodes", response_model=Items[NodeOut])
def list_nodes(project_id: int, session: SessionDep) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    return {"items": [_serialize(n) for n in service.list_nodes(session, project_id=project_id)]}


@router.post("/projects/{project_id}/nodes", status_code=status.HTTP_201_CREATED, response_model=NodeOut)
def create_node(project_id: int, payload: NodeCreate, session: SessionDep) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    node = service.create_node(
        session,
        project_id=project_id,
        code=payload.code,
        title=payload.title,
        description=payload.description,
        stage=payload.stage,
        est_hours=payload.est_hours,
        difficulty=payload.difficulty,
    )
    return _serialize(node)


@router.patch("/nodes/{node_id}", response_model=NodeOut)
def update_node(node_id: int, payload: NodeUpdate, session: SessionDep) -> dict:
    fields = payload.model_dump(exclude_unset=True)
    try:
        node = service.update_node(session, node_id, **fields)
    except ValueError as exc:
        raise ApiError("INVALID_ARGUMENT", str(exc)) from exc
    if node is None:
        raise ApiError("NOT_FOUND", "node not found")
    return _serialize(node)


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_node(node_id: int, session: SessionDep) -> Response:
    if not service.delete_node(session, node_id):
        raise ApiError("NOT_FOUND", "node not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
