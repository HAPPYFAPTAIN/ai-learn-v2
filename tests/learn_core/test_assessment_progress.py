"""Quiz and review outcomes feed mastery and daily reports in the same commit."""
from learn_core.db.engine import session_scope
from learn_core.db.models import Card, Knode
from learn_core.learning import grading, quizzes
from learn_core.learning.generation import run_generation, submit_generation
from learn_core.learning.reports import build_report
from learn_core.review import scheduler
from learn_core.tenancy.context import tenant_context
from tests.learn_core.test_generation import tenant, db_test, read_job


@db_test
def test_assessments_update_mastery_and_daily_totals_once(tenant):
    with tenant_context(tenant[0]), session_scope() as session:
        node = Knode(project_id=tenant[1], code="1", title="变量", status="learning")
        session.add(node)
        session.flush()
        nid = node.id
        quiz = quizzes.create_quiz(session, project_id=tenant[1], title="自测", questions=[
            {"stem": "Q1", "qtype": "choice", "answer": "A", "node_id": nid},
            {"stem": "Q2", "qtype": "choice", "answer": "B", "node_id": nid},
        ])
        qid = quiz.id
        ids = [q.id for q in quizzes.quiz_questions(session, quiz.id)]
        card = Card(project_id=tenant[1], node_id=nid, front="Q", back="A", next_review=scheduler._now())
        session.add(card)
        session.flush()
        cid = card.id
        jid = submit_generation(session, project_id=tenant[1], kind="grade", options={
            "quizId": qid, "answers": {str(ids[0]): "A", str(ids[1]): "A"},
        }).job_id
    run_generation(tenant=str(tenant[0]), job_id=jid)
    assert read_job(tenant, jid)[0] == "done"
    run_generation(tenant=str(tenant[0]), job_id=jid)
    with tenant_context(tenant[0]), session_scope() as session:
        node = session.get(Knode, nid)
        assert node.status == "weak" and abs(node.mastery - 0.29) < 0.001
        scheduler.review_card(session, card_id=cid, rating=3, expected_reps=0)
        assert node.mastery > 0.29
        report = build_report(session, project_id=tenant[1])
        assert report.cards_reviewed == 1
        assert "（1/2）" in report.content
        assert grading.latest_result(session, quiz_id=qid)["total"] == 2
