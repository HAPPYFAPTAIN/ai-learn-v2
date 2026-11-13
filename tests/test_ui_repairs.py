import asyncio
import json
from types import SimpleNamespace

import gradio as gr
from bs4 import BeautifulSoup
from gradio.state_holder import SessionState

from learning_ext.pages.study_workbench import StudyWorkbenchPage


def test_question_cards_pair_stems_with_correct_controls_and_clear_old_answers():
    updates = StudyWorkbenchPage._gate_render_questions([
        {'stem': '选择第一项', 'qtype': 'choice', 'options': '["A. 第一项", "B. 第二项"]'},
        {'stem': '补全______', 'qtype': 'fill', 'options': ''},
    ])
    assert len(updates) == 12
    assert '选择第一项' in updates[1]
    assert updates[2]['choices'] == [('A. 第一项', 'A'), ('B. 第二项', 'B')]
    assert updates[2]['visible'] is True and updates[3]['visible'] is False
    assert '补全' in updates[5] and '\\_' in updates[5]
    assert updates[6]['visible'] is False and updates[7]['visible'] is True
    assert updates[7]['value'] == ''
    assert updates[8]['visible'] is False
    assert all(update['visible'] is False for update in StudyWorkbenchPage._gate_render_questions([])[::4])


def test_malformed_options_leave_an_editable_answer():
    updates = StudyWorkbenchPage._gate_render_questions([{'stem': '说明原因', 'options': 'not JSON'}])
    assert updates[2]['visible'] is False
    assert updates[3]['visible'] is True


def test_workbench_builds_and_registers_real_question_events():
    with gr.Blocks(analytics_enabled=False) as blocks:
        app = SimpleNamespace(app=blocks, user_id=gr.State('default'), _tabs={})
        page = StudyWorkbenchPage(app)
        page.on_building_ui()
        page.on_register_events()
    config = blocks.get_config_file()
    assert len(page.gate_questions) == 3
    for card, stem, choice, answer in page.gate_questions:
        assert isinstance(choice, gr.Radio) and isinstance(answer, gr.Textbox)
        assert answer.lines >= 3
        assert card.visible is False
    assert any(fn.fn == page._gate_render_questions for fn in blocks.fns.values())
    choice_fn = next(fn for fn in blocks.fns.values() if fn.inputs == [page.gate_questions[0][2]])
    state = SessionState(blocks)
    async def exercise():
        radio = page.gate_questions[0][2]
        radio.choices = [('A. 第一项', 'A'), ('B. 第二项', 'B')]
        result = await blocks.process_api(choice_fn, inputs=['B'], state=state)
        assert result['data'] == ['B']
    asyncio.run(exercise())
    assert any(item['props'].get('elem_id') == 'le-gate-recite-actions' for item in config['components'])


def test_loading_markup_survives_lesson_output_but_untrusted_html_stays_escaped():
    from learning_ext.lesson_component import LessonHTML
    from learning_ext.ui_feedback import WaitingMessage
    page = object.__new__(StudyWorkbenchPage)
    waiting = page._writing_placeholder(42, 'running')
    assert isinstance(waiting, WaitingMessage)
    with gr.Blocks(analytics_enabled=False):
        component = LessonHTML()
    soup = BeautifulSoup(component.postprocess(page._truncate_guide(waiting)), 'html.parser')
    assert soup.select_one('[data-le-wait-id="lesson-42"]')
    assert not soup.select_one('progress').has_attr('value')
    assert '30–60' not in soup.text
    unsafe = BeautifulSoup(component.postprocess('<script>alert(1)</script><section onclick="evil()">bad</section>'), 'html.parser')
    assert not unsafe.select('script,[onclick]')


def test_reading_wait_output_uses_gradio_postprocessing():
    from learning_ext.lesson_component import LessonHTML
    with gr.Blocks(analytics_enabled=False) as blocks:
        button = gr.Button('Read')
        component = LessonHTML()
        page = object.__new__(StudyWorkbenchPage)
        event = button.click(lambda: page._truncate_guide(page._writing_placeholder(7)), outputs=component)
    async def exercise():
        response = await blocks.process_api(event['id'], inputs=[], state=SessionState(blocks))
        assert 'data-le-wait-id="lesson-7"' in response['data'][0]
        assert '&lt;section' not in response['data'][0]
    asyncio.run(exercise())


def test_connection_edits_do_not_trigger_background_saves(monkeypatch):
    from learning_ext.pages import quick_setup as module
    config = dict(base_url='https://api.deepseek.com/v1', api_key='', chat_model='deepseek-chat', embed_model='')
    monkeypatch.setattr(module, '_read_env', lambda: config.copy())
    monkeypatch.setattr(module.connections, 'remember', lambda *args, **kwargs: None)
    monkeypatch.setattr(module.connections, 'connection_choices', lambda *args: [])
    monkeypatch.setattr(module.QuickSetupPage, '_build_status', lambda *args: 'summary')
    with gr.Blocks(analytics_enabled=False) as blocks:
        page = module.QuickSetupPage(SimpleNamespace(app=blocks))
        page.on_building_ui()
        page.on_register_events()
    saves = [fn for fn in blocks.fns.values() if fn.fn == page._remember]
    assert len(saves) == 2
    assert all('blur' not in [target[1] for target in fn.targets] for fn in saves)
    assert page.saved_connection.filterable is False
    assert page.provider.value == 'deepseek'


def test_old_course_questions_cannot_be_submitted_for_new_course():
    page = object.__new__(StudyWorkbenchPage)
    result = page._gate_submit(2, 'A', '', '', [{'node_id': 1, 'qtype': 'choice', 'answer': 'A'}])
    assert '课程已切换' in result[0]


def test_route_generator_streams_loading_and_final_components_through_gradio(monkeypatch):
    from learning_ext.pages import path_generator as module

    monkeypatch.setattr(module, 'generate_roadmap', lambda **kwargs: {'nodes': [{'code': '1.1', 'title': 'Python'}]})
    monkeypatch.setattr(module, 'audit_and_rewrite_roadmap', lambda **kwargs: {**kwargs['roadmap'], '_audit': {}})
    page = object.__new__(module.PathGeneratorPage)
    with gr.Blocks(analytics_enabled=False) as blocks:
        button = gr.Button('Generate')
        outputs = [gr.Markdown(), gr.Code(language='json'), gr.Markdown(), gr.HTML(), gr.Button(), gr.Button()]
        event = button.click(lambda: (yield from page._generate_preview('Python', '', '', 3)), outputs=outputs)

    async def exercise():
        state = SessionState(blocks)
        iterator = None
        stages = []
        for _ in range(6):
            result = await blocks.process_api(event['id'], inputs=[], state=state, iterator=iterator)
            iterator = result['iterator']
            if not result['is_generating']:
                break
            data = result['data']
            if data[3].get('visible'):
                panel = BeautifulSoup(data[3]['value'], 'html.parser').select_one('[data-le-stage]')
                stages.append(panel['data-le-stage'])
                assert data[4]['interactive'] is False
            else:
                assert json.loads(data[1])['nodes'][0]['title'] == 'Python'
                assert data[4]['interactive'] is True
        else:
            raise AssertionError('Route generation did not finish')
        assert stages == ['1', '2', '3']

    asyncio.run(exercise())
