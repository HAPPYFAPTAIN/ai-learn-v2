"""Atomically bind a client intent to its original creation response."""
import hashlib
import json
from typing import Callable
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from learn_core.db.models import Card, CreationRequest, Note, Project
from learn_core.tenancy.context import current_tenant


class CreationConflict(ValueError):
    pass


def _saved_result(session: Session, receipt: CreationRequest) -> dict:
    model = {"note": Note, "card": Card, "project": Project}[receipt.operation]
    if session.scalar(select(model.id).where(model.id == receipt.resource_id)) is None:
        raise CreationConflict("此请求创建的记录已删除，请为新操作使用新编号")
    return dict(receipt.response)


def lookup_creation(session: Session, *, operation: str, request_id: UUID) -> dict | None:
    """Read only the current tenant's committed result, never repeat a write."""
    receipt = session.scalar(select(CreationRequest).where(
        CreationRequest.operation == operation, CreationRequest.request_id == request_id,
    ))
    return _saved_result(session, receipt) if receipt is not None else None


def create_once(session: Session, *, operation: str, request_id: UUID | None, payload: dict,
                create: Callable[[], dict]) -> dict:
    # Older clients without an intent remain supported; new clients always send it.
    if request_id is None:
        return create()
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                    {"key": f"{current_tenant()}:create:{operation}:{request_id}"})
    receipt = session.scalar(select(CreationRequest).where(
        CreationRequest.operation == operation, CreationRequest.request_id == request_id,
    ))
    if receipt is not None:
        if receipt.payload_hash != digest:
            raise CreationConflict("请求编号已用于不同内容，请为新操作使用新编号")
        return _saved_result(session, receipt)
    result = json.loads(json.dumps(create(), ensure_ascii=False, default=lambda value: value.isoformat()))
    session.add(CreationRequest(operation=operation, request_id=request_id, payload_hash=digest,
                                resource_id=result["id"], response=result))
    session.flush()
    return result
