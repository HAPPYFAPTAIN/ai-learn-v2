"""Exercise the real job persistence path; model HTTP is isolated from billing."""
import json

import pytest
from sqlalchemy import select

from tests.learn_core.test_generation import tenant, mock_gateway, read_job, db_test
from learn_core.db.engine import session_scope
from learn_core.db.models import Knode, Card, Quiz, QuizQuestion
from learn_core.learning.generation import submit_generation, run_generation, GenerationMissing
from learn_core.learning.assessment import validate_output
from learn_core.tenancy.context import tenant_context


def test_reject_malformed_question_and_card_output():
    data = {"chapters": [{"code": "1", "id": 1}]}
    options = {"count": 1, "qtype": "choice"}
    for item in [
        {"node_code": "1", "qtype": "choice", "stem": "Q", "answer": "A", "options": ["A", "B"]},
        {"node_code": "foreign", "qtype": "choice", "stem": "Q", "answer": "A", "options": ["A", "B", "C", "D"]},
        {"node_code": "1", "qtype": "short", "stem": "Q", "answer": "A"},
    ]:
        with pytest.raises(ValueError):
            validate_output("quiz", json.dumps([item]), data, options)
    with pytest.raises(ValueError):
        validate_output("cards", '{"cards":[{"front":" ","back":"A"}]}', data, options)


def add_node(tenant):
    with tenant_context(tenant[0]), session_scope() as session:
        node = Knode(project_id=tenant[1], code="1", title="变量", description="变量保存数据。")
        session.add(node)
        session.flush()
        return node.id


def submit(tenant, nid, kind):
    with tenant_context(tenant[0]), session_scope() as session:
        return submit_generation(session, project_id=tenant[1], kind=kind,
                                 options={"nodeIds": [nid], "count": 1, "qtype": "mixed"}).job_id


@db_test
@pytest.mark.parametrize("kind", ["quiz", "cards"])
def test_generate_save_refresh_and_recovery_no_duplicates(tenant, monkeypatch, kind):
    nid = add_node(tenant)
    jid = submit(tenant, nid, kind)
    assert submit(tenant, nid, kind) == jid
    payload = [{"node_code": "1", "qtype": "choice", "stem": "变量是什么？", "options": ["A. 数据命名", "B. 文件", "C. 网络", "D. 设备"], "answer": "A", "explanation": "变量用于保存数据。"}] if kind == "quiz" else {"cards": [{"front": "变量用途", "back": "给数据命名"}]}
    mock_gateway(monkeypatch, json.dumps(payload))
    run_generation(tenant=str(tenant[0]), job_id=jid)
    assert read_job(tenant, jid)[0] == "done", read_job(tenant, jid)
    run_generation(tenant=str(tenant[0]), job_id=jid)
    with tenant_context(tenant[0]), session_scope() as session:
        if kind == "quiz":
            quiz = session.scalar(select(Quiz).where(Quiz.project_id == tenant[1]))
            questions = list(session.scalars(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz.id)))
            assert len(questions) == 1 and questions[0].node_id == nid
            assert read_job(tenant, jid)[1]["quizId"] == quiz.id
        else:
            cards = list(session.scalars(select(Card).where(Card.project_id == tenant[1])))
            assert len(cards) == 1 and cards[0].node_id == nid and cards[0].next_review


@db_test
def test_no_partial_quiz_and_no_foreign_chapters(tenant, monkeypatch):
    nid = add_node(tenant)
    with tenant_context(tenant[0]), session_scope() as session:
        with pytest.raises(GenerationMissing):
            submit_generation(session, project_id=tenant[1], kind="quiz", options={"nodeIds": [nid, 999999999], "count": 1, "qtype": "mixed"})
    jid = submit(tenant, nid, "quiz")
    mock_gateway(monkeypatch, '[{"node_code":"1","qtype":"choice","stem":"bad","answer":"A","options":[]}]')
    run_generation(tenant=str(tenant[0]), job_id=jid)
    assert read_job(tenant, jid)[0] == "failed"
    with tenant_context(tenant[0]), session_scope() as session:
        assert not list(session.scalars(select(Quiz).where(Quiz.project_id == tenant[1])))
