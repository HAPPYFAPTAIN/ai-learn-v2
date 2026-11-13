import asyncio
from types import SimpleNamespace

import gradio as gr
import pytest
from gradio.state_holder import SessionState

from learning_ext.db.models import LearningProject
from learning_ext.pages import quiz, review


@pytest.mark.parametrize("module,page_type,project_attr,refresh_attr", [
    (review, review.ReviewPage, "project", "refresh"),
    (quiz, quiz.QuizPage, "project_id", "goal_refresh"),
])
def test_goal_page_empty_state_and_return_refresh(session, monkeypatch, module, page_type, project_attr, refresh_attr):
    monkeypatch.setattr(module, "engine", session.get_bind())
    with gr.Blocks(analytics_enabled=False) as blocks:
        page = page_type(SimpleNamespace(app=blocks))
        page.on_building_ui()
        page.on_register_events()
    state = SessionState(blocks)
    project = getattr(page, project_attr)
    bridge = getattr(page, refresh_attr)
    visibility = [fn for fn in blocks.fns.values() if fn.fn == page._goal_visibility]
    assert any((project._id, "change") in fn.targets for fn in visibility)
    assert any(any(event == "load" for _, event in fn.targets) for fn in visibility)
    refresh = next(fn for fn in blocks.fns.values() if (bridge._id, "click") in fn.targets)

    async def call(fn, inputs):
        return (await blocks.process_api(fn, inputs=inputs, state=state))["data"]

    def display():
        return [update["visible"] for update in asyncio.run(call(visibility[0], []))]

    session.add(LearningProject(user_id="someone-else", topic="其他人的目标"))
    session.commit()
    assert display() == [True, False]
    first = LearningProject(user_id="default", topic="第一个目标")
    session.add(first)
    session.commit()
    assert display() == [False, True]
    updates = asyncio.run(call(refresh, [None]))
    assert updates[0]["value"] == str(first.id)
    second = LearningProject(user_id="default", topic="第二个目标")
    session.add(second)
    session.commit()
    updates = asyncio.run(call(refresh, [str(first.id)]))
    assert updates[0]["value"] == str(first.id)
    if module is review:
        assert "value" not in updates[1]
    session.delete(first)
    session.delete(second)
    session.commit()
    assert display() == [True, False]
    updates = asyncio.run(call(refresh, [None]))
    assert updates[0]["choices"] == []
    assert updates[0]["value"] is None


@pytest.mark.parametrize("module,page_type", [(review, review.ReviewPage), (quiz, quiz.QuizPage)])
def test_failed_goal_query_does_not_report_empty(monkeypatch, module, page_type):
    def unavailable(*args):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(module, "Session", unavailable)
    page = page_type(SimpleNamespace())
    empty, flow = page._goal_visibility()
    assert empty["visible"] is False
    assert flow["visible"] is True
