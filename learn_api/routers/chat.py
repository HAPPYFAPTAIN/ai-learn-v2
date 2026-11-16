"""项目对话：一次请求可能拆成多步模型调用，每步一个事件 id。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from learn_api.deps import get_tenant_id
from learn_core.db.engine import session_scope
from learn_core.tenancy.context import tenant_context
from learn_core.learning.model_settings import selected_model
from learn_core.llm.lease import LeaseUnavailable
from learn_core.learning import projects as project_service
from learn_core.llm.event_id import next_event_id, step_event
from learn_core.llm.gateway import GatewayClient, GatewayError
from learn_api.errors import ApiError

from learn_api.schemas import ChatOut

router = APIRouter(prefix="/projects", tags=["chat"])

STATUS_TO_CODE = {
    401: "UNAUTHENTICATED",
    402: "INSUFFICIENT_CREDITS",
    429: "TENANT_BUSY",
}


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1, max_length=16000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    model: str = ""
    purpose: str = "chat"
    background: bool = False

    model_config = {"populate_by_name": True}


def _gateway() -> GatewayClient:
    return GatewayClient()


@router.post("/{project_id}/chat", response_model=ChatOut)
def chat(
    project_id: int,
    payload: ChatRequest,
    tenant_id=Depends(get_tenant_id),
) -> dict:
    if sum(len(m.content) for m in payload.messages) > 120000:
        raise ApiError('INVALID_ARGUMENT', '对话过长，请新建对话')
    with tenant_context(tenant_id):
        with session_scope() as session:
            if project_service.get_project(session, project_id) is None:
                raise ApiError('NOT_FOUND', '学习计划不存在')
            model = selected_model(session)
            if not model:
                raise ApiError('INVALID_ARGUMENT', '请先在模型设置选择主模型')
            if payload.model and payload.model != model:
                raise ApiError('INVALID_ARGUMENT', '请先在模型设置保存主模型')
            event_id = step_event(next_event_id(session, tenant_id=tenant_id, kind='r'), step=1)
        try:
            with _gateway() as gateway:
                result = gateway.chat_detached(
                    event_id=event_id, job_id=event_id,
                    messages=[m.model_dump() for m in payload.messages],
                    purpose='chat', model=model, lane='interactive', max_tokens=4000,
                )
        except LeaseUnavailable as exc:
            raise ApiError('TENANT_BUSY', '当前提问较多，请稍后再试', retry_after_seconds=5) from exc
        except GatewayError as exc:
            code = STATUS_TO_CODE.get(exc.status, 'GATEWAY_UNAVAILABLE')
            # These are gateway product credentials, not browser login credentials.
            if exc.status == 401:
                code = 'GATEWAY_UNAVAILABLE'
            raise ApiError(code, str(exc)) from exc

    return {"eventId": event_id, "content": result.content, "model": result.model, "usage": result.usage}
