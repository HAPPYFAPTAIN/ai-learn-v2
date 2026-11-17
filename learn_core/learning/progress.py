"""学习进度与项目概览。

进度是一串不可变的记录（谁、在哪个节点、什么指标、多少），
概览按需聚合。分开存的原因：后面要做学习曲线，历史不能被覆盖。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from learn_core.db.models import Card, Knode, ProgressRecord, QuizAttempt, QuizQuestion

METRICS = {"minutes", "cards_reviewed", "quiz_correct", "quiz_total", "mastery"}


def refresh_mastery(session: Session, *, node_id: int, incorrect: bool = False) -> float | None:
    """Legacy mastery weights; no hidden commit or duplicate answer recording."""
    node = session.scalar(select(Knode).where(Knode.id == node_id).with_for_update())
    if node is None:
        return None
    recent = list(session.scalars(select(QuizAttempt.is_correct).join(
        QuizQuestion, QuizQuestion.id == QuizAttempt.question_id,
    ).where(QuizQuestion.node_id == node_id, QuizAttempt.is_correct.is_not(None))
      .order_by(QuizAttempt.attempted_at.desc(), QuizAttempt.id.desc()).limit(10)))
    quiz_score = sum(bool(x) for x in recent) / len(recent) if recent else 0.0
    stability = session.scalar(select(func.avg(Card.stability)).where(Card.node_id == node_id)) or 0.0
    memory_score = min(1.0, max(0.0, stability) / 30)
    progress_score = {"pending": 0, "new": 0, "learning": 0.3, "reviewing": 0.6,
                      "weak": 0.4, "mastered": 1, "done": 1}.get(node.status, 0)
    node.mastery = max(0.0, min(1.0, 0.4 * quiz_score + 0.3 * memory_score + 0.3 * progress_score))
    if node.mastery >= 0.85 and node.status not in {"mastered", "done"}:
        node.status = "mastered"
    elif incorrect and node.mastery < 0.5 and node.status not in {"mastered", "done"}:
        node.status = "weak"
    session.flush()
    return node.mastery


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
