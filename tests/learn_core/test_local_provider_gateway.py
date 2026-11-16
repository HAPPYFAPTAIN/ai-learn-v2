"""Local-only provider routing: mocked upstream, no real credentials or model fees."""
import json
import socket

import httpx
import pytest
from fastapi.testclient import TestClient

from learn_api.app import create_app
from learn_api.errors import ApiError
from scripts.dev import local_provider_gateway as local

TOKEN = 'local-test-token-' + 'x' * 32


@pytest.fixture
def proxy(monkeypatch):
    monkeypatch.setenv('LEARN_DEV_AUTH', '1')
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    monkeypatch.setattr(local.socket, 'getaddrinfo', lambda *a, **kw: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))])
    seen = []

    def upstream(request):
        seen.append(request)
        if request.url.path.endswith('/models'):
            return httpx.Response(200, json={'data': [{'id': 'qwen-test'}]})
        assert json.loads(request.content)['model'] == 'qwen-test'
        return httpx.Response(200, json={'choices': [{'message': {'content': 'lesson body'}}],
                                         'model': 'qwen-test', 'usage': {'total_tokens': 10}})

    app = local.create_proxy(TOKEN, transport=httpx.MockTransport(upstream))
    with TestClient(app, headers={'Authorization': f'Bearer {TOKEN}',
                                 'X-End-User': local.LOCAL_USER}) as client:
        yield client, seen, app


def body(**changes):
    return {'provider': 'custom', 'name': '测试供应商', 'baseUrl': 'https://provider.example/v1',
            'apiKey': 'test-only-not-a-real-key', 'models': ['qwen-test'], **changes}


def test_verify_add_route_and_never_return_credentials(proxy):
    client, seen, app = proxy
    result = client.post('/providers', json=body())
    assert result.status_code == 200
    mid = result.json()['connection']['models'][0]
    assert mid.startswith('local.') and mid.endswith('.qwen-test')
    assert client.get('/v1/models').json()['data'][0]['id'] == mid
    response = client.post('/v1/chat/completions', json={'model': mid, 'messages': []})
    assert response.status_code == 200 and response.json()['model'] == mid
    assert len(seen) == 2 and seen[0].method == 'GET'
    assert all(r.headers['Authorization'] == 'Bearer test-only-not-a-real-key' for r in seen)
    assert all(r.url.host == '8.8.8.8' and r.headers['Host'] == 'provider.example' for r in seen)
    assert all(r.extensions['sni_hostname'] == 'provider.example' for r in seen)
    assert all('X-End-User' not in r.headers for r in seen)
    assert 'test-only-not-a-real-key' not in result.text + client.get('/providers').text + response.text
    assert 'test-only-not-a-real-key' not in repr(next(iter(app.state.registry.connections.values())))


def test_validation_and_upstream_errors_are_redacted(proxy):
    client, seen, app = proxy
    bad = client.post('/providers', json=body(models=[], apiKey='do-not-echo-this'))
    assert bad.status_code == 422 and 'do-not-echo-this' not in bad.text
    app.state.registry.transport = httpx.MockTransport(lambda req: httpx.Response(401, text='do-not-echo-this'))
    failed = client.post('/providers', json=body())
    assert failed.status_code == 422 and 'Key 无效' in failed.text
    assert 'do-not-echo-this' not in failed.text
    assert client.get('/providers').json()['connections'] == []


def test_unknown_model_and_unverified_model_are_rejected(proxy):
    client, seen, app = proxy
    assert client.post('/v1/chat/completions', json={'model': 'forged', 'messages': []}).status_code == 422
    assert not seen
    assert client.post('/providers', json=body(models=['not-available'])).status_code == 422
    assert client.get('/providers').json()['connections'] == []


def test_local_secret_and_expected_user_are_required(proxy):
    client, _, _ = proxy
    assert client.get('/providers', headers={'Authorization': 'Bearer wrong'}).status_code == 403
    assert client.get('/v1/models', headers={'X-End-User': 'another-user'}).status_code == 403
    assert client.get('/providers', headers={'Host': 'example.com'}).status_code == 403


@pytest.mark.parametrize('url', ['http://localhost/v1', 'https://x:abc/v1',
    'https://key@provider.example/v1', 'https://provider.example/v1?key=secret'])
def test_invalid_endpoints_never_contact_upstream(proxy, url):
    client, seen, _ = proxy
    assert client.post('/providers', json=body(baseUrl=url)).status_code == 422
    assert seen == []


def test_private_and_rebinding_addresses_are_rejected(proxy, monkeypatch):
    client, seen, _ = proxy
    monkeypatch.setattr(local.socket, 'getaddrinfo', lambda *a, **kw: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))])
    assert client.post('/providers', json=body()).status_code == 422
    assert seen == []


def test_official_app_does_not_mount_local_routes(monkeypatch):
    paths = set(create_app().openapi()['paths'])
    assert '/api/v2/local-providers' not in paths
    monkeypatch.delenv('LEARN_DEV_AUTH', raising=False)
    with pytest.raises(RuntimeError):
        local.create_proxy(TOKEN)
    with pytest.raises(RuntimeError):
        local.attach_local_controls(create_app(), proxy_url='http://127.0.0.1:18091', token=TOKEN)
