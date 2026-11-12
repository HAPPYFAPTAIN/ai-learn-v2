"""模型调用的并发租约。

用表做租约而不是进程内信号量：API 进程和 worker 进程都要受同一个上限
约束，否则一个批量任务就能把交互请求挤死。

租约带过期时间，进程崩溃后不会永久占坑；下一次 acquire 时顺手清掉。
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from learn_core.config import get_settings

LANE_LIMITS = {"interactive": "tenant_interactive_leases", "background": "background_llm_concurrency"}
DEFAULT_TTL = timedelta(seconds=120)


class LeaseUnavailable(RuntimeError):
    pass


def _limit_for(lane: str) -> int:
    settings = get_settings()
    if lane == "interactive":
        return max(1, settings.tenant_interactive_leases)
    if lane == "background":
        # 后台是全局并发，不是每租户；这里按每租户 1 处理，全局闸门在 worker 里。
        return 1
    raise ValueError(f"unknown lane: {lane}")


def holder_name() -> str:
    return f"{os.getpid()}-{uuid4().hex[:8]}"


def acquire(
    session: Session,
    *,
    tenant_id: UUID,
    lane: str,
    holder: str | None = None,
    ttl: timedelta = DEFAULT_TTL,
) -> str:
    holder = holder or holder_name()
    limit = _limit_for(lane)
    expires_at = datetime.now(timezone.utc) + ttl

    # 同一 (租户, 通道) 的并发计数加锁，避免两个请求同时数到 limit-1。
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"{tenant_id}:{lane}"},
    )
    session.execute(text("DELETE FROM llm_lease WHERE expires_at < now()"))
    active = session.execute(
        text(
            """
            SELECT count(*) FROM llm_lease
             WHERE tenant_id = :tid AND lane = :lane AND expires_at > now()
            """
        ),
        {"tid": str(tenant_id), "lane": lane},
    ).scalar_one()

    existing = session.execute(
        text(
            """
            SELECT holder FROM llm_lease
             WHERE tenant_id = :tid AND lane = :lane AND holder = :holder
            """
        ),
        {"tid": str(tenant_id), "lane": lane, "holder": holder},
    ).scalar_one_or_none()

    if existing is None and active >= limit:
        raise LeaseUnavailable(f"{lane} lane full ({active}/{limit})")

    session.execute(
        text(
            """
            INSERT INTO llm_lease (tenant_id, lane, holder, expires_at)
            VALUES (:tid, :lane, :holder, :expires_at)
            ON CONFLICT (tenant_id, lane, holder) DO UPDATE SET expires_at = excluded.expires_at
            """
        ),
        {"tid": str(tenant_id), "lane": lane, "holder": holder, "expires_at": expires_at},
    )
    return holder


def release(session: Session, *, tenant_id: UUID, lane: str, holder: str) -> None:
    session.execute(
        text(
            """
            DELETE FROM llm_lease
             WHERE tenant_id = :tid AND lane = :lane AND holder = :holder
            """
        ),
        {"tid": str(tenant_id), "lane": lane, "holder": holder},
    )


@contextmanager
def lease(session: Session, *, tenant_id: UUID, lane: str, ttl: timedelta = DEFAULT_TTL) -> Iterator[str]:
    holder = acquire(session, tenant_id=tenant_id, lane=lane, ttl=ttl)
    try:
        yield holder
    finally:
        release(session, tenant_id=tenant_id, lane=lane, holder=holder)
