import pytest
from learning_ext.db.models import LearningProject, Task


@pytest.fixture
def setup_case(session, monkeypatch):
    import learning_ext.pages.study_workbench as page
    monkeypatch.setattr(page, "engine", session.get_bind())
    project = LearningProject(user_id="alice", topic="setup")
    session.add(project)
    session.commit()
    task = Task(project_id=project.id, title="工具准备", task_type="env", description="检查 Python 版本。\n\n```bash\npython3 --version\n```", status="todo")
    session.add(task)
    session.commit()
    return page.StudyWorkbenchPage.__new__(page.StudyWorkbenchPage), project.id, task


def test_manual_checklist_is_readable_without_model_or_execution(session, monkeypatch, setup_case):
    from bs4 import BeautifulSoup
    from learning_ext.practice import auto_setup
    page, pid, task = setup_case
    monkeypatch.setattr(auto_setup, "generate_install_commands", lambda *a: pytest.fail("Must not generate commands"))
    monkeypatch.setattr(auto_setup, "run_all_commands", lambda *a, **k: pytest.fail("Must not execute commands"))
    source, display = page._load_env(session, pid)
    assert source == task.description
    assert "python3 --version" in BeautifulSoup(display, "html.parser").get_text() and "le-code-copy" in display
    assert "网站不会检测电脑或执行命令" in display
    result = page._apply_env(pid, "alice")
    assert "已自行确认" in result and "过关检查" in result
    session.refresh(task)
    assert task.status == "done"


def test_other_owner_cannot_confirm_preparation(session, setup_case):
    page, pid, task = setup_case
    result = page._apply_env(pid, "bob")
    assert "自己的学习项目" in result
    session.refresh(task)
    assert task.status == "todo"


def test_manual_checklist_escapes_untrusted_markup(setup_case):
    page, _, task = setup_case
    task.description = '<img src=x onerror="alert(1)">'
    display = page._manual_env_view(task)
    assert '<img' not in display and '&lt;img' in display


def test_workbench_has_no_installation_endpoints():
    import gradio as gr
    from unittest.mock import MagicMock
    from learning_ext.pages.study_workbench import StudyWorkbenchPage
    with gr.Blocks(analytics_enabled=False) as blocks:
        page = StudyWorkbenchPage(MagicMock())
        page.on_building_ui()
    ids = {component["props"].get("elem_id") for component in blocks.get_config_file()["components"]}
    assert "le-env-confirm" in ids and "le-env-status" in ids
    assert not ids & {"le-env-execute", "le-env-generate", "le-env-log"}
    assert not hasattr(page, "_execute_setup") and not hasattr(page, "_prepare_setup")
