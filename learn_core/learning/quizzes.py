"""测验：建卷、取卷（不带答案）、判分。

判分只做字符串比对（去空白、忽略大小写）。填空/选择题都够用；
需要模糊判分时再在这里加，接口形状不变。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from learn_core.db.models import Quiz, QuizAttempt, QuizQuestion


def create_quiz(
    session: Session,
    *,
    project_id: int,
    title: str,
    questions: list[dict],
    node_ids: list[int] | None = None,
    quiz_type: str = "mixed",
) -> Quiz:
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


def _normalize(value: str) -> str:
    return "".join(value.split()).lower()


def submit(
    session: Session, *, quiz_id: int, answers: dict[int, str]
) -> tuple[int, int, list[dict]] | None:
    quiz = session.get(Quiz, quiz_id)
    if quiz is None:
        return None

    questions = quiz_questions(session, quiz_id)
    results: list[dict] = []
    correct = 0
    for question in questions:
        given = answers.get(question.id, "")
        ok = bool(given) and _normalize(given) == _normalize(question.answer)
        correct += int(ok)
        session.add(
            QuizAttempt(
                question_id=question.id,
                user_answer=given,
                is_correct=ok,
                attempted_at=datetime.now(timezone.utc),
            )
        )
        results.append(
            {
                "questionId": question.id,
                "correct": ok,
                "expected": question.answer,
                "explanation": question.explanation,
            }
        )
    session.flush()
    return correct, len(questions), results
