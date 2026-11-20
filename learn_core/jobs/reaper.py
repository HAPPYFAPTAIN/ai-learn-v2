"""僵死任务回收。

Procrastinate 只提供查询接口：worker 进程被 kill 后，它名下的 `doing`
任务不会自动回到队列。这里补上回收逻辑，由运维定时器每分钟调用一次，
或者由独立 maintenance 进程轮询。

判定依据是 worker 心跳：心跳超过 `seconds_since_heartbeat` 的 worker
视为已死，其名下 doing 任务整体重排。
"""

from __future__ import annotations

import asyncio

from learn_core.jobs.app import app


async def _reap(seconds_since_heartbeat: float, queue: str | None) -> list[int]:
    async with app.open_async():
        stalled = list(
            await app.job_manager.get_stalled_jobs(
                seconds_since_heartbeat=seconds_since_heartbeat, queue=queue
            )
        )
        reaped: list[int] = []
        for job in stalled:
            await app.job_manager.retry_job(job)
            reaped.append(job.id)
        return reaped


def reconcile_progress(*, queue: str | None = None) -> int:
    """Reconcile through each tenant's RLS context; no elevated runtime role."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select, text, or_, and_
    from learn_core.db.engine import session_scope
    from learn_core.db.models import Tenant, JobProgress
    from learn_core.tenancy.context import tenant_context
    from learn_core.llm.gateway import UNKNOWN_RESULT
    from learn_core.jobs.logging import log_job_failure

    now = datetime.now(timezone.utc)
    count = 0
    with session_scope() as session:
        tenants = list(session.scalars(select(Tenant.id)))
    for tenant in tenants:
        with tenant_context(tenant), session_scope() as session:
            query = select(JobProgress).where(or_(
                and_(JobProgress.state == 'running', JobProgress.updated_at < now - timedelta(minutes=15)),
                and_(JobProgress.state == 'queued', JobProgress.updated_at < now - timedelta(minutes=30)),
            ))
            if queue == 'chat':
                query = query.where(JobProgress.kind.in_(['chat', 'coach', 'polish', 'assistant']))
            elif queue == 'llm':
                query = query.where(JobProgress.kind.in_(['roadmap', 'lesson', 'quiz', 'cards', 'grade']))
            elif queue == 'io':
                query = query.where(JobProgress.kind == 'index')
            elif queue is not None:
                continue
            for row in session.scalars(query.with_for_update(skip_locked=True)):
                if row.state == 'queued' and session.scalar(text(
                    "SELECT EXISTS (SELECT 1 FROM procrastinate_jobs WHERE args->>'job_id'=:job "
                    "AND args->>'tenant'=:tenant AND status IN ('todo', 'doing'))"
                ), {'job': row.job_id, 'tenant': str(tenant)}):
                    continue
                pending = row.progress.get('gatewayCallPending', False)
                row.error = UNKNOWN_RESULT if pending else ('任务超时中断，请重试' if row.state == 'running' else '任务未能开始，请重试')
                row.state = 'failed'
                row.progress = {**row.progress, 'errorCode': 'RESULT_UNCONFIRMED' if pending else 'TASK_TIMEOUT'}
                row.updated_at = now
                log_job_failure(row.kind, row.job_id, row.progress['errorCode'], tenant)
                count += 1
    return count


def reap_stalled_jobs(seconds_since_heartbeat: float = 60.0, queue: str | None = None) -> list[int]:
    """同步入口，返回被重排的任务 id。"""
    reconcile_progress(queue=queue)
    return asyncio.run(_reap(seconds_since_heartbeat, queue))


def main(argv: list[str] | None = None) -> int:
    """systemd timer 的调用入口：跑一次就退出。

    退出码 0 表示扫描成功（哪怕没有僵死任务），非 0 交给 systemd 记录失败。
    被重排的任务 id 打到 stdout，方便 journalctl 里对账。
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="回收僵死的学习任务")
    parser.add_argument(
        "--seconds-since-heartbeat",
        type=float,
        default=60.0,
        help="心跳超过这个秒数的 worker 视为已死（默认 60）",
    )
    parser.add_argument("--queue", default=None, help="只扫某个队列，默认全部")
    args = parser.parse_args(argv)

    try:
        reaped = reap_stalled_jobs(args.seconds_since_heartbeat, args.queue)
    except Exception as exc:  # noqa: BLE001 - 定时任务失败要留完整原因
        print(f"reaper failed: {exc.__class__.__name__}", file=sys.stderr)
        return 1

    print(f"reaped {len(reaped)} job(s): {','.join(str(i) for i in reaped) or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
