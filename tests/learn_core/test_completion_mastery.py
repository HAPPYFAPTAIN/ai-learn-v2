"""Reading completion is not evidence of full mastery."""

import pytest
from pydantic import ValidationError

from learn_api.routers.nodes import NodeUpdate
from learn_api.routers.review import ReviewRequest

from tests.learn_core.test_generation import db_test, tenant
from learn_core.db.engine import session_scope
from learn_core.db.models import Card, Knode, Quiz, QuizAttempt, QuizQuestion
from learn_core.learning import nodes, progress
from learn_core.tenancy.context import tenant_context


def test_client_cannot_assign_mastery_or_mastered_status():
    for values in ({"mastery": 1}, {"status": "mastered"}, {"status": None}):
        with pytest.raises(ValidationError):
            NodeUpdate.model_validate(values)


def test_review_requires_a_non_null_repetition_guard():
    for values in ({"rating": 3}, {"rating": 3, "expectedReps": None}):
        with pytest.raises(ValidationError):
            ReviewRequest.model_validate(values)


@db_test
def test_completion_recalculates_mastery_without_promoting_to_mastered(tenant):
    with tenant_context(tenant[0]), session_scope() as session:
        node = Knode(project_id=tenant[1], code="1", title="阅读")
        session.add(node)
        session.flush()
        nid = node.id
        nodes.update_node(session, node.id, status="done")
        assert node.status == "done"
        assert node.mastery == 0.3
        summary = progress.project_summary(session, project_id=tenant[1])
        assert summary["completedNodes"] == 1
        assert summary["completionRatio"] == 1
        assert summary["masteredNodes"] == 0
        assert summary["masteryRatio"] == 0
    # A new session observes the saved completion separately from mastery.
    with tenant_context(tenant[0]), session_scope() as session:
        node = session.get(Knode, nid)
        assert node.status == "done" and node.mastery == 0.3
        quiz = Quiz(project_id=tenant[1], title="证据")
        session.add(quiz)
        session.flush()
        question = QuizQuestion(quiz_id=quiz.id, node_id=nid, qtype="short", stem="Q", answer="A")
        session.add(question)
        session.flush()
        session.add(QuizAttempt(question_id=question.id, user_answer="A", is_correct=True))
        session.add(Card(project_id=tenant[1], node_id=nid, front="Q", back="A", stability=30))
        session.flush()
        assert progress.refresh_mastery(session, node_id=nid) == 1
        assert node.status == "done"
        summary = progress.project_summary(session, project_id=tenant[1])
        assert summary["completedNodes"] == summary["masteredNodes"] == 1


@db_test
def test_service_rejects_client_mastery_before_changing_node(tenant):
    with tenant_context(tenant[0]), session_scope() as session:
        node = nodes.create_node(session, project_id=tenant[1], code="1", title="阅读")
        with pytest.raises(ValueError):
            nodes.update_node(session, node.id, title="不可写入", mastery=1)
        assert node.title == "阅读" and node.mastery == 0
