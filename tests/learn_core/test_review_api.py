"""卡片与复习：排程推进、到期查询、跨租户隔离。"""

from __future__ import annotations

import os
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from learn_api.app import create_app
from learn_api.auth import Principal, set_verifier
from learn_api.errors import ApiError
from learn_core.db.engine import reset_engine
from learn_core.review import scheduler

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


def test_card_lifecycle(client):
    headers = _login(client, "rv")
    project = client.post("/api/v2/projects", json={"title": "复习"}, headers=headers).json()

    card = client.post(
        "/api/v2/cards",
        json={"front": "ATP 是什么", "back": "三磷酸腺苷", "projectId": project["id"]},
        headers=headers,
    ).json()
    assert card["state"] == scheduler.STATE_NEW

    due = client.get("/api/v2/review/due", headers=headers).json()["items"]
    assert [c["id"] for c in due] == [card["id"]]

    good = client.post(f"/api/v2/review/{card['id']}", json={"rating": 3}, headers=headers).json()
    assert good["reps"] == 1
    assert good["step"] == 1
    assert good["state"] == scheduler.STATE_LEARNING

    # 间隔 1 天后才再次到期
    assert client.get("/api/v2/review/due", headers=headers).json()["items"] == []

    easy = client.post(f"/api/v2/review/{card['id']}", json={"rating": 4}, headers=headers).json()
    assert easy["step"] == 3 and easy["state"] == scheduler.STATE_REVIEW

    again = client.post(f"/api/v2/review/{card['id']}", json={"rating": 1}, headers=headers).json()
    assert again["step"] == 0 and again["state"] == scheduler.STATE_RELEARNING
    assert client.get("/api/v2/review/due", headers=headers).json()["items"] == []


def test_due_respects_interval_and_isolation(client):
    t1 = _login(client, "rva")
    t2 = _login(client, "rvb")
    p1 = client.post("/api/v2/projects", json={"title": "a"}, headers=t1).json()
    card = client.post(
        "/api/v2/cards", json={"front": "q", "back": "a", "projectId": p1["id"]}, headers=t1
    ).json()
    client.post(f"/api/v2/review/{card['id']}", json={"rating": 3}, headers=t1)

    assert client.get("/api/v2/review/due", headers=t2).json()["items"] == []
    assert client.get(f"/api/v2/projects/{p1['id']}/cards", headers=t2).status_code == 404

    cards = client.get(f"/api/v2/projects/{p1['id']}/cards", headers=t1).json()["items"]
    assert len(cards) == 1 and cards[0]["reps"] == 1
    assert cards[0]["nextReview"] is not None


def test_invalid_rating_rejected(client):
    headers = _login(client, "rvc")
    card = client.post("/api/v2/cards", json={"front": "q", "back": "a"}, headers=headers).json()
    assert client.post(f"/api/v2/review/{card['id']}", json={"rating": 5}, headers=headers).status_code == 422
