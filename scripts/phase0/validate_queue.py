"""阶段 0 · 任务队列验证。

三条结论需要在本机真实跑出来：

1. queueing_lock 去重：同一业务对象的第二个在途任务被拒绝；
2. 同租户同通道串行、不同租户并行（lock = 租户:通道）；
3. 执行器崩溃后，僵死任务被新 worker 回收并重跑。

用法：
    PYTHONPATH=. .venv/bin/python scripts/phase0/validate_queue.py
退出码 0 表示三条全部成立。
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from datetime import datetime

from sqlalchemy import create_engine, text

from learn_core.config import get_settings
from learn_core.jobs.app import app
from learn_core.jobs.reaper import reap_stalled_jobs
from learn_core.jobs.tasks import probe

OWNER_DSN = get_settings().database_owner_url.replace("+psycopg", "")

QUEUE = "phase0"


def setup() -> None:
    owner = create_engine(OWNER_DSN, future=True)
    with owner.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS phase0_trace (
                    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    kind text NOT NULL,
                    tenant text NOT NULL,
                    event text NOT NULL,
                    ts timestamptz NOT NULL DEFAULT now()
                )
                """
            )
        )
        conn.execute(text("TRUNCATE phase0_trace"))
        conn.execute(text("GRANT SELECT, INSERT ON phase0_trace TO learn_app"))
        conn.execute(text("GRANT USAGE, SELECT ON SEQUENCE phase0_trace_id_seq TO learn_app"))
        conn.execute(text("DELETE FROM procrastinate_jobs WHERE queue_name = :q"), {"q": QUEUE})


def trace(tenant: str) -> list[tuple[str, datetime]]:
    owner = create_engine(OWNER_DSN, future=True)
    with owner.connect() as conn:
        rows = conn.execute(
            text("SELECT event, ts FROM phase0_trace WHERE tenant = :t ORDER BY id"),
            {"t": tenant},
        ).fetchall()
    return [(event, ts) for event, ts in rows]


def run_worker() -> str:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "procrastinate",
            "-a",
            "learn_core.jobs.app.app",
            "worker",
            f"--queues={QUEUE}",
            "--concurrency=2",
            "--one-shot",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stderr[-2000:]


def check_dedup() -> bool:
    key = f"phase0:{uuid.uuid4().hex}"
    with app.open():
        probe.configure(queue=QUEUE, queueing_lock=key, lock=key).defer(
            tenant="dedup", tag="first", seconds=0
        )
        try:
            probe.configure(queue=QUEUE, queueing_lock=key, lock=key).defer(
                tenant="dedup", tag="second", seconds=0
            )
        except Exception as exc:
            ok = exc.__class__.__name__ == "AlreadyEnqueued"
            print(f"[1] 去重：第二个任务被拒绝（{exc.__class__.__name__}）")
            return ok
    print("[1] 去重：第二个任务竟然被接受 —— 失败")
    return False


def check_serialization() -> bool:
    tenant_a = f"a-{uuid.uuid4().hex[:6]}"
    tenant_b = f"b-{uuid.uuid4().hex[:6]}"
    with app.open():
        for tag in ("a1", "a2", "a3"):
            probe.configure(
                queue=QUEUE, lock=f"{tenant_a}:cpu", queueing_lock=f"{tenant_a}:{tag}"
            ).defer(tenant=tenant_a, tag=tag, seconds=0.4)
        for tag in ("b1", "b2"):
            probe.configure(
                queue=QUEUE, lock=f"{tenant_b}:cpu", queueing_lock=f"{tenant_b}:{tag}"
            ).defer(tenant=tenant_b, tag=tag, seconds=0.4)
    stderr = run_worker()

    a_events = trace(tenant_a)
    b_events = trace(tenant_b)
    serial = (
        len(a_events) == 6
        and all(
            a_events[i][0].startswith("start") and a_events[i + 1][0].startswith("end")
            for i in range(0, len(a_events) - 1, 2)
        )
        and all(a_events[i][1] <= a_events[i + 1][1] for i in range(0, len(a_events) - 1, 2))
    )
    parallel = bool(a_events and b_events and b_events[0][1] < a_events[-1][1])
    print(f"[2] 串行：A 记录 {len(a_events)} 条、严格不重叠={serial}；跨租户并行={parallel}")
    if not (serial and parallel):
        print("    worker stderr:", stderr.replace("\n", " ")[-600:])
    return serial and parallel


def check_recovery() -> bool:
    tenant = f"crash-{uuid.uuid4().hex[:6]}"
    with app.open():
        job_id = probe.configure(
            queue=QUEUE, lock=f"{tenant}:cpu", queueing_lock=f"crash:{tenant}"
        ).defer(tenant=tenant, tag="recovered", seconds=0)

    owner = create_engine(OWNER_DSN, future=True)
    fake_worker = 2_000_000 + int(uuid.uuid4().int % 100000)
    with owner.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO procrastinate_workers (id, last_heartbeat) OVERRIDING SYSTEM VALUE "
                "VALUES (:id, now() - interval '10 minutes')"
            ),
            {"id": fake_worker},
        )
        conn.execute(
            text(
                "UPDATE procrastinate_jobs SET status='doing', worker_id=:w WHERE id=:j"
            ),
            {"w": fake_worker, "j": job_id},
        )
    reaped = reap_stalled_jobs(seconds_since_heartbeat=30)
    stderr = run_worker()
    events = trace(tenant)
    ok = any(event == "start:recovered" for event, _ in events)
    print(f"[3] 回收：重排 {reaped}，僵死任务重新执行={ok}（记录 {len(events)} 条）")
    if not ok:
        print("    worker stderr:", stderr.replace("\n", " ")[-600:])
    return ok


def main() -> int:
    setup()
    ok = all([check_dedup(), check_serialization(), check_recovery()])
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
