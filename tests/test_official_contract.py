"""Optional integration against the actual official API with an isolated temporary database."""
import asyncio
import importlib.util
import os
from pathlib import Path
import sys

import httpx
import pytest

SOURCE=os.environ.get('OFFICIAL_SITE_SOURCE')
pytestmark=pytest.mark.skipif(not SOURCE,reason='Set OFFICIAL_SITE_SOURCE to an official-site checkout')


def test_real_ticket_contract_and_broker_identity(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(Path(SOURCE)/'server'))
    from fastapi.testclient import TestClient
    from official_api.app import create_app
    from official_api.config import Settings
    from official_api.workspace import BatchCreate,Redeem
    official=create_app(settings=Settings.from_env({'APP_ENV':'test','LLMER_HASH_SECRET':'isolated-contract-fixture-'*3,
        'LLMER_DATABASE_PATH':str(tmp_path/'auth.sqlite3'),'LLMER_AVATAR_DIR':str(tmp_path/'avatars')}))
    auth,w=official.state.auth_service,official.state.workspace
    sessions=[auth._create_login(auth.hash('phone',str(13900000001+i)),str(i).zfill(4),auth.now()) for i in range(3)]
    owner,user,other=[s['profile']['userId'] for s in sessions]
    w.bootstrap_owner('13900000001');client=TestClient(official)
    prefix='/api/v1/console/learn-everything'
    bearer={'Authorization':'Bearer '+sessions[1]['accessToken']}
    assert client.post(prefix+'/entry',headers=bearer).status_code==403
    code=w.create_batch(owner,BatchCreate(label='contract',quantity=1,productId='learn-everything',days=1))['codes'][0]
    w.redeem(user,Redeem(code=code))
    entry=client.post(prefix+'/entry',headers=bearer)
    assert entry.status_code==200
    original=entry.json()['url']
    assert original.startswith('/official/learn-everything/?ticket=')
    authorized=client.get(prefix+'/authorize',headers={'X-Original-URI':original})
    assert authorized.status_code==204 and authorized.headers['x-learn-user']==user
    cookie=authorized.headers['x-learn-entry-cookie'].split(';',1)[0]
    monkeypatch.setenv('LE_PLATFORM_RELEASE',str(tmp_path));monkeypatch.setenv('LE_PLATFORM_PYTHON',sys.executable)
    spec=importlib.util.spec_from_file_location('contract_broker',Path(__file__).resolve().parents[1]/'le_platform/broker.py')
    broker=importlib.util.module_from_spec(spec);sys.modules[spec.name]=broker;spec.loader.exec_module(broker)
    async def run():
        workers=broker.Workers();await workers.client.aclose()
        async def authorize(request):
            assert request.url.path==prefix+'/authorize'
            reply=client.get(request.url.path,headers=dict(request.headers))
            return httpx.Response(reply.status_code,headers=dict(reply.headers),content=reply.content)
        workers.client=httpx.AsyncClient(transport=httpx.MockTransport(authorize))
        workers.items[user]=broker.Worker(user,9999,'fixture','fixture.service')
        broker.app.state.workers=workers
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=broker.app),base_url='http://learning') as browser:
            assert (await browser.get('/platform/ready')).status_code==403
            assert (await browser.get('/platform/ready',headers={'Cookie':cookie})).json()=={'state':'ready'}
            assert (await browser.get('/platform/ready',headers={'Cookie':cookie,'X-Learn-User':other})).status_code==403
            assert (await browser.get('/platform/ready',headers={'Cookie':cookie+'tampered'})).status_code==403
            with w.db.connect() as connection:
                connection.execute('UPDATE official_entitlements SET expires_at_ms=0 WHERE user_id=?',(user,))
            assert (await browser.get('/platform/ready',headers={'Cookie':cookie})).status_code==403
        await workers.client.aclose()
    asyncio.run(run())
