"""卡片与复习接口。"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from learn_api.deps import get_session
from learn_api.errors import ApiError
from learn_core.db.models import Card
from learn_core.learning import projects as project_service
from learn_core.learning.ownership import require_project_node
from learn_core.learning.creation import create_once
from learn_core.review import scheduler

from learn_api.schemas import CardOut, Items

router = APIRouter(tags=["review"])

SessionDep = Annotated[Session, Depends(get_session)]


class CardCreate(BaseModel):
    model_config = {"extra": "forbid", "populate_by_name": True}

    front: str = Field(min_length=1, max_length=4000)
    back: str = Field(min_length=1, max_length=8000)
    node_id: int | None = Field(default=None, alias="nodeId")
    project_id: int | None = Field(default=None, alias="projectId")
    card_type: str = Field(default="basic", alias="cardType")
    request_id: UUID | None = Field(default=None, alias="requestId")


class ReviewRequest(BaseModel):
    model_config = {"extra": "forbid", "populate_by_name": True}

    rating: int = Field(ge=1, le=4)
    expected_reps: int = Field(ge=0, alias="expectedReps")


def _serialize(card: Card) -> dict:
    return {
        "id": card.id,
        "projectId": card.project_id,
        "nodeId": card.node_id,
        "front": card.front,
        "back": card.back,
        "cardType": card.card_type,
        "state": card.state,
        "step": card.step,
        "reps": card.reps,
        "stability": card.stability,
        "nextReview": card.next_review,
        "suspended": card.suspended,
    }


@router.post("/cards", status_code=status.HTTP_201_CREATED, response_model=CardOut)
def create_card(payload: CardCreate, session: SessionDep) -> dict:
    if payload.project_id is not None and project_service.get_project(session, payload.project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    project_id = require_project_node(session, project_id=payload.project_id, node_id=payload.node_id)
    def create():
        card = Card(project_id=project_id, node_id=payload.node_id, front=payload.front,
                    back=payload.back, card_type=payload.card_type, next_review=scheduler._now())
        session.add(card)
        session.flush()
        return _serialize(card)
    return create_once(session, operation="card", request_id=payload.request_id,
        payload=payload.model_dump(mode="json", exclude={"request_id"}), create=create)


@router.get("/projects/{project_id}/cards", response_model=Items[CardOut])
def list_cards(project_id: int, session: SessionDep) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    cards = list(session.scalars(select(Card).where(Card.project_id == project_id).order_by(Card.id)))
    return {"items": [_serialize(c) for c in cards]}


@router.get("/review/due", response_model=Items[CardOut])
def due(session: SessionDep, limit: int = Query(default=50, ge=1, le=200)) -> dict:
    return {"items": [_serialize(c) for c in scheduler.due_cards(session, limit=limit)]}


@router.post("/review/{card_id}", response_model=CardOut)
def review(card_id: int, payload: ReviewRequest, session: SessionDep) -> dict:
    try:
        card = scheduler.review_card(session, card_id=card_id, rating=payload.rating, expected_reps=payload.expected_reps)
    except scheduler.ReviewConflict as exc:
        raise ApiError("CONFLICT", str(exc)) from exc
    except ValueError as exc:
        raise ApiError("INVALID_ARGUMENT", str(exc)) from exc
    if card is None:
        raise ApiError("NOT_FOUND", "card not found")
    return _serialize(card)
