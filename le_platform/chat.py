import os
import uuid

from kotaemon.llms import ChatOpenAI
from le_platform.worker import selected_model


class GatewayChat(ChatOpenAI):
    def prepare_params(self,**kwargs):
        from learning_ext import chat_thinking
        model=selected_model()
        kwargs['model']=model
        kwargs.pop('reasoning_effort',None)
        effort=chat_thinking.effort_for(model,chat_thinking.current_preferences()['effort'])
        if effort:kwargs['reasoning_effort']=effort
        # Upstream message/provider/reasoning compatibility must see the model
        # selected for this request, before it removes unsupported parameters.
        return super().prepare_params(**kwargs)

    def prepare_client(self,async_version=False):
        from le_platform.storage import ensure_capacity
        ensure_capacity(os.environ['LE_WORKER_ROOT'])
        from openai import OpenAI,AsyncOpenAI
        return (AsyncOpenAI if async_version else OpenAI)(
            api_key=os.environ['OPENAI_API_KEY'],base_url=os.environ['OPENAI_API_BASE'],
            timeout=self.timeout,max_retries=self.max_retries_,default_headers={
                'X-End-User':os.environ['LE_OFFICIAL_USER'],'X-Event-Id':'learn-'+uuid.uuid4().hex})
