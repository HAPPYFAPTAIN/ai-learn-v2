"""测验：建卷、取卷隐藏答案、判分、隔离。"""

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


def test_quiz_create_get_submit(client):
    headers = _login(client, "qz")
    project = client.post("/api/v2/projects", json={"title": "测验"}, headers=headers).json()

    created = client.post(
        f"/api/v2/projects/{project['id']}/quizzes",
        json={
            "title": "第一章",
            "questions": [
                {"stem": "1+1", "answer": "2"},
                {"stem": "水的化学式", "answer": "H2O", "explanation": "两个氢一个氧"},
            ],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    quiz = created.json()
    qids = [q["id"] for q in quiz["questions"]]
    assert all("answer" not in q for q in quiz["questions"])

    fetched = client.get(f"/api/v2/quizzes/{quiz['id']}", headers=headers).json()
    assert all("answer" not in q for q in fetched["questions"])

    result = client.post(
        f"/api/v2/quizzes/{quiz['id']}/submit",
        json={"answers": {str(qids[0]): " 2 ", str(qids[1]): "h2o"}},
        headers=headers,
    ).json()
    assert result["correct"] == 2 and result["score"] == 1.0

    half = client.post(
        f"/api/v2/quizzes/{quiz['id']}/submit",
        json={"answers": {str(qids[0]): "3"}},
        headers=headers,
    ).json()
    assert half["correct"] == 0 and half["score"] == 0.0
    assert len(half["results"]) == 2


def test_quiz_isolated_between_tenants(client):
    t1 = _login(client, "qza")
    t2 = _login(client, "qzb")
    p1 = client.post("/api/v2/projects", json={"title": "a"}, headers=t1).json()
    quiz = client.post(
        f"/api/v2/projects/{p1['id']}/quizzes",
        json={"questions": [{"stem": "q", "answer": "a"}]},
        headers=t1,
    ).json()

    assert client.get(f"/api/v2/quizzes/{quiz['id']}", headers=t2).status_code == 404
    assert client.get(f"/api/v2/projects/{p1['id']}/quizzes", headers=t2).status_code == 404
