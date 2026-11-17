"""路径排期：拓扑顺序、周装箱、环的兜底。"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from learn_api.app import create_app
from learn_api.auth import Principal, set_verifier
from learn_api.errors import ApiError
from learn_core.db.engine import reset_engine, session_scope
from learn_core.db.models import Kedge
from learn_core.tenancy.context import tenant_context

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
        official_user_id=f"path-{uuid.uuid4().hex[:8]}"
    )
    return {"X-Learn-Ticket": ticket}


def _tenant_id() -> str:
    with session_scope() as session:
        return session.execute(text("SELECT id FROM tenant ORDER BY created_at DESC LIMIT 1")).scalar_one()


def test_path_respects_prerequisite_order(client):
    headers = _login(client)
    project = client.post("/api/v2/projects", json={"title": "路径"}, headers=headers).json()
    pid = project["id"]

    ids = {}
    for code, hours in (("C3", 3), ("A1", 2), ("B2", 4)):
        body = client.post(
            f"/api/v2/projects/{pid}/nodes",
            json={"code": code, "title": code, "estHours": hours},
            headers=headers,
        ).json()
        ids[code] = body["id"]

    tid = _tenant_id()
    with tenant_context(tid):
        with session_scope() as session:
            session.add(Kedge(project_id=pid, source_id=ids["B2"], target_id=ids["A1"], relation="prerequisite"))
            session.add(Kedge(project_id=pid, source_id=ids["C3"], target_id=ids["B2"], relation="prerequisite"))

    plan = client.post(
        f"/api/v2/projects/{pid}/path", json={"weeks": 2, "hoursPerWeek": 5}, headers=headers
    ).json()
    order = [item["code"] for week in plan["weeks"] for item in week["items"]]
    assert order == ["A1", "B2", "C3"]
    assert plan["totalHours"] == 9
    assert sum(len(w["items"]) for w in plan["weeks"]) == 3


def test_path_with_cycle_falls_back_to_stage_code(client):
    headers = _login(client)
    project = client.post("/api/v2/projects", json={"title": "环"}, headers=headers).json()
    pid = project["id"]
    a = client.post(f"/api/v2/projects/{pid}/nodes", json={"code": "A", "title": "A"}, headers=headers).json()
    b = client.post(f"/api/v2/projects/{pid}/nodes", json={"code": "B", "title": "B"}, headers=headers).json()

    tid = _tenant_id()
    with tenant_context(tid):
        with session_scope() as session:
            session.add(Kedge(project_id=pid, source_id=a["id"], target_id=b["id"]))
            session.add(Kedge(project_id=pid, source_id=b["id"], target_id=a["id"]))

    plan = client.post(f"/api/v2/projects/{pid}/path", json={"weeks": 1}, headers=headers).json()
    codes = [i["code"] for w in plan["weeks"] for i in w["items"]]
    assert sorted(codes) == ["A", "B"]
