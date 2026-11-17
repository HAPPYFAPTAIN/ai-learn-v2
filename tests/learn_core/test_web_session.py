"""Bootstrap and expected-owner checks don't need Postgres or real credentials."""
import pytest
from fastapi.testclient import TestClient
from learn_api.app import create_app
from learn_api import auth
from learn_api.auth import Principal

@pytest.fixture
def client(monkeypatch):
    class Verifier:
        def verify(self, ticket):
            return Principal(official_user_id=ticket, display_name="Learner")
    monkeypatch.setattr(auth, "_verifier", Verifier())
    with TestClient(create_app()) as c:
        yield c

def test_bootstrap_uses_cookie_and_is_not_cached(client):
    client.cookies.set("le_ticket", "alice")
    r = client.get("/api/v2/me")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert r.json()["userId"] == "alice"
    assert r.json()["capabilities"]["coach"] is True
    assert r.json()["storage"] is None

def test_bootstrap_requires_auth(client):
    r = client.get("/api/v2/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHENTICATED"

@pytest.mark.parametrize("owner", [{"headers": {"X-Learn-Expected-User": "bob"}}, {"params": {"__le_owner": "bob"}}])
def test_owner_mismatch_before_any_database_work(client, owner):
    client.cookies.set("le_ticket", "alice")
    # The database is intentionally absent; mismatch must fail before accessing it.
    r = client.get("/api/v2/projects", **owner)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "ACCOUNT_CHANGED"

def test_me_does_not_return_ticket(client):
    client.cookies.set("le_ticket", "private-cookie")
    data = client.get("/api/v2/me", headers={"X-Learn-Expected-User": "private-cookie"}).json()
    assert "ticket" not in data
