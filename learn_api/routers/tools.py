from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from learn_api.deps import get_session
from learn_api.errors import ApiError
from learn_api.schemas import GenerationOut
from learn_core.learning import polish
from learn_core.learning.conversations import ConversationMissing, ConversationBusy

router = APIRouter(prefix='/projects',tags=['tools'])


class PolishCreate(BaseModel):
    source: str = Field(min_length=1,max_length=12000)
    purpose: str = Field(default='note',max_length=20)
    request_id: UUID = Field(alias='requestId')


@router.get('/{project_id}/polish-job',response_model=GenerationOut | None)
def latest(project_id:int,session:Session=Depends(get_session)):
    try:
        row = polish.latest(session,project_id=project_id)
        return {'jobId':row.job_id,'state':row.state} if row else None
    except ConversationMissing as exc:
        raise ApiError('NOT_FOUND',str(exc)) from exc


@router.post('/{project_id}/polish-jobs',response_model=GenerationOut,status_code=202)
def submit(project_id:int,payload:PolishCreate,session:Session=Depends(get_session)):
    try:
        row = polish.submit(session,project_id=project_id,source=payload.source,purpose=payload.purpose,request_id=str(payload.request_id))
        return {'jobId':row.job_id,'state':row.state}
    except ConversationMissing as exc:
        raise ApiError('NOT_FOUND',str(exc)) from exc
    except ConversationBusy as exc:
        raise ApiError('JOB_RUNNING',str(exc)) from exc
    except ValueError as exc:
        raise ApiError('INVALID_ARGUMENT',str(exc)) from exc
