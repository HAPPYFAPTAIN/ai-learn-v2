"""Quiz creation and retrieval. Grading runs through durable learning jobs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from learn_core.db.models import Quiz, QuizQuestion
from learn_core.learning.ownership import require_project_node


def create_quiz(
    session: Session,
    *,
    project_id: int,
    title: str,
    questions: list[dict],
    node_ids: list[int] | None = None,
    quiz_type: str = "mixed",
) -> Quiz:
    require_project_node(session, project_id=project_id)
    linked_nodes = set(node_ids or []) | {item["node_id"] for item in questions if item.get("node_id") is not None}
    for node_id in sorted(linked_nodes):
        require_project_node(session, project_id=project_id, node_id=node_id)
    quiz = Quiz(
        project_id=project_id,
        title=title,
        quiz_type=quiz_type,
        scope_node_ids=node_ids or [],
    )
    session.add(quiz)
    session.flush()

    for item in questions:
        session.add(
            QuizQuestion(
                quiz_id=quiz.id,
                node_id=item.get("node_id"),
                qtype=item.get("qtype", "short"),
                stem=item["stem"],
                options=item.get("options", []),
                answer=item["answer"],
                explanation=item.get("explanation", ""),
                difficulty=int(item.get("difficulty", 3)),
            )
        )
    session.flush()
    return quiz


def list_quizzes(session: Session, *, project_id: int) -> list[Quiz]:
    stmt = select(Quiz).where(Quiz.project_id == project_id).order_by(Quiz.id.desc())
    return list(session.scalars(stmt))


def get_quiz(session: Session, quiz_id: int) -> Quiz | None:
    return session.get(Quiz, quiz_id)


def quiz_questions(session: Session, quiz_id: int, *, with_answer: bool = False) -> list[QuizQuestion]:
    stmt = select(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id).order_by(QuizQuestion.id)
    return list(session.scalars(stmt))
