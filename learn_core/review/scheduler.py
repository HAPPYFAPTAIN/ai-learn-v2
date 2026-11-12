"""复习排程。

现在是「阶梯间隔 + 评分档位」的简化版：每一步的间隔是固定的，
评分只决定前进、原地还是后退。等接入 FSRS 参数后，把 ``_next_interval``
换成稳定性推算即可，字段（stability/difficulty/step/state）已经留好。

评分沿用 SM-2 习惯：1 again / 2 hard / 3 good / 4 easy。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from learn_core.db.models import Card, ReviewLog

# 学习态先用分钟级，进入复习态后按天扩张。
STEPS = [
    timedelta(minutes=5),
    timedelta(days=1),
    timedelta(days=3),
    timedelta(days=7),
    timedelta(days=16),
    timedelta(days=35),
    timedelta(days=75),
    timedelta(days=160),
]

STATE_NEW = 0
STATE_LEARNING = 1
STATE_REVIEW = 2
STATE_RELEARNING = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def due_cards(session: Session, *, limit: int = 50, now: datetime | None = None) -> list[Card]:
    now = now or _now()
    stmt = (
        select(Card)
        .where(Card.suspended.is_(False), Card.next_review <= now)
        .order_by(Card.next_review, Card.due_order, Card.id)
        .limit(limit)
    )
    return list(session.scalars(stmt))


def _advance(card: Card, rating: int, now: datetime) -> None:
    if rating <= 1:
        card.state = STATE_RELEARNING if card.state == STATE_REVIEW else STATE_LEARNING
        card.step = 0
        interval = STEPS[0]
    else:
        if rating == 2:
            card.step = max(0, card.step - 1)
        elif rating == 3:
            card.step = min(card.step + 1, len(STEPS) - 1)
        else:  # easy：跳一步
            card.step = min(card.step + 2, len(STEPS) - 1)

        interval = STEPS[card.step]
        if card.step >= 2 and card.state != STATE_REVIEW:
            card.state = STATE_REVIEW
        elif card.state == STATE_NEW:
            card.state = STATE_LEARNING

    card.reps += 1
    card.last_review = now
    card.next_review = now + interval
    # stability 以天为单位，方便以后接 FSRS 的召回曲线。
    card.stability = interval.total_seconds() / 86400
    card.difficulty = min(10.0, max(1.0, card.difficulty + (2 - rating) * 0.2)) if card.difficulty else max(
        1.0, min(10.0, 5.0 + (2 - rating))
    )


def review_card(
    session: Session, *, card_id: int, rating: int, now: datetime | None = None
) -> Card | None:
    if rating not in (1, 2, 3, 4):
        raise ValueError("rating must be 1..4")
    card = session.get(Card, card_id)
    if card is None:
        return None
    if card.suspended:
        raise ValueError("card is suspended")

    now = now or _now()
    _advance(card, rating, now)
    session.add(
        ReviewLog(
            card_id=card.id,
            user_id=card.user_id,
            rating=rating,
            state=card.state,
            stability=card.stability,
            difficulty=card.difficulty,
            reviewed_at=now,
        )
    )
    session.flush()
    return card
