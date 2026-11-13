from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager

from learning_ext.llm import chat, chat_json
from .prompts import DECOMPOSE, HELP

PLATFORMS = {"windows": "Windows", "macos": "macOS", "linux": "Linux"}
HELP_COOLDOWN = 10
HELP_HOURLY_LIMIT = 20
QUESTION_LIMIT = 1000

LOG_PATH = Path(os.getenv('LE_APP_DATA_DIR',str(Path(__file__).resolve().parents[2] / 'output/runtime'))) / 'action-learning.sqlite3'


def redact(text):
    text = str(text)
    text = re.sub(r"(?i)(?:sk-|Bearer\s+)[\w.\-]{8,}", "[已隐藏密钥]", text)
    return re.sub(r"(?i)((?:api[_ -]?key|token|password|密码|密钥)\s*[:=]\s*)[^\s,;]+", r"\1[已隐藏]", text)


def scrub(value):
    if isinstance(value, dict):
        sensitive = {"apikey", "token", "accesstoken", "refreshtoken", "password", "passwd", "secret", "clientsecret", "authorization", "cookie", "setcookie", "密码", "密钥"}
        return {key: "[已隐藏]" if re.sub(r"[\s_-]", "", str(key)).lower() in sensitive else scrub(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return redact(value) if isinstance(value, str) else value


class Journal:
    def __init__(self, path=LOG_PATH):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=15)
        db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, owner TEXT, node INTEGER, fingerprint TEXT, data TEXT, updated REAL)")
        db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, time REAL, session TEXT, node INTEGER, step INTEGER, event TEXT, details TEXT)")
        db.execute("CREATE INDEX IF NOT EXISTS sessions_owner_node ON sessions(owner,node,fingerprint,updated DESC)")
        db.execute("CREATE INDEX IF NOT EXISTS events_session_usage ON events(session,event,time)")
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, state, event, **details):
        details.setdefault("trace_id", state.get("id", ""))
        with self.connect() as db:
            db.execute("INSERT INTO events(time,session,node,step,event,details) VALUES(?,?,?,?,?,?)", (
                time.time(), state.get("id", ""), state.get("node"), state.get("index", 0), event,
                json.dumps(scrub(details), ensure_ascii=False),
            ))

    def save(self, state):
        data = {key: state[key] for key in ("id", "owner", "node", "fingerprint", "steps", "index", "done")}
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO sessions VALUES(?,?,?,?,?,?)", (
                state["id"], state["owner"], state["node"], state["fingerprint"],
                json.dumps(data, ensure_ascii=False), time.time(),
            ))

    def resume(self, owner, node, fingerprint):
        with self.connect() as db:
            row = db.execute("SELECT data FROM sessions WHERE owner=? AND node=? AND fingerprint=? ORDER BY updated DESC LIMIT 1", (owner, node, fingerprint)).fetchone()
        return json.loads(row[0]) if row else None

    def reserve_help(self, state, question):
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count, latest = db.execute(
                "SELECT count(*), max(events.time) FROM events JOIN sessions ON events.session=sessions.id "
                "WHERE sessions.owner=? AND events.event='ai_help_requested' AND events.time>?",
                (state["owner"], now - 3600),
            ).fetchone()
            if latest is not None and now - latest < HELP_COOLDOWN:
                raise ValueError(f"提问太快了，请等待 {HELP_COOLDOWN} 秒后再试。")
            if count >= HELP_HOURLY_LIMIT:
                raise ValueError(f"本小时已发起 {HELP_HOURLY_LIMIT} 次步骤答疑，请稍后再试；预设提示仍可查看。")
            db.execute("INSERT INTO events(time,session,node,step,event,details) VALUES(?,?,?,?,?,?)", (
                now, state["id"], state["node"], state["index"], "ai_help_requested",
                json.dumps(scrub({"question": question}), ensure_ascii=False),
            ))


def source_excerpts(context):
    source = context["lesson"] + "\n\n" + context.get("practice", "")
    return [block.strip()[:700] for block in re.split(r"\n\s*\n", source) if len(block.strip()) > 12]


def validate_steps(result, source, sources=None):
    steps = result.get("steps") if isinstance(result, dict) else None
    if not isinstance(steps, list) or not 4 <= len(steps) <= 20:
        raise ValueError("拆解结果不完整，请重试。")
    clean = []
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("步骤格式无效，请重试。")
        if sources is not None:
            index = step.get("source_index")
            if type(index) is not int or not 0 <= index < len(sources):
                raise ValueError("有一步缺少原文依据，请重新拆解。")
            step = {**step, "source": sources[index]}
        item = {}
        for key, limit in (("title", 100), ("action", 2400), ("check", 600), ("hint", 1000), ("source", 1200)):
            value = step.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise ValueError("步骤内容过长或缺少完成标准，请重试。")
            item[key] = value.strip()
        if item["source"] not in source:
            raise ValueError("有一步缺少原文依据，请重新拆解。")
        clean.append(item)
    return clean


def model_context(context, *, help_request=False):
    limits = {"course": 200, "topic": 200, "goal": 1000, "background": 1000,
              "lesson": 8000 if help_request else 18000, "practice": 2000 if help_request else 4000}
    return {**{key: str(context.get(key, ""))[:limit] for key, limit in limits.items()},
            "learner_os": PLATFORMS[context["learner_os"]]}


class ActionLearning:
    def __init__(self, journal=None):
        self.journal = journal or Journal()

    def start(self, owner, node, context):
        if context.get("learner_os") not in PLATFORMS:
            raise ValueError("请先选择你做练习使用的系统。")
        fingerprint = hashlib.sha256(json.dumps(
            {"version": "web-steps-v1", "context": context}, sort_keys=True, ensure_ascii=False,
        ).encode()).hexdigest()
        state = self.journal.resume(owner, node, fingerprint)
        if state:
            state.update(context=context)
            self.journal.record(state, "resume")
            return state
        state = dict(id=uuid.uuid4().hex, owner=owner, node=node, fingerprint=fingerprint,
                     context=context, index=0, done=[])
        self.journal.record(state, "decompose_started")
        try:
            bounded = model_context(context)
            sources = source_excerpts(bounded)
            result = chat_json(json.dumps(dict(context=bounded,
                sources=[dict(index=i, text=excerpt) for i, excerpt in enumerate(sources)]),
                ensure_ascii=False), system=DECOMPOSE, purpose="coach")
            state["steps"] = validate_steps(result, context["lesson"] + "\n" + context.get("practice", ""), sources)
        except Exception as exc:
            self.journal.record(state, "decompose_failed", error=type(exc).__name__)
            raise
        self.journal.save(state)
        self.journal.record(state, "decompose_completed", count=len(state["steps"]))
        return state

    @staticmethod
    def next_index(state, delta):
        return max(0, min(state["index"] + delta, len(state["steps"]) - 1))

    @staticmethod
    def require(state, node, owner):
        if not state or state.get("node") != node or state.get("owner") != owner:
            raise ValueError("课程已变化，请重新进入逐步行动。")

    def move(self, state, delta):
        state["index"] = self.next_index(state, delta)
        self.journal.save(state)
        self.journal.record(state, "navigate", direction=delta)
        return state

    def complete(self, state):
        if state["index"] not in state["done"]:
            state["done"].append(state["index"])
        self.journal.save(state)
        self.journal.record(state, "self_reported_complete", verified=False)
        return state

    def hint(self, state):
        self.journal.record(state, "hint")
        return state["steps"][state["index"]]["hint"]

    def help(self, state, question):
        question = str(question or "").strip() or "我该怎么开始这一步？"
        if len(question) > QUESTION_LIMIT:
            raise ValueError(f"请将问题控制在 {QUESTION_LIMIT} 字以内。")
        self.journal.reserve_help(state, question)
        answer = chat(json.dumps(dict(context=model_context(state["context"], help_request=True),
            current=state["steps"][state["index"]], question=question), ensure_ascii=False),
            system=HELP, purpose="coach", max_tokens=800)
        self.journal.record(state, "ai_help_result", answer=answer)
        return answer
