from __future__ import annotations

from functools import partial
import html

import gradio as gr
from sqlmodel import Session
from ktem.db.engine import engine

from learning_ext.action_learning.service import ActionLearning, PLATFORMS, HELP_HOURLY_LIMIT, QUESTION_LIMIT
from learning_ext.db.models import KnowledgeNode, LearningProject
from learning_ext.progress.study import get_practice_task
from learning_ext.llm.client import friendly_error
from learning_ext.rich_text import render_rich_text


def escape(value):
    return html.escape(str(value or ""))


def action_card(state):
    index = state["index"]
    step = state["steps"][index]
    done = index in state["done"]
    return (
        f'<article class="le-action-card" data-le-step-active="true" data-le-focus="step" data-step="{index}">'
        f'<div class="le-action-kicker"><span>第 {index+1:02} 步</span><span>{"已自行完成" if done else "现在，做这一件事"}</span></div>'
        f'<h2>{escape(step["title"])}</h2><div class="le-action-instruction">{render_rich_text(step["action"], legacy_commands=True)}</div>'
        f'<div class="le-action-check"><span>做到什么算完成</span>{render_rich_text(step["check"])}</div>'
        f'<details class="le-action-source"><summary>对应原文</summary><blockquote>{render_rich_text(step["source"])}</blockquote></details>'
        '</article>'
    )


class ActionLearningPanel:
    def __init__(self, page):
        self.page = page
        self.service = ActionLearning()

    def build(self):
        self.state = gr.State(None)
        with gr.Row(elem_id="le-learning-mode"):
            gr.HTML('<div class="le-mode-intro"><span class="le-mode-icon" aria-hidden="true">↳</span><strong>一次，专心做一件事</strong></div>')
            self.learner_os = gr.Dropdown(label="练习使用的系统", choices=[(name, key) for key, name in PLATFORMS.items()],
                                         value=None, interactive=True, min_width=150, scale=0, elem_id="le-step-platform")
            self.entry = gr.Button("拆解步骤 →", elem_id="le-step-entry", scale=0)
        self.notice = gr.Markdown("", elem_id="le-step-notice")
        with gr.Column(visible=False, elem_id="le-action-learning") as self.panel:
            with gr.Row(elem_id="le-action-topbar"):
                self.meta = gr.HTML("")
                self.close = gr.Button("返回全文", size="sm", scale=0, elem_id="le-action-close")
            gr.HTML('<p class="le-action-boundary">请在自己的电脑完成操作；这里提供步骤、提示与自检标准。自行完成后，仍需做课程过关检查。</p>')
            self.previous = gr.Button("已经是第一步", elem_id="le-action-previous")
            self.card = gr.HTML("")
            with gr.Row(elem_id="le-action-tools"):
                self.hint = gr.Button("给我一点提示", size="sm")
                self.assist = gr.Button("问问 AI", size="sm")
                self.done = gr.Button("这一步我做完了 ✓", variant="primary", size="sm")
            self.help = gr.HTML("", elem_id="le-action-help")
            with gr.Column(visible=False, elem_id="le-action-assistant") as self.assistant:
                gr.HTML(f'<div class="le-action-assistant-title">步骤答疑 <span>只协助当前这一步 · 每小时最多{HELP_HOURLY_LIMIT}次</span></div>')
                with gr.Row():
                    self.question = gr.Textbox(placeholder=f"卡在哪里？请在{QUESTION_LIMIT}字以内描述，不要填写密钥。", show_label=False, scale=4, lines=2)
                    self.ask = gr.Button("问 AI", scale=0)
            self.next = gr.Button("下一步 ↓", elem_id="le-action-next")
        return self

    def register(self):
        self.outputs = [self.state, self.panel, self.notice, self.meta, self.previous,
                        self.card, self.next, self.help, self.assistant]
        inputs = [self.state, self.page.current_node_id, self.page.current_project_id,
                  self.page._app.user_id, self.question, self.learner_os]
        commands = [(self.entry, "start"), (self.close, "close"), (self.previous, "previous"),
                    (self.next, "next"), (self.hint, "hint"), (self.assist, "assist"),
                    (self.done, "done"), (self.ask, "ask")]
        for button, command in commands:
            button.click(partial(self.dispatch, command), inputs=inputs, outputs=self.outputs,
                         concurrency_id="action-learning", concurrency_limit=1, show_progress="hidden")
        self.question.submit(partial(self.dispatch, "ask"), inputs=inputs, outputs=self.outputs,
                             concurrency_id="action-learning", concurrency_limit=1, show_progress="hidden")
        for component, event in ((self.learner_os, "input"), (self.page.course_drop, "change"),
                                 (self.page.project_id, "input")):
            getattr(component, event)(partial(self.handle, "close"), inputs=inputs, outputs=self.outputs,
                                     concurrency_id="action-learning", concurrency_limit=1, show_progress="hidden")
        for tab_id, tab in self.page._app._tabs.items():
            if tab_id != "learning-workbench-tab":
                tab.select(partial(self.handle, "close"), inputs=inputs, outputs=self.outputs,
                           concurrency_id="action-learning", concurrency_limit=1, show_progress="hidden")

    def dispatch(self, command, state, *args):
        if command == "start":
            yield self.render({"loading": True}, "")
        elif command == "ask" and state and state.get("active"):
            yield self.render({**state, "help": "正在想怎么帮你完成这一步…"}, "")
        yield self.handle(command, state, *args)

    @staticmethod
    def context(node_id, project_id, owner, learner_os):
        if learner_os not in PLATFORMS:
            raise ValueError("请先选择你做练习使用的系统，再拆解步骤。")
        with Session(engine) as session:
            node = session.get(KnowledgeNode, int(node_id)) if node_id else None
            project = session.get(LearningProject, node.project_id) if node else None
            if not node or not project or project.user_id != owner or str(project.id) != str(project_id):
                raise ValueError("请先打开自己的课程。")
            if len(node.description or "") < 120:
                raise ValueError("本节内容还在准备，正文就绪后再拆解。")
            practice = get_practice_task(session, node.id)
            return dict(course=node.title, goal=project.goal, topic=project.topic, background=project.background,
                        lesson=node.description, practice=practice.description if practice else "", learner_os=learner_os)

    def handle(self, command, state, node, project, owner, question, learner_os):
        owner = str(owner or "default")
        state = state or {}
        notice = ""
        try:
            if command == "close":
                state.update(active=False, loading=False, assist=False, help="")
                return self.render(state, "")
            if command == "start":
                state.update(active=False, loading=False)
                context = self.context(node, project, owner, learner_os)
                state = self.service.start(owner, int(node), context)
                state.update(active=True, assist=False, help="")
            else:
                self.service.require(state, int(node) if node else None, owner)
                if not state.get("active") or state["context"]["learner_os"] != learner_os:
                    raise ValueError("课程或练习系统已变化，请重新拆解步骤。")
                if command in {"next", "previous"}:
                    self.service.move(state, 1 if command == "next" else -1)
                    state.update(help="", assist=False)
                elif command == "done":
                    self.service.complete(state)
                    notice = "已记录为自行完成。" if len(state["done"]) < len(state["steps"]) else "本节步骤已全部自行完成。返回全文后可做过关检查。"
                elif command == "hint":
                    state["help"] = self.service.hint(state)
                elif command == "assist":
                    state["assist"] = not state.get("assist", False)
                elif command == "ask":
                    state["help"] = self.service.help(state, question)
                else:
                    raise ValueError("此操作不可用，请使用课程步骤和提示。")
        except Exception as exc:
            if state.get("id"):
                self.service.journal.record(state, "request_failed", command=command, error=type(exc).__name__)
            notice = str(exc) if isinstance(exc, ValueError) else friendly_error(exc)
        return self.render(state, notice)

    @staticmethod
    def render(state, notice):
        active = state.get("active", False) and bool(state.get("steps"))
        loading = state.get("loading", False)
        index = state.get("index", 0)
        steps = state.get("steps", [])
        previous_index = ActionLearning.next_index(state, -1) if active else index
        next_index = ActionLearning.next_index(state, 1) if active else index
        prev = "↑ 上一条 · " + steps[previous_index]["title"] if active and previous_index != index else "已经是第一步"
        next_text = "下一条 · " + steps[next_index]["title"] + " ↓" if active and next_index != index else "已经是最后一步"
        platform = PLATFORMS.get(state.get("context", {}).get("learner_os"), "")
        meta = (f'<div class="le-action-progress"><strong>{escape(state["context"]["course"])}</strong>'
                f'<span>{escape(platform)} · {index+1} / {len(steps)} · 自行完成 {len(state["done"])} 步</span>'
                f'<progress value="{len(state["done"])}" max="{len(steps)}"></progress></div>') if active else ""
        card = action_card(state) if active else ""
        if loading:
            card = ('<section class="le-action-loading" data-le-focus="loading" role="status" aria-live="polite" aria-busy="true">'
                    '<span class="le-action-loader" aria-hidden="true"></span><h2>把这一节，变成可做的小步</h2>'
                    '<p>正在整理行动、提示与完成标准</p><div class="le-action-skeleton" aria-hidden="true"><i></i><i></i><i></i></div></section>')
        return (state, gr.update(visible=active or loading), notice, meta,
                gr.update(value=prev, interactive=active and previous_index != index), card,
                gr.update(value=next_text, interactive=active and next_index != index),
                render_rich_text(state["help"], legacy_commands=True) if state.get("help") else "",
                gr.update(visible=active and state.get("assist", False)))
