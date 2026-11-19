"""租户上下文。

一次请求或一个任务只属于一个租户。上下文用 ContextVar 保存，
数据库事务钩子、文件存储、模型调用和日志都从这里取租户；
拿不到租户就报错，绝不退化成「全部可见」。
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator
from uuid import UUID


class TenantMissingError(RuntimeError):
    """当前上下文里没有租户。"""


_current_tenant: ContextVar[UUID | None] = ContextVar("learn_tenant", default=None)


def current_tenant_or_none() -> UUID | None:
    return _current_tenant.get()


def current_tenant() -> UUID:
    tenant_id = _current_tenant.get()
    if tenant_id is None:
        raise TenantMissingError(
            "no tenant in scope; wrap the call in tenant_scope() or tenant_context()"
        )
    return tenant_id


def set_tenant(tenant_id: UUID | None) -> None:
    _current_tenant.set(tenant_id)


@contextmanager
def tenant_context(tenant_id: UUID) -> Iterator[UUID]:
    """在 with 块里绑定租户，退出时恢复原值。"""
    token = _current_tenant.set(tenant_id)
    try:
        yield tenant_id
    finally:
        _current_tenant.reset(token)


# 语义更明确的别名：请求与任务都用它包一层。
tenant_scope = tenant_context
