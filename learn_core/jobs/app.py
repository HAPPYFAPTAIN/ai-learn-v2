"""任务队列（Procrastinate）入口。

设计约束（见 .project-to-act/docs/learn-multitenant-plan.md）：
- 队列按通道划分：llm / cpu / io；
- 同租户同通道串行：lock = f"{tenant_id}:{channel}"；
- 同一业务对象只允许一个在途任务：queueing_lock；
- 执行器是独立进程，心跳由 procrastinate 维护。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from procrastinate import App, PsycopgConnector

from learn_core.config import get_settings

CHANNELS = ("llm", "cpu", "io")


@dataclass(frozen=True)
class JobHandle:
    """页面拿到的句柄；job_id 同时写进 job_progress。"""

    job_id: int
    kind: str


def build_app() -> App:
    settings = get_settings()
    return App(
        connector=PsycopgConnector(conninfo=settings.procrastinate_dsn),
        import_paths=["learn_core.jobs.tasks"],
    )


app = build_app()


def channel_lock(tenant_id: UUID, channel: str) -> str:
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel: {channel}")
    return f"{tenant_id}:{channel}"


def queueing_lock(kind: str, subject: str) -> str:
    """同一业务对象的在途任务去重键。"""
    return f"{kind}:{subject}"
