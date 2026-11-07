import asyncio
import importlib.util
from pathlib import Path
import sys

import httpx
import pytest


@pytest.fixture
def broker(monkeypatch):
    monkeypatch.setenv('LE_PLATFORM_RELEASE','/immutable/source')
    monkeypatch.setenv('LE_PLATFORM_PYTHON',sys.executable)
    root=Path(__file__).resolve().parents[1];monkeypatch.syspath_prepend(str(root))
    spec=importlib.util.spec_from_file_location('history_broker_test',root/'le_platform/broker.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    return module


def test_stale_document_cannot_read_or_mutate_the_new_cookie_account(broker):
    async def run():
        workers=broker.Workers();await workers.client.aclose();acquired=[]
        async def upstream(request):
            assert request.url.port==18030
            return httpx.Response(204,headers={'x-learn-user':request.headers.get('cookie','')})
        async def acquire(owner,wait=True):
            acquired.append(owner);raise AssertionError('Wrong account must be rejected before acquire')
        workers.acquire=acquire;workers.client=httpx.AsyncClient(transport=httpx.MockTransport(upstream));broker.app.state.workers=workers
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=broker.app),base_url='http://fixture') as browser:
            for method,path in [('GET','/config'),('POST','/queue/join'),('POST','/upload'),('POST','/platform/storage/delete'),('GET','/?ticket=new')]:
                reply=await browser.request(method,path,headers={'Cookie':'user-b','X-Learn-Expected-User':'user-a'},json={} if method=='POST' else None)
                assert reply.status_code==409 and reply.headers['x-learn-error']=='ACCOUNT_CHANGED'
                assert reply.headers['cache-control']=='no-store'
            reply=await browser.get('/queue/data?session_hash=old&__le_owner=user-a',headers={'Cookie':'user-b'})
            assert reply.status_code==409
            reply=await browser.get('/config',headers={'Cookie':'user-b'})
            assert reply.status_code==409
        assert acquired==[]
        await workers.client.aclose()
    asyncio.run(run())


def test_matching_document_routes_to_only_its_worker_without_leaking_binding(broker):
    async def run():
        workers=broker.Workers();await workers.client.aclose();forwarded=[]
        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):yield b'{"history":["owner-a-route"]}'
        async def upstream(request):
            if request.url.port==18030:return httpx.Response(204,headers={'x-learn-user':'owner-a'})
            forwarded.append(request)
            return httpx.Response(200,headers={'content-type':'application/json'},stream=Stream())
        workers.client=httpx.AsyncClient(transport=httpx.MockTransport(upstream))
        workers.items['owner-a']=broker.Worker('owner-a',9999,'secret-fixture','fixture.service')
        broker.app.state.workers=workers
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=broker.app),base_url='http://fixture') as browser:
            reply=await browser.get('/config?__le_owner=owner-a')
            assert reply.status_code==200 and reply.json()['history']==['owner-a-route']
            assert reply.headers['cache-control']=='no-store'
            asset=await browser.get('/platform/storage/assets/storage.js')
            assert asset.status_code==200
        assert len(forwarded)==2 and '__le_owner' not in forwarded[0].url.params
        assert forwarded[0].headers['x-learn-user']=='owner-a'
        assert workers.items['owner-a'].active==0
        await workers.client.aclose()
    asyncio.run(run())
