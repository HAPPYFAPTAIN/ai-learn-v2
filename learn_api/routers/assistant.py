"""Tenant-wide assistant, sharing existing durable chat queue and leases."""
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from learn_api.deps import SessionDep
from learn_api.errors import ApiError
from learn_api.schemas import ConversationOut, GenerationOut
from learn_core.learning import conversations as service
from learn_core.learning.creation import CreationConflict

router = APIRouter(prefix='/assistant', tags=['assistant'])

class AssistantContext(BaseModel):
    model_config = {'extra': 'forbid'}
    page: Literal['学习首页', '学习路线', '学习工作台', '间隔复习', '查漏测验', '学习看板', '知识问答', '资料库', '学习工具', '模型设置'] = '学习首页'
    cardId: int | None = Field(default=None, gt=0)
    questionId: int | None = Field(default=None, gt=0)

class AssistantQuestion(BaseModel):
    model_config = {'extra': 'forbid'}
    content: str = Field(min_length=1, max_length=16000)
    requestId: UUID
    projectId: int | None = Field(default=None, gt=0)
    nodeId: int | None = Field(default=None, gt=0)
    context: AssistantContext = Field(default_factory=AssistantContext)

class AssistantAppend(BaseModel):
    nodeId: int = Field(gt=0)
    expectedVersion: int = Field(ge=0)


def _call(action):
    try: return action()
    except service.ConversationMissing as exc:
        raise ApiError('NOT_FOUND', str(exc)) from exc
    except service.ConversationBusy as exc:
        raise ApiError('JOB_RUNNING', str(exc)) from exc
    except CreationConflict as exc:
        raise ApiError("CONFLICT", str(exc)) from exc
    except ValueError as exc:
        raise ApiError('INVALID_ARGUMENT', str(exc)) from exc

@router.get('/conversation', response_model=ConversationOut)
def history(session: SessionDep):
    return service.history(session, project_id=None, mode='assistant')

@router.post('/chat-jobs', status_code=202, response_model=GenerationOut)
def ask(payload: AssistantQuestion, session: SessionDep):
    if not payload.content.strip(): raise ApiError('INVALID_ARGUMENT', '请输入问题')
    row = _call(lambda: service.submit(session, project_id=payload.projectId, mode='assistant',
        content=payload.content.strip(), request_id=str(payload.requestId), node_id=payload.nodeId,
        use_materials=False, material_ids=[], context=payload.context.model_dump(exclude_none=True)))
    return {'jobId':row.job_id, 'state':row.state}

@router.delete('/conversation', status_code=204)
def clear(session: SessionDep):
    _call(lambda: service.clear_assistant(session))
    return Response(status_code=204)

@router.post('/append')
def append(payload: AssistantAppend, session: SessionDep):
    return _call(lambda: service.append_assistant(session, node_id=payload.nodeId, expected_version=payload.expectedVersion))
