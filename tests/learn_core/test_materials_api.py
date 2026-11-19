"""资料上传：落盘、建元数据、派生索引任务。"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from learn_api.app import create_app
from learn_api.auth import Principal, set_verifier
from learn_api.errors import ApiError
from learn_core.config import get_settings
from learn_core.db.engine import reset_engine, session_scope
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
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LEARN_FILES_ROOT", str(tmp_path / "files"))
    get_settings.cache_clear()
    reset_engine()
    verifier = _Verifier()
    set_verifier(verifier)
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        c.verifier = verifier  # type: ignore[attr-defined]
        yield c
    reset_engine()
    get_settings.cache_clear()


def _login(client) -> dict:
    ticket = f"t-{uuid.uuid4().hex[:8]}"
    client.verifier.by_ticket[ticket] = Principal(  # type: ignore[attr-defined]
        official_user_id=f"mt-{uuid.uuid4().hex[:8]}"
    )
    return {"X-Learn-Ticket": ticket}


def test_upload_writes_file_and_queues_index(client):
    headers = _login(client)
    project = client.post("/api/v2/projects", json={"title": "资料"}, headers=headers).json()

    content = "第一章 绪论\n学习是把新信息接到旧结构上。"
    response = client.post(
        f"/api/v2/projects/{project['id']}/materials",
        files={"file": ("intro.txt", content.encode(), "text/plain")},
        headers=headers,
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["jobId"] and body["sizeBytes"] == len(content.encode())
    with session_scope() as session:
        args = session.execute(text("SELECT args FROM procrastinate_jobs WHERE args->>'job_id'=:j"), {'j':body['jobId']}).scalar_one()
        assert args['file_id'] == body['fileId'] and 'text' not in args

    root = Path(get_settings().files_root)
    assert list(root.rglob(body["sha256"])), "文件应已落盘"

    listing = client.get(f"/api/v2/projects/{project['id']}/materials", headers=headers).json()
    assert listing["items"][0]["name"] == "intro.txt"


def test_upload_rejects_empty_and_missing_project(client):
    headers = _login(client)

    project = client.post("/api/v2/projects", json={"title": "x"}, headers=headers).json()
    empty = client.post(
        f"/api/v2/projects/{project['id']}/materials",
        files={"file": ("e.txt", b"", "text/plain")},
        headers=headers,
    )
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "INVALID_ARGUMENT"

    other = client.post(
        "/api/v2/projects/999999/materials",
        files={"file": ("a.txt", b"hi", "text/plain")},
        headers=headers,
    )
    assert other.status_code == 404


def test_upload_dedupes_content_but_keeps_one_row(client):
    headers = _login(client)
    project = client.post("/api/v2/projects", json={"title": "d"}, headers=headers).json()

    for _ in range(2):
        client.post(
            f"/api/v2/projects/{project['id']}/materials",
            files={"file": ("a.txt", b"same", "text/plain")},
            headers=headers,
        )
    with session_scope() as session:
        tenant_id = session.execute(
            text("SELECT id FROM tenant ORDER BY created_at DESC LIMIT 1")
        ).scalar_one()
    with tenant_context(tenant_id):
        with session_scope() as session:
            count = session.execute(
                text("SELECT count(*) FROM stored_file WHERE sha256 = :h"),
                {"h": __import__("hashlib").sha256(b"same").hexdigest()},
            ).scalar_one()
    assert count == 1
