"""学习项目的读写。

约定：业务 service 的第一个参数是 ``Session``，由调用方负责事务边界。
这样页面、API、任务队列可以复用同一套逻辑，也方便测试。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from learn_core.db.models import Project


def create_project(
    session: Session,
    *,
    title: str,
    topic: str = "",
    background: str = "",
    goal: str = "",
    weekly_hours: float = 10.0,
) -> Project:
    project = Project(
        title=title.strip(),
        topic=topic.strip(),
        background=background.strip(),
        goal=goal.strip(),
        weekly_hours=weekly_hours,
    )
    session.add(project)
    session.flush()
    return project


def list_projects(session: Session, *, limit: int = 50, offset: int = 0) -> list[Project]:
    stmt = (
        select(Project)
        .order_by(Project.updated_at.desc(), Project.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(stmt))


def get_project(session: Session, project_id: int) -> Project | None:
    return session.get(Project, project_id)


def update_project(session: Session, project_id: int, **fields: object) -> Project | None:
    project = session.get(Project, project_id)
    if project is None:
        return None
    allowed = {"title", "topic", "background", "goal", "weekly_hours", "status"}
    for key, value in fields.items():
        if key not in allowed:
            raise ValueError(f"field not writable: {key}")
        setattr(project, key, value)
    session.flush()
    return project


def delete_project(session: Session, project_id: int) -> bool:
    project = session.get(Project, project_id)
    if project is None:
        return False
    from sqlalchemy import delete
    from learn_core.db.ktem import KtemConversation
    session.execute(delete(KtemConversation).where(KtemConversation.id.in_([f'learn-project-{project_id}',f'learn-coach-{project_id}'])))
    session.delete(project)
    return True
