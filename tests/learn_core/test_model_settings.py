"""Real RLS preference saves; mocked official gateway catalog with no paid calls."""
import json
from uuid import uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from learn_api.app import create_app
from learn_api.auth import Principal, get_principal
from learn_api.deps import get_tenant_id
from learn_api.routers import models
from learn_core.db.engine import get_engine, session_scope
from learn_core.db.models import Tenant, TenantSetting
from learn_core.learning import generation
from learn_core.llm.gateway import GatewayClient
from learn_core.tenancy.context import tenant_context
from tests.learn_core.test_generation import tenant, db_test


def client_for(tid, uid):
    app = create_app()
    app.dependency_overrides[get_principal] = lambda: Principal(official_user_id=uid)
    app.dependency_overrides[get_tenant_id] = lambda: tid
    return TestClient(app)


@db_test
def test_catalog_selection_isolated_and_next_generation_uses_saved_model(tenant, monkeypatch):
    with session_scope() as session:
        uid = session.get(Tenant, tenant[0]).official_user_id
    seen = []
    def handler(request):
        assert get_engine().pool.checkedout() == 0
        assert request.method == 'GET' and request.url.path == '/models'
        assert request.headers['Authorization'] == 'Bearer test-key'
        seen.append(request.headers['X-End-User'])
        return httpx.Response(200, json={'data': [{'id': 'qwen-test', 'owned_by': 'alibaba'}, {'id': 'deepseek-test'}]})
    monkeypatch.setattr(models, '_gateway', lambda: GatewayClient(base_url='https://gateway.test', product_key='test-key', transport=httpx.MockTransport(handler)))
    with client_for(tenant[0], uid) as client:
        data = client.get('/api/v2/models')
        assert data.headers['cache-control'] == 'no-store'
        assert data.json()['selectedModel'] == 'deepseek-test'
        assert client.patch('/api/v2/models/selection', json={'model': 'qwen-test'}).status_code == 200
        assert client.get('/api/v2/models').json()['selectedModel'] == 'qwen-test'
        assert client.patch('/api/v2/models/selection', json={'model': 'forged-model'}).status_code == 422
        assert client.get('/api/v2/models').json()['selectedModel'] == 'qwen-test'
    with tenant_context(tenant[0]), session_scope() as session:
        row = generation.submit_generation(session, project_id=tenant[1], kind='roadmap')
        assert row.progress['model'] == 'qwen-test'
        setting = session.get(TenantSetting, tenant[0])
        assert setting.reasoning == {} and setting.prep_ahead == 2
    foreign = uuid4()
    with tenant_context(foreign), session_scope() as session:
        assert session.get(TenantSetting, tenant[0]) is None
    assert set(seen) == {uid}


@db_test
@pytest.mark.parametrize('response', [httpx.Response(401, text='secret-key'), httpx.Response(200, json={'data':'malformed'}), httpx.Response(503, text='private-host')])
def test_catalog_failure_never_saves_or_exposes_upstream_body(tenant, monkeypatch, response):
    monkeypatch.setattr(models, '_gateway', lambda: GatewayClient(transport=httpx.MockTransport(lambda req: response)))
    with client_for(tenant[0], 'verified-user') as client:
        r = client.patch('/api/v2/models/selection', json={'model': 'forged-model'})
        assert r.status_code == 503
        assert 'secret-key' not in r.text and 'private-host' not in r.text
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.get(TenantSetting, tenant[0]).chat_model == 'deepseek-test'


@db_test
def test_missing_preference_created_without_other_tenant_writes(tenant, monkeypatch):
    with tenant_context(tenant[0]), session_scope() as session:
        session.delete(session.get(TenantSetting, tenant[0]))
    monkeypatch.setattr(models, '_gateway', lambda: GatewayClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={'data':[{'id':'deepseek-test'}]}))))
    with client_for(tenant[0], 'verified-user') as client:
        assert client.get('/api/v2/models').json()['selectedModel'] == ''
        assert client.patch('/api/v2/models/selection', json={'model':'deepseek-test'}).status_code == 200
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.get(TenantSetting, tenant[0]).chat_model == 'deepseek-test'
