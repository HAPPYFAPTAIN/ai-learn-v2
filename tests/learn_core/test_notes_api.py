"""笔记与任务接口。"""

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
        self.by_ticket: dict[str, Principal] = {}

    def verify(self, ticket: str) -> Principal:
        if ticket not in self.by_ticket:
            raise ApiError("UNAUTHENTICATED", "unknown ticket")
        return self.by_ticket[ticket]


@pytest.fixture()
def client():
    reset_engine()
    verifier = _Verifier()
    set_verifier(verifier)
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        c.verifier = verifier  # type: ignore[attr-defined]
        yield c
    reset_engine()


def _login(client, prefix: str) -> dict:
    ticket = f"t-{uuid.uuid4().hex[:8]}"
    client.verifier.by_ticket[ticket] = Principal(  # type: ignore[attr-defined]
        official_user_id=f"{prefix}-{uuid.uuid4().hex[:8]}"
    )
    return {"X-Learn-Ticket": ticket}


def _project(client, headers, title="笔记") -> int:
    return client.post("/api/v2/projects", json={"title": title}, headers=headers).json()["id"]


def test_note_crud(client):
    headers = _login(client, "nt")
    project_id = _project(client, headers)
    node = client.post(
        f"/api/v2/projects/{project_id}/nodes",
        json={"code": "A1", "title": "节点"},
        headers=headers,
    ).json()

    created = client.post(
        f"/api/v2/projects/{project_id}/notes",
        json={"nodeId": node["id"], "content": "第一条笔记", "selection": "原文"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    note = created.json()
    assert note["content"] == "第一条笔记"

    listed = client.get(
        f"/api/v2/projects/{project_id}/notes",
        params={"nodeId": node["id"]},
        headers=headers,
    ).json()
    assert len(listed["items"]) == 1

    updated = client.patch(f"/api/v2/notes/{note['id']}", json={"content": "改过"}, headers=headers)
    assert updated.json()["content"] == "改过"

    assert client.delete(f"/api/v2/notes/{note['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/v2/projects/{project_id}/notes", headers=headers).json()["items"] == []


def test_task_lifecycle_and_validation(client):
    headers = _login(client, "tk")
    project_id = _project(client, headers, "任务")

    created = client.post(
        f"/api/v2/projects/{project_id}/tasks",
        json={"title": "读第一章", "taskType": "reading"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["status"] == "pending"

    done = client.patch(
        f"/api/v2/tasks/{task['id']}",
        json={"status": "done", "output": "读完"},
        headers=headers,
    ).json()
    assert done["status"] == "done" and done["output"] == "读完"

    bad = client.patch(f"/api/v2/tasks/{task['id']}", json={"status": "whatever"}, headers=headers)
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "INVALID_ARGUMENT"

    pending = client.get(
        f"/api/v2/projects/{project_id}/tasks", params={"status": "pending"}, headers=headers
    ).json()
    assert pending["items"] == []


def test_notes_isolated_between_tenants(client):
    t1 = _login(client, "nta")
    t2 = _login(client, "ntb")
    project_id = _project(client, t1, "隔离")
    node = client.post(
        f"/api/v2/projects/{project_id}/nodes",
        json={"code": "B1", "title": "n"},
        headers=t1,
    ).json()
    note = client.post(
        f"/api/v2/projects/{project_id}/notes",
        json={"nodeId": node["id"], "content": "私有"},
        headers=t1,
    ).json()

    assert client.patch(f"/api/v2/notes/{note['id']}", json={"content": "x"}, headers=t2).status_code == 404
    assert client.get(f"/api/v2/projects/{project_id}/notes", headers=t2).status_code == 404
