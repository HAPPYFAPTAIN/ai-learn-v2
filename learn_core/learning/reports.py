"""每日学习报告。

数字从 le_progress 现算，正文按模板拼——不调模型。
这样报告可重复生成、可对账；以后要换成模型润色，把 `_compose` 换掉即可。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from learn_core.db.models import DailyReport, ProgressRecord
from learn_core.learning.ownership import require_project_node

# The official learning product uses the same civil day in every browser.
# Keep FSRS timestamps in UTC; only report aggregation uses this fixed +08 day.
REPORT_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=REPORT_TIMEZONE)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def _compose(day: date, *, minutes: int, cards: int, correct: int, total: int, nodes: int) -> str:
    if not any([minutes, cards, total, nodes]):
        return f"{day.isoformat()}：今天没有学习记录。"
    parts = [f"{day.isoformat()}：学习 {minutes} 分钟"]
    if nodes:
        parts.append(f"推进 {nodes} 个节点")
    if cards:
        parts.append(f"复习 {cards} 张卡片")
    if total:
        parts.append(f"测验正确率 {round(correct / total * 100)}%（{correct}/{total}）")
    return "，".join(parts) + "。"


def build_report(session: Session, *, project_id: int, day: date | None = None) -> DailyReport:
    require_project_node(session, project_id=project_id)
    day = day or datetime.now(REPORT_TIMEZONE).date()
    start, end = _day_bounds(day)

    records = list(
        session.scalars(
            select(ProgressRecord).where(
                ProgressRecord.project_id == project_id,
                ProgressRecord.recorded_at >= start,
                ProgressRecord.recorded_at < end,
            )
        )
    )
    buckets: dict[str, float] = {}
    for record in records:
        buckets[record.metric] = buckets.get(record.metric, 0.0) + float(record.value)

    minutes = int(buckets.get("minutes", 0))
    cards = int(buckets.get("cards_reviewed", 0))
    correct = int(buckets.get("quiz_correct", 0))
    total = int(buckets.get("quiz_total", 0))
    nodes = len({r.node_id for r in records if r.node_id and r.metric == "mastery"})

    report = DailyReport(
        project_id=project_id,
        report_date=datetime.combine(day, time.min, tzinfo=timezone.utc),
        content=_compose(day, minutes=minutes, cards=cards, correct=correct, total=total, nodes=nodes),
        study_minutes=minutes,
        cards_reviewed=cards,
        nodes_progressed=nodes,
    )
    session.add(report)
    session.flush()
    return report


def list_reports(session: Session, *, project_id: int | None = None, limit: int = 30,
                 offset: int = 0, from_date: date | None = None, to_date: date | None = None) -> list[DailyReport]:
    # Rank before limiting: snapshots from one busy day must not evict history.
    ranked = select(DailyReport.id, func.row_number().over(
        partition_by=(DailyReport.project_id, DailyReport.report_date),
        order_by=DailyReport.id.desc(),
    ).label("rank"))
    if project_id is not None:
        ranked = ranked.where(DailyReport.project_id == project_id)
    if from_date is not None:
        ranked = ranked.where(DailyReport.report_date >= datetime.combine(from_date, time.min, tzinfo=timezone.utc))
    if to_date is not None:
        ranked = ranked.where(DailyReport.report_date <= datetime.combine(to_date, time.min, tzinfo=timezone.utc))
    latest = ranked.subquery()
    stmt = (select(DailyReport).join(latest, DailyReport.id == latest.c.id)
            .where(latest.c.rank == 1).order_by(DailyReport.report_date.desc(), DailyReport.id.desc())
            .offset(offset).limit(limit))
    return list(session.scalars(stmt))
