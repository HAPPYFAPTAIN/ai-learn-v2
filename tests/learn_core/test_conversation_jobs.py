"""Real queue/RLS chat history and library citations, with isolated HTTP models."""
import json
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from learn_api.app import create_app
from learn_api.deps import get_tenant_id
from learn_core.db.engine import session_scope, get_engine
from learn_core.db.models import StoredFile, JobProgress, Knode
from learn_core.learning import conversations, materials
from learn_core.jobs.tasks import index_material_task
from learn_core.llm.gateway import GatewayClient
from learn_core.config import get_settings
from learn_core.tenancy.context import tenant_context
from tests.learn_core.test_generation import tenant, db_test


@pytest.fixture
def client(tenant):
    app = create_app()
    app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    with TestClient(app) as c:
        c.app_under_test = app
        yield c


@db_test
def test_chat_persists_history_deduplicates_and_uses_chapter_and_selected_materials(tenant, client, tmp_path, monkeypatch):
    monkeypatch.setenv('LEARN_FILES_ROOT',str(tmp_path)); get_settings.cache_clear()
    class Embedder:
        def __init__(self,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def embed(self,chunks):
            assert get_engine().pool.checkedout() == 0
            return [[1.0]+[0.0]*383 for _ in chunks]
    monkeypatch.setattr('learn_core.rag.embedding.EmbeddingClient',Embedder)
    with tenant_context(tenant[0]), session_scope() as session:
        node = Knode(project_id=tenant[1],code='1',title='变量章节',description='用名字引用和保存数据。')
        session.add(node); session.flush(); nid=node.id
        chosen, job = materials.upload(session,data='变量可以保存数据。'.encode(),name='变量.txt',index=True)
        fid,jid = str(chosen.id),job.job_id
        other, other_job = materials.upload(session,data='不应该进入本次模型的其他资料'.encode(),name='other.txt',index=True)
        ofid,ojid = str(other.id),other_job.job_id
    index_material_task(tenant=str(tenant[0]),job_id=jid,file_id=fid)
    index_material_task(tenant=str(tenant[0]),job_id=ojid,file_id=ofid)
    calls=[]
    def respond(request):
        assert get_engine().pool.checkedout() == 0
        assert request.headers['X-End-User'].startswith('fusion-')
        body=json.loads(request.content); calls.append(body)
        assert body['model']=='deepseek-test'
        assert '变量章节' in body['messages'][0]['content']
        assert '变量.txt' in body['messages'][0]['content']
        assert '其他资料' not in body['messages'][0]['content']
        return httpx.Response(200,json={'choices':[{'message':{'content':'变量用于保存数据[资料1]。'},'finish_reason':'stop'}]})
    monkeypatch.setattr(conversations,'GatewayClient',lambda:GatewayClient(transport=httpx.MockTransport(respond)))
    payload={'content':'解释变量','requestId':str(uuid4()),'nodeId':nid,'materialIds':[fid]}
    first=client.post(f'/api/v2/projects/{tenant[1]}/chat-jobs',json=payload)
    assert first.status_code==202, first.text
    jid=first.json()['jobId']
    assert client.post(f'/api/v2/projects/{tenant[1]}/chat-jobs',json=payload).json()['jobId']==jid
    conflict=client.post(f'/api/v2/projects/{tenant[1]}/chat-jobs',json={**payload,'requestId':str(uuid4())})
    assert conflict.status_code==409
    pending=client.get(f'/api/v2/projects/{tenant[1]}/conversation').json()
    assert pending['activeJob']['jobId']==jid and pending['pendingQuestion']=='解释变量'
    conversations.run_answer(tenant=str(tenant[0]),job_id=jid)
    conversations.run_answer(tenant=str(tenant[0]),job_id=jid)
    history=client.get(f'/api/v2/projects/{tenant[1]}/conversation').json()
    assert history['activeJob'] is None and len(history['messages'])==2
    assert history['messages'][1]['references'][0]['fileId']==fid
    assert client.post(f'/api/v2/projects/{tenant[1]}/chat-jobs',json=payload).json()['jobId']==jid
    assert len(calls)==1
    assert client.post(f'/api/v2/projects/{tenant[1]}/chat-jobs',json={**payload,'content':'不同问题'}).status_code==422
    client.app_under_test.dependency_overrides[get_tenant_id] = lambda:uuid4()
    assert client.get(f'/api/v2/projects/{tenant[1]}/conversation').status_code==404
    assert client.get(f'/api/v2/jobs/{jid}').status_code==404
    assert client.post(f'/api/v2/projects/{tenant[1]}/chat-jobs',json={**payload,'requestId':str(uuid4())}).status_code==404
    get_settings.cache_clear()


@db_test
def test_chat_recovery_reuses_saved_input_after_chapter_edit(tenant, client, monkeypatch):
    with tenant_context(tenant[0]), session_scope() as session:
        node = Knode(project_id=tenant[1], code='1', title='原章节', description='原教材内容')
        session.add(node); session.flush(); nid = node.id
    jid = client.post(f'/api/v2/projects/{tenant[1]}/chat-jobs', json={
        'content':'解释一下', 'requestId':str(uuid4()), 'nodeId':nid, 'useMaterials':False,
    }).json()['jobId']
    calls = []
    def respond(request):
        calls.append((request.headers['X-Event-Id'], json.loads(request.content)))
        if len(calls) == 1:
            raise SystemExit('simulated worker interruption')
        return httpx.Response(200, json={'choices':[{'message':{'content':'恢复后的回答'}}]})
    monkeypatch.setattr(conversations, 'GatewayClient', lambda:GatewayClient(transport=httpx.MockTransport(respond)))
    with pytest.raises(SystemExit):
        conversations.run_answer(tenant=str(tenant[0]), job_id=jid)
    with tenant_context(tenant[0]), session_scope() as session:
        session.get(Knode, nid).description = '后来修改的教材'
    conversations.run_answer(tenant=str(tenant[0]), job_id=jid)
    assert len(calls) == 2 and calls[0] == calls[1]
    assert '原教材内容' in calls[1][1]['messages'][0]['content']
    assert len(client.get(f'/api/v2/projects/{tenant[1]}/conversation').json()['messages']) == 2


@db_test
def test_chat_failure_does_not_append_partial_turn_and_records_error(tenant, client, monkeypatch):
    monkeypatch.setattr(conversations,'GatewayClient',lambda:GatewayClient(transport=httpx.MockTransport(lambda req:httpx.Response(402,text='do-not-expose-token'))))
    payload={'content':'解释变量','requestId':str(uuid4()),'useMaterials':False}
    response=client.post(f'/api/v2/projects/{tenant[1]}/chat-jobs',json=payload)
    jid=response.json()['jobId']
    conversations.run_answer(tenant=str(tenant[0]),job_id=jid)
    job=client.get(f'/api/v2/jobs/{jid}').json()
    assert job['state']=='failed' and '402' in job['error'] and 'do-not-expose' not in job['error']
    assert client.get(f'/api/v2/projects/{tenant[1]}/conversation').json()['messages']==[]


@db_test
def test_chat_rejects_foreign_chapter_or_material_before_queueing(tenant, client):
    payload={'content':'解释变量','requestId':str(uuid4())}
    assert client.post(f'/api/v2/projects/{tenant[1]}/chat-jobs',json={**payload,'nodeId':99999999}).status_code==404
    assert client.post(f'/api/v2/projects/{tenant[1]}/chat-jobs',json={**payload,'materialIds':[str(uuid4())]}).status_code==404
    with tenant_context(tenant[0]), session_scope() as session:
        assert not list(session.scalars(select(JobProgress)))
