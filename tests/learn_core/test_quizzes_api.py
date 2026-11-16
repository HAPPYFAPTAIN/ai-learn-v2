"""测验：建卷、取卷隐藏答案、判分、隔离。"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

from learn_api.app import create_app
from learn_api.auth import Principal, set_verifier
from learn_api.errors import ApiError
from learn_core.db.engine import reset_engine, session_scope
from learn_core.db.models import Tenant
from learn_core.learning.generation import run_generation
from sqlalchemy import select

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
                {"stem": "1+1", "qtype": "choice", "answer": "A", "options": ["A.2", "B.3", "C.4", "D.5"]},
                {"stem": "水的化学式", "qtype": "choice", "answer": "B", "options": ["A.O2", "B.H2O", "C.CO2", "D.H2"], "explanation": "两个氢一个氧"},
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

    submitted = client.post(
        f"/api/v2/quizzes/{quiz['id']}/submit",
        json={"answers": {str(qids[0]): " a ", str(qids[1]): "b"}},
        headers=headers,
    )
    assert submitted.status_code == 202, submitted.text
    official_id = client.verifier.by_ticket[headers["X-Learn-Ticket"]].official_user_id
    with session_scope() as session:
        tid = session.scalar(select(Tenant.id).where(Tenant.official_user_id == official_id))
    run_generation(tenant=str(tid), job_id=submitted.json()["jobId"])
    result = client.get(f"/api/v2/quizzes/{quiz['id']}/result", headers=headers).json()
    assert result["correct"] == 2 and result["score"] == 1.0

    duplicate = client.post(
        f"/api/v2/quizzes/{quiz['id']}/submit",
        json={"answers": {str(qids[0]): "B"}},
        headers=headers,
    ).json()
    assert duplicate["jobId"] == submitted.json()["jobId"]
    assert client.get(f"/api/v2/quizzes/{quiz['id']}/result", headers=headers).json() == result


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
