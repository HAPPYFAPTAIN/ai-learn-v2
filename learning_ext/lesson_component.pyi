import gradio as gr

from learning_ext.rich_text import render_lesson

from gradio.events import Dependency

class LessonHTML(gr.HTML):
    is_template = True

    def postprocess(self, value):
        if isinstance(value, WaitingMessage):
            return str(value)
        return render_lesson(value) if value is not None else None
    from typing import Callable, Literal, Sequence, Any, TYPE_CHECKING
    from gradio.blocks import Block
    if TYPE_CHECKING:
        from gradio.components import Timer