import json
import os
from pathlib import Path

import gradio as gr
from ktem.app import BasePage
from le_platform.worker import model_client,selected_model


class PlatformModelsPage(BasePage):
    def on_building_ui(self):
        gr.Markdown('## 模型配置\n模型由平台统一提供，使用当前官网账号积分。')
        self.model=gr.Dropdown(label='调用模型',choices=[],allow_custom_value=False)
        self.refresh=gr.Button('刷新可用模型')
        self.status=gr.Markdown('正在读取可用模型…')
        gr.Markdown('网页版支持学习路线、资料问答、复习、测验和导出。操作本机桌面、剪贴板及安装环境需使用桌面端。')

    def on_register_events(self):
        def refresh():
            try:
                with model_client() as client:models=sorted(row.id for row in client.models.list().data)
                current=selected_model()
                if models and current not in models:
                    current=models[0]
                    path=Path(os.environ['LE_WORKER_ROOT'])/'data/model-selection.json'
                    path.write_text(json.dumps({'model':current}));path.chmod(0o600)
                return gr.update(choices=models,value=current if current in models else next(iter(models),None)), '可用模型已更新。'
            except Exception:
                return gr.update(choices=[],value=None),'暂时无法读取可用模型，请稍后重试。'

        def choose(value):
            with model_client() as client:allowed={row.id for row in client.models.list().data}
            if value not in allowed:raise gr.Error('所选模型当前不可用。')
            path=Path(os.environ['LE_WORKER_ROOT'])/'data/model-selection.json'
            temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps({'model':value}));temporary.chmod(0o600);temporary.replace(path)
            return '调用模型已更新。'
        self._app.app.load(refresh,outputs=[self.model,self.status])
        self.refresh.click(refresh,outputs=[self.model,self.status])
        self.model.input(choose,inputs=[self.model],outputs=[self.status])
