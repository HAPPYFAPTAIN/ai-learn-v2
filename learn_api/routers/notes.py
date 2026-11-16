"""笔记与任务接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from learn_api.deps import get_session
from learn_api.errors import ApiError
from learn_core.learning import notes as service
from learn_core.learning import projects as project_service

from learn_api.schemas import Items, NoteOut, TaskOut

router = APIRouter(tags=["notes"])

SessionDep = Annotated[Session, Depends(get_session)]


class NoteCreate(BaseModel):
    model_config = {"extra": "forbid", "populate_by_name": True}

    node_id: int = Field(alias="nodeId")
    content: str = Field(min_length=1)
    selection: str = ""


class NoteUpdate(BaseModel):
    model_config = {"extra": "forbid", "populate_by_name": True}

    content: str | None = Field(default=None, min_length=1)
    selection: str | None = None


class TaskCreate(BaseModel):
    model_config = {"extra": "forbid", "populate_by_name": True}

    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    task_type: str = Field(default="practice", alias="taskType")
    node_id: int | None = Field(default=None, alias="nodeId")


class TaskUpdate(BaseModel):
    model_config = {"extra": "forbid", "populate_by_name": True}

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = None
    output: str | None = None


def _note(note) -> dict:
    return {
        "id": note.id,
        "projectId": note.project_id,
        "nodeId": note.node_id,
        "content": note.content,
        "selection": note.selection,
        "updatedAt": note.updated_at,
    }


def _task(task) -> dict:
    return {
        "id": task.id,
        "projectId": task.project_id,
        "nodeId": task.node_id,
        "title": task.title,
        "description": task.description,
        "taskType": task.task_type,
        "status": task.status,
        "output": task.output,
    }


@router.post("/projects/{project_id}/notes", status_code=status.HTTP_201_CREATED, response_model=NoteOut)
def create_note(project_id: int, payload: NoteCreate, session: SessionDep) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    note = service.create_note(
        session,
        project_id=project_id,
        node_id=payload.node_id,
        content=payload.content,
        selection=payload.selection,
    )
    return _note(note)


@router.get("/projects/{project_id}/notes", response_model=Items[NoteOut])
def list_notes(project_id: int, session: SessionDep, nodeId: int | None = None) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    return {"items": [_note(n) for n in service.list_notes(session, project_id=project_id, node_id=nodeId)]}


@router.patch("/notes/{note_id}", response_model=NoteOut)
def update_note(note_id: int, payload: NoteUpdate, session: SessionDep) -> dict:
    fields = payload.model_dump(exclude_none=True)
    note = service.update_note(session, note_id, **fields)
    if note is None:
        raise ApiError("NOT_FOUND", "note not found")
    return _note(note)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: int, session: SessionDep) -> Response:
    if not service.delete_note(session, note_id):
        raise ApiError("NOT_FOUND", "note not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/projects/{project_id}/tasks", status_code=status.HTTP_201_CREATED, response_model=TaskOut)
def create_task(project_id: int, payload: TaskCreate, session: SessionDep) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    try:
        task = service.create_task(
            session,
            project_id=project_id,
            title=payload.title,
            description=payload.description,
            task_type=payload.task_type,
            node_id=payload.node_id,
        )
    except ValueError as exc:
        raise ApiError("INVALID_ARGUMENT", str(exc)) from exc
    return _task(task)


@router.get("/projects/{project_id}/tasks", response_model=Items[TaskOut])
def list_tasks(
    project_id: int,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status"),
) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    tasks = service.list_tasks(session, project_id=project_id, status=status_filter)
    return {"items": [_task(t) for t in tasks]}


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, payload: TaskUpdate, session: SessionDep) -> dict:
    fields = payload.model_dump(exclude_none=True)
    try:
        task = service.update_task(session, task_id, **fields)
    except ValueError as exc:
        raise ApiError("INVALID_ARGUMENT", str(exc)) from exc
    if task is None:
        raise ApiError("NOT_FOUND", "task not found")
    return _task(task)
