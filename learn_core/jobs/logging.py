"""Task metadata only: never log exceptions, input or model output."""
import logging
import re

log = logging.getLogger("learn_worker")

def _safe(value):
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(value))[:80]

def log_job_failure(kind, job_id, code, tenant):
    log.warning("task_failed kind=%s job_id=%s code=%s tenant=%s",
                _safe(kind), _safe(job_id), _safe(code), _safe(str(tenant)[:8]))
