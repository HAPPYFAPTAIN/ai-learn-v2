"""对话接口：事件 id 递增、网关错误映射。"""

from __future__ import annotations

import json
import os
import re
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from learn_api.app import create_app
from learn_api.auth import Principal, set_verifier
from learn_core.db.engine import reset_engine, session_scope
from learn_core.llm.gateway import GatewayClient

_USER = ""

pytestmark = pytest.mark.skipif(
    os.getenv("LEARN_DATABASE_URL") is None,
    reason="需要 LEARN_DATABASE_URL 指向测试库",
)


def _ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"model": "m1", "choices": [{"message": {"content": "答复"}}], "usage": {"total_tokens": 3}},
    )


@pytest.fixture()
def client(monkeypatch):
    reset_engine()
    global _USER
    user = _USER = f"chat-{uuid.uuid4().hex[:8]}"

    class Verifier:
        def verify(self, ticket: str) -> Principal:
            return Principal(official_user_id=user)

    set_verifier(Verifier())
    monkeypatch.setattr(
        "learn_api.routers.chat._gateway",
        lambda: GatewayClient(base_url="http://gw.test/v1", product_key="k", transport=httpx.MockTransport(_ok_handler)),
    )
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    reset_engine()


def _project(client: TestClient) -> int:
    r = client.post("/api/v2/projects", json={"title": "对话"}, headers={"X-Learn-Ticket": "t"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_chat_returns_content_and_increments_event_id(client):
    pid = _project(client)
    body = {"messages": [{"role": "user", "content": "你好"}]}

    first = client.post(f"/api/v2/projects/{pid}/chat", json=body, headers={"X-Learn-Ticket": "t"})
    assert first.status_code == 200, first.text
    assert first.json()["content"] == "答复"
    event_id = first.json()["eventId"]
    assert re.fullmatch(r"ln-j\d{6}-1-1", event_id), event_id

    second = client.post(f"/api/v2/projects/{pid}/chat", json=body, headers={"X-Learn-Ticket": "t"})
    assert second.status_code == 200
    assert second.json()["eventId"] != event_id, "业务重试必须是新号"

    from learn_core.tenancy.context import tenant_context

    with session_scope() as session:
        tid = session.execute(
            text("SELECT id FROM tenant WHERE official_user_id = :u"), {"u": _USER}
        ).scalar_one()
    with tenant_context(tid):
        with session_scope() as session:
            rows = session.execute(
                text("SELECT event_id, status FROM model_call ORDER BY id")
            ).all()
    assert [r[1] for r in rows] == ["ok", "ok"]
    assert rows[-1][0] == second.json()["eventId"], "记账的事件 id 要和返回的一致"


def test_chat_maps_gateway_429_to_tenant_busy(client, monkeypatch):
    pid = _project(client)
    monkeypatch.setattr(
        "learn_api.routers.chat._gateway",
        lambda: GatewayClient(
            base_url="http://gw.test/v1",
            product_key="k",
            transport=httpx.MockTransport(lambda r: httpx.Response(429, text="busy")),
        ),
    )
    r = client.post(
        f"/api/v2/projects/{pid}/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
        headers={"X-Learn-Ticket": "t"},
    )
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "TENANT_BUSY"
    assert r.json()["error"]["retryable"] is True
