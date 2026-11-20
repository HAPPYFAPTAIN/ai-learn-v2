"""Route deletion preserves the plan/library and cannot race active generation."""
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from learn_api.app import create_app
from learn_api.deps import get_tenant_id
from learn_core.db.engine import session_scope
from learn_core.db.models import (
    Card, JobProgress, Kedge, Knode, Note, Project, Quiz, QuizQuestion,
    ReviewLog, StoredFile, Tenant, Task,
)
from learn_core.learning import generation, nodes, notes, projects, quizzes
from learn_core.learning.roadmaps import Roadmap, save_roadmap
from learn_core.tenancy.context import tenant_context
from tests.learn_core.test_generation import ROADMAP, db_test, tenant


@db_test
def test_delete_roadmap_clears_associated_records_and_allows_regeneration(tenant):
    with tenant_context(tenant[0]), session_scope() as session:
        save_roadmap(session, project_id=tenant[1], roadmap=Roadmap.model_validate(ROADMAP))
        nid = nodes.list_nodes(session, project_id=tenant[1])[0].id
        notes.create_note(session, project_id=tenant[1], node_id=nid, content="chapter note")
        notes.create_task(session, project_id=tenant[1], node_id=nid, title="task")
        quizzes.create_quiz(session, project_id=tenant[1], title="quiz", questions=[
            {"stem": "Q", "answer": "A", "node_id": nid},
        ])
        card = Card(project_id=tenant[1], node_id=nid, front="Q", back="A")
        session.add(card)
        session.flush()
        session.add(ReviewLog(card_id=card.id, rating=3, state=0, stability=1, difficulty=1))
        session.add(StoredFile(kind="upload", sha256="a" * 64, storage_key="test-only", original_name="kept.md"))
        other = projects.create_project(session, title="unaffected plan")
        other_id = other.id
        other_node = nodes.create_node(session, project_id=other_id, code="1", title="keep chapter")
        general_id = notes.create_note(session, project_id=other_id, node_id=other_node.id, content="keep note").id
    app = create_app()
    app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    with TestClient(app) as client:
        url = f"/api/v2/projects/{tenant[1]}/roadmap"
        assert client.delete(url).status_code == 204
        assert client.delete(url).status_code == 204
        assert client.get(f"/api/v2/projects/{tenant[1]}/nodes").json()["items"] == []
        assert client.get(f"/api/v2/projects/{tenant[1]}").json()["title"] == "Python"
        # This enqueues only, never calls a real model.
        response = client.post(f"/api/v2/projects/{tenant[1]}/roadmap-jobs")
        assert response.status_code == 202, response.text
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.get(Project, tenant[1]).roadmap_json == {}
        assert len(nodes.list_nodes(session, project_id=other_id)) == 1
        assert [n.id for n in session.scalars(select(Note))] == [general_id]
        assert session.scalar(select(func.count()).select_from(StoredFile)) == 1
        for model in (Kedge, Card, ReviewLog, Quiz, QuizQuestion, Task):
            assert session.scalar(select(func.count()).select_from(model)) == 0, model.__name__


@db_test
def test_delete_roadmap_refuses_active_job_without_partial_deletion(tenant):
    with tenant_context(tenant[0]), session_scope() as session:
        node = nodes.create_node(session, project_id=tenant[1], code="1", title="keep")
        nid = node.id
        jid = generation.submit_generation(session, project_id=tenant[1], kind="lesson", node_id=nid).job_id
    app = create_app()
    app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    with TestClient(app) as client:
        for state in ("queued", "running"):
            with tenant_context(tenant[0]), session_scope() as session:
                session.scalar(select(JobProgress).where(JobProgress.job_id == jid)).state = state
            response = client.delete(f"/api/v2/projects/{tenant[1]}/roadmap")
            assert response.status_code == 409, response.text
            assert response.json()["error"]["code"] == "JOB_RUNNING"
            assert len(client.get(f"/api/v2/projects/{tenant[1]}/nodes").json()["items"]) == 1


@db_test
def test_delete_roadmap_cannot_access_another_tenant(tenant):
    foreign_id = uuid4()
    with session_scope() as session:
        session.add(Tenant(id=foreign_id, official_user_id=f"delete-route-{foreign_id.hex}"))
    try:
        with tenant_context(foreign_id), session_scope() as session:
            project = projects.create_project(session, title="private")
            pid = project.id
            nodes.create_node(session, project_id=pid, code="1", title="private")
        app = create_app()
        app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
        with TestClient(app) as client:
            assert client.delete(f"/api/v2/projects/{pid}/roadmap").status_code == 404
        with tenant_context(foreign_id), session_scope() as session:
            assert len(nodes.list_nodes(session, project_id=pid)) == 1
    finally:
        with session_scope() as session:
            session.execute(text("DELETE FROM tenant WHERE id=:id"), {"id": foreign_id})


@db_test
def test_account_library_remains_accessible_after_last_plan_is_deleted(tenant):
    other_tenant = uuid4()
    with session_scope() as session:
        session.add(Tenant(id=other_tenant, official_user_id=f"library-{other_tenant.hex}"))
    try:
        with tenant_context(tenant[0]), session_scope() as session:
            session.add(StoredFile(kind="material", sha256="b" * 64, storage_key="test-own", original_name="own.md"))
            assert projects.delete_project(session, tenant[1])
        with tenant_context(other_tenant), session_scope() as session:
            session.add(StoredFile(kind="material", sha256="c" * 64, storage_key="test-foreign", original_name="private.md"))
        app = create_app()
        app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
        with TestClient(app) as client:
            assert client.get("/api/v2/projects").json()["items"] == []
            response = client.get("/api/v2/materials")
            assert response.status_code == 200, response.text
            assert [f["name"] for f in response.json()["items"]] == ["own.md"]
    finally:
        with session_scope() as session:
            session.execute(text("DELETE FROM tenant WHERE id=:id"), {"id": other_tenant})
