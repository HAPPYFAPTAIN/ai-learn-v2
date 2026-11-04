from flowsettings import *  # noqa: F403
import os

from le_platform.worker import selected_model

KH_APP_NAME='Learn Everything · 以太智元'
KH_ENABLE_FIRST_SETUP=False
KH_FEATURE_USER_MANAGEMENT=False
KH_GRADIO_SHARE=False
KH_LLMS={'openai':{'spec':{'__type__':'le_platform.chat.GatewayChat',
    'base_url':os.environ['OPENAI_API_BASE'],'api_key':'server-managed',
    'model':selected_model(),'temperature':0.3,'timeout':120},'default':True}}
KH_EMBEDDINGS={'local':{'spec':{'__type__':'le_platform.embeddings.LocalEmbeddings',
    'model_name':os.environ.get('LE_EMBED_MODEL','sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')},'default':True}}
KH_RERANKINGS={'llm':{'spec':{'__type__':'kotaemon.indices.rankings.LLMReranking','concurrent':False},'default':True}}
SETTINGS_REASONING={**SETTINGS_REASONING,'lang':{**SETTINGS_REASONING['lang'],'value':'zh'}}  # noqa: F405
