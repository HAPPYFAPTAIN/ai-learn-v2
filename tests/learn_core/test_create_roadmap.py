"""Create project and roadmap job as one transaction; tenant-local ETA samples."""
import json
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from learn_api.app import create_app
from learn_api.deps import get_tenant_id
from learn_core.db.engine import session_scope
from learn_core.db.models import JobProgress, Project, Tenant, TenantSetting
from learn_core.learning import generation
from learn_core.tenancy.context import tenant_context
from tests.learn_core.test_generation import tenant, db_test, mock_gateway, read_job, ROADMAP


@db_test
def test_create_submits_roadmap_in_same_transaction(tenant, monkeypatch):
    app = create_app()
    app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    with TestClient(app) as client:
        response = client.post('/api/v2/projects', json={
            'title': '自动生成', 'goal': 'Python 入门', 'weeklyHours': 5, 'generateRoadmap': True,
        })
        assert response.status_code == 201, response.text
        project = response.json()
        jid = project['generation']['jobId']
        assert project['generation']['state'] == 'queued'
        duplicate = client.post(f"/api/v2/projects/{project['id']}/roadmap-jobs")
        assert duplicate.json()['jobId'] == jid
        job = client.get(f'/api/v2/jobs/{jid}').json()
        assert job['progress']['estimatedModelMs'] == 45000
        assert job['progress']['estimateSource'] == 'default'
        with tenant_context(tenant[0]), session_scope() as session:
            assert session.scalar(text("SELECT count(*) FROM procrastinate_jobs WHERE args->>'job_id'=:j"), {'j': jid}) == 1
        mock_gateway(monkeypatch, json.dumps(ROADMAP))
        generation.run_generation(tenant=str(tenant[0]), job_id=jid)
        state, progress, error = read_job(tenant, jid)
        assert state == 'done', error
        assert progress['phase'] == 'done' and progress['count'] == 3
        assert progress['attemptStartedAt']
        assert client.get(f"/api/v2/projects/{project['id']}/nodes").json()['items']


@db_test
def test_model_not_configured_rolls_back_project_and_queue(tenant):
    with tenant_context(tenant[0]), session_scope() as session:
        session.get(TenantSetting, tenant[0]).chat_model = ''
    app = create_app()
    app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    with TestClient(app) as client:
        response = client.post('/api/v2/projects', json={'title': '不能留下半份计划', 'generateRoadmap': True})
        assert response.status_code == 409, response.text
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.scalar(select(func.count()).select_from(Project)) == 1
        assert session.scalar(select(func.count()).select_from(JobProgress)) == 0


@db_test
def test_estimate_uses_only_own_successful_model_history(tenant):
    foreign = uuid4()
    with session_scope() as session:
        session.add(Tenant(id=foreign, official_user_id=f'estimate-{foreign.hex}'))
    try:
        with tenant_context(foreign), session_scope() as session:
            session.add(JobProgress(job_id=f'foreign-{foreign.hex}', kind='roadmap', subject='project:1', state='done', progress={'model': 'deepseek-test', 'modelMs': 99999}))
        with tenant_context(tenant[0]), session_scope() as session:
            assert generation.estimated_model_ms(session, kind='roadmap', model='deepseek-test') == (45000, 'default')
            for model, kind, state, duration in [
                ('deepseek-test', 'roadmap', 'done', 20000),
                ('deepseek-test', 'roadmap', 'done', 40000),
                ('other-model', 'roadmap', 'done', 99999),
                ('deepseek-test', 'lesson', 'done', 99999),
                ('deepseek-test', 'roadmap', 'failed', 99999),
            ]:
                session.add(JobProgress(job_id=uuid4().hex, kind=kind, subject='project:1', state=state, progress={'model': model, 'modelMs': duration}))
            session.flush()
            assert generation.estimated_model_ms(session, kind='roadmap', model='deepseek-test') == (30000, 'history')
    finally:
        with session_scope() as session:
            session.execute(text('DELETE FROM tenant WHERE id=:id'), {'id': foreign})
