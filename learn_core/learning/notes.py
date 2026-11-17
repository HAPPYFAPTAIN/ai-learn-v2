"""笔记与学习任务。

笔记挂在节点上（node_id 必填），任务可以不挂节点——都是项目内的附属物，
所以查询一律按项目 + 可选节点过滤。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from learn_core.db.models import Note, Task
from learn_core.learning.ownership import require_project_node


# ------------------------------------------------------------------ 笔记


def create_note(
    session: Session,
    *,
    project_id: int,
    node_id: int,
    content: str,
    selection: str = "",
) -> Note:
    require_project_node(session, project_id=project_id, node_id=node_id)
    note = Note(
        project_id=project_id,
        node_id=node_id,
        content=content,
        selection=selection,
    )
    session.add(note)
    session.flush()
    return note


def list_notes(session: Session, *, project_id: int, node_id: int | None = None) -> list[Note]:
    stmt = select(Note).where(Note.project_id == project_id)
    if node_id is not None:
        stmt = stmt.where(Note.node_id == node_id)
    stmt = stmt.order_by(Note.updated_at.desc(), Note.id.desc())
    return list(session.scalars(stmt))


def get_note(session: Session, note_id: int) -> Note | None:
    return session.get(Note, note_id)


def update_note(session: Session, note_id: int, **fields: object) -> Note | None:
    note = session.get(Note, note_id)
    if note is None:
        return None
    for key, value in fields.items():
        if key not in {"content", "selection"}:
            raise ValueError(f"field not writable: {key}")
        setattr(note, key, value)
    note.updated_at = datetime.now(timezone.utc)
    session.flush()
    return note


def delete_note(session: Session, note_id: int) -> bool:
    note = session.get(Note, note_id)
    if note is None:
        return False
    session.delete(note)
    session.flush()
    return True


# ------------------------------------------------------------------ 任务

TASK_STATUSES = {"pending", "running", "done", "skipped"}
TASK_TYPES = {"practice", "reading", "review", "project", "custom"}


def create_task(
    session: Session,
    *,
    project_id: int,
    title: str,
    description: str = "",
    task_type: str = "practice",
    node_id: int | None = None,
) -> Task:
    if task_type not in TASK_TYPES:
        raise ValueError(f"unknown task_type: {task_type}")
    require_project_node(session, project_id=project_id, node_id=node_id)
    task = Task(
        project_id=project_id,
        node_id=node_id,
        title=title.strip(),
        description=description,
        task_type=task_type,
    )
    session.add(task)
    session.flush()
    return task


def list_tasks(session: Session, *, project_id: int, status: str | None = None) -> list[Task]:
    stmt = select(Task).where(Task.project_id == project_id)
    if status:
        stmt = stmt.where(Task.status == status)
    stmt = stmt.order_by(Task.status, Task.id)
    return list(session.scalars(stmt))


def update_task(session: Session, task_id: int, **fields: object) -> Task | None:
    task = session.get(Task, task_id)
    if task is None:
        return None
    if "status" in fields and fields["status"] not in TASK_STATUSES:
        raise ValueError(f"unknown status: {fields['status']}")
    for key, value in fields.items():
        if key not in {"title", "description", "status", "output"}:
            raise ValueError(f"field not writable: {key}")
        setattr(task, key, value)
    session.flush()
    return task
