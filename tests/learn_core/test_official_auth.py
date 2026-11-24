"""Existing official cookie protocol, proxy boundary and renewal without a database."""
import httpx
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from learn_api import auth
from learn_api.app import create_app
from learn_core.config import get_settings

SECRET = 'trial-proxy-secret-' + 'x' * 32


@pytest.fixture
def setup_client(monkeypatch):
    monkeypatch.setenv('LEARN_PUBLIC_ORIGIN', 'https://learn.example.com')
    get_settings.cache_clear()
    calls = []
    def build(status=204, owner='alice', renewed=''):
        def respond(request):
            calls.append(request)
            assert request.method == 'GET'
            assert request.url.path == '/api/v1/console/learn-everything/authorize'
            assert request.headers['cookie'] == 'learn_entry=official-ticket'
            assert request.headers['X-Original-URI'] == '/official/learn-everything/'
            assert 'X-Learn-User' not in request.headers
            return httpx.Response(status, headers={'X-Learn-User':owner, 'X-Learn-Entry-Cookie':renewed}, text='private-upstream-error')
        monkeypatch.setattr(auth, '_verifier', auth.HttpTicketVerifier(
            internal_secret=SECRET, transport=httpx.MockTransport(respond)))
        app = create_app()
        @app.post('/api/v2/auth-probe', include_in_schema=False)
        def probe(principal=Depends(auth.get_principal)):
            return {'user':principal.official_user_id}
        c = TestClient(app)
        c.cookies.set('learn_entry', 'official-ticket')
        return c
    yield build, calls
    get_settings.cache_clear()


def test_verifier_reuses_client_without_caching_identity(setup_client):
    build, calls = setup_client
    c = build()
    verifier = auth._verifier
    client = verifier._client
    for _ in range(2):
        r = c.get('/api/v2/me', headers={'X-Learn-Internal-Secret':SECRET})
        assert r.status_code == 200
    assert verifier._client is client and len(calls) == 2


def test_official_bootstrap_and_renewal_preserve_cookie_flags(setup_client):
    build, calls = setup_client
    cookie = 'learn_entry=renewed-ticket; Path=/official/learn-everything; HttpOnly; Secure; SameSite=Lax'
    c = build(renewed=cookie)
    r = c.get('/api/v2/me', headers={'X-Learn-Internal-Secret':SECRET})
    assert r.status_code == 200 and r.json()['userId'] == 'alice'
    assert r.headers['set-cookie'] == cookie and r.headers['cache-control'] == 'no-store'
    assert 'official-ticket' not in r.text and len(calls) == 1


def test_untrusted_requests_and_personal_ticket_headers_never_reach_official(setup_client):
    build, calls = setup_client
    c = build()
    for headers in ({}, {'X-Learn-Internal-Secret':'forged','X-Learn-User':'alice'}):
        assert c.get('/api/v2/me',headers=headers).status_code == 401
    c.cookies.clear()
    r = c.get('/api/v2/me',headers={'X-Learn-Internal-Secret':SECRET,'X-Learn-Ticket':'official-ticket'})
    assert r.status_code == 401 and not calls


@pytest.mark.parametrize('headers', [
    {}, {'X-Learn-Expected-User':'bob'}, {'__owner':'invalid'},
])
def test_missing_or_changed_owner_blocks_before_database(setup_client, headers):
    build, _ = setup_client
    c = build()
    r = c.get('/api/v2/projects',headers={'X-Learn-Internal-Secret':SECRET,**headers})
    assert r.status_code == 409 and r.json()['error']['code'] == 'ACCOUNT_CHANGED'


def test_owner_bound_sse_and_forged_proxy_user(setup_client):
    build, _ = setup_client
    c = build()
    r = c.post('/api/v2/auth-probe?__le_owner=alice',headers={'X-Learn-Internal-Secret':SECRET})
    assert r.status_code == 200
    r = c.get('/api/v2/me',headers={'X-Learn-Internal-Secret':SECRET,'X-Learn-User':'bob'})
    assert r.status_code == 401


@pytest.mark.parametrize('origin,site', [
    ('https://attacker.example','cross-site'), ('https://learn.example.com','same-site'),
    ('null','cross-site'), ('https://other.example.com','same-origin'),
])
def test_cross_origin_writes_rejected_without_official_or_database(setup_client, origin, site):
    build, calls = setup_client
    c = build()
    r = c.post('/api/v2/auth-probe',headers={
        'X-Learn-Internal-Secret':SECRET,'X-Learn-Expected-User':'alice',
        'Origin':origin,'Sec-Fetch-Site':site,
    })
    assert r.status_code == 403 and not calls


def test_same_origin_write_uses_verified_owner(setup_client):
    build, _ = setup_client
    c = build()
    r = c.post('/api/v2/auth-probe',headers={
        'X-Learn-Internal-Secret':SECRET,'X-Learn-Expected-User':'alice',
        'Origin':'https://learn.example.com','Sec-Fetch-Site':'same-origin',
    })
    assert r.status_code == 200 and r.json() == {'user':'alice'}


@pytest.mark.parametrize('status,owner,expected', [(401,'alice',401),(403,'alice',403),(302,'alice',503),(500,'alice',503),(204,'invalid user',401)])
def test_official_failure_never_falls_back_or_leaks_body(setup_client, status, owner, expected):
    build, _ = setup_client
    c = build(status=status, owner=owner)
    r = c.get('/api/v2/me',headers={'X-Learn-Internal-Secret':SECRET})
    assert r.status_code == expected and 'private-upstream-error' not in r.text
    assert r.headers['cache-control'] == 'no-store'


def test_missing_proxy_configuration_fails_closed(setup_client, monkeypatch):
    build, calls = setup_client
    c = build()
    monkeypatch.setattr(auth._verifier,'_secret','')
    r = c.get('/api/v2/me',headers={'X-Learn-Internal-Secret':SECRET})
    assert r.status_code == 500 and not calls
