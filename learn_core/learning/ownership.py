"""Validate learning relationships in the current tenant before writing them."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from learn_core.db.models import Knode, Project


class LearningObjectMissing(LookupError):
    """Missing, foreign and unrelated objects have the same public response."""


def require_project_node(
    session: Session, *, project_id: int | None, node_id: int | None = None,
) -> int | None:
    if node_id is not None:
        node_project_id = session.scalar(select(Knode.project_id).where(Knode.id == node_id))
        if node_project_id is None or (project_id is not None and node_project_id != project_id):
            raise LearningObjectMissing("learning object not found")
        project_id = node_project_id
    if project_id is not None:
        # Keep a parent deletion from racing the child insert. SHARE permits
        # concurrent readers; deletion takes an exclusive parent lock.
        project = session.scalar(select(Project).where(Project.id == project_id).with_for_update(read=True))
        if project is None:
            raise LearningObjectMissing("learning object not found")
        # A node deletion may have finished while we waited for the parent.
        # Query columns again rather than trusting the ORM identity map.
        if node_id is not None and session.scalar(select(Knode.id).where(
            Knode.id == node_id, Knode.project_id == project_id,
        )) is None:
            raise LearningObjectMissing("learning object not found")
    return project_id
