"""Delete owned learning records together, preserving the account's library."""

from datetime import datetime, timezone

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from learn_core.db.ktem import KtemConversation
from learn_core.db.models import (
    ActionEvent, ActionSession, AdaptSnapshot, Annotation, Card, DailyReport,
    JobProgress, Kedge, KnodeCollection, LessonGate, Note, ProgressRecord,
    Quiz, QuizAttempt, QuizQuestion, Resource, ReviewLog, Task,
)


def _related_quiz_ids(session: Session, node_ids: list[int]) -> list[int]:
    questions = select(QuizQuestion.quiz_id).where(QuizQuestion.node_id.in_(node_ids))
    return list(session.scalars(select(Quiz.id).where(or_(
        Quiz.node_id.in_(node_ids), Quiz.id.in_(questions), Quiz.scope_node_ids.overlap(node_ids),
    ))))


def cancel_learning_jobs(session: Session, *, project_id: int, node_id: int | None = None) -> None:
    quiz_ids = set(_related_quiz_ids(session, [node_id])) if node_id is not None else set()
    jobs = session.scalars(select(JobProgress).where(
        JobProgress.progress["projectId"].as_integer() == project_id,
        JobProgress.state.in_(["queued", "running"]),
    ).order_by(JobProgress.id).with_for_update())
    for job in jobs:
        options = job.progress.get("options", {})
        if node_id is None or job.progress.get("nodeId") == node_id or node_id in options.get("nodeIds", []) or (job.kind == "grade" and options.get("quizId") in quiz_ids):
            job.state, job.error = "cancelled", "学习计划或章节已删除"
            job.updated_at = datetime.now(timezone.utc)


def clear_learning_records(session: Session, *, project_id: int, node_ids: list[int], whole_project: bool) -> None:
    card_condition = or_(Card.project_id == project_id, Card.node_id.in_(node_ids)) if whole_project else Card.node_id.in_(node_ids)
    card_ids = select(Card.id).where(card_condition)
    session.execute(delete(ReviewLog).where(ReviewLog.card_id.in_(card_ids)))
    session.execute(delete(Card).where(card_condition))

    # A quiz is an assessment snapshot. Remove the whole snapshot when any of
    # its chapters is deleted; keeping half would change its grading semantics.
    if whole_project:
        quiz_condition = or_(Quiz.project_id == project_id, Quiz.id.in_(_related_quiz_ids(session, node_ids)))
    else:
        quiz_condition = Quiz.id.in_(_related_quiz_ids(session, node_ids))
    quiz_ids = list(session.scalars(select(Quiz.id).where(quiz_condition)))
    question_ids = select(QuizQuestion.id).where(QuizQuestion.quiz_id.in_(quiz_ids))
    session.execute(delete(QuizAttempt).where(QuizAttempt.question_id.in_(question_ids)))
    session.execute(delete(QuizQuestion).where(QuizQuestion.quiz_id.in_(quiz_ids)))
    session.execute(delete(Quiz).where(Quiz.id.in_(quiz_ids)))

    action_condition = or_(ActionSession.project_id == project_id, ActionSession.node_id.in_(node_ids)) if whole_project else ActionSession.node_id.in_(node_ids)
    action_ids = select(ActionSession.id).where(action_condition)
    session.execute(delete(ActionEvent).where(ActionEvent.session_id.in_(action_ids)))
    session.execute(delete(ActionSession).where(action_condition))
    for model in (Note, Annotation, Resource, LessonGate, Task, ProgressRecord):
        condition = or_(model.project_id == project_id, model.node_id.in_(node_ids)) if whole_project else model.node_id.in_(node_ids)
        session.execute(delete(model).where(condition))
    session.execute(delete(KnodeCollection).where(KnodeCollection.node_id.in_(node_ids)))
    session.execute(delete(Kedge).where(or_(Kedge.source_id.in_(node_ids), Kedge.target_id.in_(node_ids))))
    # Aggregated reports are stale after either kind of deletion.
    session.execute(delete(DailyReport).where(DailyReport.project_id == project_id))
    if whole_project:
        session.execute(delete(AdaptSnapshot).where(AdaptSnapshot.project_id == project_id))
        session.execute(delete(KtemConversation).where(KtemConversation.id.in_(
            [f"learn-project-{project_id}", f"learn-coach-{project_id}"])))
