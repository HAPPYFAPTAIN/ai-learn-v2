import asyncio
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import httpx
import pytest


@pytest.fixture
def broker(monkeypatch):
    monkeypatch.setenv('LE_PLATFORM_RELEASE','/immutable/source')
    monkeypatch.setenv('LE_PLATFORM_PYTHON',sys.executable)
    monkeypatch.delenv('LE_IDLE_TTL_SECONDS',raising=False)
    path=Path(__file__).resolve().parents[1]/'le_platform/broker.py'
    monkeypatch.syspath_prepend(str(path.parents[1]))
    spec=importlib.util.spec_from_file_location('learn_startup_test',path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module;spec.loader.exec_module(module)
    return module


def test_browser_entry_returns_before_startup_and_reuses_one_start(broker):
    async def run():
        workers=broker.Workers();await workers.client.aclose()
        calls=[];complete=asyncio.Event()
        class Body(httpx.AsyncByteStream):
            async def __aiter__(self):yield b'workspace ready'
        async def upstream(request):
            if request.url.port==18030:
                if request.headers.get('cookie')!='fixture=owner':return httpx.Response(403)
                return httpx.Response(204,headers={'x-learn-user':'owner'})
            return httpx.Response(200,stream=Body())
        workers.client=httpx.AsyncClient(transport=httpx.MockTransport(upstream))
        async def start(owner):
            calls.append(owner);await complete.wait()
            value=broker.Worker(owner,9999,'fixture','owned.service')
            async with workers.lock:
                workers.items[owner]=value;workers.starts.pop(owner,None)
            return value
        workers.start=start;broker.app.state.workers=workers
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=broker.app),base_url='http://local') as browser:
            denied=await browser.get('/platform/ready')
            assert denied.status_code==403 and not calls
            headers={'cookie':'fixture=owner','accept':'text/html'}
            first,second=await asyncio.wait_for(asyncio.gather(browser.get('/',headers=headers),browser.get('/',headers=headers)),1)
            assert first.status_code==second.status_code==200
            assert '正在准备你的学习空间' in first.text
            assert first.headers['cache-control']=='no-store'
            assert not complete.is_set() and calls==['owner']
            pending=await browser.get('/platform/ready',headers=headers)
            assert pending.json()=={'state':'starting'}
            assert pending.headers['cache-control']=='no-store'
            assert await workers.startup_state('another-owner')=='failed'
            complete.set();await workers.starts['owner']
            ready=await browser.get('/platform/ready',headers=headers)
            assert ready.json()=={'state':'ready'}
            assert workers.items['owner'].active==0
            page=await browser.get('/',headers=headers)
            assert page.text=='workspace ready' and workers.items['owner'].active==0
        await workers.client.aclose()
    asyncio.run(run())


def test_startup_failure_is_reported_without_polling_restarts(broker):
    async def run():
        workers=broker.Workers();calls=[]
        async def start(owner):
            calls.append(owner)
            async with workers.lock:workers.starts.pop(owner,None)
            raise RuntimeError('injected startup failure')
        workers.start=start
        assert await workers.acquire('owner',wait=False) is None
        task=workers.starts['owner']
        await asyncio.gather(task,return_exceptions=True)
        assert await workers.startup_state('owner')=='failed'
        assert await workers.startup_state('owner')=='failed'
        assert calls==['owner']
        await workers.client.aclose()
    asyncio.run(run())


def test_idle_retention_reclaims_old_worker_only_under_capacity_pressure(broker,monkeypatch):
    async def run():
        monkeypatch.setattr(broker,'time',SimpleNamespace(monotonic=lambda:1000))
        workers=broker.Workers();workers.limit=1;stopped=[]
        value=broker.Worker('owner',9999,'fixture','owned.service',last=400)
        workers.items['owner']=value
        await workers.client.aclose()
        workers.client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'busy':False})))
        async def stop(worker):stopped.append(worker.owner)
        workers.stop=stop
        await workers.retire_idle()
        assert not stopped and workers.items['owner'] is value
        with pytest.raises(broker.HTTPException) as error:await workers.acquire('new-owner',wait=False)
        assert error.value.headers['X-Learn-Error']=='CAPACITY_BUSY'
        await workers.retire_idle()
        assert stopped==['owner'] and not workers.items and not workers.retiring
        await workers.client.aclose()
    asyncio.run(run())


@pytest.mark.parametrize('protection',['active-request','background-work','arriving-request','recently-used','probe-failed'])
def test_capacity_pressure_never_stops_active_or_unconfirmed_worker(broker,monkeypatch,protection):
    async def run():
        monkeypatch.setattr(broker,'time',SimpleNamespace(monotonic=lambda:1000))
        workers=broker.Workers();workers.pressure_until=1060;stopped=[]
        value=broker.Worker('owner',9999,'fixture','owned.service',last=400)
        if protection=='active-request':value.active=1
        if protection=='recently-used':value.last=900
        workers.items['owner']=value
        await workers.client.aclose()
        async def probe(request):
            if protection=='arriving-request':await workers.acquire('owner')
            if protection=='probe-failed':raise httpx.ConnectError('injected probe failure')
            return httpx.Response(200,json={'busy':protection=='background-work'})
        workers.client=httpx.AsyncClient(transport=httpx.MockTransport(probe))
        async def stop(worker):stopped.append(worker.owner)
        workers.stop=stop
        await workers.retire_idle()
        assert not stopped and workers.items['owner'] is value
        await workers.client.aclose()
    asyncio.run(run())


def test_expired_worker_retires_without_capacity_pressure(broker,monkeypatch):
    async def run():
        monkeypatch.setattr(broker,'time',SimpleNamespace(monotonic=lambda:1000))
        workers=broker.Workers();stopped=[]
        workers.items['owner']=broker.Worker('owner',9999,'fixture','owned.service',last=0)
        await workers.client.aclose()
        workers.client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'busy':False})))
        async def stop(worker):stopped.append(worker.owner)
        workers.stop=stop
        await workers.retire_idle()
        assert stopped==['owner']
        await workers.client.aclose()
    asyncio.run(run())


def test_pressure_reclaims_only_one_slot_and_non_browser_waits(broker,monkeypatch):
    async def run():
        monkeypatch.setattr(broker,'time',SimpleNamespace(monotonic=lambda:1000))
        workers=broker.Workers();workers.limit=2;workers.pressure_until=1060;stopped=[]
        workers.items['newer']=broker.Worker('newer',9998,'fixture','newer.service',last=500)
        workers.items['oldest']=broker.Worker('oldest',9999,'fixture','oldest.service',last=400)
        await workers.client.aclose()
        workers.client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'busy':False})))
        async def stop(worker):stopped.append(worker.owner)
        workers.stop=stop
        await workers.retire_idle()
        assert stopped==['oldest'] and list(workers.items)==['newer']
        entered=asyncio.Event();complete=asyncio.Event()
        async def start(owner):
            entered.set();await complete.wait()
            value=broker.Worker(owner,9997,'fixture','fresh.service')
            async with workers.lock:workers.items[owner]=value;workers.starts.pop(owner,None)
            return value
        workers.start=start
        waiting=asyncio.create_task(workers.acquire('fresh'));await entered.wait()
        assert not waiting.done()
        complete.set();worker=await waiting
        assert worker.active==1
        await workers.release(worker);await workers.client.aclose()
    asyncio.run(run())


def test_shutdown_cancels_pending_startup_and_closes_transport(broker):
    async def run():
        workers=broker.Workers();entered=asyncio.Event();cancelled=[]
        async def start(owner):
            entered.set()
            try:await asyncio.Event().wait()
            finally:
                cancelled.append(owner)
                async with workers.lock:workers.starts.pop(owner,None)
        workers.start=start
        await workers.acquire('owner',wait=False);await entered.wait()
        await workers.close()
        assert cancelled==['owner'] and workers.client.is_closed
        assert await workers.startup_state('owner')=='failed'
        with pytest.raises(broker.HTTPException):await workers.acquire('new-owner',wait=False)
    asyncio.run(run())
