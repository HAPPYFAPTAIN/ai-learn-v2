"""学习节点接口：项目下增删改查 + 跨租户隔离。"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from learn_api.app import create_app
from learn_api.auth import Principal, set_verifier
from learn_api.errors import ApiError
from learn_core.db.engine import reset_engine

pytestmark = pytest.mark.skipif(
    os.getenv("LEARN_DATABASE_URL") is None,
    reason="需要 LEARN_DATABASE_URL 指向测试库",
)


class _Verifier:
    def __init__(self) -> None:
        self.user_by_ticket: dict[str, Principal] = {}

    def verify(self, ticket: str) -> Principal:
        if ticket not in self.user_by_ticket:
            raise ApiError("UNAUTHENTICATED", "unknown ticket")
        return self.user_by_ticket[ticket]


@pytest.fixture()
def client():
    reset_engine()
    verifier = _Verifier()
    set_verifier(verifier)
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        c.verifier = verifier  # type: ignore[attr-defined]
        yield c
    reset_engine()


def _headers(ticket: str) -> dict[str, str]:
    return {"X-Learn-Ticket": ticket}


def _login(client, prefix: str) -> str:
    ticket = f"t-{uuid.uuid4().hex[:8]}"
    client.verifier.user_by_ticket[ticket] = Principal(
        official_user_id=f"{prefix}-{uuid.uuid4().hex[:8]}"
    )
    return ticket


def test_node_crud_and_isolation(client):
    t1 = _login(client, "na")
    t2 = _login(client, "nb")
    project = client.post("/api/v2/projects", json={"title": "节点项目"}, headers=_headers(t1)).json()

    created = client.post(
        f"/api/v2/projects/{project['id']}/nodes",
        json={"code": "K1", "title": "第一课", "estHours": 2.5},
        headers=_headers(t1),
    )
    assert created.status_code == 201, created.text
    node = created.json()
    assert node["estHours"] == 2.5 and node["mastery"] == 0.0

    listed = client.get(f"/api/v2/projects/{project['id']}/nodes", headers=_headers(t1)).json()
    assert [n["code"] for n in listed["items"]] == ["K1"]

    patched = client.patch(
        f"/api/v2/nodes/{node['id']}", json={"mastery": 0.6, "status": "doing"}, headers=_headers(t1)
    )
    assert patched.status_code == 200 and patched.json()["mastery"] == 0.6

    # 另一个租户看不到，也改不了
    assert client.get(f"/api/v2/projects/{project['id']}/nodes", headers=_headers(t2)).status_code == 404
    assert client.patch(f"/api/v2/nodes/{node['id']}", json={"mastery": 1.0}, headers=_headers(t2)).status_code == 404

    assert client.delete(f"/api/v2/nodes/{node['id']}", headers=_headers(t1)).status_code == 204
    assert client.get(f"/api/v2/projects/{project['id']}/nodes", headers=_headers(t1)).json()["items"] == []


def test_create_node_rejects_unknown_field(client):
    t = _login(client, "nc")
    project = client.post("/api/v2/projects", json={"title": "x"}, headers=_headers(t)).json()
    resp = client.post(
        f"/api/v2/projects/{project['id']}/nodes",
        json={"code": "K1", "title": "t", "unknown": 1},
        headers=_headers(t),
    )
    assert resp.status_code == 422, resp.text
