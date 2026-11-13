from bs4 import BeautifulSoup
from learning_ext.db.models import KnowledgeNode
from learning_ext.progress import environment


def node(content=""):
    return KnowledgeNode(id=1, project_id=1, code="1.0", title="环境搭建：Python 与编辑器", description=content)


def test_reading_preserves_all_preparation_without_host_probes(monkeypatch):
    from learning_ext.practice import environment as probes
    monkeypatch.setattr(probes, "inspect_environment", lambda *a: (_ for _ in ()).throw(AssertionError("Host inspected")))
    content = "# 环境搭建\n\n### 安装 Python\n\n准备工具。\n\n### 创建项目\n\n```bash\nmkdir demo\n```"
    result = environment.adapt_reading(node(content), "Python", content)
    assert result.startswith("# 环境搭建\n")
    assert "自己的电脑" in result and "网站不会检测环境或执行命令" in result
    assert content.split("\n\n", 1)[1] in result
    assert "<details>" not in result and "已验证" not in result


def test_regular_lesson_is_not_rewritten():
    lesson = node()
    lesson.title = "条件语句"
    assert environment.adapt_reading(lesson, "Python", "课程正文") == "课程正文"


def test_both_generation_paths_request_self_checks_without_probes(monkeypatch):
    from learning_ext.progress import study
    from learning_ext.practice import environment as probes
    monkeypatch.setattr(probes, "inspect_environment", lambda *a: (_ for _ in ()).throw(AssertionError("Host inspected")))
    prompts = []
    monkeypatch.setattr(study, "chat", lambda prompt, **kwargs: prompts.append((prompt, kwargs["system"])) or "## 本节小结\n完成")
    study.generate_node_summary(node(), "Python", environment_context="需要 Python >=3.12")
    study.generate_practice_lesson(node(), "Python", environment_context="需要 Python >=3.12")
    for prompt, system in prompts:
        assert "供学习者自检" in prompt and "Python >=3.12" in prompt
        assert "网站没有检测学习者的电脑" in prompt
        assert "当前主机为" not in system


def test_lesson_rich_text_survives_gradio_updates():
    import asyncio
    asyncio.run(_exercise_gradio_updates())


async def _exercise_gradio_updates():
    import gradio as gr
    from gradio.state_holder import SessionState
    from learning_ext.lesson_component import LessonHTML
    with gr.Blocks() as app:
        trigger = gr.Button()
        lesson = LessonHTML()
        trigger.click(lambda: "", outputs=lesson)
    state = SessionState(app)
    fn = app.fns[0]
    for update in [gr.update(), gr.update(visible=True), gr.update(value="## 更新标题\n\n**重点**")]:
        await app.postprocess_data(fn, update, state)
        data = await app.postprocess_data(fn, "## 本节导览\n\n**重点**\n\n```python\nprint(1)\n```", state)
        soup = BeautifulSoup(data[0], "html.parser")
        assert soup.h2.text == "本节导览"
        assert soup.strong.text == "重点"
        assert soup.select_one(".le-code-copy")
        assert soup.select_one("code").text.strip() == "print(1)"
    assert lesson.get_block_name() == "html"
