"""模型调用的事件 id。

格式 ``ln-j42-3-1``：``j`` 是业务请求（job）、``r`` 是重试（retry），
中间是全局随机 UUID，第三段是被调用的步骤，第四段是同一 id 的传输重试次数。

传输失败用同一个 id 重发，业务层重试用新号——
网关按事件 id 做幂等扣费，所以这个区分直接决定账对不对。
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.orm import Session


def next_event_id(session: Session, *, tenant_id: UUID, kind: str = "j") -> str:
    # UUIDs remain unique across tenants, restores and database rebuilds.
    return f"ln-{kind}-{uuid4().hex}"



def step_event(base: str, step: int, attempt: int = 1) -> str:
    """同一业务请求里的第 step 步；attempt 只给传输重试用。"""
    return f"{base}-{step}-{attempt}"
