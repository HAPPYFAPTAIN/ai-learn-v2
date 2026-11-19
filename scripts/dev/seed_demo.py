"""给本地演示灌一份数据：一个项目、四个节点、几张卡、一套测验、一些进度。

用法（本地）::

    export LEARN_DEV_AUTH=1
    export LEARN_DATABASE_URL=postgresql+psycopg://learn_app:app@127.0.0.1:5432/learn_dev
    python scripts/dev/seed_demo.py

重复执行是安全的：先删掉 demo 租户的数据再重建。
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select, text  # noqa: E402

from learn_core.db.engine import session_scope  # noqa: E402
from learn_core.db.models import Card, Project  # noqa: E402
from learn_core.learning import nodes as node_service  # noqa: E402
from learn_core.learning import paths as path_service  # noqa: E402
from learn_core.learning import progress as progress_service  # noqa: E402
from learn_core.learning import quizzes as quiz_service  # noqa: E402
from learn_core.learning import reports as report_service  # noqa: E402
from learn_core.review import scheduler  # noqa: E402
from learn_core.tenancy.context import tenant_context  # noqa: E402
from learn_core.tenancy.service import get_or_create_tenant  # noqa: E402

OFFICIAL_ID = "dev-demo"


def main() -> None:
    if os.getenv("LEARN_DEV_AUTH") != "1":
        raise SystemExit("请先 export LEARN_DEV_AUTH=1，这个脚本只用于本地演示")

    with session_scope() as session:
        tenant = get_or_create_tenant(session, official_user_id=OFFICIAL_ID)
        tenant_id = tenant.id

    with tenant_context(tenant_id):
        with session_scope() as session:
            # 清掉上次的 demo 数据
            for table in ("le_reviewlog", "le_card", "le_quiz_attempt", "le_quiz_question",
                          "le_quiz", "le_progress", "le_daily_report", "le_note", "le_task",
                          "le_kedge", "le_knode", "le_project"):
                session.execute(text(f"DELETE FROM {table}"))

            project = Project(
                title="线性代数：从矩阵到特征值",
                goal="四周内能独立完成特征值分解的推导与计算",
                weekly_hours=8,
            )
            session.add(project)
            session.flush()

            specs = [
                ("A1", "向量与线性组合", "读懂线性组合、张成空间", "基础", 2.0),
                ("A2", "矩阵与线性变换", "矩阵是线性变换的坐标表示", "基础", 3.0),
                ("B1", "行列式与可逆性", "行列式的几何意义", "进阶", 3.0),
                ("C1", "特征值与特征向量", "Av = λv 的推导与求解", "进阶", 4.0),
            ]
            nodes = [
                node_service.create_node(
                    session,
                    project_id=project.id,
                    code=code,
                    title=title,
                    description=desc,
                    stage=stage,
                    est_hours=hours,
                )
                for code, title, desc, stage, hours in specs
            ]
            node_service.update_node(session, nodes[0].id, status="done", mastery=1.0)
            node_service.update_node(session, nodes[1].id, status="in_progress", mastery=0.6)
            session.flush()

            cards = [
                ("什么是线性组合？", "若干向量各乘一个标量再相加。"),
                ("矩阵乘法为什么不可交换？", "它表示两次线性变换的先后顺序，顺序不同结果不同。"),
            ]
            for front, back in cards:
                session.add(
                    Card(
                        project_id=project.id,
                        node_id=nodes[0].id,
                        front=front,
                        back=back,
                        next_review=scheduler._now(),
                    )
                )
            session.flush()

            quiz_service.create_quiz(
                session,
                project_id=project.id,
                title="第一章小测",
                questions=[
                    {"stem": "2×2 单位矩阵的行列式是多少？", "answer": "1",
                     "explanation": "对角元乘积减副对角元乘积：1×1−0×0=1。"},
                    {"stem": "特征值的定义式中，Av 等于什么？（用 λ 和 v 表示）",
                     "answer": "λv", "explanation": "定义就是 Av = λv。"},
                ],
                node_ids=[nodes[0].id, nodes[3].id],
            )

            for metric, value in (("minutes", 45), ("cards_reviewed", 2), ("quiz_correct", 1), ("quiz_total", 2)):
                progress_service.record_progress(
                    session, project_id=project.id, metric=metric, value=value, node_id=nodes[0].id
                )
            session.flush()

            report_service.build_report(session, project_id=project.id)
            plan = path_service.build_plan(session, project_id=project.id, weeks=3, hours_per_week=8)

            print(f"tenant   {tenant_id}")
            print(f"project  #{project.id} {project.title}")
            print(f"nodes    {len(nodes)}")
            print(f"path     {len(plan['weeks'])} 周 / {plan['totalHours']} 小时")
            print(f"demo url http://127.0.0.1:8000/app/?ticket=demo")
            print(f"时间     {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
