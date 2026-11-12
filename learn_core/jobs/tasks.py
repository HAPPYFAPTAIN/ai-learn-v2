"""阶段 0 的探针任务。

只用于验证队列语义（去重、串行、心跳回收），不承载业务逻辑；
业务任务在阶段 1 随各 service 一起落地。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import text

from learn_core.db.engine import get_engine
from learn_core.jobs.app import app, channel_lock


def _record(kind: str, tenant: str, event: str) -> None:
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO phase0_trace (kind, tenant, event, ts) "
                "VALUES (:kind, :tenant, :event, :ts)"
            ),
            {"kind": kind, "tenant": tenant, "event": event, "ts": datetime.now(timezone.utc)},
        )


@app.task(name="learn_core.jobs.tasks.probe", queue="phase0", retry=1)
def probe(tenant: str, tag: str, seconds: float = 0.4) -> str:
    _record("probe", tenant, f"start:{tag}")
    time.sleep(seconds)
    _record("probe", tenant, f"end:{tag}")
    return tag


@app.task(name="learn_core.jobs.tasks.tenant_probe", queue="cpu")
def tenant_probe(tenant: str, channel: str, tag: str, seconds: float = 0.4) -> str:
    """带 lock=租户:通道 的任务，同一租户同一通道必须串行。"""
    _record("tenant_probe", tenant, f"start:{tag}")
    time.sleep(seconds)
    _record("tenant_probe", tenant, f"end:{tag}")
    return tag


__all__ = ["probe", "tenant_probe", "channel_lock"]
