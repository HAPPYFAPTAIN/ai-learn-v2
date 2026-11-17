"""Regression cases found while taking over the 8d0500a backend."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from learn_api.app import create_app
from learn_api.deps import get_session, get_tenant_id
from fastapi.testclient import TestClient
from learn_core.db.engine import get_engine, session_scope
from learn_core.db.models import (
    Card, DailyReport, JobProgress, Knode, Note, ProgressRecord, Project,
    Quiz, QuizAttempt, QuizQuestion, ReviewLog, Task,
)
from learn_core.learning import generation, notes, projects, quizzes
from learn_core.learning import nodes
from learn_core.learning.reports import build_report
from learn_core.rag.store import hybrid_search, upsert_chunks
from learn_core.tenancy.context import tenant_context
from learn_core.review import scheduler
from tests.learn_core.test_generation import (
    ROADMAP, db_test, enqueue, mock_gateway, read_job, tenant,
)
from tests.learn_core.test_notes_api import client, _login


@db_test
def test_job_polling_and_events_exclude_persisted_replay_prompt(tenant):
    progress = {"phase": "done", "count": 3, "prepared": [{"role": "user", "content": "private-replay-input"}]}
    with tenant_context(tenant[0]), session_scope() as session:
        session.add(JobProgress(job_id="replay-prompt", kind="roadmap", state="done", progress=progress))
    app = create_app()
    app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    with TestClient(app) as local_client:
        response = local_client.get("/api/v2/jobs/replay-prompt")
        assert response.status_code == 200
        assert response.json()["progress"] == {"phase": "done", "count": 3}
        events = local_client.get("/api/v2/jobs/replay-prompt/events")
        assert events.status_code == 200 and "event: end" in events.text
        assert "prepared" not in events.text and "private-replay-input" not in events.text
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.scalar(select(JobProgress).where(JobProgress.job_id == "replay-prompt")).progress == progress


@db_test
@pytest.mark.parametrize("kind", ["notes", "tasks", "cards", "quizzes", "progress"])
def test_child_writes_reject_foreign_and_wrong_project_nodes(client, kind):
    # RLS hides a foreign node, but does not validate a child row's integer ID.
    owner = _login(client, "owner")
    other = _login(client, "other")
    own_project = client.post("/api/v2/projects", json={"title": "own"}, headers=owner).json()["id"]
    for headers in (owner, other):
        pid = client.post("/api/v2/projects", json={"title": "different"}, headers=headers).json()["id"]
        nid = client.post(f"/api/v2/projects/{pid}/nodes", json={"code": "1", "title": "elsewhere"}, headers=headers).json()["id"]
        payloads = {
            "notes": {"nodeId": nid, "content": "private"},
            "tasks": {"nodeId": nid, "title": "practice"},
            "cards": {"projectId": own_project, "nodeId": nid, "front": "Q", "back": "A"},
            "quizzes": {"nodeIds": [nid], "questions": [{"stem": "Q", "answer": "A", "nodeId": nid}]},
            "progress": {"nodeId": nid, "metric": "minutes", "value": 1},
        }
        url = "/api/v2/cards" if kind == "cards" else f"/api/v2/projects/{own_project}/{kind}"
        response = client.post(url, json=payloads[kind], headers=owner)
        assert response.status_code == 404, response.text


@db_test
def test_project_deletion_clears_learning_records_and_cancels_jobs(tenant):
    with tenant_context(tenant[0]), session_scope() as session:
        node = Knode(project_id=tenant[1], code="1", title="chapter")
        session.add(node)
        session.flush()
        nid = node.id
        notes.create_note(session, project_id=tenant[1], node_id=nid, content="note")
        notes.create_task(session, project_id=tenant[1], node_id=nid, title="task")
        quiz = quizzes.create_quiz(session, project_id=tenant[1], title="quiz", questions=[
            {"stem": "Q", "answer": "A", "node_id": nid},
        ])
        qid = quiz.id
        question = quizzes.quiz_questions(session, qid)[0]
        session.add(QuizAttempt(question_id=question.id, user_answer="A", is_correct=True))
        card = Card(project_id=tenant[1], node_id=nid, front="Q", back="A")
        session.add(card)
        session.flush()
        session.add(ReviewLog(card_id=card.id, rating=3, state=0, stability=1, difficulty=1))
        session.add(ProgressRecord(project_id=tenant[1], node_id=nid, metric="minutes", value=5))
        build_report(session, project_id=tenant[1])
        jid = generation.submit_generation(session, project_id=tenant[1], kind="lesson", node_id=nid).job_id
    with tenant_context(tenant[0]), session_scope() as session:
        assert projects.delete_project(session, tenant[1])
    with tenant_context(tenant[0]), session_scope() as session:
        for model in (Project, Knode, Card, ReviewLog, Note, Task, Quiz, QuizQuestion, QuizAttempt, ProgressRecord, DailyReport):
            assert session.scalar(select(func.count()).select_from(model)) == 0, model.__name__
        assert session.scalar(select(JobProgress).where(JobProgress.job_id == jid)).state == "cancelled"


@db_test
def test_source_queue_and_progress_are_invisible_until_commit_and_rollback_together(tenant):
    async def rollback_request():
        with tenant_context(tenant[0]), session_scope() as session:
            yield session
            with session_scope() as observer:
                assert observer.scalar(text("SELECT count(*) FROM procrastinate_jobs WHERE args->>'tenant' = :t"), {"t": str(tenant[0])}) == 0
                assert observer.scalar(select(func.count()).select_from(JobProgress)) == 0
            session.rollback()

    app = create_app()
    app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    app.dependency_overrides[get_session] = rollback_request
    with TestClient(app) as client:
        response = client.post(f"/api/v2/projects/{tenant[1]}/sources", json={"sourceId": "same", "text": "document"})
        assert response.status_code == 202, response.text
        job_id = response.json()["jobId"]
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.scalar(select(JobProgress).where(JobProgress.job_id == job_id)) is None
        assert session.scalar(text("SELECT count(*) FROM procrastinate_jobs WHERE args->>'job_id' = :j"), {"j": job_id}) == 0


@db_test
def test_hybrid_search_does_not_mix_indexes_with_same_chunk_id(tenant):
    vector = [1.0] + [0.0] * 383
    with tenant_context(tenant[0]), session_scope() as session:
        for index, content in (("first", "alpha document"), ("second", "beta private document")):
            upsert_chunks(session, index_id=index, source_id="same", chunks=[content], vectors=[vector], metadata={"index": index})
    with tenant_context(tenant[0]), session_scope() as session:
        hits = hybrid_search(session, index_id="first", query="alpha", query_vector=vector)
        assert len(hits) == 1
        assert hits[0].text == "alpha document" and hits[0].metadata["index"] == "first"


@db_test
def test_generation_crash_reuses_event_and_request_with_new_queue_attempt(tenant, monkeypatch):
    job_id = enqueue(tenant)
    requests = []

    def respond(request):
        requests.append((request.headers["X-Event-Id"], request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(ROADMAP)}}]})

    mock_gateway(monkeypatch, handler=respond)
    original = generation.parse_roadmap

    def crash_after_http(content):
        raise SystemExit("worker stopped after upstream accepted request")

    monkeypatch.setattr(generation, "parse_roadmap", crash_after_http)
    with pytest.raises(SystemExit):
        generation.run_generation(tenant=str(tenant[0]), job_id=job_id)
    monkeypatch.setattr(generation, "parse_roadmap", original)
    generation.run_generation(tenant=str(tenant[0]), job_id=job_id, attempt=1)
    assert read_job(tenant, job_id)[0] == "done"
    assert len(requests) == 2 and requests[0] == requests[1]


@db_test
def test_prefetched_review_card_does_not_bypass_repetition_guard(tenant):
    with tenant_context(tenant[0]), session_scope() as session:
        card = Card(project_id=tenant[1], front="Q", back="A")
        session.add(card)
        session.flush()
        cid = card.id
    ready = Barrier(2)

    def review():
        with tenant_context(tenant[0]), session_scope() as session:
            cached = session.get(Card, cid)
            ready.wait(timeout=10)
            try:
                scheduler.review_card(session, card_id=cached.id, rating=3, expected_reps=0)
            except scheduler.ReviewConflict:
                return "conflict"
        return "saved"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: review(), range(2)))
    assert sorted(results) == ["conflict", "saved"]
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.get(Card, cid).reps == 1
        assert session.scalar(select(func.count()).select_from(ReviewLog)) == 1


@db_test
def test_deleted_node_is_revalidated_after_waiting_for_parent_lock(tenant):
    with tenant_context(tenant[0]), session_scope() as session:
        node = nodes.create_node(session, project_id=tenant[1], code="1", title="deleted")
        nid = node.id
    reached, resume = Event(), Event()

    class PausedSession(Session):
        def scalar(self, statement, *args, **kwargs):
            descriptions = getattr(statement, "column_descriptions", [])
            if descriptions and descriptions[0].get("entity") is Project:
                reached.set()
                assert resume.wait(timeout=10)
            return super().scalar(statement, *args, **kwargs)

    def create_note():
        with tenant_context(tenant[0]), PausedSession(get_engine()) as session:
            try:
                notes.create_note(session, project_id=tenant[1], node_id=nid, content="should not survive")
                session.commit()
            except LookupError:
                session.rollback()
                return "missing"
        return "created"

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(create_note)
        try:
            assert reached.wait(timeout=10)
            with tenant_context(tenant[0]), session_scope() as session:
                assert nodes.delete_node(session, nid)
        finally:
            resume.set()
        assert result.result(timeout=10) == "missing"
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.scalar(select(func.count()).select_from(Note)) == 0


@db_test
def test_deleting_one_chapter_preserves_other_chapters_and_grading(tenant):
    with tenant_context(tenant[0]), session_scope() as session:
        first = nodes.create_node(session, project_id=tenant[1], code="1", title="remove")
        second = nodes.create_node(session, project_id=tenant[1], code="2", title="keep")
        first_id, second_id = first.id, second.id
        for node in (first, second):
            notes.create_note(session, project_id=tenant[1], node_id=node.id, content=node.title)
            notes.create_task(session, project_id=tenant[1], node_id=node.id, title=node.title)
            session.add(Card(project_id=tenant[1], node_id=node.id, front=node.title, back="A"))
        quiz = quizzes.create_quiz(session, project_id=tenant[1], title="keep", node_ids=[second_id], questions=[
            {"stem": "Q", "qtype": "choice", "answer": "A", "node_id": second_id},
        ])
        quiz_id = quiz.id
        question_id = quizzes.quiz_questions(session, quiz_id)[0].id
        jid = generation.submit_generation(session, project_id=tenant[1], kind="grade", options={
            "quizId": quiz_id, "answers": {str(question_id): "A"},
        }).job_id
    with tenant_context(tenant[0]), session_scope() as session:
        assert nodes.delete_node(session, first_id)
    with tenant_context(tenant[0]), session_scope() as session:
        for model in (Knode, Note, Task, Card):
            rows = list(session.scalars(select(model)))
            assert len(rows) == 1, model.__name__
        assert session.get(Quiz, quiz_id) is not None
        assert session.scalar(select(JobProgress).where(JobProgress.job_id == jid)).state == "queued"
    generation.run_generation(tenant=str(tenant[0]), job_id=jid)
    assert read_job(tenant, jid)[0] == "done"
