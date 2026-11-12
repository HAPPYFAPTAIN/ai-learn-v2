"""项目对话：一次请求可能拆成多步模型调用，每步一个事件 id。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from learn_api.deps import get_session, get_tenant_id
from learn_core.learning import projects as project_service
from learn_core.llm.event_id import next_event_id, step_event
from learn_core.llm.gateway import GatewayClient, GatewayError
from learn_api.errors import ApiError

router = APIRouter(prefix="/projects", tags=["chat"])

STATUS_TO_CODE = {
    401: "UNAUTHENTICATED",
    402: "INSUFFICIENT_CREDITS",
    429: "TENANT_BUSY",
}


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)
    model: str = ""
    purpose: str = "chat"
    background: bool = False

    model_config = {"populate_by_name": True}


def _gateway() -> GatewayClient:
    return GatewayClient()


@router.post("/{project_id}/chat")
def chat(
    project_id: int,
    payload: ChatRequest,
    tenant_id=Depends(get_tenant_id),
    session: Session = Depends(get_session),
) -> dict:
    project_service.get_project(session, project_id)

    base = next_event_id(session, tenant_id=tenant_id, kind="r" if payload.background else "j")
    event_id = step_event(base, step=1)
    gateway = _gateway()
    try:
        result = gateway.chat(
            session,
            tenant_id=tenant_id,
            event_id=event_id,
            messages=[m.model_dump() for m in payload.messages],
            purpose=payload.purpose,
            model=payload.model,
            background=payload.background,
        )
    except GatewayError as exc:
        code = STATUS_TO_CODE.get(exc.status, "INTERNAL")
        raise ApiError(code, f"gateway {exc.status}: {exc}") from exc
    finally:
        gateway.close()

    return {"eventId": event_id, "content": result.content, "model": result.model, "usage": result.usage}
