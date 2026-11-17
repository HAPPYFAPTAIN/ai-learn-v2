"""FSRS 6 scheduling migrated from learning_ext/fsrs_review/service.py.

Timestamps remain aware UTC. The caller owns the transaction; the row lock and
expected repetition count prevent two tabs from rating the same review twice.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from learn_core.db.models import Card, ReviewLog

STATE_NEW = 0
STATE_LEARNING = 1
STATE_REVIEW = 2
STATE_RELEARNING = 3


class ReviewConflict(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def due_cards(session: Session, *, limit: int = 50, now: datetime | None = None) -> list[Card]:
    now = now or _now()
    return list(session.scalars(select(Card).where(
        Card.suspended.is_(False), Card.next_review <= now,
    ).order_by(Card.next_review, Card.due_order, Card.id).limit(limit)))


def _advance(card: Card, rating: int, now: datetime) -> None:
    from fsrs import Card as FSRSCard, Rating, Scheduler, State

    state = State(card.state if card.state in (1, 2, 3) else 1)
    source = FSRSCard(
        card_id=card.id,
        state=state,
        step=card.step if state in (State.Learning, State.Relearning) else None,
        stability=card.stability if card.stability > 0 else None,
        difficulty=card.difficulty if card.difficulty > 0 else None,
        due=card.next_review or now,
        last_review=card.last_review,
    )
    result, _ = Scheduler().review_card(source, Rating(rating), review_datetime=now)
    card.state = int(result.state)
    card.step = result.step or 0
    card.stability = float(result.stability or 0)
    card.difficulty = float(result.difficulty or 0)
    card.last_review = result.last_review
    card.next_review = result.due
    card.reps += 1


def review_card(
    session: Session, *, card_id: int, rating: int, now: datetime | None = None,
    expected_reps: int | None = None,
) -> Card | None:
    if rating not in (1, 2, 3, 4):
        raise ValueError("rating must be 1..4")
    card = session.scalar(select(Card).where(Card.id == card_id).with_for_update())
    if card is None:
        return None
    if card.suspended:
        raise ValueError("card is suspended")
    if expected_reps is not None and card.reps != expected_reps:
        raise ReviewConflict("此卡片已在其他窗口复习，请刷新后查看最新安排")
    now = now or _now()
    previous_state = card.state
    _advance(card, rating, now)
    session.add(ReviewLog(
        card_id=card.id, user_id=card.user_id, rating=rating,
        state=previous_state, stability=card.stability,
        difficulty=card.difficulty, reviewed_at=now,
    ))
    session.flush()
    from learn_core.learning.progress import record_progress, refresh_mastery
    if card.project_id is not None:
        record_progress(session, project_id=card.project_id, node_id=card.node_id, metric="cards_reviewed", value=1)
    if card.node_id is not None:
        refresh_mastery(session, node_id=card.node_id)
    return card
