"""Legacy roadmap JSON/DAG semantics, adapted to the shared PostgreSQL service."""
from __future__ import annotations

import json
from graphlib import TopologicalSorter, CycleError

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from learn_core.db.models import Project, Knode, Kedge


class RoadmapNode(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, allow_inf_nan=False)
    code: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=12000)
    stage: str = Field(default="base", min_length=1, max_length=16)
    est_hours: float = Field(default=2, gt=0, le=1000)
    difficulty: int = Field(default=3, ge=1, le=5)
    prerequisites: list[str] = Field(default_factory=list, max_length=100)


class Roadmap(BaseModel):
    summary: str = Field(default="", max_length=8000)
    stages: list[dict[str, str]] = Field(default_factory=list, max_length=100)
    nodes: list[RoadmapNode] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_dependencies(self):
        codes = {n.code for n in self.nodes}
        if len(codes) != len(self.nodes):
            raise ValueError("章节编号重复")
        graph = {}
        for node in self.nodes:
            if any(p not in codes or p == node.code for p in node.prerequisites):
                raise ValueError("章节前置依赖不存在或引用自身")
            node.prerequisites = list(dict.fromkeys(node.prerequisites))
            graph[node.code] = node.prerequisites
        try:
            tuple(TopologicalSorter(graph).static_order())
        except CycleError as exc:
            raise ValueError("章节前置依赖存在循环") from exc
        return self


def parse_roadmap(content: str) -> Roadmap:
    # Tolerate the same fenced JSON seen in legacy chat_json, not arbitrary text.
    content = content.strip()
    if content.startswith("```json\n") and content.endswith("```"):
        content = content[8:-3].strip()
    return Roadmap.model_validate(json.loads(content))


def save_roadmap(session: Session, *, project_id: int, roadmap: Roadmap) -> int:
    """Fill an empty project atomically; never clear existing learning records."""
    project = session.scalar(select(Project).where(Project.id == project_id).with_for_update())
    if project is None:
        raise ValueError("学习计划已不存在")
    if session.scalar(select(Knode.id).where(Knode.project_id == project_id).limit(1)):
        raise ValueError("学习计划已有章节，已保留原内容")
    code_to_id = {}
    for data in roadmap.nodes:
        node = Knode(project_id=project_id, **data.model_dump(exclude={"prerequisites"}))
        session.add(node)
        session.flush()
        code_to_id[node.code] = node.id
    for data in roadmap.nodes:
        for prerequisite in data.prerequisites:
            # Legacy source = dependent, target = prerequisite.
            session.add(Kedge(project_id=project_id, source_id=code_to_id[data.code],
                              target_id=code_to_id[prerequisite], relation="prerequisite"))
    project.roadmap_json = roadmap.model_dump()
    session.flush()
    return len(code_to_id)
