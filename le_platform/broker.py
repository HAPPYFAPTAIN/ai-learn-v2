"""Bounded account workers behind the existing official-site entitlement gate."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass,field
import hashlib
import importlib.util
import fcntl
import json
import logging
import os
from pathlib import Path
import pwd
import re
import secrets
import shutil
import socket
import time
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse,HTMLResponse,JSONResponse,StreamingResponse
from starlette.background import BackgroundTask

ROOT=Path(os.environ.get('LE_PLATFORM_STATE','/data/learn-everything'))
RELEASE=Path(os.environ['LE_PLATFORM_RELEASE'])
PYTHON=os.environ['LE_PLATFORM_PYTHON']
PREFIX='/official/learn-everything'
UID_RE=re.compile(r'[A-Za-z0-9_-]{1,80}')
HOP={'host','connection','content-length','transfer-encoding','keep-alive','upgrade','proxy-authorization','proxy-authenticate'}


async def command(*argv,timeout=30):
    process=await asyncio.create_subprocess_exec(*argv,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:
        stdout,stderr=await asyncio.wait_for(process.communicate(),timeout)
    except BaseException:
        if process.returncode is None:process.kill()
        await process.wait()
        raise
    if process.returncode:
        detail=(stderr or stdout).decode(errors='replace')[:1200]
        raise RuntimeError(f'Learning worker service operation failed (exit {process.returncode}): '+detail)
    return stdout.decode().strip()


def platform_directory(path,mode):
    """Set exact bootstrap access without weakening the broker's private umask.

    New directories inherit UMask=0077. Reconcile only platform-owned
    boundaries; customer data directories retain their own UID and 0700 mode.
    """
    path.mkdir(mode=mode,exist_ok=True)
    descriptor=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        if os.fstat(descriptor).st_uid!=0:raise RuntimeError('Learning bootstrap must be platform-owned')
        os.fchmod(descriptor,mode)
    finally:os.close(descriptor)


@dataclass
class Worker:
    owner:str
    port:int
    key:str
    unit:str
    active:int=0
    last:float=0
    upload_pending:int=0
    upload_lock:asyncio.Lock=field(default_factory=asyncio.Lock)


class Workers:
    def __init__(self):
        self.items={};self.starts={};self.retiring={};self.units={};self.lock=asyncio.Lock();self.launch=asyncio.Semaphore(1)
        self.limit=int(os.environ.get('LE_MAX_WORKERS','2'));self.closing=False
        self.idle_ttl=int(os.environ.get('LE_IDLE_TTL_SECONDS','900'));self.pressure_until=0
        if not 300<=self.idle_ttl<=3600:raise ValueError('LE_IDLE_TTL_SECONDS must be between 300 and 3600')
        self.client=httpx.AsyncClient(trust_env=False,timeout=httpx.Timeout(180,connect=5),limits=httpx.Limits(max_connections=80))

    async def stop(self,worker):
        try:await command('systemctl','stop',worker.unit,timeout=30)
        except RuntimeError:pass
        state=await command('systemctl','show',worker.unit,'--property=ActiveState','--value')
        if state not in {'inactive','failed',''}:raise RuntimeError('Prior learning worker did not exit')
        if self.units.get(worker.owner)==worker.unit:
            self.units.pop(worker.owner);self.save_units()

    def save_units(self):
        path=ROOT/'private/units.json';temporary=path.with_suffix('.tmp')
        fd=os.open(temporary,os.O_CREAT|os.O_TRUNC|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as stream:json.dump(self.units,stream)
        os.replace(temporary,path)

    async def recover(self):
        path=ROOT/'private/units.json'
        if not path.exists():return
        info=path.lstat()
        if path.is_symlink() or info.st_uid!=0 or info.st_mode&0o077:raise RuntimeError('Private worker registry required')
        self.units=json.loads(path.read_text())
        for owner,unit in list(self.units.items()):
            if not re.fullmatch(r'aethericai-learn-le_[a-f0-9]{20}-[a-f0-9]{10}\.service',unit):
                raise RuntimeError('Unknown recovery unit')
            await self.stop(Worker(owner,0,'',unit))

    async def acquire(self,owner,wait=True):
        async with self.lock:
            if self.closing:raise HTTPException(503,'学习工作台正在更新，请稍后重试。')
            worker=self.items.get(owner)
            if worker:
                worker.active+=1;worker.last=time.monotonic();return worker
            start=self.starts.get(owner)
            if owner in self.retiring:raise HTTPException(503,'学习空间正在准备，请稍后重试。')
            if start is None:
                if len(self.items)+len(self.starts)+len(self.retiring)>=self.limit:
                    self.pressure_until=time.monotonic()+60
                    raise HTTPException(503,'学习工作空间繁忙，请稍后重试。',headers={'X-Learn-Error':'CAPACITY_BUSY'})
                start=asyncio.create_task(self.start(owner));self.starts[owner]=start
                # HTML requests return before startup; consume failures even if all browsers leave.
                start.add_done_callback(lambda task:None if task.cancelled() else task.exception())
            if not wait:return None
        try:worker=await asyncio.shield(start)
        except asyncio.CancelledError:raise
        except Exception:
            raise HTTPException(503,'学习工作空间暂时无法启动，请稍后重试。',headers={'X-Learn-Error':'STARTUP_FAILED'}) from None
        async with self.lock:
            if self.closing:raise HTTPException(503,'学习工作台正在更新。')
            worker.active+=1;worker.last=time.monotonic();return worker

    async def startup_state(self,owner):
        async with self.lock:
            if self.closing:return 'failed'
            if owner in self.items:return 'ready'
            if owner in self.starts:return 'starting'
            return 'failed'

    async def start(self,owner):
        worker=None
        try:
            async with self.launch:
                parent=os.environ.get('LE_BROKER_UNIT','')
                if not re.fullmatch(r'(?:learn-candidate-[a-f0-9]{12}|aethericai-learn)\.service',parent):
                    raise RuntimeError('Learning worker requires an owned broker unit')
                name='le_'+hashlib.sha256(owner.encode()).hexdigest()[:20]
                home=ROOT/'users'/name
                platform_directory(ROOT,0o711)
                platform_directory(home.parent,0o711)
                try:user=pwd.getpwnam(name)
                except KeyError:
                    await command('useradd','--system','--home-dir',str(home/'home'),'--shell','/usr/sbin/nologin',name)
                    user=pwd.getpwnam(name)
                if home.is_symlink():raise RuntimeError('Linked learning home')
                platform_directory(home,0o711)
                for child in ['home','data','workspace','cache','tmp','downloads']:
                    path=home/child
                    if path.is_symlink():raise RuntimeError('Linked learning state')
                    path.mkdir(mode=0o700,exist_ok=True);os.chown(path,user.pw_uid,user.pw_gid);os.chmod(path,0o700)
                work=home/'work'
                platform_directory(work,0o755)
                if (work/'flowsettings.py').is_symlink():raise RuntimeError('Linked bootstrap settings')
                shutil.copyfile(RELEASE/'source/kotaemon/flowsettings.py',work/'flowsettings.py')
                (work/'flowsettings.py').chmod(0o644)
                for link,target in [('libs',RELEASE/'source/kotaemon/libs'),('docs',RELEASE/'source/kotaemon/docs'),
                        ('ktem_app_data',home/'data'),('.theflow',home/'cache')]:
                    path=home/'work'/link
                    if path.is_symlink():
                        if path.resolve()!=target.resolve():
                            prior=path.readlink()
                            if link not in {'libs','docs'} or not prior.is_relative_to(RELEASE.parent):
                                raise RuntimeError('Learning source link drift')
                            temporary=path.with_name(path.name+'.next');temporary.symlink_to(target,target_is_directory=True);os.replace(temporary,path)
                    elif path.exists():raise RuntimeError('Unexpected learning runtime source')
                    else:path.symlink_to(target,target_is_directory=True)
                with socket.socket() as reserve:reserve.bind(('127.0.0.1',0));port=reserve.getsockname()[1]
                key=secrets.token_urlsafe(48);unit='aethericai-learn-'+name+'-'+secrets.token_hex(5)+'.service'
                worker=Worker(owner,port,key,unit,last=time.monotonic())
                env={k:v for k,v in os.environ.items() if k in {'OPENAI_API_KEY','OPENAI_API_BASE','OPENAI_CHAT_MODEL','LE_EMBED_MODEL','LE_EMBEDDING_PATH','FASTEMBED_CACHE_PATH'}}
                env.update(HOME=str(home/'home'),LE_PLATFORM_RELEASE=str(RELEASE),LE_WORKER_ROOT=str(home),LE_OFFICIAL_USER=owner,LE_WORKER_KEY=key,
                    LE_ISOLATED_WORKER='1',LE_SERVER_MODE='1',LE_SERVER_NAME='127.0.0.1',LE_SERVER_PORT=str(port),
                    LE_ROOT_PATH=PREFIX,PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1',
                    PYTHONPATH=':'.join(map(str,[home/'work',RELEASE/'platform',RELEASE/'source',RELEASE/'source/kotaemon',
                        RELEASE/'source/kotaemon/libs/ktem',RELEASE/'source/kotaemon/libs/kotaemon'])))
                private=ROOT/'private';private.mkdir(mode=0o700,exist_ok=True)
                environment=private/(name+'.env')
                for value in env.values():
                    if '\n' in value or '\r' in value or '\x00' in value:raise RuntimeError('Invalid worker configuration')
                fd=os.open(environment,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
                with os.fdopen(fd,'w') as stream:
                    for k,v in env.items():stream.write(k+'='+json.dumps(v,ensure_ascii=False)+'\n')
                self.units[owner]=unit;self.save_units()
                await command('systemd-run','--quiet','--collect','--unit',unit,'--service-type=exec',
                    '--property=User='+name,'--property=Group='+name,'--property=EnvironmentFile='+str(environment),
                    '--property=WorkingDirectory='+str(home/'work'),'--property=MemoryMax=1400M',
                    '--property=CPUQuota=150%','--property=TasksMax=192','--property=UMask=0077',
                    '--property=ProtectSystem=strict','--property=ProtectHome=true','--property=PrivateTmp=true',
                    '--property=PrivateDevices=true','--property=NoNewPrivileges=true','--property=RestrictNamespaces=true',
                    '--property=ReadWritePaths='+str(home),'--property=KillMode=control-group',
                    '--property=BindsTo='+parent,'--property=After='+parent,'--property=TimeoutStopSec=20',
                    PYTHON,str(RELEASE/'source/custom_app.py'))
                deadline=time.monotonic()+150
                while time.monotonic()<deadline:
                    try:
                        response=await self.client.get('http://127.0.0.1:'+str(port)+'/config',
                            headers={'X-Learn-User':owner,'X-Learn-Worker-Key':key},timeout=3)
                        if response.status_code==200:break
                    except (httpx.RequestError,TimeoutError):pass
                    state=await command('systemctl','show',unit,'--property=ActiveState','--value')
                    if state in {'failed','inactive',''}:raise RuntimeError('Learning worker failed readiness')
                    await asyncio.sleep(.5)
                else:raise RuntimeError('Learning worker readiness deadline')
            async with self.lock:
                self.items[owner]=worker;self.starts.pop(owner,None)
            return worker
        except BaseException:
            logging.exception('Learning worker failed to start')
            if worker is not None:
                try:await self.stop(worker)
                except Exception:
                    async with self.lock:self.retiring[owner]=worker
                    logging.exception('Unconfirmed worker exit; account remains reserved')
            async with self.lock:self.starts.pop(owner,None)
            raise

    async def release(self,worker):
        async with self.lock:
            worker.active-=1;worker.last=time.monotonic()

    async def forget_exited(self,worker):
        state=await command('systemctl','show',worker.unit,'--property=ActiveState','--value')
        if state not in {'inactive','failed',''}:return
        async with self.lock:
            if self.items.get(worker.owner) is not worker:return
            self.items.pop(worker.owner);self.retiring[worker.owner]=worker
        await self.stop(worker)
        async with self.lock:self.retiring.pop(worker.owner,None)

    async def reap_idle(self):
        while True:
            await asyncio.sleep(30)
            await self.retire_idle()

    async def retire_idle(self):
        async with self.lock:
            now=time.monotonic()
            ttl=300 if now<self.pressure_until else self.idle_ttl
            candidates=[(worker,worker.last) for worker in self.items.values()
                if worker.active==0 and now-worker.last>ttl]
            candidates.sort(key=lambda item:item[1])
        for worker,last in candidates:
            try:
                status=await self.client.get('http://127.0.0.1:'+str(worker.port)+'/platform/activity',
                    headers={'X-Learn-User':worker.owner,'X-Learn-Worker-Key':worker.key},timeout=5)
                if status.status_code!=200 or status.json().get('busy') is not False:continue
                async with self.lock:
                    if self.items.get(worker.owner) is not worker or worker.active or worker.last!=last:continue
                    if now-last<=self.idle_ttl and len(self.items)+len(self.starts)+len(self.retiring)<self.limit:continue
                    self.items.pop(worker.owner);self.retiring[worker.owner]=worker
                await self.stop(worker)
                async with self.lock:self.retiring.pop(worker.owner,None)
            except asyncio.CancelledError:raise
            except Exception:logging.exception('Learning idle recovery needs inspection')

    async def close(self):
        async with self.lock:self.closing=True;starts=list(self.starts.values())
        for task in starts:task.cancel()
        await asyncio.gather(*starts,return_exceptions=True)
        await asyncio.gather(*(self.stop(worker) for worker in [*self.items.values(),*self.retiring.values()]),return_exceptions=True)
        await self.client.aclose()


@asynccontextmanager
async def lifespan(app):
    if os.geteuid()!=0:raise RuntimeError('Broker must provision isolated workers')
    if not Path('/data').is_mount() or not ROOT.resolve().is_relative_to('/data/learn-everything'):
        raise RuntimeError('The mounted product data volume is required; refusing system-disk fallback')
    platform_directory(ROOT,0o711)
    private=ROOT/'private';private.mkdir(mode=0o700,parents=True,exist_ok=True)
    if private.is_symlink() or private.stat().st_uid!=0 or private.stat().st_mode&0o077:
        raise RuntimeError('Private broker state required')
    descriptor=os.open(private/'broker.lock',os.O_CREAT|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
    workers=Workers();app.state.workers=workers
    await workers.recover()
    reaper=asyncio.create_task(workers.reap_idle())
    try:yield
    finally:
        reaper.cancel();await asyncio.gather(reaper,return_exceptions=True)
        await workers.close()
        os.close(descriptor)


app=FastAPI(lifespan=lifespan)


@app.get('/healthz')
async def health():return {'status':'ok','release':RELEASE.name}


# Gradio 4.44 also loads its versioned base CSS from the origin root.
# Serve only this public framework file; account routes remain authorized below.
@app.get('/assets/index-BOW2xVAS.css')
async def framework_stylesheet():
    package=Path(importlib.util.find_spec('gradio').origin).parent
    return FileResponse(package/'templates/frontend/assets/index-BOW2xVAS.css',
        media_type='text/css',headers={'Cache-Control':'public, max-age=31536000, immutable'})


@app.api_route('/{path:path}',methods=['GET','POST','PUT','DELETE','PATCH','OPTIONS','HEAD'])
async def proxy(request:Request,path:str):
    workers=request.app.state.workers
    if request.client is None or request.client.host not in {'127.0.0.1','::1'}:raise HTTPException(403)
    path=path.removeprefix(PREFIX.lstrip('/')+'/')
    original=PREFIX+'/'+path+('?' + request.url.query if request.url.query else '')
    auth=await workers.client.get('http://127.0.0.1:18030/api/v1/console/learn-everything/authorize',
        headers={'Cookie':request.headers.get('cookie',''),'X-Original-URI':original},timeout=10)
    owner=auth.headers.get('x-learn-user','')
    if auth.status_code!=204 or not UID_RE.fullmatch(owner):raise HTTPException(403,'请从官网重新进入学习工作台。')
    supplied=request.headers.get('x-learn-user')
    if supplied is not None and supplied!=owner:raise HTTPException(403,'工作空间身份不匹配。')
    expected=request.headers.get('x-learn-expected-user') or request.query_params.get('__le_owner')
    bound_path=(path in {'config','info','upload'} or path.startswith(('queue/','api/','run/','call/','platform/storage'))) and not path.startswith('platform/storage/assets/')
    if (expected is not None and expected!=owner) or (bound_path and not expected):
        raise HTTPException(409,'登录账号已变化，请从官网重新打开学习工作台。',headers={'X-Learn-Error':'ACCOUNT_CHANGED','Cache-Control':'no-store'})
    if request.method not in {'GET','HEAD','OPTIONS'}:
        origin=request.headers.get('origin')
        if origin and (urlsplit(origin).scheme,urlsplit(origin).netloc)!=(request.url.scheme,request.headers.get('host')):
            raise HTTPException(403,'请从当前学习工作台操作。')
        if request.headers.get('sec-fetch-site') in {'cross-site','same-site'}:raise HTTPException(403,'请从当前学习工作台操作。')
    if path=='platform/ready' and request.method=='GET':
        return JSONResponse({'state':await workers.startup_state(owner)},headers={'Cache-Control':'no-store'})
    browser_entry=request.method=='GET' and path=='' and 'text/html' in request.headers.get('accept','')
    try:worker=await workers.acquire(owner,wait=not browser_entry)
    except HTTPException as error:
        if error.status_code!=503 or request.method!='GET' or path!='':raise
        capacity=(error.headers or {}).get('X-Learn-Error')=='CAPACITY_BUSY'
        title='学习空间正在准备' if capacity else '学习空间暂时无法启动'
        detail='当前学习空间繁忙，稍后会自动重试。' if capacity else '个人学习空间启动失败，系统会稍后重试。'
        return HTMLResponse('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Learn Everything</title><body style="font:16px/1.8 system-ui;background:#f5f7fa;color:#1b3348;max-width:560px;margin:15vh auto;padding:24px"><h1>'+title+'</h1><p>'+detail+'你的学习内容仍保存在个人空间。</p><button onclick="location.reload()" style="background:#2d6496;color:white;border:0;border-radius:12px;padding:12px 24px;cursor:pointer">重新连接</button><script>setTimeout(()=>location.reload(),10000)</script></body></html>',status_code=503,headers={'Retry-After':'10','Cache-Control':'no-store',**(error.headers or {})})
    if worker is None:
        return FileResponse(Path(__file__).parent/'assets/startup.html',media_type='text/html',headers={'Cache-Control':'no-store'})
    headers={k:v for k,v in request.headers.items() if k.lower() not in HOP|{'x-learn-worker-key','x-learn-user','authorization'}}
    headers.update({'Host':request.headers.get('host','8.130.144.193'),
        'X-Learn-User':owner,'X-Learn-Worker-Key':worker.key,'X-Forwarded-Prefix':PREFIX,
        'X-Forwarded-Host':request.headers.get('host','8.130.144.193')})
    reserved=0
    try:
        from le_platform.storage import account_root,ensure_capacity,StorageQuotaExceeded
        if request.method=='POST' and (path=='upload' or path.startswith(('queue/join','api/','run/','call/'))):
            root=account_root(owner,ROOT)
            if path=='upload':
                length=request.headers.get('content-length','')
                if not length.isdecimal() or int(length)<=0:raise HTTPException(411,'请重新选择文件上传，以便确认所需空间。')
                reserved=int(length)
                async with worker.upload_lock:
                    await asyncio.to_thread(ensure_capacity,root,worker.upload_pending+reserved)
                    worker.upload_pending+=reserved
            else:await asyncio.to_thread(ensure_capacity,root)
    except BaseException as error:
        await workers.release(worker)
        if isinstance(error,StorageQuotaExceeded):raise HTTPException(507,str(error)) from None
        raise
    received=0
    async def incoming():
        nonlocal received
        async for chunk in request.stream():
            received+=len(chunk)
            if reserved and received>reserved:raise HTTPException(413,'上传内容超过声明的大小，请重试。')
            yield chunk
    async def release_upload():
        nonlocal reserved
        if reserved:
            async with worker.upload_lock:
                worker.upload_pending-=reserved;reserved=0
    upstream=workers.client.build_request(request.method,'http://127.0.0.1:'+str(worker.port)+'/'+path,
        params=[(k,v) for k,v in request.query_params.multi_items() if k!='__le_owner'],headers=headers,content=incoming())
    try:response=await workers.client.send(upstream,stream=True)
    except httpx.RequestError:
        await release_upload()
        await workers.release(worker)
        await workers.forget_exited(worker)
        raise HTTPException(503,'学习空间连接已中断，请重新连接后继续。') from None
    except BaseException:
        await release_upload()
        await workers.release(worker);raise
    finished=False
    async def finish():
        nonlocal finished
        if finished:return
        finished=True
        try:await response.aclose()
        finally:
            await release_upload()
            await workers.release(worker)
    async def body():
        try:
            async for chunk in response.aiter_raw():yield chunk
        finally:await finish()
    response_headers={k:v for k,v in response.headers.items() if k.lower() not in HOP}
    if not path.startswith(('assets/','static/')):response_headers['Cache-Control']='no-store'
    return StreamingResponse(body(),status_code=response.status_code,
        headers=response_headers,background=BackgroundTask(finish))
