"""模型调用的事件 id。

格式 ``ln-j42-3-1``：``j`` 是业务请求（job）、``r`` 是重试（retry），
中间是租户内自增号，第三段是被调用的步骤，第四段是同一 id 的传输重试次数。

传输失败用同一个 id 重发，业务层重试用新号——
网关按事件 id 做幂等扣费，所以这个区分直接决定账对不对。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def next_event_id(session: Session, *, tenant_id: UUID, kind: str = "j") -> str:
    row = session.execute(
        text(
            """
            INSERT INTO llm_event_counter (tenant_id, kind, value) VALUES (:tid, :kind, 1)
            ON CONFLICT (tenant_id, kind) DO UPDATE SET value = llm_event_counter.value + 1
            RETURNING value
            """
        ),
        {"tid": str(tenant_id), "kind": kind},
    ).scalar_one()
    return f"ln-{kind}{row:06d}"


def step_event(base: str, step: int, attempt: int = 1) -> str:
    """同一业务请求里的第 step 步；attempt 只给传输重试用。"""
    return f"{base}-{step}-{attempt}"
