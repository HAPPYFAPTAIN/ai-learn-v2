import json
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from learn_api.app import create_app
from learn_api.deps import get_tenant_id
from learn_core.db.engine import get_engine
from learn_core.learning import polish, conversations
from learn_core.learning.polish_text import _protect, validate_output
from learn_core.llm.gateway import GatewayClient
from tests.learn_core.test_generation import tenant, db_test


@pytest.fixture
def client(tenant):
    app = create_app()
    app.dependency_overrides[get_tenant_id] = lambda:tenant[0]
    with TestClient(app) as c:
        c.app_under_test = app
        yield c


def test_polish_rules_preserve_numbers_links_and_code():
    source = '我就是想问一下，`print(3)` 为啥输出3？链接 https://example.org/a'
    protected, spans = _protect(source)
    result = validate_output(source,protected.replace('我就是想问一下，',''),spans,'question')
    assert '`print(3)`' in result and 'https://example.org/a' in result
    with pytest.raises(ValueError):validate_output(source,protected.replace('输出3','输出4'),spans,'question')
    with pytest.raises(ValueError):validate_output(source,protected.replace('？','。'),spans,'question')
    with pytest.raises(ValueError):validate_output(source,protected.replace(spans[0][0],''),spans,'question')


@db_test
def test_polish_job_preserves_source_deduplicates_and_recovers_result(tenant,client,monkeypatch):
    calls=[]
    def respond(request):
        assert get_engine().pool.checkedout() == 0
        assert request.headers['X-End-User'].startswith('fusion-')
        body = json.loads(request.content);calls.append(body)
        source = json.loads(body['messages'][1]['content'])['source']
        return httpx.Response(200,json={'choices':[{'message':{'content':source.replace('我就是想','我想')}}]})
    monkeypatch.setattr(polish,'GatewayClient',lambda:GatewayClient(transport=httpx.MockTransport(respond)))
    path=f'/api/v2/projects/{tenant[1]}'
    payload={'source':'我就是想每周学3小时 Python，用 `print(3)` 练习。','purpose':'goal','requestId':str(uuid4())}
    assert client.get(path+'/polish-job').json() is None
    first=client.post(path+'/polish-jobs',json=payload);assert first.status_code==202
    jid=first.json()['jobId']
    assert client.post(path+'/polish-jobs',json=payload).json()['jobId']==jid
    assert client.post(path+'/polish-jobs',json={**payload,'requestId':str(uuid4())}).status_code==409
    polish.run_polish(tenant=str(tenant[0]),job_id=jid)
    polish.run_polish(tenant=str(tenant[0]),job_id=jid)
    job=client.get(f'/api/v2/jobs/{jid}').json()
    assert job['state']=='done' and job['progress']['result'].startswith('我想')
    assert job['progress']['source']==payload['source'] and len(calls)==1
    assert client.get(path+'/polish-job').json()['jobId']==jid
    assert client.post(path+'/polish-jobs',json={**payload,'source':'不同内容'}).status_code==422
    client.app_under_test.dependency_overrides[get_tenant_id]=lambda:uuid4()
    assert client.get(path+'/polish-job').status_code==404
    assert client.get(f'/api/v2/jobs/{jid}').status_code==404
    assert client.post(path+'/polish-jobs',json=payload).status_code==404


@db_test
def test_changed_protected_content_fails_without_overwriting_original(tenant,client,monkeypatch):
    monkeypatch.setattr(polish,'GatewayClient',lambda:GatewayClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'choices':[{'message':{'content':'每周学习4小时。'}}]}))))
    payload={'source':'每周学习3小时。','requestId':str(uuid4())}
    jid=client.post(f'/api/v2/projects/{tenant[1]}/polish-jobs',json=payload).json()['jobId']
    polish.run_polish(tenant=str(tenant[0]),job_id=jid)
    job=client.get(f'/api/v2/jobs/{jid}').json()
    assert job['state']=='failed' and '数字' in job['error']
    assert job['progress']['source']==payload['source'] and 'result' not in job['progress']


@db_test
def test_coach_history_separate_and_prompt_has_no_execution_permission(tenant,client,monkeypatch):
    def respond(request):
        assert get_engine().pool.checkedout()==0
        system=json.loads(request.content)['messages'][0]['content']
        assert '没有设备观察、程序执行' in system and '用户自述' in system
        return httpx.Response(200,json={'choices':[{'message':{'content':'第一步：写出一个变量，运行后告诉我输出。'}}]})
    monkeypatch.setattr(conversations,'GatewayClient',lambda:GatewayClient(transport=httpx.MockTransport(respond)))
    path=f'/api/v2/projects/{tenant[1]}'
    payload={'content':'带我练习变量','mode':'coach','useMaterials':False,'requestId':str(uuid4())}
    jid=client.post(path+'/chat-jobs',json=payload).json()['jobId']
    assert client.get(path+'/conversation?mode=coach').json()['activeJob']['jobId']==jid
    conversations.run_answer(tenant=str(tenant[0]),job_id=jid)
    assert len(client.get(path+'/conversation?mode=coach').json()['messages'])==2
    assert client.get(path+'/conversation').json()['messages']==[]
    assert client.get(path+'/conversation?mode=desktop').status_code==422
