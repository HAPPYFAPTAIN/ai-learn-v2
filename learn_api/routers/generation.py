"""Explicit paid generation actions; long operations always return a durable job."""
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from sqlalchemy.orm import Session

from learn_api.deps import get_session
from learn_api.errors import ApiError
from learn_api.schemas import GenerationOut
from learn_core.db.models import Knode
from learn_core.learning.generation import (
    submit_generation, GenerationConflict, GenerationMissing,
)

router = APIRouter(tags=["generation"])
SessionDep = Annotated[Session, Depends(get_session)]


class LessonGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    force: bool = False


class AssessmentGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    node_ids: list[int] = Field(min_length=1, max_length=20, alias="nodeIds")
    count: int = Field(default=5, ge=1, le=20)
    qtype: Literal["mixed", "choice", "fill", "short", "practice"] = "mixed"


def _submit(session: Session, response: Response, **kwargs) -> dict:
    try:
        row = submit_generation(session, **kwargs)
    except GenerationMissing as exc:
        raise ApiError("NOT_FOUND", str(exc)) from exc
    except GenerationConflict as exc:
        raise ApiError("CONFLICT", str(exc)) from exc
    response.headers["Location"] = f"/official/learn-everything/api/v2/jobs/{row.job_id}"
    return {"jobId": row.job_id, "state": row.state}


@router.post("/projects/{project_id}/roadmap-jobs", status_code=202, response_model=GenerationOut)
def generate_roadmap(project_id: int, response: Response, session: SessionDep) -> dict:
    return _submit(session, response, project_id=project_id, kind="roadmap")


@router.post("/nodes/{node_id}/lesson-jobs", status_code=202, response_model=GenerationOut)
def generate_lesson(node_id: int, payload: LessonGenerate, response: Response, session: SessionDep) -> dict:
    node = session.get(Knode, node_id)
    if node is None:
        raise ApiError("NOT_FOUND", "章节不存在")
    return _submit(session, response, project_id=node.project_id, node_id=node_id,
                   kind="lesson", force=payload.force)


@router.post("/projects/{project_id}/quiz-jobs", status_code=202, response_model=GenerationOut)
def generate_quiz(project_id: int, payload: AssessmentGenerate, response: Response, session: SessionDep) -> dict:
    return _submit(session, response, project_id=project_id, kind="quiz", options=payload.model_dump(by_alias=True))


@router.post("/projects/{project_id}/card-jobs", status_code=202, response_model=GenerationOut)
def generate_cards(project_id: int, payload: AssessmentGenerate, response: Response, session: SessionDep) -> dict:
    return _submit(session, response, project_id=project_id, kind="cards", options=payload.model_dump(by_alias=True))
