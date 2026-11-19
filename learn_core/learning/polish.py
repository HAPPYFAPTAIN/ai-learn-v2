"""Durable copy editing with legacy protected-text rules and the shared gateway."""
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from learn_core.db.engine import session_scope
from learn_core.db.models import Project, JobProgress
from learn_core.learning.model_settings import selected_model
from learn_core.learning.conversations import ConversationMissing, ConversationBusy
from learn_core.learning.prompts.polish import PURPOSES, build_prompt
from learn_core.learning.polish_text import _protect, validate_output
from learn_core.tenancy.context import tenant_context, current_tenant
from learn_core.llm.event_id import next_event_id, step_event
from learn_core.llm.gateway import GatewayClient, GatewayError


def latest(session: Session, *, project_id: int):
    if session.get(Project, project_id) is None:
        raise ConversationMissing('学习计划不存在')
    return session.scalar(select(JobProgress).where(JobProgress.kind == 'polish', JobProgress.subject == f'project:{project_id}').order_by(JobProgress.id.desc()).limit(1))


def submit(session: Session, *, project_id: int, source: str, purpose: str, request_id: str):
    if not source.strip() or len(source) > 12000 or purpose not in PURPOSES:
        raise ValueError('请输入 12000 字以内的文字，并选择润色用途')
    session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key':f'{current_tenant()}:polish:{project_id}'})
    if session.get(Project, project_id) is None:
        raise ConversationMissing('学习计划不存在')
    previous = session.scalar(select(JobProgress).where(JobProgress.kind == 'polish', JobProgress.subject == f'project:{project_id}', JobProgress.progress['requestId'].astext == request_id).limit(1))
    if previous:
        if previous.progress['source'] != source or previous.progress['purpose'] != purpose:
            raise ValueError('同一请求编号不能润色不同内容')
        return previous
    existing = latest(session,project_id=project_id)
    if existing and existing.state in {'queued','running'}:
        raise ConversationBusy('润色正在进行，请等待完成')
    model = selected_model(session)
    if not model:
        raise ValueError('请先在模型设置选择主模型')
    protected, spans = _protect(source)
    system, prompt = build_prompt(purpose, protected, '')
    row = JobProgress(job_id=f'polish-{uuid4().hex}',kind='polish',subject=f'project:{project_id}',state='queued',progress={
        'projectId':project_id,'source':source,'purpose':purpose,'requestId':request_id,'model':model,
        'messages':[{'role':'system','content':system},{'role':'user','content':prompt}], 'spans':spans,
        'eventId':step_event(next_event_id(session,tenant_id=current_tenant(),kind='r'),1),
    })
    session.add(row);session.flush()
    session.execute(text('''SELECT procrastinate_defer_jobs_v1(ARRAY[
      ROW('llm','learn_core.jobs.tasks.polish_text',200,:lock,:dedupe,CAST(:args AS jsonb),NULL::timestamptz)
    ]::procrastinate_job_to_defer_v1[])'''),{'lock':f'{current_tenant()}:fg','dedupe':f'{current_tenant()}:polish:{project_id}','args':json.dumps({'tenant':str(current_tenant()),'job_id':row.job_id})})
    return row


def run_polish(*, tenant: str, job_id: str):
    with tenant_context(UUID(tenant)):
        try:
            with session_scope() as session:
                row = session.scalar(select(JobProgress).where(JobProgress.job_id == job_id).with_for_update())
                if row is None or row.state in {'done','failed','cancelled'}: return
                p = dict(row.progress)
                if session.get(Project,p['projectId']) is None: raise ConversationMissing('学习计划已删除')
                row.state, row.error = 'running', None
                row.updated_at = datetime.now(timezone.utc)
            with GatewayClient() as gateway:
                result = gateway.chat_detached(event_id=p['eventId'],job_id=job_id,messages=p['messages'],purpose='polish',model=p['model'],lane='interactive',temperature=0.1,max_tokens=min(16384,max(512,len(p['messages'][1]['content'])*2+512)))
            output = validate_output(p['source'], result.content, p['spans'], p['purpose'])
            with session_scope() as session:
                row = session.scalar(select(JobProgress).where(JobProgress.job_id == job_id).with_for_update())
                if row is None or row.state in {'done','cancelled'}: return
                if session.get(Project,p['projectId']) is None: raise ConversationMissing('学习计划已删除')
                row.state, row.error = 'done', None
                row.progress = {**p,'result':output,'changed':output != p['source'],'done':1,'total':1}
                row.updated_at = datetime.now(timezone.utc)
        except Exception as exc:
            with session_scope() as session:
                row = session.scalar(select(JobProgress).where(JobProgress.job_id == job_id).with_for_update())
                if row and row.state not in {'done','cancelled'}:
                    row.state = 'cancelled' if isinstance(exc,ConversationMissing) else 'failed'
                    row.error = str(exc) if isinstance(exc,(ValueError,GatewayError)) else '润色未完成，请稍后重试。原文已保留'
                    row.updated_at = datetime.now(timezone.utc)
