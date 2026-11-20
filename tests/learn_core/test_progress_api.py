"""进度记录与项目概览。"""

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


def test_summary_aggregates_nodes_and_minutes(client):
    headers = _login(client, "pg")
    project = client.post("/api/v2/projects", json={"title": "进度项目"}, headers=headers).json()
    pid = project["id"]

    for code, status in (("K1", "todo"), ("K2", "done"), ("K3", "done")):
        node = client.post(
            f"/api/v2/projects/{pid}/nodes",
            json={"code": code, "title": code, "estHours": 1},
            headers=headers,
        ).json()
        if status != "todo":
            client.patch(f"/api/v2/nodes/{node['id']}", json={"status": status}, headers=headers)

    for minutes in (25, 35):
        assert (
            client.post(
                f"/api/v2/projects/{pid}/progress",
                json={"metric": "minutes", "value": minutes},
                headers=headers,
            ).status_code
            == 201
        )

    summary = client.get(f"/api/v2/projects/{pid}/summary", headers=headers).json()
    assert summary["totalNodes"] == 3
    assert summary["completedNodes"] == 2
    assert summary["completionRatio"] == 0.6667
    assert summary["masteredNodes"] == 0
    assert summary["masteryRatio"] == 0
    assert summary["studyMinutes"] == 60.0

    listed = client.get(f"/api/v2/projects/{pid}/progress", headers=headers).json()
    assert len(listed["items"]) == 4
    assert sum(r['metric'] == 'mastery' for r in listed['items']) == 2


def test_unknown_metric_is_rejected(client):
    headers = _login(client, "ph")
    pid = client.post("/api/v2/projects", json={"title": "x"}, headers=headers).json()["id"]
    resp = client.post(
        f"/api/v2/projects/{pid}/progress",
        json={"metric": "vibes", "value": 1},
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_ARGUMENT"
