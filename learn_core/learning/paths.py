"""学习路径：按依赖关系排期。

先拓扑排序（有环时退化为按 stage/code 排），再按每周可投入学时装箱。
这是确定性算法——同样的节点和参数每次得到同一份计划，方便做断点续学和测试。
需要「按掌握度动态调整顺序」时，再在 `_order` 前后加一层策略，不改接口。
"""

from __future__ import annotations

from collections import defaultdict, deque

from sqlalchemy import select
from sqlalchemy.orm import Session

from learn_core.db.models import Kedge, Knode
from learn_core.learning.generation import course_code_sort_key


def _order(nodes: list[Knode], edges: list[Kedge]) -> list[Knode]:
    by_id = {n.id: n for n in nodes}
    indegree = {n.id: 0 for n in nodes}
    children: dict[int, list[int]] = defaultdict(list)
    for edge in edges:
        if edge.source_id in by_id and edge.target_id in by_id:
            # Same semantics as the legacy roadmap: source depends on target.
            children[edge.target_id].append(edge.source_id)
            indegree[edge.source_id] += 1

    def sort_key(nid: int) -> tuple:
        node = by_id[nid]
        return (course_code_sort_key(node.code), node.id)

    ready = deque(sorted((nid for nid, d in indegree.items() if d == 0), key=sort_key))
    ordered: list[Knode] = []
    while ready:
        nid = ready.popleft()
        ordered.append(by_id[nid])
        for child in sorted(children[nid], key=sort_key):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)

    if len(ordered) != len(nodes):  # 有环：剩下的按 stage/code 兜底
        seen = {n.id for n in ordered}
        ordered.extend(sorted((n for n in nodes if n.id not in seen), key=lambda n: (n.stage or "", n.code or "", n.id)))
    return ordered


def build_plan(
    session: Session,
    *,
    project_id: int,
    weeks: int = 8,
    hours_per_week: float = 10.0,
) -> dict:
    nodes = list(
        session.scalars(select(Knode).where(Knode.project_id == project_id).order_by(Knode.id))
    )
    edges = list(session.scalars(select(Kedge).where(Kedge.project_id == project_id)))
    ordered = _order(nodes, edges)

    weeks = max(1, weeks)
    hours_per_week = max(0.5, hours_per_week)
    total_hours = sum(float(n.est_hours or 0) for n in ordered)

    buckets: list[list[dict]] = [[] for _ in range(weeks)]
    used = [0.0] * weeks
    # 按时长平均摊到各周，避免所有节点堆在最后一周。
    target = max(hours_per_week, total_hours / weeks) if ordered else hours_per_week

    cursor = 0
    for node in ordered:
        hours = float(node.est_hours or 0)
        while cursor < weeks - 1 and used[cursor] + hours > target:
            cursor += 1
        buckets[cursor].append(
            {"nodeId": node.id, "code": node.code, "title": node.title, "hours": hours}
        )
        used[cursor] += hours

    return {
        "projectId": project_id,
        "weeks": [
            {
                "index": i + 1,
                "hours": round(used[i], 2),
                "items": buckets[i],
            }
            for i in range(weeks)
        ],
        "totalHours": round(total_hours, 2),
    }
