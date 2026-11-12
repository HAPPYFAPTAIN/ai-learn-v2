"""FastAPI 依赖：身份与租户会话。"""

from __future__ import annotations

from typing import AsyncIterator

from fastapi import Depends
from sqlalchemy.orm import Session

from learn_api.auth import Principal, get_principal
from learn_api.errors import ApiError
from learn_core.db.engine import session_scope
from learn_core.tenancy.context import tenant_context
from learn_core.tenancy.service import get_or_create_tenant


def get_tenant_id(principal: Principal = Depends(get_principal)):
    """把官网用户映射到租户；第一次访问时建租户。"""
    with session_scope() as session:
        tenant = get_or_create_tenant(session, principal.official_user_id)
        if tenant.status != "active":
            raise ApiError("ENTITLEMENT_REQUIRED", f"tenant {tenant.status}")
        return tenant.id


async def get_session(tenant_id=Depends(get_tenant_id)) -> AsyncIterator[Session]:
    """必须 async：租户上下文用 ContextVar 保存，只有同一个事件循环上下文
    里 set/reset 才对得上；同步依赖会被丢到线程池，token 会跨 Context。"""
    with tenant_context(tenant_id):
        with session_scope() as session:
            yield session


def get_principal_dep(principal: Principal = Depends(get_principal)) -> Principal:
    return principal
