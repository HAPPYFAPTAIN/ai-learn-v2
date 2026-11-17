"""学习节点（知识树上的一个可学单元）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from learn_core.db.models import Knode, Project
from learn_core.learning.generation import course_code_sort_key


def create_node(
    session: Session,
    *,
    project_id: int,
    code: str,
    title: str,
    description: str = "",
    stage: str = "",
    est_hours: float = 1.0,
    difficulty: float = 1.0,
) -> Knode:
    if session.scalar(select(Project).where(Project.id == project_id).with_for_update()) is None:
        raise ValueError("project not found")
    node = Knode(
        project_id=project_id,
        code=code.strip(),
        title=title.strip(),
        description=description,
        stage=stage,
        est_hours=est_hours,
        difficulty=difficulty,
    )
    session.add(node)
    session.flush()
    return node


def list_nodes(session: Session, *, project_id: int) -> list[Knode]:
    stmt = (
        select(Knode)
        .where(Knode.project_id == project_id)
        .order_by(Knode.stage, Knode.code, Knode.id)
    )
    return sorted(session.scalars(stmt), key=lambda n: course_code_sort_key(n.code))


def get_node(session: Session, node_id: int) -> Knode | None:
    return session.get(Knode, node_id)


def update_node(session: Session, node_id: int, **fields: object) -> Knode | None:
    node = session.scalar(select(Knode).where(Knode.id == node_id).with_for_update())
    if node is None:
        return None
    allowed = {"title", "description", "stage", "est_hours", "difficulty", "mastery", "status"}
    for key, value in fields.items():
        if key not in allowed:
            raise ValueError(f"field not writable: {key}")
        setattr(node, key, value)
    if any(k in fields for k in ("title", "description", "stage", "est_hours", "difficulty")):
        node.content_version += 1
    session.flush()
    return node


def delete_node(session: Session, node_id: int) -> bool:
    node = session.get(Knode, node_id)
    if node is None:
        return False
    session.delete(node)
    return True
