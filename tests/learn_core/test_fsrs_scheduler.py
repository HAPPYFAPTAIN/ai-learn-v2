"""FSRS migration and concurrent review protection on real PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from learn_api.app import create_app
from learn_api.deps import get_tenant_id
from learn_core.db.engine import session_scope
from learn_core.db.models import Card, ReviewLog
from learn_core.review import scheduler
from learn_core.tenancy.context import tenant_context
from tests.learn_core.test_generation import tenant, db_test


def create_card(tenant, now):
    with tenant_context(tenant[0]), session_scope() as session:
        card = Card(project_id=tenant[1], front="变量", back="保存数据", next_review=now)
        session.add(card)
        session.flush()
        return card.id


@db_test
def test_fsrs_learning_review_relearning_and_utc_restore(tenant):
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    cid = create_card(tenant, now)
    with tenant_context(tenant[0]), session_scope() as session:
        card = scheduler.review_card(session, card_id=cid, rating=3, now=now, expected_reps=0)
        assert card.state == scheduler.STATE_LEARNING and card.step == 1
        assert card.last_review == now and card.next_review == now + timedelta(minutes=10)
        assert card.stability > 0 and 1 <= card.difficulty <= 10
    with tenant_context(tenant[0]), session_scope() as session:
        later = now + timedelta(minutes=10)
        card = scheduler.review_card(session, card_id=cid, rating=4, now=later, expected_reps=1)
        assert card.state == scheduler.STATE_REVIEW and card.reps == 2
        assert card.next_review > later + timedelta(days=1)
        due = card.next_review
    with tenant_context(tenant[0]), session_scope() as session:
        card = scheduler.review_card(session, card_id=cid, rating=1, now=due, expected_reps=2)
        assert card.state == scheduler.STATE_RELEARNING and card.reps == 3
        assert card.next_review == due + timedelta(minutes=10)
        assert card.last_review.tzinfo is not None
        logs = list(session.scalars(select(ReviewLog).order_by(ReviewLog.id)))
        assert [log.state for log in logs] == [0, 1, 2]


@db_test
def test_two_tabs_cannot_grade_one_review_twice(tenant):
    now = scheduler._now()
    cid = create_card(tenant, now)

    def review():
        try:
            with tenant_context(tenant[0]), session_scope() as session:
                scheduler.review_card(session, card_id=cid, rating=3, now=now, expected_reps=0)
            return "saved"
        except scheduler.ReviewConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: review(), range(2)))
    assert sorted(results) == ["conflict", "saved"]
    with tenant_context(tenant[0]), session_scope() as session:
        assert session.get(Card, cid).reps == 1
        assert session.scalar(select(func.count()).select_from(ReviewLog)) == 1
    app = create_app()
    app.dependency_overrides[get_tenant_id] = lambda: tenant[0]
    with TestClient(app) as client:
        response = client.post(f"/api/v2/review/{cid}", json={"rating": 3, "expectedReps": 0})
        assert response.status_code == 409, response.text
