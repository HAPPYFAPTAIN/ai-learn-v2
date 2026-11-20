"""学习节点（知识树上的一个可学单元）。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
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
    if session.scalar(select(Knode.id).where(Knode.project_id == project_id, Knode.code == code.strip())) is not None:
        from learn_core.learning.creation import CreationConflict
        raise CreationConflict('章节编号已存在')
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
    allowed = {"title", "description", "stage", "est_hours", "difficulty", "status"}
    if set(fields) - allowed:
        raise ValueError("field not writable")
    if "status" in fields and fields["status"] not in {"pending", "learning", "reviewing", "done"}:
        raise ValueError("status is not writable")
    was_done = node.status == "done"
    for key, value in fields.items():
        setattr(node, key, value)
    if any(k in fields for k in ("title", "description", "stage", "est_hours", "difficulty")):
        node.content_version += 1
    session.flush()
    if "status" in fields:
        from learn_core.learning.progress import refresh_mastery
        refresh_mastery(session, node_id=node_id)
        if node.status == 'done' and not was_done:
            from learn_core.learning.progress import record_progress
            record_progress(session, project_id=node.project_id, node_id=node_id, metric='mastery', value=node.mastery)
    return node


def delete_node(session: Session, node_id: int) -> bool:
    node = session.get(Knode, node_id)
    if node is None:
        return False
    from learn_core.learning.lifecycle import cancel_learning_jobs, clear_learning_records
    cancel_learning_jobs(session, project_id=node.project_id, node_id=node_id)
    if session.scalar(select(Project).where(Project.id == node.project_id).with_for_update()) is None:
        return False
    clear_learning_records(session, project_id=node.project_id, node_ids=[node_id], whole_project=False)
    session.delete(node)
    return True


def delete_roadmap(session: Session, project_id: int) -> bool:
    """Clear chapter records atomically while retaining the plan and library.

    Lock the parent as enqueue does. Do not lock jobs here: workers lock job
    then parent. Refuse an active generation so it cannot restore the route.
    """
    from learn_core.db.models import AdaptSnapshot, JobProgress, Kedge
    from learn_core.learning.generation import GenerationConflict
    from learn_core.learning.lifecycle import clear_learning_records

    project = session.scalar(select(Project).where(Project.id == project_id).with_for_update())
    if project is None:
        return False
    active = session.scalar(select(JobProgress.id).where(
        JobProgress.progress["projectId"].as_integer() == project_id,
        JobProgress.state.in_(["queued", "running"]),
    ).limit(1))
    if active is not None:
        raise GenerationConflict("请等待当前学习任务完成后，再删除学习路线。")
    node_ids = list(session.scalars(select(Knode.id).where(Knode.project_id == project_id)))
    clear_learning_records(session, project_id=project_id, node_ids=node_ids, whole_project=False)
    session.execute(delete(Kedge).where(Kedge.project_id == project_id))
    session.execute(delete(Knode).where(Knode.project_id == project_id))
    session.execute(delete(AdaptSnapshot).where(AdaptSnapshot.project_id == project_id))
    project.roadmap_json = {}
    project.updated_at = datetime.now(timezone.utc)
    session.flush()
    return True
