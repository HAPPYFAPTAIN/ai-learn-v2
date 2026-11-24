"""Online audit regressions: real PostgreSQL/ASGI, fake upstreams, no paid calls."""
import asyncio
from contextlib import AsyncExitStack, contextmanager
from datetime import datetime, timedelta, timezone
import io
import json
import logging
import socket
import threading
import time
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from learn_api.app import create_app
from learn_api.deps import SessionDep, get_tenant_id
from learn_core.db.engine import get_engine, session_scope
from learn_core.db.models import Tenant, TenantSetting, JobProgress, Knode, Card, Project
from learn_core.jobs.reaper import reconcile_progress
from learn_core.learning import generation, conversations, polish
from learn_core.llm.gateway import GatewayClient, UNKNOWN_RESULT
from learn_core.tenancy.context import tenant_context
from tests.learn_core.test_generation import tenant, db_test, enqueue, read_job, LESSON

@pytest.fixture
def client(tenant):
    app = create_app()
    app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

@db_test
def test_commit_failure_never_sends_success_and_hides_data(tenant, caplog):
    app = create_app()
    app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    @app.post('/__test/commit-failure')
    def fail(session: SessionDep):
        session.execute(text('CREATE TEMP TABLE commit_probe (value text UNIQUE DEFERRABLE INITIALLY DEFERRED) ON COMMIT DROP'))
        session.execute(text("INSERT INTO commit_probe VALUES ('private-test-value'), ('private-test-value')"))
        return {'saved': True}
    with TestClient(app, raise_server_exceptions=False) as c, caplog.at_level(logging.WARNING):
        response = c.post('/__test/commit-failure?secret=hidden')
        assert response.status_code == 500
        assert response.json()['error']['code'] == 'INTERNAL'
        assert c.get('/healthz').status_code == 200
    assert 'private-test-value' not in caplog.text and 'secret=hidden' not in caplog.text
    assert len([r for r in caplog.records if 'api_error' in r.message]) == 1
    assert get_engine().pool.checkedout() == 0

@db_test
def test_first_generation_and_question_events_are_distinct_for_two_tenants(tenant):
    tid = uuid4()
    with session_scope() as s:
        s.add(Tenant(id=tid, official_user_id=f'event-{tid.hex}'))
    try:
        with tenant_context(tid), session_scope() as s:
            s.add(TenantSetting(tenant_id=tid, chat_model='test-model'))
            project = Project(title='Second tenant'); s.add(project); s.flush(); pid = project.id
        ids=[]
        for current, project_id in [tenant, (tid,pid)]:
            with tenant_context(current), session_scope() as s:
                ids.append(generation.submit_generation(s, project_id=project_id, kind='roadmap').progress['eventBase'])
                ids.append(conversations.submit(s, project_id=project_id, content='Q', request_id=str(uuid4()), node_id=None, use_materials=False, material_ids=[]).progress['eventId'])
        assert len(set(ids)) == 4
    finally:
        with session_scope() as s:
            s.execute(text("DELETE FROM procrastinate_jobs WHERE args->>'tenant'=:tid"), {'tid':str(tid)})
            s.execute(text('DELETE FROM tenant WHERE id=:tid'), {'tid':tid})

@contextmanager
def server_for(tenant):
    import uvicorn
    app = create_app(); app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    sock=socket.socket(); sock.bind(('127.0.0.1', 0)); port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app, log_level='critical', access_log=False))
    worker=threading.Thread(target=lambda:server.run(sockets=[sock]), daemon=True); worker.start()
    deadline=time.monotonic()+5
    while not server.started and time.monotonic()<deadline: time.sleep(.01)
    assert server.started
    try: yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit=True; worker.join(timeout=5); sock.close()

@db_test
def test_six_progress_streams_release_entry_connections_and_leave_api_responsive(tenant):
    with tenant_context(tenant[0]), session_scope() as s:
        for i in range(6): s.add(JobProgress(job_id=f'stream-{i}', kind='test', subject='test',state='running',progress={}))
    async def exercise(url):
        async with httpx.AsyncClient(base_url=url, timeout=5) as c, AsyncExitStack() as stack:
            responses=await asyncio.gather(*[stack.enter_async_context(c.stream('GET',f'/api/v2/jobs/stream-{i}/events')) for i in range(6)])
            assert all(r.status_code==200 for r in responses)
            # Each stream is open; entry sessions must already be closed.
            await asyncio.sleep(.1)
            assert get_engine().pool.checkedout() <= 1
            start=time.monotonic()
            assert (await c.get('/api/v2/projects')).status_code==200
            assert time.monotonic()-start < 1
    with server_for(tenant) as url: asyncio.run(exercise(url))

@db_test
def test_same_tenant_concurrent_uploads_finish_without_deadlock(tenant, monkeypatch, tmp_path):
    from learn_core.config import get_settings
    monkeypatch.setenv('LEARN_FILES_ROOT', str(tmp_path)); get_settings.cache_clear()
    async def exercise(url):
        async with httpx.AsyncClient(base_url=url, timeout=5) as c:
            results=await asyncio.gather(*[c.post(f'/api/v2/projects/{tenant[1]}/materials',files={'file':(f'{i}.txt',f'upload {i}'.encode())},data={'index':'false'}) for i in range(2)])
            assert [r.status_code for r in results] == [202,202]
            assert (await c.get('/healthz')).status_code == 200
    with server_for(tenant) as url: asyncio.run(exercise(url))

@db_test
@pytest.mark.parametrize('kind',['chat','polish'])
def test_unknown_results_are_not_replayed_and_partial_answers_are_saved(tenant, monkeypatch, kind):
    service = conversations if kind=='chat' else polish
    with tenant_context(tenant[0]), session_scope() as s:
        job = conversations.submit(s,project_id=tenant[1], content='Explain',request_id=str(uuid4()),node_id=None,use_materials=False,material_ids=[]) if kind=='chat' else polish.submit(s,project_id=tenant[1],source='原文',purpose='note',request_id=str(uuid4()))
        jid=job.job_id
    calls=[]
    def crash(req): calls.append(req); raise SystemExit('worker killed after send')
    monkeypatch.setattr(service,'GatewayClient',lambda:GatewayClient(transport=httpx.MockTransport(crash)))
    runner = service.run_answer if kind=='chat' else service.run_polish
    with pytest.raises(SystemExit): runner(tenant=str(tenant[0]),job_id=jid)
    runner(tenant=str(tenant[0]),job_id=jid)
    state,p,error=read_job(tenant,jid)
    assert len(calls)==1 and state=='failed' and error==UNKNOWN_RESULT and p['errorCode']=='RESULT_UNCONFIRMED'
    # The direct runner above bypasses Procrastinate's normal completion cleanup.
    with session_scope() as s:
        s.execute(text("DELETE FROM procrastinate_jobs WHERE args->>'job_id'=:jid"), {'jid':jid})
    with tenant_context(tenant[0]), session_scope() as s:
        job = conversations.submit(s,project_id=tenant[1], content='Next',request_id=str(uuid4()),node_id=None,use_materials=False,material_ids=[]) if kind=='chat' else polish.submit(s,project_id=tenant[1],source='下一段原文',purpose='note',request_id=str(uuid4()))
        jid=job.job_id
    def partial(req):
        body=json.loads(req.content)
        assert body['max_tokens']==(8000 if kind=='chat' else 4000)
        return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'可保留的部分答案'}}], 'usage':{'completion_tokens':8}})
    monkeypatch.setattr(service,'GatewayClient',lambda:GatewayClient(transport=httpx.MockTransport(partial)))
    runner(tenant=str(tenant[0]),job_id=jid)
    state,p,error=read_job(tenant,jid)
    assert state=='done' and p['truncated'] is True and p['warning']=='回答可能不完整' and not p['gatewayCallPending']
    if kind=='chat':
        with tenant_context(tenant[0]),session_scope() as s:
            assert conversations.history(s,project_id=tenant[1])['messages'][-1]['content']=='可保留的部分答案'
    else: assert p['result']=='可保留的部分答案'

@db_test
def test_truncated_lesson_has_explicit_code_and_never_overwrites_content(tenant, monkeypatch):
    with tenant_context(tenant[0]),session_scope() as s:
        node=Knode(project_id=tenant[1],code='partial',title='Original',description='Keep original');s.add(node);s.flush();nid=node.id
    jid=enqueue(tenant,'lesson',node_id=nid)
    def partial(req):
        assert json.loads(req.content)['max_tokens']==250000
        return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':LESSON}}]})
    monkeypatch.setattr(generation,'GatewayClient',lambda **kwargs:GatewayClient(transport=httpx.MockTransport(partial),**kwargs))
    generation.run_generation(tenant=str(tenant[0]),job_id=jid)
    state,p,error=read_job(tenant,jid)
    assert state=='failed' and p['errorCode']=='OUTPUT_TRUNCATED' and '缩小章节范围' in error
    with tenant_context(tenant[0]),session_scope() as s: assert s.get(Knode,nid).description=='Keep original'

@db_test
def test_reaper_reconciles_running_and_missing_queued_jobs(tenant):
    old=datetime.now(timezone.utc)-timedelta(minutes=40)
    with tenant_context(tenant[0]),session_scope() as s:
        for name,state,p in [('pending','running',{'gatewayCallPending':True}),('stuck','running',{}),('lost','queued',{})]:
            s.add(JobProgress(job_id=name,kind='chat',subject='test',state=state,updated_at=old,progress=p))
        actual=conversations.submit(s,project_id=tenant[1],content='Keep queued',request_id=str(uuid4()),node_id=None,use_materials=False,material_ids=[])
        actual.updated_at=old;jid=actual.job_id
    assert reconcile_progress(queue='chat')>=3
    assert read_job(tenant,'pending')[2]==UNKNOWN_RESULT
    assert read_job(tenant,'stuck')[2]=='任务超时中断，请重试'
    assert read_job(tenant,'lost')[2]=='任务未能开始，请重试'
    assert read_job(tenant,jid)[0]=='queued'

@db_test
def test_duplicate_codes_nulls_enums_and_bounds_are_safe(tenant,client):
    pid=tenant[1]
    node=client.post(f'/api/v2/projects/{pid}/nodes',json={'code':'a'*32,'title':'b'*200,'description':'x'*50000,'stage':'s'*16})
    assert node.status_code==201,node.text
    nid=node.json()['id']
    duplicate=client.post(f'/api/v2/projects/{pid}/nodes',json={'code':'a'*32,'title':'duplicate'})
    assert duplicate.status_code==409 and duplicate.json()['error']['message']=='章节编号已存在'
    requests=[('POST',f'/api/v2/projects/{pid}/nodes',{'code':'a'*33,'title':'ok'}),('PATCH',f'/api/v2/nodes/{nid}',{'description':None}),('PATCH',f'/api/v2/projects/{pid}',{'goal':None}),('PATCH',f'/api/v2/projects/{pid}',{'status':'invalid'}),('POST','/api/v2/projects',{'title':'x'*201}),('POST','/api/v2/projects',{'title':'ok','goal':'x'*5001}),('PATCH',f'/api/v2/nodes/{nid}',{'description':'x'*50001}),('POST','/api/v2/cards',{'front':'x','back':'y','cardType':'invalid'})]
    for method,path,body in requests:
        response=client.request(method,path,json=body)
        assert response.status_code==422,(path,response.text)
        assert response.json()['error']['message'].startswith('输入不符合要求：')

@db_test
def test_request_ids_logs_and_csp_are_sanitized(client,caplog):
    with caplog.at_level(logging.WARNING):
        r=client.post('/api/v2/projects?secret=must-not-log',json={'title':None},headers={'X-Request-ID':'bad_id!key'})
    assert r.status_code==422 and r.headers['x-request-id']!='bad_id!key'
    assert 'secret=' not in caplog.text and 'bad_id!' not in caplog.text
    assert "script-src 'self'" in r.headers['content-security-policy']
    assert r.headers['x-content-type-options']=='nosniff'
    assert client.get('/healthz',headers={'X-Request-ID':'valid-123'}).headers['x-request-id']=='valid-123'

@pytest.mark.parametrize('origin',['https://localhost','https://production.example','http://localhost.evil.test','http://127.0.0.1@evil.test','http://localhost/path'])
def test_dev_auth_rejects_remote_or_confusing_origins(monkeypatch,origin):
    from learn_api.auth import validate_dev_auth
    from learn_core.config import get_settings
    monkeypatch.setenv('LEARN_DEV_AUTH','1');monkeypatch.setenv('LEARN_PUBLIC_ORIGIN',origin);get_settings.cache_clear()
    with pytest.raises(RuntimeError): validate_dev_auth()


def test_document_parser_timeout_and_child_failure_are_safe(monkeypatch):
    from learn_core.storage import parsing
    import subprocess
    def timeout(*args,**kwargs): raise subprocess.TimeoutExpired('parser',120)
    monkeypatch.setattr(subprocess,'run',timeout)
    with pytest.raises(ValueError,match='^文件无法解析$'): parsing.extract_text(b'bad','file.pdf')
    monkeypatch.setattr(subprocess,'run',lambda *a,**k: (_ for _ in ()).throw(subprocess.CalledProcessError(-9,'parser')))
    with pytest.raises(ValueError,match='^文件无法解析$'): parsing.extract_text(b'bad','file.docx')
