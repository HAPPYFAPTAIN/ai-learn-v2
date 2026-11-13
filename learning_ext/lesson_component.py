import gradio as gr

from learning_ext.rich_text import render_lesson
from learning_ext.ui_feedback import WaitingMessage


class LessonHTML(gr.HTML):
    is_template = True

    def postprocess(self, value):
        if isinstance(value, WaitingMessage):
            return str(value)
        return render_lesson(value) if value is not None else None
