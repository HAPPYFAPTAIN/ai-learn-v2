"""Small-beta regressions: assessment deletion and paid project creation replay."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text

from learn_api.deps import get_session, get_tenant_id
from learn_core.db.engine import session_scope
from learn_core.db.models import Card, CreationRequest, JobProgress, Knode, Project, Quiz, QuizAttempt, Tenant, TenantSetting
from learn_core.learning import nodes, quizzes
from learn_core.learning.progress import project_summary, refresh_mastery
from learn_core.tenancy.context import tenant_context
from tests.learn_core.test_generation import db_test, tenant
from tests.learn_core.test_pr10_followup import api


@db_test
@pytest.mark.parametrize("completed", [False, True])
def test_deleting_shared_quiz_recomputes_surviving_chapter_mastery(tenant, completed):
    with tenant_context(tenant[0]), session_scope() as session:
        first = nodes.create_node(session, project_id=tenant[1], code="1", title="remove")
        second = nodes.create_node(session, project_id=tenant[1], code="2", title="keep")
        first_id, second_id = first.id, second.id
        if completed:
            second.status = "done"
            session.add(Card(project_id=tenant[1], node_id=second.id, front="Q", back="A", stability=30))
        quiz = quizzes.create_quiz(session, project_id=tenant[1], title="shared", node_ids=[first.id, second.id], questions=[
            {"stem": "Q", "answer": "A", "node_id": second.id},
        ])
        quiz_id = quiz.id
        question = quizzes.quiz_questions(session, quiz.id)[0]
        session.add(QuizAttempt(question_id=question.id, is_correct=True, user_answer="A"))
        session.flush()
        assert refresh_mastery(session, node_id=second.id) == pytest.approx(1 if completed else .4)
    with tenant_context(tenant[0]), session_scope() as session:
        assert nodes.delete_node(session, first_id)
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.get(Quiz, quiz_id) is None
        survivor = session.get(Knode, second_id)
        assert survivor.mastery == pytest.approx(.6 if completed else 0)
        summary = project_summary(session, project_id=tenant[1])
        assert summary["masteredNodes"] == 0
        assert summary["completedNodes"] == int(completed)


def project_intent():
    return {"title": "replay project", "goal": "learn Python", "generateRoadmap": True, "requestId": str(uuid4())}


@db_test
@pytest.mark.parametrize("concurrent", [False, True])
def test_project_replay_creates_one_project_and_one_paid_job(tenant, api, concurrent):
    client, _ = api
    payload = project_intent()
    ready = Barrier(2)
    def send():
        if concurrent:
            ready.wait(timeout=10)
        response = client.post("/api/v2/projects", json=payload)
        assert response.status_code == 201, response.text
        return response.json()
    if concurrent:
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda _: send(), range(2)))
    else:
        replies = [send(), send()]
    assert replies[0] == replies[1]
    lookup = client.get(f"/api/v2/projects/creation-requests/{payload['requestId']}")
    assert lookup.status_code == 200 and lookup.json() == replies[0]
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.scalar(select(func.count()).select_from(Project).where(Project.title == payload["title"])) == 1
        assert session.scalar(select(func.count()).select_from(JobProgress)) == 1
        assert session.scalar(text("SELECT count(*) FROM procrastinate_jobs WHERE args->>'tenant' = :tid"), {"tid": str(tenant[0])}) == 1
    assert client.post("/api/v2/projects", json={**payload, "goal": "changed"}).status_code == 409
    deliberate = client.post("/api/v2/projects", json={**payload, "requestId": str(uuid4())})
    assert deliberate.status_code == 201 and deliberate.json()["id"] != replies[0]["id"]


@db_test
def test_project_rollback_retries_without_orphan_queue_or_consumed_receipt(tenant, api):
    client, _ = api
    payload = project_intent()
    async def rollback():
        with tenant_context(tenant[0]), session_scope() as session:
            yield session
            session.rollback()
    client.app.dependency_overrides[get_session] = rollback
    assert client.post("/api/v2/projects", json=payload).status_code == 201
    del client.app.dependency_overrides[get_session]
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.scalar(select(func.count()).select_from(JobProgress)) == 0
        assert session.scalar(select(func.count()).select_from(CreationRequest)) == 0
        assert session.scalar(text("SELECT count(*) FROM procrastinate_jobs WHERE args->>'tenant' = :tid"), {"tid": str(tenant[0])}) == 0
    saved = client.post("/api/v2/projects", json=payload)
    assert saved.status_code == 201
    assert client.post("/api/v2/projects", json=payload).json() == saved.json()


@db_test
def test_deleted_project_replay_cannot_recreate_or_requeue_it(tenant, api):
    client, _ = api
    payload = project_intent()
    saved = client.post("/api/v2/projects", json=payload)
    assert saved.status_code == 201
    assert client.delete(f"/api/v2/projects/{saved.json()['id']}").status_code == 204
    assert client.post("/api/v2/projects", json=payload).status_code == 409
    assert client.get(f"/api/v2/projects/creation-requests/{payload['requestId']}").status_code == 409
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.scalar(select(CreationRequest)).response == {}
        assert list(session.scalars(select(JobProgress.state))) == ["cancelled"]


@db_test
def test_project_receipts_isolate_same_intent_between_accounts(tenant, api):
    client, _ = api
    payload = project_intent()
    first = client.post("/api/v2/projects", json=payload)
    assert first.status_code == 201
    with session_scope() as session:
        other = Tenant(official_user_id=f"project-intent-{uuid4().hex}")
        session.add(other)
        session.flush()
        other_id = other.id
    try:
        with tenant_context(other_id), session_scope() as session:
            session.add(TenantSetting(tenant_id=other_id, chat_model="deepseek-test"))
        client.app.dependency_overrides[get_tenant_id] = lambda: other_id
        assert client.get(f"/api/v2/projects/creation-requests/{payload['requestId']}").json() is None
        second = client.post("/api/v2/projects", json=payload)
        assert second.status_code == 201 and second.json()["id"] != first.json()["id"]
        assert client.post("/api/v2/projects", json=payload).json() == second.json()
    finally:
        client.app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
        with session_scope() as session:
            session.execute(text("DELETE FROM procrastinate_jobs WHERE args->>'tenant' = :tid"), {"tid": str(other_id)})
            session.delete(session.get(Tenant, other_id))
