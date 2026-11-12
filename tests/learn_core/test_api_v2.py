"""API 契约测试：身份、错误体、项目 CRUD、任务事件流。"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from learn_api.auth import Principal, set_verifier
from learn_api.app import create_app
from learn_core.db.engine import reset_engine, session_scope
from learn_core.db.models import Tenant
from learn_core.tenancy.context import tenant_context

pytestmark = pytest.mark.skipif(
    os.getenv("LEARN_DATABASE_URL") is None,
    reason="需要 LEARN_DATABASE_URL 指向测试库",
)


class FakeVerifier:
    def __init__(self) -> None:
        self.by_ticket: dict[str, Principal] = {}

    def verify(self, ticket: str) -> Principal:
        if ticket not in self.by_ticket:
            from learn_api.errors import ApiError

            raise ApiError("UNAUTHENTICATED", "unknown ticket")
        return self.by_ticket[ticket]


@pytest.fixture()
def client():
    reset_engine()
    verifier = FakeVerifier()
    set_verifier(verifier)
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as c:
        c.verifier = verifier  # type: ignore[attr-defined]
        yield c
    reset_engine()


def _login(client: TestClient, ticket: str) -> str:
    user_id = f"api-{ticket}-{uuid.uuid4().hex[:6]}"
    client.verifier.by_ticket[ticket] = Principal(official_user_id=user_id)  # type: ignore[attr-defined]
    return user_id


def _headers(ticket: str) -> dict:
    return {"X-Learn-Ticket": ticket}


def _drop_user(user_id: str) -> None:
    with session_scope() as session:
        session.execute(text("DELETE FROM tenant WHERE official_user_id = :u"), {"u": user_id})


def test_missing_ticket_is_unauthenticated(client: TestClient):
    response = client.get("/api/v2/projects")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "UNAUTHENTICATED"
    assert body["error"]["retryable"] is False


def test_project_crud_and_error_shapes(client: TestClient):
    uid = _login(client, "t1")
    try:
        created = client.post(
            "/api/v2/projects",
            json={"title": "线性代数复习", "topic": "math", "weeklyHours": 6},
            headers=_headers("t1"),
        )
        assert created.status_code == 201, created.text
        project = created.json()
        assert project["title"] == "线性代数复习"
        assert project["weeklyHours"] == 6

        listed = client.get("/api/v2/projects", headers=_headers("t1")).json()
        assert [p["id"] for p in listed["items"]] == [project["id"]]

        updated = client.patch(
            f"/api/v2/projects/{project['id']}",
            json={"status": "paused"},
            headers=_headers("t1"),
        ).json()
        assert updated["status"] == "paused"

        invalid = client.post("/api/v2/projects", json={"title": ""}, headers=_headers("t1"))
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "INVALID_ARGUMENT"

        missing = client.get("/api/v2/projects/999999", headers=_headers("t1"))
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "NOT_FOUND"

        deleted = client.delete(f"/api/v2/projects/{project['id']}", headers=_headers("t1"))
        assert deleted.status_code == 204
    finally:
        _drop_user(uid)


def test_projects_are_isolated_between_accounts(client: TestClient):
    uid_a = _login(client, "ta")
    uid_b = _login(client, "tb")
    try:
        client.post(
            "/api/v2/projects",
            json={"title": "甲的课题"},
            headers=_headers("ta"),
        )
        b_items = client.get("/api/v2/projects", headers=_headers("tb")).json()["items"]
        assert b_items == []
    finally:
        _drop_user(uid_a)
        _drop_user(uid_b)


def test_job_status_and_event_stream(client: TestClient):
    uid = _login(client, "tj")
    try:
        with session_scope() as session:
            tenant = session.execute(
                text(
                    """
                    INSERT INTO tenant (official_user_id) VALUES (:u)
                    ON CONFLICT (official_user_id) DO UPDATE SET last_seen_at = now()
                    RETURNING id
                    """
                ),
                {"u": uid},
            ).scalar_one()
        with tenant_context(tenant):
            with session_scope() as session:
                session.execute(
                    text(
                        """
                        INSERT INTO job_progress (tenant_id, job_id, kind, subject, state, progress)
                        VALUES (:tid, 'job-1', 'index', 'file.pdf', 'running', '{"done": 1}')
                        """
                    ),
                    {"tid": tenant},
                )

        status = client.get("/api/v2/jobs/job-1", headers=_headers("tj")).json()
        assert status["state"] == "running"

        with client.stream("GET", "/api/v2/jobs/job-1/events", headers=_headers("tj")) as stream:
            lines = stream.iter_lines()
            first = next(lines)
            second = next(lines)
        assert first.startswith("event: progress")
        assert '"jobId": "job-1"' in second
    finally:
        _drop_user(uid)


def test_search_degrades_when_embeddings_are_unavailable(client: TestClient):
    uid = _login(client, "ts")
    try:
        response = client.post(
            "/api/v2/search",
            json={"indexId": "course:1", "query": "能量最小化", "limit": 5},
            headers=_headers("ts"),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["hits"] == []
    finally:
        _drop_user(uid)
