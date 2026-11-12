"""学习进度与项目概览。

进度是一串不可变的记录（谁、在哪个节点、什么指标、多少），
概览按需聚合。分开存的原因：后面要做学习曲线，历史不能被覆盖。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from learn_core.db.models import Knode, ProgressRecord

METRICS = {"minutes", "cards_reviewed", "quiz_correct", "quiz_total", "mastery"}


def record_progress(
    session: Session,
    *,
    project_id: int,
    node_id: int | None,
    metric: str,
    value: float,
) -> ProgressRecord:
    if metric not in METRICS:
        raise ValueError(f"unknown metric: {metric}")
    row = ProgressRecord(
        project_id=project_id,
        node_id=node_id,
        metric=metric,
        value=value,
        recorded_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.flush()
    return row


def list_progress(session: Session, *, project_id: int, limit: int = 200) -> list[ProgressRecord]:
    stmt = (
        select(ProgressRecord)
        .where(ProgressRecord.project_id == project_id)
        .order_by(ProgressRecord.recorded_at.desc(), ProgressRecord.id.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt))


def project_summary(session: Session, *, project_id: int) -> dict:
    nodes_by_status = dict(
        session.execute(
            select(Knode.status, func.count()).where(Knode.project_id == project_id).group_by(Knode.status)
        ).all()
    )
    total_nodes = sum(nodes_by_status.values())
    mastered = nodes_by_status.get("done", 0) + nodes_by_status.get("mastered", 0)

    minutes = session.execute(
        select(func.coalesce(func.sum(ProgressRecord.value), 0.0)).where(
            ProgressRecord.project_id == project_id, ProgressRecord.metric == "minutes"
        )
    ).scalar_one()

    return {
        "totalNodes": total_nodes,
        "nodesByStatus": nodes_by_status,
        "masteredNodes": mastered,
        "masteryRatio": round(mastered / total_nodes, 4) if total_nodes else 0.0,
        "studyMinutes": float(minutes),
    }
