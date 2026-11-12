"""学习节点（知识树上的一个可学单元）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from learn_core.db.models import Knode


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
    return list(session.scalars(stmt))


def get_node(session: Session, node_id: int) -> Knode | None:
    return session.get(Knode, node_id)


def update_node(session: Session, node_id: int, **fields: object) -> Knode | None:
    node = session.get(Knode, node_id)
    if node is None:
        return None
    allowed = {"title", "description", "stage", "est_hours", "difficulty", "mastery", "status"}
    for key, value in fields.items():
        if key not in allowed:
            raise ValueError(f"field not writable: {key}")
        setattr(node, key, value)
    session.flush()
    return node


def delete_node(session: Session, node_id: int) -> bool:
    node = session.get(Knode, node_id)
    if node is None:
        return False
    session.delete(node)
    return True
