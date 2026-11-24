"""Personal key persistence, tenant isolation, safe network routing and failures."""
import json
import socket
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select, text

from learn_core.config import get_settings, Settings
from learn_core.db.engine import session_scope, get_engine
from learn_core.db.models import ModelProvider, TenantSetting, JobProgress, ModelCall
from learn_core.llm import providers
from learn_core.llm.gateway import GatewayClient, GatewayError, output_token_limit, validate_output_tokens
from learn_core.tenancy.context import tenant_context
from tests.learn_core.test_generation import tenant, db_test, ROADMAP
from tests.learn_core.test_model_settings import client_for


@pytest.fixture
def personal(monkeypatch):
    monkeypatch.setattr(get_settings(), 'model_source', 'personal')
    monkeypatch.setattr(get_settings(), 'provider_encryption_key', SecretStr(Fernet.generate_key().decode()))
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))])


def payload(**kwargs):
    return providers.ProviderInput(id=uuid4().hex[:12], provider='custom', name='我的模型',
        baseUrl='https://api.provider.test/v1', apiKey='test-user-private-key', models=['qwen-test'], **kwargs)


def test_generation_limits_have_dedicated_defaults(monkeypatch):
    for name in ('LEARN_GATEWAY_READ_TIMEOUT', 'LEARN_GENERATION_READ_TIMEOUT', 'LEARN_GENERATION_MAX_TOKENS'):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(_env_file=None)
    assert settings.gateway_read_timeout == 120
    assert settings.generation_read_timeout == 600
    assert settings.generation_max_tokens == 250000


@pytest.mark.parametrize('model', ['glm-5.3', 'GLM-5.3-Flash', 'glm-5.3-flashx', 'personal.abc123.glm-5.3-flashx-legal'])
def test_known_model_output_limit_is_enforced_without_clamping(model):
    assert output_token_limit(model) == 128000
    validate_output_tokens(model, 128000)
    with pytest.raises(GatewayError) as excinfo:
        validate_output_tokens(model, 250000)
    assert excinfo.value.status == 422
    assert excinfo.value.code == 'MODEL_OUTPUT_LIMIT'
    assert '128000' in str(excinfo.value)


def test_unknown_model_output_limit_is_not_invented():
    assert output_token_limit('custom-model') is None
    validate_output_tokens('custom-model', 250000)


def test_default_is_personal_and_encryption_is_bound_to_tenant_and_connection(personal, monkeypatch):
    monkeypatch.delenv('LEARN_MODEL_SOURCE', raising=False)
    assert Settings(_env_file=None).model_source == 'personal'
    cid = uuid4().hex[:12]
    tid = uuid4()
    with tenant_context(tid):
        sealed = providers.encrypt_key('private-key', cid)
        assert 'private-key' not in sealed
        assert providers.decrypt_key(sealed, cid) == 'private-key'
        with pytest.raises(providers.ProviderError):
            providers.decrypt_key(sealed, 'different-id')
    with tenant_context(uuid4()), pytest.raises(providers.ProviderError):
        providers.decrypt_key(sealed, cid)


@pytest.mark.parametrize('url', ['http://api.provider.test/v1', 'https://127.0.0.1/v1',
    'https://api.provider.test:8443/v1', 'https://user:secret@api.provider.test/v1', 'https://api.provider.test/v1?key=secret'])
def test_private_targets_and_unsafe_urls_never_receive_a_key(personal, monkeypatch, url):
    if '127.0.0.1' in url:
        monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))])
    with pytest.raises(providers.ProviderError):
        providers.public_target(url, '/models')


def test_provider_validation_pins_dns_and_sanitizes_credential_errors(personal):
    def handler(req):
        assert req.url.host == '8.8.8.8' and req.headers['Host'] == 'api.provider.test'
        assert req.extensions['sni_hostname'] == 'api.provider.test'
        assert req.headers['Authorization'] == 'Bearer test-user-private-key'
        assert 'X-End-User' not in req.headers
        return httpx.Response(401, text='secret upstream debug output')
    with pytest.raises(providers.ProviderError) as exc:
        providers.verify(payload(), transport=httpx.MockTransport(handler))
    assert exc.value.code == 'PROVIDER_KEY_INVALID'
    assert 'secret upstream' not in str(exc.value)


@db_test
def test_import_respects_existing_concurrency_limit_without_sending_key(tenant, personal, monkeypatch):
    from learn_core.llm.lease import acquire, release
    with tenant_context(tenant[0]), session_scope() as session:
        holders = [acquire(session, tenant_id=tenant[0], lane='interactive') for _ in range(get_settings().tenant_interactive_leases)]
    def unexpected(*args, **kwargs):
        raise AssertionError('A busy account must not send credentials upstream')
    monkeypatch.setattr(providers, 'call', unexpected)
    value = payload()
    with client_for(tenant[0], 'owner') as client:
        response = client.post('/api/v2/model-providers', json=value.model_dump() | {'apiKey':value.apiKey.get_secret_value()})
        assert response.status_code == 429
        assert response.json()['error']['code'] == 'TENANT_BUSY'
    with tenant_context(tenant[0]), session_scope() as session:
        for holder in holders:
            release(session, tenant_id=tenant[0], lane='interactive', holder=holder)


@db_test
def test_missing_encryption_config_never_stores_plaintext_or_sends_key(tenant, personal, monkeypatch):
    monkeypatch.setattr(get_settings(), 'provider_encryption_key', SecretStr(''))
    def unexpected(*args, **kwargs):
        raise AssertionError('A deployment without encryption must not send credentials')
    monkeypatch.setattr(providers, 'call', unexpected)
    value = payload()
    with client_for(tenant[0], 'owner') as client:
        assert client.get('/api/v2/models').json()['providerImportEnabled'] is False
        response = client.post('/api/v2/model-providers', json=value.model_dump() | {'apiKey':value.apiKey.get_secret_value()})
        assert response.status_code == 422
        assert response.json()['error']['code'] == 'PROVIDER_SETUP_REQUIRED'
        assert 'test-user-private-key' not in response.text
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.scalar(select(ModelProvider.id)) is None


@db_test
def test_import_retry_reload_selection_isolation_and_delete(tenant, personal, monkeypatch):
    sent = []
    def call(credential, method, path, **kwargs):
        assert get_engine().pool.checkedout() == 0
        assert method == 'GET' and path == '/models'
        sent.append(credential.key)
        return httpx.Response(200, json={'data': [{'id': 'qwen-test'}]})
    monkeypatch.setattr(providers, 'call', call)
    value = payload()
    wire = value.model_dump() | {'apiKey': value.apiKey.get_secret_value()}
    alias = f'personal.{value.id}.qwen-test'
    with client_for(tenant[0], 'owner') as client:
        empty = client.get('/api/v2/models').json()
        assert empty['source'] == 'personal' and empty['items'] == [] and empty['selectedModel'] == ''
        for _ in range(2):
            response = client.post('/api/v2/model-providers', json=wire)
            assert response.status_code == 200, response.text
            assert 'test-user-private-key' not in response.text
        assert len(client.get('/api/v2/model-providers').json()['connections']) == 1
        assert client.patch('/api/v2/models/selection', json={'model': alias}).status_code == 200
        assert client.get('/api/v2/models').json()['selectedModel'] == alias
    with tenant_context(tenant[0]), session_scope() as session:
        row = session.get(ModelProvider, value.id)
        assert 'test-user-private-key' not in row.encrypted_key
        assert 'test-user-private-key' not in json.dumps(row.metadata_json)
    with client_for(uuid4(), 'foreign') as foreign:
        assert foreign.get('/api/v2/models').json()['items'] == []
        assert foreign.patch('/api/v2/models/selection', json={'model': alias}).status_code == 422
        assert foreign.delete(f'/api/v2/model-providers/{value.id}').status_code == 404
    with client_for(tenant[0], 'owner') as client:
        assert client.delete(f'/api/v2/model-providers/{value.id}').status_code == 204
        assert client.get('/api/v2/models').json()['selectedModel'] == ''
    assert len(sent) == 2  # /models browsing and selection never query paid APIs.


@db_test
def test_missing_key_prevents_atomic_project_creation_and_job_enqueue(tenant, personal):
    with client_for(tenant[0], 'owner') as client:
        response = client.post('/api/v2/projects', json={'title': '没有 Key', 'generateRoadmap': True})
        assert response.status_code == 422
        assert response.json()['error']['code'] == 'MODEL_NOT_CONFIGURED'
        assert '导入 API Key' in response.json()['error']['message']
        assert all(row['title'] != '没有 Key' for row in client.get('/api/v2/projects').json()['items'])
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.scalar(select(JobProgress.id)) is None
        assert session.scalar(text("SELECT count(*) FROM procrastinate_jobs WHERE args->>'tenant' = :tid"), {'tid': str(tenant[0])}) == 0


@db_test
def test_real_generation_uses_owned_key_without_gateway_fallback_or_db_lease(tenant, personal, monkeypatch):
    from learn_core.learning.generation import submit_generation, run_generation
    value = payload()
    with tenant_context(tenant[0]), session_scope() as session:
        data = providers.save(session, payload=value)
        alias = data['models'][0]
        session.get(TenantSetting, tenant[0]).chat_model = alias
        session.flush()
        job = submit_generation(session, project_id=tenant[1], kind='roadmap')
        jid = job.job_id
    def call(credential, method, path, **kwargs):
        assert get_engine().pool.checkedout() == 0
        assert credential.key == 'test-user-private-key'
        assert kwargs['payload']['model'] == 'qwen-test'
        assert kwargs['payload']['max_tokens'] == 250000
        assert kwargs['timeout'] == 600
        return httpx.Response(200, json={'model':'qwen-test', 'choices':[{'message':{'content':json.dumps(ROADMAP)}, 'finish_reason':'stop'}], 'usage':{'total_tokens':42}})
    monkeypatch.setattr(providers, 'call', call)
    run_generation(tenant=str(tenant[0]), job_id=jid)
    with tenant_context(tenant[0]), session_scope() as session:
        row = session.scalar(select(JobProgress).where(JobProgress.job_id == jid))
        assert row.state == 'done', row.error
        assert 'test-user-private-key' not in json.dumps(row.progress)
        usage = session.scalar(select(ModelCall).where(ModelCall.job_id == jid))
        assert usage.model == alias and usage.status == 'ok'


@db_test
def test_edit_keeps_key_revalidates_models_and_clears_removed_primary(tenant, personal, monkeypatch):
    value = payload()
    with tenant_context(tenant[0]), session_scope() as session:
        original = providers.save(session, payload=value)
        session.get(TenantSetting, tenant[0]).chat_model = original['models'][0]
    seen = []
    def call(credential, method, path, **kwargs):
        assert get_engine().pool.checkedout() == 0
        seen.append(credential.key)
        return httpx.Response(200, json={'data': [{'id': 'replacement'}]})
    monkeypatch.setattr(providers, 'call', call)
    wire = {'revision': original['revision'], 'name': '已编辑', 'baseUrl': value.baseUrl,
            'apiKey': '', 'models': ['replacement'], 'remark': '新备注'}
    with client_for(tenant[0], 'owner') as client:
        result = client.put(f'/api/v2/model-providers/{value.id}', json=wire)
        assert result.status_code == 200, result.text
        assert 'test-user-private-key' not in result.text
        saved = result.json()['connection']
        assert saved['id'] == value.id and saved['name'] == '已编辑'
        assert saved['remark'] == '新备注' and saved['revision'] != original['revision']
        assert client.get('/api/v2/models').json()['selectedModel'] == ''
        assert client.get('/api/v2/model-providers').json()['connections'] == [saved]
        # Stale windows never send the key or overwrite another edit.
        assert client.put(f'/api/v2/model-providers/{value.id}', json=wire).status_code == 409
    assert seen == ['test-user-private-key']
    with client_for(uuid4(), 'foreign') as client:
        assert client.put(f'/api/v2/model-providers/{value.id}', json=wire).status_code == 404
    assert len(seen) == 1


@db_test
def test_edit_address_requires_new_key_and_failed_validation_keeps_original(tenant, personal, monkeypatch):
    value = payload()
    with tenant_context(tenant[0]), session_scope() as session:
        original = providers.save(session, payload=value)
    wire = {'revision': original['revision'], 'name': value.name,
            'baseUrl': 'https://new.provider.test/v1', 'models': value.models}
    sent = []
    def call(credential, *args, **kwargs):
        assert get_engine().pool.checkedout() == 0
        sent.append(credential.key)
        return httpx.Response(401, text='private upstream response')
    monkeypatch.setattr(providers, 'call', call)
    with client_for(tenant[0], 'owner') as client:
        result = client.put(f'/api/v2/model-providers/{value.id}', json=wire)
        assert result.status_code == 422 and '重新填写' in result.json()['error']['message']
        assert not sent
        wire['apiKey'] = 'replacement-secret'
        result = client.put(f'/api/v2/model-providers/{value.id}', json=wire)
        assert result.status_code == 422 and result.json()['error']['code'] == 'PROVIDER_KEY_INVALID'
        assert 'replacement-secret' not in result.text and 'private upstream' not in result.text
        assert client.get('/api/v2/model-providers').json()['connections'] == [original]
    assert sent == ['replacement-secret']


@db_test
def test_edit_rotates_key_without_changing_model_identity(tenant, personal, monkeypatch):
    value = payload()
    with tenant_context(tenant[0]), session_scope() as session:
        original = providers.save(session, payload=value)
        session.get(TenantSetting, tenant[0]).chat_model = original['models'][0]
    def call(credential, *args, **kwargs):
        assert credential.key == 'new-secret'
        return httpx.Response(200, json={'data': [{'id': 'qwen-test'}]})
    monkeypatch.setattr(providers, 'call', call)
    wire = {'revision': original['revision'], 'name': value.name, 'baseUrl': value.baseUrl,
            'apiKey': 'new-secret', 'models': value.models}
    with client_for(tenant[0], 'owner') as client:
        result = client.put(f'/api/v2/model-providers/{value.id}', json=wire)
        assert result.status_code == 200, result.text
        assert 'new-secret' not in result.text
        assert client.get('/api/v2/models').json()['selectedModel'] == original['models'][0]
    with tenant_context(tenant[0]), session_scope() as session:
        assert providers.resolve(session, original['models'][0]).key == 'new-secret'


@db_test
def test_edit_does_not_recreate_deleted_connection_after_verification(tenant, personal, monkeypatch):
    value = payload()
    with tenant_context(tenant[0]), session_scope() as session:
        original = providers.save(session, payload=value)
    def call(*args, **kwargs):
        with tenant_context(tenant[0]), session_scope() as session:
            providers.remove(session, value.id)
        return httpx.Response(200, json={'data': [{'id': 'qwen-test'}]})
    monkeypatch.setattr(providers, 'call', call)
    wire = {'revision': original['revision'], 'name': value.name, 'baseUrl': value.baseUrl,
            'models': value.models}
    with client_for(tenant[0], 'owner') as client:
        assert client.put(f'/api/v2/model-providers/{value.id}', json=wire).status_code == 404
        assert client.get('/api/v2/model-providers').json()['connections'] == []


@db_test
def test_edit_rechecks_revision_after_network_and_rejects_duplicate_names(tenant, personal, monkeypatch):
    value = payload()
    with tenant_context(tenant[0]), session_scope() as session:
        original = providers.save(session, payload=value)
        other = providers.save(session, payload=providers.ProviderInput(
            **(value.model_dump() | {'id': uuid4().hex[:12], 'name': '其他连接'})))
    changed = []
    def call(*args, **kwargs):
        if not changed:
            with tenant_context(tenant[0]), session_scope() as session:
                changed.append(providers.update(session, payload=providers.ProviderInput(
                    **(value.model_dump() | {'name': '其他窗口已保存'})), revision=original['revision']))
        return httpx.Response(200, json={'data': [{'id': 'qwen-test'}]})
    monkeypatch.setattr(providers, 'call', call)
    wire = {'revision': original['revision'], 'name': '过期编辑', 'baseUrl': value.baseUrl,
            'models': value.models}
    with client_for(tenant[0], 'owner') as client:
        assert client.put(f'/api/v2/model-providers/{value.id}', json=wire).status_code == 409
        wire.update(revision=changed[0]['revision'], name=other['name'])
        result = client.put(f'/api/v2/model-providers/{value.id}', json=wire)
        assert result.status_code == 422 and '名称已存在' in result.json()['error']['message']
        saved = client.get('/api/v2/model-providers').json()['connections']
        assert next(c for c in saved if c['id'] == value.id)['name'] == '其他窗口已保存'
