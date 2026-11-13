import asyncio
from types import SimpleNamespace

import gradio as gr
from gradio.state_holder import SessionState

from learning_ext.db.models import LearningProject
from learning_ext.pages import study_workbench as module


def test_workbench_empty_state_follows_saved_plans_through_gradio(session, monkeypatch):
    monkeypatch.setattr(module, "engine", session.get_bind())
    with gr.Blocks(analytics_enabled=False) as blocks:
        page = module.StudyWorkbenchPage(SimpleNamespace(app=blocks, user_id=gr.State("default"), _tabs={}))
        page.on_building_ui()
        page.on_register_events()
    state = SessionState(blocks)
    handlers = [fn for fn in blocks.fns.values() if fn.fn == page._workbench_visibility]
    assert any((page.project_id._id, "change") in fn.targets for fn in handlers)
    assert any(any(event == "load" for _, event in fn.targets) for fn in handlers)

    async def display():
        result = await blocks.process_api(handlers[0], inputs=[], state=state)
        return [update["visible"] for update in result["data"]]

    assert asyncio.run(display()) == [True, False]
    plan = LearningProject(user_id="default", topic="学习 Python")
    session.add(plan)
    session.commit()
    assert asyncio.run(display()) == [False, True]
    session.delete(plan)
    session.commit()
    assert asyncio.run(display()) == [True, False]


def test_failed_plan_query_does_not_claim_there_are_no_plans(monkeypatch):
    def unavailable(*args):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(module, "Session", unavailable)
    page = module.StudyWorkbenchPage(SimpleNamespace())
    empty, workbench = page._workbench_visibility()
    assert empty["visible"] is False
    assert workbench["visible"] is True
