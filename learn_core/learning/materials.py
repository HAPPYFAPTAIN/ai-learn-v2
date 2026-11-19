"""Tenant-shared library with atomic index scheduling and deletion safeguards."""
import hashlib
import io
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import select, text, func
from sqlalchemy.orm import Session
from learn_core.db.models import StoredFile, Tenant, JobProgress
from learn_core.tenancy.context import current_tenant
from learn_core.storage import files as storage
from learn_core.rag.store import delete_source


def storage_lock(session: Session):
    session.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key':f'{current_tenant()}:storage'})


def defer(session: Session, *, task: str, args: dict, subject: str):
    session.execute(text('''
        SELECT procrastinate_defer_jobs_v1(ARRAY[
          ROW('io', :task, 0, :lock, :dedupe, CAST(:args AS jsonb), NULL::timestamptz)
        ]::procrastinate_job_to_defer_v1[])
    '''), {'task':task, 'lock':f'{current_tenant()}:io', 'dedupe':subject,
           'args':json.dumps({'tenant':str(current_tenant()), **args})})


def schedule_index(session: Session, *, row: StoredFile) -> JobProgress:
    active = session.scalar(select(JobProgress).where(JobProgress.kind == 'index', JobProgress.subject == str(row.id), JobProgress.state.in_(['queued','running'])).limit(1))
    if active:
        return active
    job = JobProgress(job_id=f'idx-{uuid4().hex}', kind='index', subject=str(row.id), state='queued', progress={'done':0,'total':0})
    session.add(job)
    session.flush()
    defer(session, task='learn_core.jobs.tasks.index_material', args={'job_id':job.job_id,'file_id':str(row.id)}, subject=f'{current_tenant()}:index:{row.id}')
    return job


def upload(session: Session, *, data: bytes, name: str, index: bool):
    storage_lock(session)
    sha = hashlib.sha256(data).hexdigest()
    row = session.scalar(select(StoredFile).where(StoredFile.sha256 == sha, StoredFile.kind == 'material'))
    if row:
        return row, schedule_index(session, row=row) if index else None
    tenant = session.get(Tenant, current_tenant())
    used = session.scalar(select(func.coalesce(func.sum(StoredFile.size_bytes),0)))
    if used + len(data) > tenant.quota_bytes:
        raise OverflowError('学习空间不足，请删除不再需要的资料')
    saved = storage.put(io.BytesIO(data), kind='material')
    try:
        # Keep the outer storage lock during rollback/cleanup if scheduling fails.
        with session.begin_nested():
            row = StoredFile(id=uuid4(), kind='material', sha256=sha, size_bytes=saved.size_bytes, storage_key=saved.storage_key, original_name=name)
            session.add(row)
            session.flush()
            job = schedule_index(session, row=row) if index else None
        return row, job
    except Exception:
        if saved.created:
            storage.delete(saved.storage_key)
        raise


def remove(session: Session, *, row: StoredFile):
    storage_lock(session)
    delete_source(session, index_id='material', source_id=str(row.id))
    jobs = session.scalars(select(JobProgress).where(JobProgress.kind == 'index', JobProgress.subject == str(row.id), JobProgress.state.in_(['queued','running'])).with_for_update())
    for job in jobs:
        job.state, job.error = 'cancelled', '资料已删除'
        job.updated_at = datetime.now(timezone.utc)
    defer(session, task='learn_core.jobs.tasks.purge_material', args={'storage_key':row.storage_key}, subject=f'{current_tenant()}:purge:{row.id}')
    session.delete(row)
