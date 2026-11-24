"""Bounded, opt-in local metrics without a resident monitoring service."""
from __future__ import annotations

import os
import socket
import threading
import time
from collections import Counter, deque
from datetime import datetime, timedelta, timezone

from learn_core.config import get_settings

_MAX_SAMPLES = 1000
_MAX_LOCAL_TENANTS = 64
_MONITOR_PREFIX = "/api/v2/local-monitor"
_STARTED = time.monotonic()
_lock = threading.Lock()
_samples = deque(maxlen=_MAX_SAMPLES)
_routes: dict[tuple[str, str], dict] = {}
_statuses = Counter()
_total = 0
_errors = 0


def enabled() -> bool:
    return bool(get_settings().local_monitor) and os.getenv("LEARN_DEV_AUTH") == "1"


def reset() -> None:
    global _total, _errors
    with _lock:
        _samples.clear()
        _routes.clear()
        _statuses.clear()
        _total = 0
        _errors = 0


def record_request(request, status: int, elapsed_ms: float) -> None:
    global _total, _errors
    if not enabled() or request.url.path.startswith(_MONITOR_PREFIX):
        return
    route = request.scope.get("route")
    route_path = getattr(route, "path", "") or "unmatched"
    method = request.method.upper()
    with _lock:
        _total += 1
        _errors += int(status >= 400)
        _statuses[str(status)] += 1
        _samples.append(float(elapsed_ms))
        row = _routes.setdefault((method, route_path), {"count": 0, "errors": 0, "totalMs": 0.0, "maxMs": 0.0})
        row["count"] += 1
        row["errors"] += int(status >= 400)
        row["totalMs"] += float(elapsed_ms)
        row["maxMs"] = max(row["maxMs"], float(elapsed_ms))


def request_snapshot() -> dict:
    with _lock:
        durations = sorted(_samples)
        rows = [(key, dict(value)) for key, value in _routes.items()]
        statuses = dict(sorted(_statuses.items()))
        total, errors = _total, _errors
    p95 = durations[min(len(durations) - 1, int(len(durations) * 0.95))] if durations else 0.0
    return {
        "total": total,
        "errors": errors,
        "recentSamples": len(durations),
        "p95Ms": round(p95, 2),
        "maxMs": round(durations[-1], 2) if durations else 0.0,
        "byStatus": statuses,
        "byRoute": [
            {
                "method": method,
                "route": route,
                "count": row["count"],
                "errors": row["errors"],
                "avgMs": round(row["totalMs"] / row["count"], 2),
                "maxMs": round(row["maxMs"], 2),
            }
            for (method, route), row in sorted(rows, key=lambda item: item[1]["count"], reverse=True)[:50]
        ],
    }


def process_snapshot() -> dict:
    try:
        import psutil
    except ImportError:
        return {"available": False}
    process = psutil.Process(os.getpid())
    return {
        "available": True,
        "pid": os.getpid(),
        "rssMiB": round(process.memory_info().rss / 1024**2, 2),
        "cpuPercent": round(process.cpu_percent(interval=None), 2),
        "threads": process.num_threads(),
    }


def embedding_snapshot() -> dict:
    from urllib.parse import urlsplit

    settings = get_settings()
    try:
        host = urlsplit(settings.embed_url).hostname
    except ValueError:
        host = None
    if host not in {"127.0.0.1", "::1", "localhost"}:
        return {"available": False}

    try:
        import httpx

        with httpx.Client(timeout=0.5, trust_env=False, follow_redirects=False) as client:
            response = client.get(f"{settings.embed_url.rstrip('/')}/healthz")
        if response.status_code != 200:
            raise ValueError("embedding health failed")
        body = response.json()
        queue = body.get("queue")
        if not isinstance(queue, dict):
            raise ValueError("embedding queue missing")
        values = [queue.get(key) for key in ("active", "waiting", "concurrency", "queueSize")]
        if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
            raise ValueError("embedding queue invalid")
        active, waiting, concurrency, queue_size = values
        return {
            "available": True,
            "status": str(body.get("status", ""))[:16],
            "dim": body.get("dim"),
            "queue": {
                "active": active,
                "waiting": waiting,
                "concurrency": concurrency,
                "queueSize": queue_size,
            },
        }
    except Exception:
        return {"available": False}


def database_snapshot() -> dict:
    from sqlalchemy import func, or_, select
    from sqlalchemy.engine import make_url

    from learn_core.db.engine import get_engine, session_scope
    from learn_core.db.models import JobProgress, ModelCall, Tenant
    from learn_core.tenancy.context import tenant_context

    pool = get_engine().pool
    pool_data = {
        "size": pool.size(),
        "checkedOut": pool.checkedout(),
        "checkedIn": pool.checkedin(),
        "overflow": max(0, pool.overflow()),
    }
    unavailable = {
        "available": False,
        "pool": pool_data,
        "windowMinutes": 15,
        "oldestQueuedSeconds": None,
        "jobs": {"byState": {}, "byKind": {}},
        "modelCalls": {"total": 0, "byStatus": {}},
    }
    try:
        url = make_url(get_settings().database_url)
        if url.host:
            with socket.create_connection((url.host, url.port or 5432), timeout=0.5):
                pass
        with session_scope() as session:
            tenant_ids = list(session.scalars(select(Tenant.id)))
        if len(tenant_ids) > _MAX_LOCAL_TENANTS:
            raise RuntimeError("local tenant limit")
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=15)
        job_states = Counter()
        job_kinds = Counter()
        model_statuses = Counter()
        oldest_queued = None
        for tenant_id in tenant_ids:
            with tenant_context(tenant_id), session_scope() as session:
                jobs = session.execute(
                    select(
                        JobProgress.state,
                        JobProgress.kind,
                        func.count(),
                        func.min(JobProgress.updated_at).filter(JobProgress.state == "queued"),
                    )
                    .where(or_(
                        JobProgress.state.in_(["queued", "running"]),
                        JobProgress.updated_at >= cutoff,
                    ))
                    .group_by(JobProgress.state, JobProgress.kind)
                ).all()
                models = session.execute(
                    select(ModelCall.status, func.count())
                    .where(ModelCall.created_at >= cutoff)
                    .group_by(ModelCall.status)
                ).all()
            for state, kind, count, queued_at in jobs:
                job_states[state] += count
                job_kinds[kind] += count
                if queued_at is not None and (oldest_queued is None or queued_at < oldest_queued):
                    oldest_queued = queued_at
            for status, count in models:
                model_statuses[status] += count
        return {
            "available": True,
            "pool": pool_data,
            "windowMinutes": 15,
            "oldestQueuedSeconds": round(max(0.0, (now - oldest_queued).total_seconds()), 1) if oldest_queued else None,
            "jobs": {"byState": dict(sorted(job_states.items())), "byKind": dict(sorted(job_kinds.items()))},
            "modelCalls": {"total": sum(model_statuses.values()), "byStatus": dict(sorted(model_statuses.items()))},
        }
    except Exception:
        return unavailable


def snapshot() -> dict:
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "uptimeSeconds": round(time.monotonic() - _STARTED, 1),
        "http": request_snapshot(),
        "process": process_snapshot(),
        "database": database_snapshot(),
    }
