"""Semantic grading uses durable jobs, one atomic result, and tenant-safe recovery."""
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from learn_api.app import create_app
from learn_api.deps import get_tenant_id
from learn_core.db.engine import session_scope
from learn_core.db.models import QuizAttempt, QuizQuestion, TenantSetting
from learn_core.learning import generation, grading, quizzes
from learn_core.learning.generation import run_generation, submit_generation
from learn_core.tenancy.context import tenant_context
from tests.learn_core.test_generation import tenant, mock_gateway, read_job, db_test


def make_quiz(tenant, *, objective=False):
    with tenant_context(tenant[0]), session_scope() as session:
        quiz = quizzes.create_quiz(session, project_id=tenant[1], title="变量测验", questions=[
            {"stem": "哪个是变量？", "qtype": "choice", "options": ["A", "B", "C", "D"], "answer": "A"},
            *([] if objective else [{"stem": "解释变量的用途", "qtype": "short", "answer": "给数据命名并保存数据"}]),
        ])
        return quiz.id, [q.id for q in quizzes.quiz_questions(session, quiz.id)]


def enqueue(tenant, quiz_id, answers):
    with tenant_context(tenant[0]), session_scope() as session:
        return submit_generation(session, project_id=tenant[1], kind="grade",
                                 options={"quizId": quiz_id, "answers": answers}).job_id


@db_test
def test_semantic_grade_duplicate_submit_restore_and_no_recharge(tenant, monkeypatch):
    quiz_id, ids = make_quiz(tenant)
    answers = {str(ids[0]): " a ", str(ids[1]): "用名称引用、存储数据"}
    jid = enqueue(tenant, quiz_id, answers)
    # First submission owns the in-flight answers, including another tab's retry.
    assert enqueue(tenant, quiz_id, {str(ids[0]): "B"}) == jid
    mock_gateway(monkeypatch, json.dumps([{"questionId": ids[1], "correct": True, "feedback": "覆盖了命名和存储两个要点。"}]))
    run_generation(tenant=str(tenant[0]), job_id=jid)
    assert read_job(tenant, jid)[0] == "done", read_job(tenant, jid)
    monkeypatch.setattr(generation, "GatewayClient", lambda: pytest.fail("完成后不得重复扣费"))
    run_generation(tenant=str(tenant[0]), job_id=jid)
    assert enqueue(tenant, quiz_id, answers) == jid
    with tenant_context(tenant[0]), session_scope() as session:
        result = grading.latest_result(session, quiz_id=quiz_id)
        assert result["score"] == 1.0 and result["total"] == 2
        assert result["results"][1]["userAnswer"] == answers[str(ids[1])]
        assert session.scalar(select(func.count()).select_from(QuizAttempt)) == 2
    app = create_app()
    app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    with TestClient(app) as client:
        assert client.get(f"/api/v2/quizzes/{quiz_id}/result").json() == result
        assert client.get(f"/api/v2/quizzes/{quiz_id}/grade-job").json()["jobId"] == jid
        assert "answer" not in client.get(f"/api/v2/quizzes/{quiz_id}").json()["questions"][0]
        app.dependency_overrides[get_tenant_id] = lambda: uuid4()
        assert client.get(f"/api/v2/quizzes/{quiz_id}/result").status_code == 404
        assert client.get(f"/api/v2/quizzes/{quiz_id}/grade-job").status_code == 404
        assert client.post(f"/api/v2/quizzes/{quiz_id}/grade-jobs", json={"answers": answers}).status_code == 404


@db_test
def test_choice_grading_does_not_require_or_call_model(tenant, monkeypatch):
    quiz_id, ids = make_quiz(tenant, objective=True)
    with tenant_context(tenant[0]), session_scope() as session:
        session.get(TenantSetting, tenant[0]).chat_model = ""
    jid = enqueue(tenant, quiz_id, {str(ids[0]): "B"})
    monkeypatch.setattr(generation, "GatewayClient", lambda: pytest.fail("选择题不调用模型"))
    run_generation(tenant=str(tenant[0]), job_id=jid)
    assert read_job(tenant, jid)[0] == "done"
    assert read_job(tenant, jid)[1]["grade"]["correct"] == 0


@db_test
@pytest.mark.parametrize("output", [[], [{"correct": "true", "feedback": "invalid"}], [{"correct": True, "feedback": "ok"}, {"correct": True, "feedback": "duplicate"}]])
def test_malformed_grading_cannot_save_partial_attempts(tenant, monkeypatch, output):
    quiz_id, ids = make_quiz(tenant)
    jid = enqueue(tenant, quiz_id, {str(ids[1]): "数据容器"})
    mock_gateway(monkeypatch, json.dumps([{**item, "questionId": ids[1]} for item in output]))
    run_generation(tenant=str(tenant[0]), job_id=jid)
    assert read_job(tenant, jid)[0] == "failed"
    with tenant_context(tenant[0]), session_scope() as session:
        assert grading.latest_result(session, quiz_id=quiz_id) is None
        assert session.scalar(select(func.count()).select_from(QuizAttempt)) == 0


@db_test
def test_grading_rejects_stale_questions_and_unknown_answers(tenant, monkeypatch):
    quiz_id, ids = make_quiz(tenant)
    with pytest.raises(generation.GenerationMissing):
        enqueue(tenant, quiz_id, {"999999999": "foreign"})
    jid = enqueue(tenant, quiz_id, {str(ids[1]): "数据容器"})
    with tenant_context(tenant[0]), session_scope() as session:
        session.get(QuizQuestion, ids[1]).answer = "修改后的答案"
    monkeypatch.setattr(generation, "GatewayClient", lambda: pytest.fail("过期题目不应调用模型"))
    run_generation(tenant=str(tenant[0]), job_id=jid)
    assert read_job(tenant, jid)[0] == "cancelled"


@db_test
def test_grading_api_validation_and_pending_recovery(tenant):
    quiz_id, ids = make_quiz(tenant)
    app = create_app()
    app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    with TestClient(app) as client:
        assert client.get(f"/api/v2/quizzes/{quiz_id}/result").json() is None
        assert client.get(f"/api/v2/quizzes/{quiz_id}/grade-job").json() is None
        response = client.post(f"/api/v2/quizzes/{quiz_id}/grade-jobs", json={"answers": {str(ids[1]): "用名称保存数据"}})
        assert response.status_code == 202, response.text
        assert client.get(f"/api/v2/quizzes/{quiz_id}/grade-job").json() == response.json()
        assert client.post(f"/api/v2/quizzes/{quiz_id}/grade-jobs", json={"answers": {str(ids[1]): "x" * 8001}}).status_code == 422
