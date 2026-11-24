"""User-requested roadmap/lesson migration: durable jobs, short transactions, CAS writes."""
from __future__ import annotations

import hashlib
import json
import time
from statistics import median
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from learn_core.config import get_settings
from learn_core.db.engine import session_scope
from learn_core.db.models import JobProgress, Project, Knode, TenantSetting
from learn_core.learning.prompts.roadmap import SYSTEM as ROADMAP_SYSTEM, USER_TEMPLATE
from learn_core.learning.prompts.lesson import SYSTEM as LESSON_SYSTEM, lesson_prompt
from learn_core.learning.roadmaps import parse_roadmap, save_roadmap
from learn_core.learning import assessment, grading
from learn_core.jobs.logging import log_job_failure
from learn_core.llm.event_id import next_event_id, step_event
from learn_core.llm.gateway import UNKNOWN_RESULT, GatewayClient, GatewayError
from learn_core.llm.lease import LeaseUnavailable
from learn_core.tenancy.context import current_tenant, tenant_context

ACTIVE_STATES = ("queued", "running")


class GenerationConflict(ValueError):
    pass


class GenerationBusy(GenerationConflict):
    pass


class GenerationMissing(ValueError):
    pass


class RetryableGenerationError(RuntimeError):
    def __init__(self, delay: int):
        self.delay = delay
        super().__init__("模型暂时不可用，任务稍后重试")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def course_code_sort_key(code: str) -> tuple:
    """Numeric segment order migrated from learning_ext/progress/study.py."""
    import re
    return tuple((0, int(p)) if p.isdigit() else (1, p.lower())
                 for p in re.split(r"([0-9]+)", code or "") if p)


def _snapshot(project: Project, node: Knode | None = None) -> dict:
    data = {"topic": project.topic or project.title, "background": project.background,
            "goal": project.goal, "weekly_hours": project.weekly_hours}
    if node is not None:
        data["chapter"] = {"code": node.code, "title": node.title,
                           "description": node.description, "difficulty": node.difficulty,
                           "est_hours": node.est_hours, "stage": node.stage}
        data["version"] = node.content_version
    return data


def _digest(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _input_snapshot(session: Session, project: Project, node: Knode | None, kind: str, options: dict) -> dict:
    data = _snapshot(project, node)
    if kind in {"quiz", "cards"}:
        data["chapters"] = assessment.selected_chapters(session, project_id=project.id, node_ids=options["nodeIds"])
    if kind == "grade":
        data.update(grading.snapshot(session, project_id=project.id, options=options))
    return data


def estimated_model_ms(session: Session, *, kind: str, model: str) -> tuple[int, str]:
    """Only this tenant's last ten successful requests for the same model/kind."""
    rows = session.scalars(select(JobProgress).where(
        JobProgress.kind == kind, JobProgress.state == "done",
        JobProgress.progress["model"].astext == model,
    ).order_by(JobProgress.id.desc()).limit(10))
    durations = [r.progress.get("modelMs") for r in rows]
    durations = [v for v in durations if isinstance(v, (int, float)) and 1000 <= v <= 600_000]
    return (max(5000, round(median(durations))), "history") if durations else (45_000, "default")


def submit_generation(
    session: Session, *, project_id: int, kind: str, node_id: int | None = None,
    force: bool = False, options: dict | None = None,
) -> JobProgress:
    if kind not in {"roadmap", "lesson", "quiz", "cards", "grade"}:
        raise ValueError("unknown generation kind")
    options = dict(options or {})
    project = session.scalar(select(Project).where(Project.id == project_id).with_for_update())
    if project is None:
        raise GenerationMissing("学习计划不存在")
    node = session.get(Knode, node_id) if kind == "lesson" else None
    if kind == "lesson" and (node is None or node.project_id != project_id):
        raise GenerationMissing("章节不存在")
    if kind in {"quiz", "cards"}:
        ids = options.get("nodeIds", [])
        if not ids or len(ids) > 20 or len(set(ids)) != len(ids):
            raise GenerationConflict("请选择 1–20 个有效章节")
        if kind == "cards" and len(ids) != 1:
            raise GenerationConflict("每次请选择一个章节生成复习卡")
        if not isinstance(options.get("count"), int) or not 1 <= options["count"] <= 20:
            raise GenerationConflict("生成数量应为 1–20")
        if kind == "quiz" and options.get("qtype") not in {"mixed", "choice", "fill", "short", "practice"}:
            raise GenerationConflict("不支持的题型")
        options["nodeIds"] = sorted(ids)
        # Fail before charging if a chapter belongs to another project/tenant.
        try:
            assessment.selected_chapters(session, project_id=project_id, node_ids=ids)
        except ValueError as exc:
            raise GenerationMissing(str(exc)) from exc
    if kind == "grade":
        try:
            grading.snapshot(session, project_id=project_id, options=options)
        except ValueError as exc:
            raise GenerationMissing(str(exc)) from exc
    subject = f"quiz:{options['quizId']}" if kind == "grade" else f"project:{project_id}" if kind in {"roadmap", "quiz", "cards"} else f"node:{node_id}"
    active = session.scalar(select(JobProgress).where(
        JobProgress.kind == kind, JobProgress.subject == subject,
        JobProgress.state.in_((*ACTIVE_STATES, "done") if kind == "grade" else ACTIVE_STATES),
    ).order_by(JobProgress.id.desc()).limit(1))
    if active:
        if active.state == 'done': return active
        if active.progress.get('options', {}) != options or active.progress.get('force', False) != force or active.progress.get('nodeId') != node_id:
            raise GenerationBusy('已有同类任务在进行，完成后再提交')
        return active
    if kind == "roadmap" and session.scalar(select(Knode.id).where(Knode.project_id == project_id).limit(1)):
        raise GenerationConflict("已有章节，已保留原学习内容；请新建计划生成路线")
    if node is not None and node.content_version > 0 and is_content_valid(node.description) and not force:
        raise GenerationConflict("已有课程内容，如需重新生成请明确选择重新生成")
    tenant_id = current_tenant()
    setting = session.get(TenantSetting, tenant_id)
    snapshot = _input_snapshot(session, project, node, kind, options)
    requires_model = kind != "grade" or grading.grading_prompt(snapshot) is not None
    if requires_model:
        from learn_core.learning.model_settings import require_model
        require_model(session)
    estimate_ms, estimate_source = estimated_model_ms(session, kind=kind, model=setting.chat_model if setting else "")
    job_id = f"{kind}-{uuid4().hex}"
    row = JobProgress(job_id=job_id, kind=kind, subject=subject, state="queued", progress={
        "done": 0, "total": 1, "projectId": project_id, "nodeId": node_id,
        "inputDigest": _digest(snapshot), "options": options, "force": force,
        "model": setting.chat_model if setting else "", "eventBase": next_event_id(session, tenant_id=tenant_id),
        "queuedAt": now_iso(),
        "phase": "queued", "estimatedModelMs": estimate_ms, "estimateSource": estimate_source,
    })
    session.add(row)
    session.flush()
    # Procrastinate 3.x's SQL enqueue function, in THIS transaction:
    # the worker can only fetch the job after its progress row is committed.
    session.execute(text("""
        SELECT procrastinate_defer_jobs_v1(ARRAY[
          ROW('llm', 'learn_core.jobs.tasks.generate_learning', 100,
              :lock, :dedupe, CAST(:args AS jsonb), NULL::timestamptz)
        ]::procrastinate_job_to_defer_v1[])
    """), {"lock": f"{tenant_id}:fg", "dedupe": f"{tenant_id}:{kind}:{subject}",
           "args": json.dumps({"tenant": str(tenant_id), "job_id": job_id})})
    return row


def _load_input(session: Session, row: JobProgress) -> dict:
    progress = row.progress
    project = session.scalar(select(Project).where(
        Project.id == progress["projectId"]).with_for_update())
    if project is None:
        raise GenerationMissing("学习计划已删除，已停止生成")
    node = None
    if row.kind == "lesson":
        node = session.get(Knode, progress["nodeId"])
        if node is None or node.project_id != project.id:
            raise GenerationMissing("章节已删除，已停止生成")
    try:
        data = _input_snapshot(session, project, node, row.kind, progress.get("options", {}))
    except ValueError as exc:
        raise GenerationMissing(str(exc)) from exc
    if _digest(data) != progress["inputDigest"]:
        raise GenerationConflict("目标或章节已修改，已丢弃过期生成结果")
    if row.kind == "roadmap" and session.scalar(select(Knode.id).where(Knode.project_id == project.id).limit(1)):
        raise GenerationConflict("已添加章节，已保留现有内容")
    return data


def _finish_error(job_id: str, message: str, state: str = "failed", *, new_event: bool = False, error_code: str = "INTERNAL") -> None:
    with session_scope() as session:
        row = session.scalar(select(JobProgress).where(JobProgress.job_id == job_id).with_for_update())
        if row and row.state in ACTIVE_STATES:
            progress = {**row.progress, "gatewayCallPending": False, "errorCode": error_code}
            if new_event:
                progress["eventAttempt"] = progress.get("eventAttempt", 1) + 1
            row.progress = progress
            row.state = state
            row.error = message
            if state == 'failed':
                log_job_failure(row.kind, job_id, error_code, current_tenant())
            row.updated_at = datetime.now(timezone.utc)


def run_generation(*, tenant: str, job_id: str, attempt: int = 0) -> None:
    """No ORM object or business transaction survives the network phase."""
    with tenant_context(UUID(tenant)):
        try:
            with session_scope() as session:
                row = session.scalar(select(JobProgress).where(JobProgress.job_id == job_id).with_for_update())
                if row is None or row.state in {"done", "cancelled", "failed"}:
                    return
                # Older running jobs used the persisted prompt as their only
                # durable indication that the request might have been sent.
                pending = row.progress.get("gatewayCallPending", "prepared" in row.progress)
                if row.state == "running" and pending:
                    row.state, row.error = "failed", UNKNOWN_RESULT
                    row.progress = {**row.progress, 'errorCode': 'RESULT_UNCONFIRMED'}
                    log_job_failure(row.kind, job_id, 'RESULT_UNCONFIRMED', tenant)
                    row.updated_at = datetime.now(timezone.utc)
                    return
                data = _load_input(session, row)
                kind = row.kind
                progress = dict(row.progress)
                progress.setdefault("startedAt", now_iso())
                progress["attempt"] = attempt
                # Queue attempts include crash recovery. Only an explicit
                # upstream rejection starts a new logical billing event.
                progress.setdefault("eventAttempt", 1)
                progress["eventId"] = step_event(progress["eventBase"], 1, progress["eventAttempt"])
                progress["gatewayCallPending"] = False
                progress["phase"] = "generating"
                progress["attemptStartedAt"] = now_iso()
                row.state, row.error, row.progress = "running", None, progress
                row.updated_at = datetime.now(timezone.utc)
            if kind == "roadmap":
                prompt = USER_TEMPLATE.format(topic=data["topic"], background=data["background"] or "初学者",
                                              goal=data["goal"] or "掌握并应用核心知识", weekly_hours=data["weekly_hours"])
                system = ROADMAP_SYSTEM
            elif kind == "lesson":
                prompt = lesson_prompt(chapter=data["chapter"], project_topic=data["topic"], learning_goal=data["goal"])
                system = LESSON_SYSTEM
            elif kind == "grade":
                pair = grading.grading_prompt(data)
                system, prompt = pair if pair else ("", "")
            else:
                system, prompt = assessment.generation_prompt(kind, data, progress["options"])
            started = time.monotonic()
            result = None
            if prompt:
                if len(system) + len(prompt) > 120_000:
                    raise ValueError("所选学习内容过长，请缩小范围")
                if "prepared" not in progress:
                    progress["prepared"] = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
                with session_scope() as session:
                    row = session.scalar(select(JobProgress).where(JobProgress.job_id == job_id).with_for_update())
                    if row is None or row.state != "running":
                        return
                    progress["gatewayCallPending"] = True
                    row.progress = dict(progress)
                settings = get_settings()
                with GatewayClient(timeout=settings.generation_read_timeout) as gateway:
                    result = gateway.chat_detached(
                        event_id=progress["eventId"], job_id=job_id,
                        messages=progress["prepared"],
                        purpose=kind, model=progress["model"],
                        max_tokens=settings.generation_max_tokens,
                    )
                if result.truncated:
                    raise GatewayError(422, "生成内容超出长度上限，未能保存。可以缩小章节范围后重试。", code='OUTPUT_TRUNCATED')
            model_ms = round((time.monotonic() - started) * 1000)
            roadmap = parse_roadmap(result.content) if kind == "roadmap" else None
            items = assessment.validate_output(kind, result.content, data, progress["options"]) if kind in {"quiz", "cards"} else None
            grades = grading.validate_results(data, result.content if result else None) if kind == "grade" else None
            if kind == "lesson" and (len(result.content) > 50000 or not is_content_valid(result.content)):
                raise ValueError("教材内容过短或无效，原内容已保留")
            writing = time.monotonic()
            with session_scope() as session:
                row = session.scalar(select(JobProgress).where(JobProgress.job_id == job_id).with_for_update())
                if row is None or row.state != "running":
                    return
                progress["phase"] = "saving"
                row.progress = dict(progress)
                row.updated_at = datetime.now(timezone.utc)
            with session_scope() as session:
                row = session.scalar(select(JobProgress).where(JobProgress.job_id == job_id).with_for_update())
                if row is None or row.state != "running":
                    return
                _load_input(session, row)
                if kind == "roadmap":
                    count = save_roadmap(session, project_id=progress["projectId"], roadmap=roadmap)
                    output = {"count": count}
                elif kind == "lesson":
                    changed = session.execute(update(Knode).where(
                        Knode.id == progress["nodeId"], Knode.content_version == data["version"],
                    ).values(description=result.content, content_version=Knode.content_version + 1))
                    if changed.rowcount != 1:
                        raise GenerationConflict("章节已修改，原内容已保留")
                    count = 1
                    output = {"count": count}
                elif kind == "grade":
                    output = grading.save_result(session, results=grades, project_id=progress["projectId"])
                else:
                    output = assessment.save_output(session, project_id=progress["projectId"], kind=kind, data=data, items=items, options=progress["options"])
                finished = datetime.now(timezone.utc)
                row.state, row.error = "done", None
                progress["gatewayCallPending"] = False
                row.progress = {**progress, "done": 1, "total": 1, **output,
                    "phase": "done",
                    "modelMs": model_ms, "saveMs": round((time.monotonic() - writing) * 1000),
                    "queueMs": max(0, round((datetime.fromisoformat(progress["startedAt"]) - datetime.fromisoformat(progress["queuedAt"])).total_seconds() * 1000)),
                    "totalMs": max(0, round((finished - datetime.fromisoformat(progress["queuedAt"])).total_seconds() * 1000)),
                    "finishedAt": finished.isoformat()}
                row.updated_at = finished
        except (GenerationMissing, GenerationConflict) as exc:
            _finish_error(job_id, str(exc), "cancelled")
        except (GatewayError, LeaseUnavailable) as exc:
            retryable = isinstance(exc, LeaseUnavailable) or exc.retryable
            if retryable and attempt < 2:
                _finish_error(job_id, "模型暂时繁忙，正在等待重试", "queued",
                              new_event=isinstance(exc, GatewayError) and exc.status == 429)
                raise RetryableGenerationError((10, 40)[attempt]) from exc
            message = str(exc) if isinstance(exc, GatewayError) else "模型并发额度已满，请稍后重试"
            _finish_error(job_id, message, error_code=exc.code if isinstance(exc, GatewayError) else "TENANT_BUSY")
        except (ValueError, TypeError) as exc:
            # Never publish raw provider JSON, Pydantic input values or secrets.
            _finish_error(job_id, "生成内容未通过校验，原内容已保留；请调整模型后重试")
        except Exception:
            _finish_error(job_id, "生成任务执行失败，原内容已保留")
            raise


def is_content_valid(description: str | None) -> bool:
    """Legacy content validator from progress/study.py (without its runtime imports)."""
    content = (description or "").strip()
    if len(content) < 100 or any(s in content for s in ("模拟的 LLM", "该知识点暂无", "*暂无", "这是模拟")):
        return False
    return len(content) >= 500 or content.count("\n## ") + int(content.startswith("## ")) >= 2
