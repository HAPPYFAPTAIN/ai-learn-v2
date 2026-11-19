"""Legacy quiz/card generation rules without legacy ORM or model-client imports."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from learn_core.db.models import Card, Knode
from learn_core.learning.prompts.quiz import SYSTEM as QUIZ_SYSTEM
from learn_core.learning.quizzes import create_quiz
from learn_core.review.scheduler import _now


class GeneratedQuestion(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    node_code: str = Field(min_length=1, max_length=32)
    qtype: Literal["choice", "fill", "short", "practice"]
    stem: str = Field(min_length=1, max_length=8000)
    options: list[str] = Field(default_factory=list, max_length=4)
    answer: str = Field(min_length=1, max_length=8000)
    explanation: str = Field(default="", max_length=8000)
    difficulty: int = Field(default=3, ge=1, le=5)

    @model_validator(mode="after")
    def validate_choice(self):
        if self.qtype == "choice":
            if len(self.options) != 4 or any(not o.strip() for o in self.options):
                raise ValueError("选择题必须提供四个有效选项")
            if self.answer.upper() not in {"A", "B", "C", "D"}:
                raise ValueError("选择题答案必须为 A/B/C/D")
            self.answer = self.answer.upper()
        elif self.options:
            raise ValueError("非选择题不能包含选项")
        return self


class GeneratedCard(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    front: str = Field(min_length=1, max_length=4000)
    back: str = Field(min_length=1, max_length=8000)
    card_type: Literal["basic", "cloze", "concept"] = "basic"


def parse_json(content: str):
    content = content.strip()
    if content.startswith("```") and content.endswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(content)


def selected_chapters(session: Session, *, project_id: int, node_ids: list[int]) -> list[dict]:
    nodes = list(session.scalars(select(Knode).where(
        Knode.project_id == project_id, Knode.id.in_(node_ids),
    ).order_by(Knode.id)))
    if len(nodes) != len(node_ids):
        raise ValueError("所选章节不存在或不属于当前学习计划")
    return [{"id": n.id, "code": n.code, "title": n.title,
             "description": n.description, "difficulty": n.difficulty,
             "contentVersion": n.content_version} for n in nodes]


def generation_prompt(kind: str, data: dict, options: dict) -> tuple[str, str]:
    chapters = data["chapters"]
    count = options["count"]
    if kind == "quiz":
        text = "\n".join(f"- [{n['code']}] {n['title']} (难度{n['difficulty']}): {n['description']}" for n in chapters)
        return QUIZ_SYSTEM, f"请为以下知识点出 {count} 道测验题。\n题型偏好：{options['qtype']}\n\n【知识点】\n{text}\n\n返回 {count} 题的 JSON 数组。"
    node = chapters[0]
    # Same schema/instructions as the old generate_cards_from_node.
    return "你是严谨的学习卡片编辑。只返回 JSON。", f"""请基于以下知识点内容，提炼 {count} 张用于间隔重复复习的卡片。
【知识点】{node['title']}
【内容】{node['description']}
返回 JSON：{{"cards":[{{"front":"问题","back":"答案","card_type":"basic|cloze|concept"}}]}}
只返回 JSON。"""


def validate_output(kind: str, content: str, data: dict, options: dict) -> list:
    result = parse_json(content)
    items = result if isinstance(result, list) else result.get("questions" if kind == "quiz" else "cards") if isinstance(result, dict) else None
    if not isinstance(items, list) or len(items) != options["count"]:
        raise ValueError("模型返回的数量不符合要求")
    if kind == "cards":
        cards = [GeneratedCard.model_validate(item) for item in items]
        if len({c.front for c in cards}) != len(cards):
            raise ValueError("复习卡片包含重复问题")
        return cards
    questions = [GeneratedQuestion.model_validate(item) for item in items]
    codes = {n["code"] for n in data["chapters"]}
    for q in questions:
        if q.node_code not in codes or (options["qtype"] != "mixed" and q.qtype != options["qtype"]):
            raise ValueError("题目超出所选范围或题型")
    return questions


def save_output(session: Session, *, project_id: int, kind: str, data: dict, items: list, options: dict | None = None) -> dict:
    if kind == "quiz":
        codes = {n["code"]: n["id"] for n in data["chapters"]}
        quiz = create_quiz(session, project_id=project_id, title=f"测验 ({len(items)}题)",
                           node_ids=list(codes.values()), quiz_type=(options or {}).get("qtype", "mixed"),
                           questions=[{**q.model_dump(exclude={"node_code"}), "node_id": codes[q.node_code]} for q in items])
        return {"quizId": quiz.id, "count": len(items)}
    ids = []
    for item in items:
        card = Card(project_id=project_id, node_id=data["chapters"][0]["id"],
                    **item.model_dump(), next_review=_now())
        session.add(card)
        session.flush()
        ids.append(card.id)
    return {"cardIds": ids, "count": len(ids)}
