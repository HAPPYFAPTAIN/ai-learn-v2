import hmac
import json
import os
from pathlib import Path
import secrets
import sys
import uuid


def enabled():
    return os.environ.get('LE_ISOLATED_WORKER') == '1'


def prepare():
    root=Path(os.environ['LE_WORKER_ROOT']).resolve()
    if root.stat().st_uid!=0 or (root/'data').stat().st_uid!=os.geteuid() or os.geteuid()==0:
        raise RuntimeError('Learning worker requires its isolated Unix account')
    for name in ['data','cache','tmp','home','workspace']:
        (root/name).mkdir(mode=0o700,exist_ok=True)
    os.environ.update(LE_APP_DATA_DIR=str(root/'data'),LE_CACHE_DIR=str(root/'cache'),
        GRADIO_TEMP_DIR=str(root/'tmp/gradio'),THEFLOW_TEMP_PATH=str(root/'tmp/theflow'),
        MPLCONFIGDIR=str(root/'cache/matplotlib'),XDG_CACHE_HOME=str(root/'cache'),
        NUMBA_CACHE_DIR=str(root/'cache/numba'),NLTK_DATA='/data/learn-everything/runtime/nltk',
        TIKTOKEN_CACHE_DIR=str(root/'cache/tiktoken'),
        THEFLOW_SETTINGS_MODULE='le_platform.settings',GRADIO_ANALYTICS_ENABLED='False',
        ANONYMIZED_TELEMETRY='False',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
        KH_ENABLE_FIRST_SETUP='False',KH_FEATURE_USER_MANAGEMENT='False',KH_GRADIO_SHARE='False')
    # flowsettings is an unchanged copy of the upstream file in this private cwd.
    sys.path.insert(0,os.getcwd())


def authenticated(request):
    if not enabled():return None
    key=request.headers.get('x-learn-worker-key','')
    owner=request.headers.get('x-learn-user','')
    if (hmac.compare_digest(key,os.environ['LE_WORKER_KEY'])
            and owner==os.environ['LE_OFFICIAL_USER']):return owner
    return None


def selected_model():
    path=Path(os.environ['LE_WORKER_ROOT'])/'data/model-selection.json'
    try:value=json.loads(path.read_text()).get('model')
    except (FileNotFoundError,ValueError):value=None
    return value or os.environ.get('OPENAI_CHAT_MODEL','deepseek-v4-pro')


def model_client():
    from openai import OpenAI
    return OpenAI(api_key=os.environ['OPENAI_API_KEY'],base_url=os.environ['OPENAI_API_BASE'],
        timeout=120,max_retries=0,default_headers={
            'X-End-User':os.environ['LE_OFFICIAL_USER'],'X-Event-Id':'learn-'+uuid.uuid4().hex})


def model_config():
    return {'api_key':os.environ['OPENAI_API_KEY'],'base_url':os.environ['OPENAI_API_BASE'],
        'chat_model':selected_model(),'embed_model':''}


def terminal_model_error(error):
    seen=set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if getattr(error,'status_code',None) in {400,401,402,403,404,422,507}:return True
        error=error.__cause__ or error.__context__
    return False


def model_error_message(error):
    seen=set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if getattr(error,'status_code',None)==507:return '5 GB个人学习空间已满，请在空间管理中下载或删除文件后继续。'
        if getattr(error,'status_code',None)==402:return '官网账号积分不足，请充值后继续学习。'
        if getattr(error,'status_code',None) in {401,403}:return '当前账号暂时不能调用这个模型，请刷新可用模型或联系平台。'
        error=error.__cause__ or error.__context__
    return '模型请求未能完成，请检查所选模型后重试。'


def register_routes(app,learning_app=None):
    from contextlib import asynccontextmanager
    from fastapi import Request
    from fastapi.responses import JSONResponse

    original_lifespan=app.router.lifespan_context

    @asynccontextmanager
    async def isolated_lifespan(application):
        async with original_lifespan(application) as state:
            # Gradio's unauthenticated loopback startup request is deliberately
            # rejected by our transport gate. Start its real queue on this loop.
            if not application.startup_events_triggered:
                application.get_blocks().startup_events()
                application.startup_events_triggered=True
            yield state

    app.router.lifespan_context=isolated_lifespan
    if learning_app is not None:
        from le_platform.storage_api import register
        register(app,learning_app)

    @app.middleware('http')
    async def isolated_transport(request:Request,call_next):
        if authenticated(request) is None:return JSONResponse({'detail':'未登录或工作空间不匹配'},status_code=401)
        if request.url.path.startswith('/file='):
            requested=request.url.path.removeprefix('/file=')
            try:
                path=Path(requested).resolve()
                release=Path(os.environ['LE_PLATFORM_RELEASE'])
                allowed=[Path(os.environ['LE_WORKER_ROOT']).resolve(),
                    (release/'source/learning_ext/assets').resolve(),
                    (release/'source/kotaemon/libs/ktem/ktem/assets').resolve()]
                if not any(path.is_relative_to(root) for root in allowed):raise ValueError('Outside account')
            except (ValueError,OSError):
                return JSONResponse({'detail':'无权访问这份文件'},status_code=403)
        return await call_next(request)

    @app.get('/api/v1/account/context')
    def context():
        return {'api_version':1,'mode':'server','connection':{'configured':True,'status':'connected'},
            'storage':{'managed':True,'initialQuotaBytes':5*1024**3},
            'capabilities':{'interactive_sign_in':False,'multi_user_ui':True},
            'identity':{'user':{'id':os.environ['LE_OFFICIAL_USER'],'display_name':'官网用户'},
                'workspace':{'id':os.environ['LE_OFFICIAL_USER'],'name':'个人学习空间'},
                'source':'server','capabilities':{'learning':True,'cloud_sync':False,'manage_members':False}}}

    @app.get('/platform/activity')
    def activity():
        from learning_ext.llm.client import _REQUEST_SLOT
        from learning_ext.progress.prep import has_pending
        return {'busy':_REQUEST_SLOT.busy() or has_pending()}


def tool_allowed(name):
    return name in {'ask_user','update_plan','web_search','search_web','fetch_url','list_dir','read_file','write_file'}


def execute_tool(name,args,handler):
    if not tool_allowed(name):return '网页版不直接操作本机桌面或安装软件；可在桌面端使用这项能力。'
    args=dict(args)
    if name in {'list_dir','read_file','write_file'}:
        root=(Path(os.environ['LE_WORKER_ROOT'])/'workspace').resolve()
        field='path'
        path=Path(str(args.get(field,'.'))).expanduser()
        path=(root/path).resolve() if not path.is_absolute() else path.resolve()
        if not path.is_relative_to(root):return '只能访问当前账号学习空间中的文件。'
        args[field]=str(path)
        if name=='write_file':
            from le_platform.storage import ensure_capacity
            ensure_capacity(Path(os.environ['LE_WORKER_ROOT']),len(str(args.get('content','')).encode()))
    return handler(**args)
