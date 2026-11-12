"""索引任务：切块落库、重索引替换、以及 202 提交接口。"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from learn_api.app import create_app
from learn_api.auth import Principal, set_verifier
from learn_core.db.engine import reset_engine, session_scope
from learn_core.db.models import Tenant
from learn_core.learning import projects as project_service
from learn_core.rag.index import index_source
from learn_core.tenancy.context import tenant_context

pytestmark = pytest.mark.skipif(
    os.getenv("LEARN_DATABASE_URL") is None,
    reason="需要 LEARN_DATABASE_URL 指向测试库",
)


class FakeEmbedder:
    """固定向量：只有文本长度参与，保证可复现。"""

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        out = []
        for t in texts:
            v = [0.0] * 384
            v[0] = 1.0
            v[1] = (len(t) % 97) / 97.0
            out.append(v)
        return out


def _tenant_with_project() -> tuple[uuid.UUID, int]:
    with session_scope() as session:
        tenant = Tenant(official_user_id=f"idx-{uuid.uuid4().hex[:8]}")
        session.add(tenant)
        session.flush()
        tid = tenant.id
    with tenant_context(tid):
        with session_scope() as session:
            project = project_service.create_project(session, title="索引测试")
            pid = project.id
    return tid, pid


def test_index_source_writes_chunks_and_replaces_stale_ones():
    tid, _ = _tenant_with_project()
    long_text = "\n\n".join(f"第 {i} 段。" + "内容" * 200 for i in range(6))
    short_text = "只有一小段。"

    with tenant_context(tid):
        with session_scope() as session:
            n1 = index_source(session, source_id="src-1", text=long_text, embedder=FakeEmbedder())
            assert n1 > 1
        with session_scope() as session:
            ids = session.execute(
                text("SELECT chunk_id FROM rag_chunk WHERE tenant_id = :t ORDER BY chunk_id"),
                {"t": tid},
            ).scalars().all()
            assert ids == [f"src-1:{i}" for i in range(n1)]

        with session_scope() as session:
            n2 = index_source(session, source_id="src-1", text=short_text, embedder=FakeEmbedder())
            assert n2 == 1
        with session_scope() as session:
            ids = session.execute(
                text("SELECT chunk_id FROM rag_chunk WHERE tenant_id = :t"), {"t": tid}
            ).scalars().all()
    assert ids == ["src-1:0"], "重新切块变短后，旧块必须删掉"


def test_index_source_is_tenant_isolated():
    tid_a, _ = _tenant_with_project()
    tid_b, _ = _tenant_with_project()
    with tenant_context(tid_a):
        with session_scope() as session:
            index_source(session, source_id="same", text="甲的资料", embedder=FakeEmbedder())
    with tenant_context(tid_b):
        with session_scope() as session:
            rows = session.execute(text("SELECT count(*) FROM rag_chunk")).scalar_one()
    assert rows == 0


def test_submit_source_returns_202_and_hides_enqueue_details(monkeypatch):
    reset_engine()
    calls: list[dict] = []
    monkeypatch.setattr(
        "learn_core.jobs.enqueue.enqueue_index",
        lambda **kw: calls.append(kw) or "42",
    )

    stable_user = f"src-{uuid.uuid4().hex[:8]}"

    class Verifier:
        def verify(self, ticket: str) -> Principal:
            return Principal(official_user_id=stable_user)

    set_verifier(Verifier())
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        project = client.post(
            "/api/v2/projects",
            json={"title": "资料"},
            headers={"X-Learn-Ticket": "t1"},
        )
        assert project.status_code == 201, project.text
        pid = project.json()["id"]

        resp = client.post(
            f"/api/v2/projects/{pid}/sources",
            json={"sourceId": "paper-1", "text": "第一段。\n\n第二段。"},
            headers={"X-Learn-Ticket": "t1"},
        )
        assert resp.status_code == 202, resp.text
        job_id = resp.json()["jobId"]
        assert job_id.startswith("idx-")
        assert resp.headers["Location"].endswith(f"/jobs/{job_id}")

        status = client.get(f"/api/v2/jobs/{job_id}", headers={"X-Learn-Ticket": "t1"})
    assert status.status_code == 200
    assert status.json()["state"] == "queued"

    assert len(calls) == 1
    assert calls[0]["source_id"] == "paper-1"
    assert calls[0]["job_id"] == job_id
    reset_engine()
