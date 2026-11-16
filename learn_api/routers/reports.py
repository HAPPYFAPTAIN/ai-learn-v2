"""每日报告接口。"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from learn_api.deps import get_session
from learn_api.errors import ApiError
from learn_core.learning import projects as project_service
from learn_core.learning import reports as service

from learn_api.schemas import Items, ReportOut

router = APIRouter(prefix="/projects", tags=["reports"])

SessionDep = Annotated[Session, Depends(get_session)]


def _payload(report) -> dict:
    return {
        "id": report.id,
        "date": report.report_date.date().isoformat(),
        "content": report.content,
        "studyMinutes": report.study_minutes,
        "cardsReviewed": report.cards_reviewed,
        "nodesProgressed": report.nodes_progressed,
    }


@router.post("/{project_id}/reports", response_model=ReportOut)
def build_report(project_id: int, session: SessionDep) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    return _payload(service.build_report(session, project_id=project_id))


@router.get("/{project_id}/reports", response_model=Items[ReportOut])
def list_reports(project_id: int, session: SessionDep) -> dict:
    if project_service.get_project(session, project_id) is None:
        raise ApiError("NOT_FOUND", "project not found")
    return {"items": [_payload(r) for r in service.list_reports(session, project_id=project_id)]}
