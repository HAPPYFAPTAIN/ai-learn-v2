"""测验接口。"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from learn_api.deps import SessionDep
from learn_api.errors import ApiError
from learn_core.learning import projects as project_service
from learn_core.learning import quizzes as service
from learn_core.learning import grading
from learn_api.routers.generation import _submit

from learn_api.schemas import GenerationOut, GradeOut, Items, QuizBrief, QuizOut

router = APIRouter(tags=["quizzes"])



class QuestionIn(BaseModel):
    model_config = {"extra": "forbid", "populate_by_name": True, "allow_inf_nan": False}

    stem: str = Field(min_length=1, max_length=50000)
    answer: str = Field(min_length=1, max_length=50000)
    qtype: Literal["choice", "fill", "short", "practice"] = "short"
    options: list[Annotated[str, Field(max_length=4000)]] = Field(default_factory=list, max_length=20)
    explanation: str = Field(default="", max_length=50000)
    node_id: int | None = Field(default=None, alias="nodeId")
    difficulty: int = Field(default=3, ge=1, le=5)


class QuizCreate(BaseModel):
    model_config = {"extra": "forbid", "populate_by_name": True, "allow_inf_nan": False}

    title: str = Field(default="", max_length=200)
    quiz_type: Literal["mixed", "choice", "fill", "short", "practice", "diagnostic", "review"] = Field(default="mixed", alias="quizType")
    node_ids: list[int] = Field(default_factory=list, max_length=100, alias="nodeIds")
    questions: list[QuestionIn] = Field(min_length=1, max_length=100)


class GradeSubmit(BaseModel):
    model_config = {"extra": "forbid"}
    answers: dict[str, Annotated[str, Field(max_length=8000)]] = Field(max_length=100)


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


@router.post("/projects/{project_id}/quizzes", status_code=status.HTTP_201_CREATED, response_model=QuizOut)
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


@router.get("/projects/{project_id}/quizzes", response_model=Items[QuizBrief])
def list_quizzes(project_id: int, session: SessionDep) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    return {
        "items": [
            {"id": q.id, "title": q.title, "quizType": q.quiz_type, "createdAt": q.created_at}
            for q in service.list_quizzes(session, project_id=project_id)
        ]
    }


@router.get("/quizzes/{quiz_id}", response_model=QuizOut)
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


@router.post("/quizzes/{quiz_id}/submit", status_code=202, response_model=GenerationOut, deprecated=True)
@router.post("/quizzes/{quiz_id}/grade-jobs", status_code=202, response_model=GenerationOut)
def grade_quiz(quiz_id: int, payload: GradeSubmit, response: Response, session: SessionDep) -> dict:
    quiz = service.get_quiz(session, quiz_id)
    if quiz is None or quiz.project_id is None:
        raise ApiError("NOT_FOUND", "测验不存在")
    return _submit(session, response, project_id=quiz.project_id, kind="grade",
                   options={"quizId": quiz_id, "answers": payload.answers})


@router.get("/quizzes/{quiz_id}/result", response_model=GradeOut | None)
def quiz_result(quiz_id: int, session: SessionDep) -> dict | None:
    if service.get_quiz(session, quiz_id) is None:
        raise ApiError("NOT_FOUND", "测验不存在")
    return grading.latest_result(session, quiz_id=quiz_id)


@router.get("/quizzes/{quiz_id}/grade-job", response_model=GenerationOut | None)
def quiz_grade_job(quiz_id: int, session: SessionDep) -> dict | None:
    if service.get_quiz(session, quiz_id) is None:
        raise ApiError("NOT_FOUND", "测验不存在")
    row = grading.latest_job(session, quiz_id=quiz_id)
    return {"jobId": row.job_id, "state": row.state} if row else None
