"""每日报告：按当天进度汇总、空日也有记录。"""

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


def _login(client) -> dict:
    ticket = f"t-{uuid.uuid4().hex[:8]}"
    client.verifier.by_ticket[ticket] = Principal(  # type: ignore[attr-defined]
        official_user_id=f"rep-{uuid.uuid4().hex[:8]}"
    )
    return {"X-Learn-Ticket": ticket}


def test_report_aggregates_today_and_lists(client):
    headers = _login(client)
    project = client.post("/api/v2/projects", json={"title": "报告"}, headers=headers).json()
    pid = project["id"]

    for metric, value in (("minutes", 35), ("cards_reviewed", 12), ("quiz_correct", 4), ("quiz_total", 5)):
        client.post(
            f"/api/v2/projects/{pid}/progress",
            json={"metric": metric, "value": value},
            headers=headers,
        )

    report = client.post(f"/api/v2/projects/{pid}/reports", headers=headers).json()
    assert report["studyMinutes"] == 35
    assert report["cardsReviewed"] == 12
    assert "80%" in report["content"]

    listed = client.get(f"/api/v2/projects/{pid}/reports", headers=headers).json()
    assert listed["items"][0]["id"] == report["id"]


def test_report_for_quiet_day(client):
    headers = _login(client)
    project = client.post("/api/v2/projects", json={"title": "空"}, headers=headers).json()
    report = client.post(f"/api/v2/projects/{project['id']}/reports", headers=headers).json()
    assert report["studyMinutes"] == 0
    assert "没有学习记录" in report["content"]
