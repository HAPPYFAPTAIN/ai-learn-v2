import asyncio
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def worker(monkeypatch,tmp_path):
    monkeypatch.syspath_prepend(str(ROOT))
    from le_platform import worker
    monkeypatch.setenv('LE_ISOLATED_WORKER','1');monkeypatch.setenv('LE_WORKER_ROOT',str(tmp_path))
    monkeypatch.setenv('LE_OFFICIAL_USER','owner-a');monkeypatch.setenv('LE_WORKER_KEY','private-test-worker-key')
    return worker,tmp_path


def test_worker_auth_needs_both_owner_and_private_transport_key(worker):
    module,_=worker
    def request(owner,key):return SimpleNamespace(headers={'x-learn-user':owner,'x-learn-worker-key':key})
    assert module.authenticated(request('owner-a','private-test-worker-key'))=='owner-a'
    assert module.authenticated(request('owner-b','private-test-worker-key')) is None
    assert module.authenticated(request('owner-a','wrong-key')) is None
    assert module.authenticated(SimpleNamespace(headers={})) is None


def test_actual_tool_executor_rejects_desktop_operations_and_path_escape(worker):
    module,root=worker; (root/'workspace').mkdir();(root/'workspace/link').symlink_to(root.parent)
    calls=[]
    def handler(**args):calls.append(args);return 'executed'
    for name in ['run_command','clipboard_get','observe_screen','launch_app','mcp__unknown']:
        assert module.execute_tool(name,{},handler)!='executed'
    for path in ['../secret',str(root.parent/'secret'),'link/secret']:
        assert module.execute_tool('read_file',{'path':path},handler)!='executed'
    assert calls==[]
    assert module.execute_tool('read_file',{'path':'lesson.txt'},handler)=='executed'
    assert calls==[{'path':str(root/'workspace/lesson.txt')}]


def test_gateway_client_binds_identity_and_event_once(worker,monkeypatch):
    module,_=worker;monkeypatch.setenv('OPENAI_API_KEY','platform-private');monkeypatch.setenv('OPENAI_API_BASE','http://127.0.0.1:18040/v1')
    calls=[]
    monkeypatch.setitem(sys.modules,'openai',SimpleNamespace(OpenAI=lambda **args:calls.append(args)))
    module.model_client();module.model_client()
    assert all(args['default_headers']['X-End-User']=='owner-a' for args in calls)
    assert calls[0]['default_headers']['X-Event-Id']!=calls[1]['default_headers']['X-Event-Id']
    assert all(args['max_retries']==0 for args in calls)


def test_broker_deduplicates_startup_and_cancelled_waiter_does_not_cancel_peer(monkeypatch):
    monkeypatch.setenv('LE_PLATFORM_RELEASE','/immutable/source');monkeypatch.setenv('LE_PLATFORM_PYTHON',sys.executable)
    path=ROOT/'le_platform/broker.py'
    spec=importlib.util.spec_from_file_location('learn_broker_test',path);module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    async def run():
        workers=module.Workers();calls=[];entered=asyncio.Event();complete=asyncio.Event()
        async def start(owner):
            calls.append(owner);entered.set();await complete.wait()
            value=module.Worker(owner,1234,'key','owned.service')
            async with workers.lock:workers.items[owner]=value;workers.starts.pop(owner,None)
            return value
        workers.start=start
        first=asyncio.create_task(workers.acquire('one'));await entered.wait()
        second=asyncio.create_task(workers.acquire('one'));first.cancel()
        with pytest.raises(asyncio.CancelledError):await first
        complete.set();value=await second
        assert calls==['one'] and value.active==1
        await workers.release(value);assert value.active==0
        workers.limit=1
        with pytest.raises(module.HTTPException) as error:await workers.acquire('two')
        assert error.value.status_code==503
        await workers.client.aclose()
    asyncio.run(run())


def test_authenticated_gradio_queue_starts_on_server_lifespan(worker):
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    module,_=worker;events=[]
    @asynccontextmanager
    async def original(app):
        events.append('enter');yield;events.append('exit')
    app=FastAPI(lifespan=original)
    app.startup_events_triggered=False
    app.get_blocks=lambda:SimpleNamespace(startup_events=lambda:events.append(asyncio.get_running_loop().is_running()))
    module.register_routes(app)
    async def run():
        async with app.router.lifespan_context(app):
            assert events==['enter',True] and app.startup_events_triggered
    asyncio.run(run())
    assert events==['enter',True,'exit']


def test_terminal_model_failures_survive_user_facing_wrapping(worker):
    module,_=worker
    class StatusError(Exception):
        status_code=402
    error=RuntimeError('用户可读提示');error.__cause__=StatusError('credit failure')
    assert module.terminal_model_error(error)
    assert '积分不足' in module.model_error_message(error)
    assert not module.terminal_model_error(TimeoutError('transient network failure'))


def test_cloud_quota_counts_every_private_area_but_never_shared_links(worker):
    module,root=worker
    from le_platform import storage
    for name in ['data/user_data','workspace','tmp','cache','home','downloads','work']:(root/name).mkdir(parents=True,exist_ok=True)
    (root/'workspace/note.txt').write_bytes(b'12345')
    os.link(root/'workspace/note.txt',root/'workspace/same-file.txt')
    (root/'data/user_data/sql.db').write_bytes(b'1234567')
    (root/'tmp/upload.txt').write_bytes(b'123')
    (root/'cache/index.log').write_bytes(b'12')
    (root/'home/preferences').write_bytes(b'1')
    (root/'work/platform.py').write_bytes(b'x'*100)
    (root/'downloads/platform-copy.zip').write_bytes(b'x'*100)
    (root/'workspace/external').symlink_to(root.parent,target_is_directory=True)
    usage=storage.snapshot(root)
    assert usage['quotaBytes']==5*1024**3
    assert usage['usedBytes']==18==sum(item['bytes'] for item in usage['categories'])
    assert usage['remainingBytes']==5*1024**3-18


def test_cloud_quota_blocks_sparse_full_account_and_reopens_after_cleanup(worker):
    _,root=worker
    from le_platform import storage
    (root/'workspace').mkdir()
    file=root/'workspace/full.bin'
    with file.open('wb') as stream:stream.truncate(storage.INITIAL_STORAGE_BYTES)
    assert storage.snapshot(root)['remainingBytes']==0
    with pytest.raises(storage.StorageQuotaExceeded):storage.ensure_capacity(root)
    file.unlink()
    assert storage.ensure_capacity(root,100)['usedBytes']==0


def test_storage_descriptor_download_and_delete_reject_links_and_stale_items(worker):
    _,root=worker
    from le_platform import storage
    (root/'workspace').mkdir();(root/'data').mkdir()
    file=root/'workspace/note.txt';file.write_bytes(b'owned')
    (root/'workspace/link').symlink_to(root/'data',target_is_directory=True)
    (root/'data/private.txt').write_bytes(b'private')
    for path in ['../secret','/etc/passwd','workspace/link/private.txt']:
        with pytest.raises((ValueError,OSError)):storage.open_file(root,path)
    fd,info=storage.open_file(root,'workspace/note.txt')
    try:assert os.read(fd,100)==b'owned'
    finally:os.close(fd)
    file.write_bytes(b'changed')
    with pytest.raises(ValueError):storage.remove_file(root,'workspace/note.txt',storage.version(info))
    assert file.read_bytes()==b'changed'
    storage.remove_file(root,'workspace/note.txt',storage.version(file.stat()))
    assert not file.exists()


def test_concurrent_uploads_reserve_capacity_until_the_first_stream_finishes(worker,monkeypatch):
    import hashlib
    import httpx
    from le_platform import storage
    _,root=worker
    monkeypatch.setenv('LE_PLATFORM_RELEASE','/immutable/source');monkeypatch.setenv('LE_PLATFORM_PYTHON',sys.executable)
    spec=importlib.util.spec_from_file_location('learn_upload_broker_test',ROOT/'le_platform/broker.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    module.ROOT=root;owner='upload-owner';home=storage.account_root(owner,root)
    (home/'workspace').mkdir(parents=True);(home/'workspace/existing').write_bytes(b'x'*16)
    monkeypatch.setattr(storage,'INITIAL_STORAGE_BYTES',128)
    async def run():
        started=asyncio.Event();finish=asyncio.Event();forwarded=[]
        class Body(httpx.AsyncByteStream):
            async def __aiter__(self):yield b'[]'
        async def upstream(request):
            if request.url.port==18030:return httpx.Response(204,headers={'x-learn-user':owner})
            forwarded.append(await request.aread());started.set();await finish.wait()
            return httpx.Response(200,stream=Body(),headers={'content-type':'application/json'})
        workers=module.Workers();await workers.client.aclose()
        workers.client=httpx.AsyncClient(transport=httpx.MockTransport(upstream))
        value=module.Worker(owner,9999,'key','owned.service');workers.items[owner]=value;module.app.state.workers=workers
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://learn.test',headers={'X-Learn-Expected-User':owner}) as browser:
            first=asyncio.create_task(browser.post('/upload',content=b'a'*100))
            await asyncio.wait_for(started.wait(),2)
            try:
                second=await browser.post('/upload',content=b'b'*100)
                assert second.status_code==507 and len(forwarded)==1
                finish.set();assert (await first).status_code==200
                assert value.upload_pending==0
                assert (await browser.post('/upload',content=b'c'*100)).status_code==200
                assert len(forwarded)==2 and value.upload_pending==0 and value.active==0
            finally:finish.set();await asyncio.gather(first,return_exceptions=True)
        await workers.client.aclose()
    asyncio.run(run())


def test_new_bootstrap_modes_ignore_private_service_umask(monkeypatch,tmp_path):
    monkeypatch.setenv('LE_PLATFORM_RELEASE','/immutable/source');monkeypatch.setenv('LE_PLATFORM_PYTHON',sys.executable)
    spec=importlib.util.spec_from_file_location('learn_bootstrap_permissions_test',ROOT/'le_platform/broker.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    # Local tests need not run as root. Only the ownership observation is
    # supplied; mkdir, umask, O_NOFOLLOW and fchmod use the real filesystem.
    fstat=module.os.fstat
    monkeypatch.setattr(module.os,'fstat',lambda fd:SimpleNamespace(**{**{name:getattr(fstat(fd),name) for name in dir(fstat(fd)) if name.startswith('st_')},'st_uid':0}))
    previous=os.umask(0o077)
    try:
        home=tmp_path/'account';module.platform_directory(home,0o711)
        work=home/'work';module.platform_directory(work,0o755)
        assert home.stat().st_mode&0o777==0o711
        assert work.stat().st_mode&0o777==0o755
        assert os.umask(0o077)==0o077
        home.chmod(0o700);work.chmod(0o700)
        module.platform_directory(home,0o711);module.platform_directory(work,0o755)
        assert home.stat().st_mode&0o777==0o711 and work.stat().st_mode&0o777==0o755
    finally:os.umask(previous);monkeypatch.setattr(module.os,'fstat',fstat)


def test_bootstrap_never_chmods_a_link_or_user_owned_directory(monkeypatch,tmp_path):
    monkeypatch.setenv('LE_PLATFORM_RELEASE','/immutable/source');monkeypatch.setenv('LE_PLATFORM_PYTHON',sys.executable)
    spec=importlib.util.spec_from_file_location('learn_bootstrap_refusals_test',ROOT/'le_platform/broker.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    target=tmp_path/'private';target.mkdir(mode=0o700);link=tmp_path/'link';link.symlink_to(target,target_is_directory=True)
    with pytest.raises(OSError):module.platform_directory(link,0o755)
    fstat=module.os.fstat
    monkeypatch.setattr(module.os,'fstat',lambda fd:SimpleNamespace(**{**{name:getattr(fstat(fd),name) for name in dir(fstat(fd)) if name.startswith('st_')},'st_uid':12345}))
    with pytest.raises(RuntimeError):module.platform_directory(target,0o755)
    assert target.stat().st_mode&0o777==0o700


def test_startup_failure_is_not_reported_as_capacity_busy(monkeypatch):
    import httpx
    monkeypatch.setenv('LE_PLATFORM_RELEASE','/immutable/source');monkeypatch.setenv('LE_PLATFORM_PYTHON',sys.executable)
    spec=importlib.util.spec_from_file_location('learn_startup_error_test',ROOT/'le_platform/broker.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    async def run():
        workers=module.Workers();await workers.client.aclose()
        workers.client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(204,headers={'x-learn-user':'test-owner'})))
        async def failed_start(owner):raise RuntimeError('synthetic startup failure')
        workers.start=failed_start;module.app.state.workers=workers
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://learn.test') as browser:
            response=await browser.get('/')
            assert response.status_code==503
            assert response.headers['x-learn-error']=='STARTUP_FAILED'
            assert '暂时无法启动' in response.text and '繁忙' not in response.text
            workers.starts.clear();workers.limit=0
            response=await browser.get('/')
            assert response.status_code==503 and response.headers['x-learn-error']=='CAPACITY_BUSY'
            assert '繁忙' in response.text
        await workers.client.aclose()
    asyncio.run(run())
