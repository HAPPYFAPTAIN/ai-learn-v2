"""Global companion uses existing chat machinery and strict tenant ownership."""
import json
from uuid import uuid4
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import text
from learn_api.app import create_app
from learn_api.deps import get_tenant_id
from learn_core.db.engine import session_scope
from learn_core.db.models import Knode, Card, Tenant, TenantSetting
from learn_core.db.ktem import KtemConversation
from learn_core.learning import conversations
from learn_core.llm.gateway import GatewayClient
from learn_core.tenancy.context import tenant_context
from tests.learn_core.test_generation import tenant, db_test

@db_test
def test_assistant_without_a_plan_persists_and_isolates_two_accounts(tenant,monkeypatch):
    other=uuid4()
    with session_scope() as s:s.add(Tenant(id=other,official_user_id=f'assistant-{other.hex}'))
    try:
        with tenant_context(other),session_scope() as s:s.add(TenantSetting(tenant_id=other,chat_model='test-model'))
        calls=[]
        def respond(req):
            calls.append(json.loads(req.content))
            return httpx.Response(200,json={'choices':[{'message':{'content':'学习建议'}}]})
        monkeypatch.setattr(conversations,'GatewayClient',lambda:GatewayClient(transport=httpx.MockTransport(respond)))
        app=create_app()
        with TestClient(app) as c:
            for tid in [tenant[0],other]:
                app.dependency_overrides[get_tenant_id]=lambda tid=tid:tid
                assert c.get('/api/v2/assistant/conversation').json()['messages']==[]
                body={'content':'如何安排学习？','requestId':str(uuid4()),'context':{'page':'学习首页'}}
                job=c.post('/api/v2/assistant/chat-jobs',json=body)
                assert job.status_code==202,job.text
                assert c.post('/api/v2/assistant/chat-jobs',json=body).json()==job.json()
                assert c.delete('/api/v2/assistant/conversation').status_code==409
                conversations.run_answer(tenant=str(tid),job_id=job.json()['jobId'])
                assert len(c.get('/api/v2/assistant/conversation').json()['messages'])==2
            assert len(calls)==2
            assert c.delete('/api/v2/assistant/conversation').status_code==204
            assert c.get('/api/v2/assistant/conversation').json()['messages']==[]
            app.dependency_overrides[get_tenant_id]=lambda:tenant[0]
            assert len(c.get('/api/v2/assistant/conversation').json()['messages'])==2
    finally:
        with session_scope() as s:
            s.execute(text("DELETE FROM procrastinate_jobs WHERE args->>'tenant'=:tid"),{'tid':str(other)})
            s.execute(text('DELETE FROM tenant WHERE id=:tid'),{'tid':other})

@db_test
def test_assistant_resolves_context_and_appends_with_version_guard(tenant,monkeypatch):
    with tenant_context(tenant[0]),session_scope() as s:
        node=Knode(project_id=tenant[1],code='assistant',title='当前章节',description='原有课程正文');s.add(node);s.flush();nid=node.id
        card=Card(project_id=tenant[1],node_id=nid,front='变量是什么',back='数据的名字');s.add(card);s.flush();cid=card.id
    def respond(req):
        prompt=json.loads(req.content)['messages'][0]['content']
        assert '当前章节' in prompt and '变量是什么' in prompt and '数据的名字' in prompt
        return httpx.Response(200,json={'choices':[{'message':{'content':'课程补充内容'}}]})
    monkeypatch.setattr(conversations,'GatewayClient',lambda:GatewayClient(transport=httpx.MockTransport(respond)))
    app=create_app();app.dependency_overrides[get_tenant_id]=lambda:tenant[0]
    with TestClient(app) as c:
        body={'content':'解释一下','requestId':str(uuid4()),'projectId':tenant[1],'nodeId':nid,'context':{'page':'间隔复习','cardId':cid}}
        job=c.post('/api/v2/assistant/chat-jobs',json=body);assert job.status_code==202,job.text
        conversations.run_answer(tenant=str(tenant[0]),job_id=job.json()['jobId'])
        assert c.post('/api/v2/assistant/append',json={'nodeId':nid,'expectedVersion':0}).status_code==200
        stale=c.post('/api/v2/assistant/append',json={'nodeId':nid,'expectedVersion':0})
        assert stale.status_code==409 and stale.json()['error']['code']=='CONFLICT'
        with tenant_context(tenant[0]),session_scope() as s:
            assert s.get(Knode,nid).description=='原有课程正文\n\n## 助教补充\n\n课程补充内容'
        assert c.post('/api/v2/assistant/chat-jobs',json={**body,'requestId':str(uuid4()),'context':{'page':'间隔复习','cardId':999999999}}).status_code==404
