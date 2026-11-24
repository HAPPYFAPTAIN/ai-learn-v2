"""Local monitor access, bounded request metrics and real tenant-scoped aggregates."""
import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from learn_api.app import create_app
from learn_core import monitoring
from learn_core.config import get_settings
from learn_core.db.engine import session_scope
from learn_core.db.models import JobProgress, ModelCall
from learn_core.tenancy.context import tenant_context
from tests.learn_core.test_generation import db_test, tenant


@pytest.fixture(autouse=True)
def clean_monitor(monkeypatch):
    monkeypatch.delenv("LEARN_LOCAL_MONITOR", raising=False)
    monkeypatch.delenv("LEARN_DEV_AUTH", raising=False)
    get_settings.cache_clear()
    monitoring.reset()
    yield
    get_settings.cache_clear()
    monitoring.reset()


def enable(monkeypatch):
    monkeypatch.setenv("LEARN_DEV_AUTH", "1")
    monkeypatch.setenv("LEARN_LOCAL_MONITOR", "1")
    monkeypatch.setenv("LEARN_PUBLIC_ORIGIN", "http://127.0.0.1")
    get_settings.cache_clear()


def local_client(app, host="127.0.0.1"):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=(host, 12345)),
        base_url="http://127.0.0.1",
    )


def test_monitor_is_disabled_by_default_and_hidden_from_remote(monkeypatch):
    async def exercise():
        app = create_app()
        async with local_client(app) as client:
            assert (await client.get("/api/v2/local-monitor")).status_code == 404
        enable(monkeypatch)
        async with local_client(app, "192.0.2.10") as client:
            assert (await client.get("/api/v2/local-monitor")).status_code == 404
    asyncio.run(exercise())


def test_disabled_monitor_does_not_collect_request_samples():
    async def exercise():
        async with local_client(create_app()) as client:
            assert (await client.get("/healthz")).status_code == 200
        assert monitoring.request_snapshot()["total"] == 0
    asyncio.run(exercise())


def test_monitor_page_and_real_request_metrics_do_not_expose_query_data(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setattr(monitoring, "database_snapshot", lambda: {
        "available": True,
        "pool": {"size": 5, "checkedOut": 0, "checkedIn": 0, "overflow": 0},
        "windowMinutes": 15,
        "oldestQueuedSeconds": 12.5,
        "jobs": {"byState": {}, "byKind": {}},
        "modelCalls": {"total": 0, "byStatus": {}},
    })
    monkeypatch.setattr(monitoring, "embedding_snapshot", lambda: {
        "available": True,
        "status": "ok",
        "dim": 384,
        "queue": {"active": 1, "waiting": 2, "concurrency": 1, "queueSize": 8},
    })

    async def exercise():
        app = create_app()
        async with local_client(app) as client:
            assert (await client.get("/healthz?private=must-not-appear")).status_code == 200
            page = await client.get("/api/v2/local-monitor")
            assert page.status_code == 200 and "AI Learn 本地性能监控" in page.text
            assert "script-src 'self'" in page.headers["content-security-policy"]
            assert (await client.get("/api/v2/local-monitor/assets.js")).status_code == 200
            response = await client.get("/api/v2/local-monitor/data")
        assert response.status_code == 200
        data = response.json()
        assert data["http"]["total"] == 1
        assert data["http"]["byRoute"][0]["route"] == "/healthz"
        if data["process"]["available"]:
            assert data["process"]["rssMiB"] > 0
        else:
            assert data["process"] == {"available": False}
        assert data["events"] == {"listenerActive": False, "subscribers": 0, "jobs": 0}
        assert data["embedding"]["queue"] == {"active": 1, "waiting": 2, "concurrency": 1, "queueSize": 8}
        assert data["database"]["oldestQueuedSeconds"] == 12.5
        assert "must-not-appear" not in response.text
        assert "/api/v2/local-monitor" not in app.openapi()["paths"]
    asyncio.run(exercise())


def test_embedding_snapshot_only_probes_loopback_and_whitelists_fields(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "status": "ok",
                "dim": 384,
                "queue": {"active": 0, "waiting": 1, "concurrency": 1, "queueSize": 8},
                "private": "must-not-leak",
            }

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url):
            calls.append(url)
            return FakeResponse()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(get_settings(), "embed_url", "http://127.0.0.1:18090")
    data = monitoring.embedding_snapshot()
    assert data == {
        "available": True,
        "status": "ok",
        "dim": 384,
        "queue": {"active": 0, "waiting": 1, "concurrency": 1, "queueSize": 8},
    }
    assert "private" not in json.dumps(data)
    assert calls[0] == {"timeout": 0.5, "trust_env": False, "follow_redirects": False}
    assert calls[1] == "http://127.0.0.1:18090/healthz"

    calls.clear()
    monkeypatch.setattr(get_settings(), "embed_url", "http://192.0.2.10:18090")
    assert monitoring.embedding_snapshot() == {"available": False}
    assert calls == []


@db_test
def test_database_metrics_use_real_records_without_exposing_tenant(tenant):
    marker = uuid4().hex
    with tenant_context(tenant[0]), session_scope() as session:
        session.add(JobProgress(job_id=f"monitor-{marker}", kind="monitor-probe", state="queued", progress={}))
        session.add(ModelCall(event_id=f"monitor-{marker}", status="monitor-ok", usage={}))
    data = monitoring.database_snapshot()
    assert data["available"] is True
    assert data["jobs"]["byKind"]["monitor-probe"] == 1
    assert data["modelCalls"]["byStatus"]["monitor-ok"] == 1
    assert str(tenant[0]) not in json.dumps(data)
