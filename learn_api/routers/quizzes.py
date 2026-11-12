"""测验接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from learn_api.deps import get_session
from learn_api.errors import ApiError
from learn_core.learning import projects as project_service
from learn_core.learning import quizzes as service

router = APIRouter(tags=["quizzes"])

SessionDep = Annotated[Session, Depends(get_session)]


class QuestionIn(BaseModel):
    model_config = {"extra": "forbid", "populate_by_name": True}

    stem: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    qtype: str = "short"
    options: list = Field(default_factory=list)
    explanation: str = ""
    node_id: int | None = Field(default=None, alias="nodeId")
    difficulty: int = Field(default=3, ge=1, le=5)


class QuizCreate(BaseModel):
    model_config = {"extra": "forbid", "populate_by_name": True}

    title: str = Field(default="", max_length=200)
    quiz_type: str = Field(default="mixed", alias="quizType")
    node_ids: list[int] = Field(default_factory=list, alias="nodeIds")
    questions: list[QuestionIn] = Field(min_length=1)


class QuizSubmit(BaseModel):
    model_config = {"extra": "forbid", "populate_by_name": True}

    # {questionId: answer}
    answers: dict[str, str]


def _question_payload(q, *, with_answer: bool) -> dict:
    data = {
        "id": q.id,
        "qtype": q.qtype,
        "stem": q.stem,
        "options": q.options,
        "difficulty": q.difficulty,
    }
    if with_answer:
        data["answer"] = q.answer
        data["explanation"] = q.explanation
    return data


@router.post("/projects/{project_id}/quizzes", status_code=status.HTTP_201_CREATED)
def create_quiz(project_id: int, payload: QuizCreate, session: SessionDep) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    quiz = service.create_quiz(
        session,
        project_id=project_id,
        title=payload.title,
        questions=[q.model_dump() for q in payload.questions],
        node_ids=payload.node_ids,
        quiz_type=payload.quiz_type,
    )
    questions = service.quiz_questions(session, quiz.id)
    return {
        "id": quiz.id,
        "title": quiz.title,
        "quizType": quiz.quiz_type,
        "questions": [_question_payload(q, with_answer=False) for q in questions],
    }


@router.get("/projects/{project_id}/quizzes")
def list_quizzes(project_id: int, session: SessionDep) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    return {
        "items": [
            {"id": q.id, "title": q.title, "quizType": q.quiz_type, "createdAt": q.created_at}
            for q in service.list_quizzes(session, project_id=project_id)
        ]
    }


@router.get("/quizzes/{quiz_id}")
def get_quiz(quiz_id: int, session: SessionDep) -> dict:
    quiz = service.get_quiz(session, quiz_id)
    if quiz is None:
        raise ApiError("NOT_FOUND", "quiz not found")
    questions = service.quiz_questions(session, quiz_id)
    return {
        "id": quiz.id,
        "title": quiz.title,
        "quizType": quiz.quiz_type,
        "questions": [_question_payload(q, with_answer=False) for q in questions],
    }


@router.post("/quizzes/{quiz_id}/submit")
def submit(quiz_id: int, payload: QuizSubmit, session: SessionDep) -> dict:
    answers = {int(k): v for k, v in payload.answers.items() if str(k).isdigit()}
    result = service.submit(session, quiz_id=quiz_id, answers=answers)
    if result is None:
        raise ApiError("NOT_FOUND", "quiz not found")
    correct, total, items = result
    return {
        "correct": correct,
        "total": total,
        "score": round(correct / total, 4) if total else 0.0,
        "results": items,
    }
