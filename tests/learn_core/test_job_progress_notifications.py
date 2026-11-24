import json
from uuid import uuid4

import psycopg

from learn_core.config import get_settings
from learn_core.db.engine import session_scope
from learn_core.db.models import JobProgress
from learn_core.jobs.tasks import _set_job
from learn_core.tenancy.context import tenant_context
from tests.learn_core.test_generation import db_test, tenant


def _next_notice(listener, job_id):
    for notification in listener.notifies(timeout=2):
        payload = json.loads(notification.payload)
        if payload.get("jobId") == job_id:
            return payload
    return None


@db_test
def test_job_progress_commit_notifies_once_and_rollback_does_not(tenant):
    listener = psycopg.connect(get_settings().procrastinate_dsn, autocommit=True)
    listener.execute("LISTEN learn_job_progress")
    job_id = f"notify-{uuid4().hex}"
    try:
        with tenant_context(tenant[0]), session_scope() as session:
            session.add(JobProgress(job_id=job_id, kind="test", subject="notify", state="running", progress={}))
        notice = _next_notice(listener, job_id)
        assert notice == {"tenantId": str(tenant[0]), "jobId": job_id}

        _set_job(tenant[0], job_id, progress={"done": 1, "total": 1})
        notice = _next_notice(listener, job_id)
        assert notice == {"tenantId": str(tenant[0]), "jobId": job_id}

        rolled_back = f"notify-{uuid4().hex}"
        try:
            with tenant_context(tenant[0]), session_scope() as session:
                session.add(JobProgress(job_id=rolled_back, kind="test", subject="rollback", state="running", progress={}))
                raise RuntimeError("rollback")
        except RuntimeError:
            pass
        assert list(listener.notifies(timeout=0.3)) == []
    finally:
        listener.close()
