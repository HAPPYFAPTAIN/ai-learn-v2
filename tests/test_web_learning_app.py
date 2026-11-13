import ast
from pathlib import Path
from types import SimpleNamespace

import gradio as gr


ROOT = Path(__file__).resolve().parents[1]


def test_learning_tabs_do_not_register_standalone_coach(monkeypatch):
    import learning_ext.pages as pages
    built = []
    class Page:
        def __init__(self, app):
            self.app = app
        def on_building_ui(self):
            built.append(True)
    for name in ("DashboardPage", "PathGeneratorPage", "QuizPage", "ReviewPage", "StudyWorkbenchPage"):
        monkeypatch.setattr(pages, name, Page)
    source = ast.parse((ROOT / "learning_ext/app.py").read_text())
    app = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == "LearningApp")
    method = next(node for node in app.body if isinstance(node, ast.FunctionDef) and node.name == "_build_learning_tabs")
    namespace = {"gr": gr}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "app.py", "exec"), namespace)
    host = SimpleNamespace(_tabs={})
    with gr.Blocks(analytics_enabled=False) as blocks:
        with gr.Tabs():
            namespace["_build_learning_tabs"](host, True)
    labels = {item["props"].get("label") for item in blocks.get_config_file()["components"]}
    assert len(built) == 5
    assert {"学习路线", "学习工作台", "间隔复习", "查漏测验", "学习看板"} <= labels
    assert "动手学" not in labels and not hasattr(host, "coach_page")
    assert "learning-coach-tab" not in host._tabs
