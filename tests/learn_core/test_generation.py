"""Legacy migration contract and real PostgreSQL job/tenant/version regression."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from learn_api.app import create_app
from learn_api.deps import get_tenant_id
from learn_core.db.engine import get_engine, reset_engine, session_scope
from learn_core.db.models import Tenant, TenantSetting, Project, JobProgress, Knode, Kedge, ModelCall
from learn_core.learning import generation
from learn_core.learning.generation import GenerationConflict, GenerationMissing, submit_generation, run_generation
from learn_core.learning.paths import build_plan
from learn_core.learning.roadmaps import Roadmap, parse_roadmap
from learn_core.llm.gateway import GatewayClient
from learn_core.tenancy.context import tenant_context

ROADMAP = {"summary": "Python 学习路线", "stages": [{"name": "基础", "stage": "base"}], "nodes": [
    {"code": "2.10", "title": "综合实践", "prerequisites": ["2.2"]},
    {"code": "2.2", "title": "变量", "prerequisites": ["1.1"]},
    {"code": "1.1", "title": "入门", "prerequisites": []},
]}
LESSON = "## 本节导览\n" + "解释变量并用真实例子验证学习结果。" * 45 + "\n## 本节小结\n用自己的话解释变量。"


def test_legacy_roadmap_json_and_validation():
    assert parse_roadmap("```json\n" + json.dumps(ROADMAP) + "\n```").nodes[0].code == "2.10"
    for nodes in (
        [{"code": "A", "title": "A"}, {"code": "A", "title": "duplicate"}],
        [{"code": "A", "title": "A", "prerequisites": ["missing"]}],
        [{"code": "A", "title": "A", "prerequisites": ["B"]}, {"code": "B", "title": "B", "prerequisites": ["A"]}],
        [{"code": "A", "title": "A", "est_hours": float("nan")}],
    ):
        with pytest.raises(ValueError):
            Roadmap.model_validate({"nodes": nodes})


def test_prompts_do_not_import_legacy_runtime():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, "-c", "import sys; import learn_core.learning.generation; assert not any(n.startswith(('learning_ext', 'gradio', 'ktem')) for n in sys.modules)"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    from learn_core.learning.prompts.lesson import lesson_prompt
    prompt = lesson_prompt(chapter={"code": "1.1", "title": "变量", "description": "变量基础", "difficulty": 1, "est_hours": 2}, project_topic="Python", learning_goal="理解变量")
    assert "核心概念详解" in prompt and "本节小结" in prompt
    assert "<details>" not in prompt
    assert sorted(["2.10", "2.2", "1.1"], key=generation.course_code_sort_key) == ["1.1", "2.2", "2.10"]


db_test = pytest.mark.skipif(not os.getenv("LEARN_DATABASE_URL"), reason="需要独立 PostgreSQL 测试库")


@pytest.fixture
def tenant():
    reset_engine()
    with session_scope() as session:
        row = Tenant(official_user_id=f"fusion-{uuid4().hex}")
        session.add(row)
        session.flush()
        tid = row.id
    with tenant_context(tid), session_scope() as session:
        session.add(TenantSetting(tenant_id=tid, chat_model="deepseek-test"))
        project = Project(title="Python", topic="Python", goal="学会基础")
        session.add(project)
        session.flush()
        pid = project.id
    yield tid, pid
    with session_scope() as session:
        session.execute(text("DELETE FROM procrastinate_jobs WHERE args->>'tenant' = :tid"), {"tid": str(tid)})
        session.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tid})
    reset_engine()


def enqueue(tenant, kind="roadmap", node_id=None, force=False):
    tid, pid = tenant
    with tenant_context(tid), session_scope() as session:
        row = submit_generation(session, project_id=pid, kind=kind, node_id=node_id, force=force)
        return row.job_id


def read_job(tenant, jid):
    with tenant_context(tenant[0]), session_scope() as session:
        row = session.scalar(select(JobProgress).where(JobProgress.job_id == jid))
        return row.state, dict(row.progress), row.error


def mock_gateway(monkeypatch, content=None, handler=None):
    def respond(request):
        assert get_engine().pool.checkedout() == 0, "HTTP 等待不能占用业务数据库连接"
        assert request.headers["X-End-User"].startswith("fusion-")
        body = json.loads(request.content)
        assert body["reasoning_effort"] == "low"
        return httpx.Response(200, json={"model": "deepseek-test", "choices": [{"message": {"content": content}, "finish_reason": "stop"}], "usage": {"total_tokens": 42}})
    monkeypatch.setattr(generation, "GatewayClient", lambda: GatewayClient(transport=httpx.MockTransport(handler or respond)))


@db_test
def test_atomic_enqueue_and_duplicate_clicks(tenant):
    jid = enqueue(tenant)
    assert enqueue(tenant) == jid
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.scalar(text("SELECT count(*) FROM procrastinate_jobs WHERE args->>'job_id' = :j"), {"j": jid}) == 1
    # A rolled back business transaction must not leave an executable queue job.
    with tenant_context(tenant[0]), session_scope() as session:
        project = Project(title="rollback")
        session.add(project)
        session.flush()
        orphan = submit_generation(session, project_id=project.id, kind="roadmap").job_id
        session.rollback()
    with session_scope() as session:
        assert session.scalar(text("SELECT count(*) FROM procrastinate_jobs WHERE args->>'job_id' = :j"), {"j": orphan}) == 0


@db_test
def test_roadmap_and_lesson_use_legacy_rules_and_persist_timings(tenant, monkeypatch):
    jid = enqueue(tenant)
    mock_gateway(monkeypatch, json.dumps(ROADMAP))
    run_generation(tenant=str(tenant[0]), job_id=jid)
    state, progress, error = read_job(tenant, jid)
    assert state == "done", error
    assert progress["count"] == 3 and progress["totalMs"] >= progress["modelMs"] >= 0
    with tenant_context(tenant[0]), session_scope() as session:
        plan = build_plan(session, project_id=tenant[1], weeks=1)
        assert [n["code"] for n in plan["weeks"][0]["items"]] == ["1.1", "2.2", "2.10"]
        node = session.scalar(select(Knode).where(Knode.project_id == tenant[1], Knode.code == "1.1"))
        nid = node.id
    # Crash recovery after the result commit is a no-op, not a second charge.
    monkeypatch.setattr(generation, "GatewayClient", lambda: pytest.fail("已经完成不应再次调用模型"))
    run_generation(tenant=str(tenant[0]), job_id=jid)
    lesson = enqueue(tenant, "lesson", nid)
    mock_gateway(monkeypatch, LESSON)
    run_generation(tenant=str(tenant[0]), job_id=lesson)
    assert read_job(tenant, lesson)[0] == "done"
    with tenant_context(tenant[0]), session_scope() as session:
        node = session.get(Knode, nid)
        assert node.content_version == 1 and node.description == LESSON
        calls = list(session.scalars(select(ModelCall)))
        assert {c.job_id for c in calls} == {jid, lesson}
        assert session.scalar(text("SELECT count(*) FROM llm_lease")) == 0


@db_test
def test_invalid_model_output_does_not_create_partial_nodes(tenant, monkeypatch):
    jid = enqueue(tenant)
    mock_gateway(monkeypatch, '{"nodes":[{"code":"1","title":"A","prerequisites":["missing"]}]}')
    run_generation(tenant=str(tenant[0]), job_id=jid)
    assert read_job(tenant, jid)[0] == "failed"
    with tenant_context(tenant[0]), session_scope() as session:
        assert not list(session.scalars(select(Knode)))


@db_test
def test_inflight_edit_discards_result_and_other_tenant_cannot_generate(tenant, monkeypatch):
    jid = enqueue(tenant)
    def respond(request):
        with tenant_context(tenant[0]), session_scope() as session:
            session.get(Project, tenant[1]).goal = "新目标"
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(ROADMAP)}}]})
    mock_gateway(monkeypatch, handler=respond)
    run_generation(tenant=str(tenant[0]), job_id=jid)
    assert read_job(tenant, jid)[0] == "cancelled"
    with tenant_context(uuid4()), session_scope() as session:
        with pytest.raises(GenerationMissing):
            submit_generation(session, project_id=tenant[1], kind="roadmap")
        assert session.scalar(select(JobProgress).where(JobProgress.job_id == jid)) is None


@db_test
def test_transport_replay_same_event_but_business_retry_new_event(tenant, monkeypatch):
    jid = enqueue(tenant)
    seen = []
    def respond(request):
        seen.append(request.headers["X-Event-Id"])
        if len(seen) == 1:
            raise httpx.ReadTimeout("simulated disconnect")
        return httpx.Response(503, text="provider secret must not reach UI")
    mock_gateway(monkeypatch, handler=respond)
    with pytest.raises(generation.RetryableGenerationError) as exc:
        run_generation(tenant=str(tenant[0]), job_id=jid)
    assert exc.value.delay == 10
    assert seen[0] == seen[1]
    assert read_job(tenant, jid)[0] == "queued"
    mock_gateway(monkeypatch, json.dumps(ROADMAP))
    run_generation(tenant=str(tenant[0]), job_id=jid, attempt=1)
    assert read_job(tenant, jid)[0] == "done"
    with tenant_context(tenant[0]), session_scope() as session:
        calls = list(session.scalars(select(ModelCall).order_by(ModelCall.id)))
        assert calls[0].event_id != calls[1].event_id
        assert calls[0].status == "http_503" and calls[1].status == "ok"


@db_test
@pytest.mark.parametrize("status", [400, 401, 402, 403, 404])
def test_terminal_gateway_failure_is_visible_without_retry(tenant, monkeypatch, status):
    jid = enqueue(tenant)
    mock_gateway(monkeypatch, handler=lambda request: httpx.Response(status, text="private-token"))
    run_generation(tenant=str(tenant[0]), job_id=jid)
    state, _, error = read_job(tenant, jid)
    assert state == "failed" and str(status) in error and "private-token" not in error


@db_test
def test_generation_api_returns_job_and_rejects_nonempty_project(tenant):
    app = create_app()
    app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    with TestClient(app) as client:
        response = client.post(f"/api/v2/projects/{tenant[1]}/roadmap-jobs")
        assert response.status_code == 202, response.text
        assert response.json()["state"] == "queued"
        assert client.post(f"/api/v2/projects/{tenant[1]}/roadmap-jobs").json() == response.json()
        assert client.post("/api/v2/nodes/999999999/lesson-jobs", json={}).status_code == 404


@db_test
def test_versioned_lesson_does_not_overwrite_edit_during_model_call(tenant, monkeypatch):
    with tenant_context(tenant[0]), session_scope() as session:
        node = Knode(project_id=tenant[1], code="1", title="变量", description="原章节说明")
        session.add(node)
        session.flush()
        nid = node.id
    jid = enqueue(tenant, "lesson", nid)
    def respond(request):
        from learn_core.learning.nodes import update_node
        with tenant_context(tenant[0]), session_scope() as session:
            update_node(session, nid, description="用户刚刚修改的内容")
        return httpx.Response(200, json={"choices": [{"message": {"content": LESSON}}]})
    mock_gateway(monkeypatch, handler=respond)
    run_generation(tenant=str(tenant[0]), job_id=jid)
    assert read_job(tenant, jid)[0] == "cancelled"
    with tenant_context(tenant[0]), session_scope() as session:
        node = session.get(Knode, nid)
        assert node.description == "用户刚刚修改的内容" and node.content_version == 1


@db_test
def test_nonempty_project_is_preserved_and_missing_model_rejected(tenant):
    with tenant_context(tenant[0]), session_scope() as session:
        node = Knode(project_id=tenant[1], code="1", title="手动章节")
        session.add(node)
    with tenant_context(tenant[0]), session_scope() as session:
        with pytest.raises(GenerationConflict, match="已有章节"):
            submit_generation(session, project_id=tenant[1], kind="roadmap")
        session.get(TenantSetting, tenant[0]).chat_model = ""
        nid = session.scalar(select(Knode.id).where(Knode.project_id == tenant[1]))
    with tenant_context(tenant[0]), session_scope() as session:
        with pytest.raises(GenerationConflict, match="主模型"):
            submit_generation(session, project_id=tenant[1], kind="lesson", node_id=nid)


@db_test
def test_real_queue_worker_executes_the_registered_generation_task(tenant, monkeypatch):
    from learn_core.jobs.app import app
    jid = enqueue(tenant)
    mock_gateway(monkeypatch, json.dumps(ROADMAP))
    with app.open():
        app.run_worker(queues=["llm"], concurrency=1, wait=False, install_signal_handlers=False)
    assert read_job(tenant, jid)[0] == "done"
