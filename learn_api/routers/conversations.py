from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from learn_api.deps import get_session
from learn_api.errors import ApiError
from learn_api.schemas import ConversationOut, GenerationOut
from learn_core.learning import conversations as service

router = APIRouter(prefix='/projects',tags=['conversations'])


class QuestionCreate(BaseModel):
    mode: Literal['chat','coach'] = 'chat'
    content: str = Field(min_length=1,max_length=16000)
    request_id: UUID = Field(alias='requestId')
    node_id: int | None = Field(default=None,alias='nodeId')
    use_materials: bool = Field(default=True,alias='useMaterials')
    material_ids: list[UUID] = Field(default_factory=list,max_length=20,alias='materialIds')


@router.get('/{project_id}/conversation',response_model=ConversationOut)
def history(project_id:int,mode:Literal['chat','coach']='chat',session:Session=Depends(get_session)):
    try:
        return service.history(session,project_id=project_id,mode=mode)
    except service.ConversationMissing as exc:
        raise ApiError('NOT_FOUND',str(exc)) from exc


@router.post('/{project_id}/chat-jobs',response_model=GenerationOut,status_code=202)
def submit(project_id:int,payload:QuestionCreate,session:Session=Depends(get_session)):
    if not payload.content.strip():
        raise ApiError('INVALID_ARGUMENT','请输入问题')
    try:
        row = service.submit(session,project_id=project_id,content=payload.content.strip(),request_id=str(payload.request_id),
                             node_id=payload.node_id,use_materials=payload.use_materials,material_ids=sorted(set(str(i) for i in payload.material_ids)),mode=payload.mode)
        return {'jobId':row.job_id,'state':row.state}
    except service.ConversationMissing as exc:
        raise ApiError('NOT_FOUND',str(exc)) from exc
    except service.ConversationBusy as exc:
        raise ApiError('JOB_RUNNING',str(exc)) from exc
    except ValueError as exc:
        raise ApiError('INVALID_ARGUMENT',str(exc)) from exc
