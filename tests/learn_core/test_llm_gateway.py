"""模型租约与网关记账的测试。"""

from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import text

from learn_core.db.engine import reset_engine, session_scope
from learn_core.db.models import Tenant, TenantSetting
from learn_core.llm.gateway import GatewayClient, GatewayError
from learn_core.llm.lease import LeaseUnavailable, acquire, release
from learn_core.tenancy.context import tenant_context

pytestmark = pytest.mark.skipif(
    os.getenv("LEARN_DATABASE_URL") is None,
    reason="需要 LEARN_DATABASE_URL 指向测试库",
)


@pytest.fixture(scope="module", autouse=True)
def _engine():
    reset_engine()
    yield
    reset_engine()


@contextmanager
def _tenant(official_id: str):
    with session_scope() as session:
        tenant = Tenant(official_user_id=official_id)
        session.add(tenant)
        session.flush()
        tenant_id = tenant.id
    with tenant_context(tenant_id), session_scope() as session:
        session.add(TenantSetting(tenant_id=tenant_id, chat_model="doubao-pro"))
    yield tenant_id
    with session_scope() as session:
        session.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


def test_interactive_lane_is_capped_per_tenant():
    suffix = uuid.uuid4().hex[:8]
    with _tenant(f"lease-{suffix}") as tid:
        with tenant_context(tid):
            with session_scope() as session:
                h1 = acquire(session, tenant_id=tid, lane="interactive")
                h2 = acquire(session, tenant_id=tid, lane="interactive")
                with pytest.raises(LeaseUnavailable):
                    acquire(session, tenant_id=tid, lane="interactive")
                release(session, tenant_id=tid, lane="interactive", holder=h1)
                h3 = acquire(session, tenant_id=tid, lane="interactive")

            with session_scope() as session:
                rows = session.execute(
                    text("SELECT holder FROM llm_lease WHERE tenant_id = :tid"), {"tid": tid}
                ).scalars().all()
            assert set(rows) == {h2, h3}


def test_expired_lease_is_reclaimed():
    suffix = uuid.uuid4().hex[:8]
    with _tenant(f"lease-exp-{suffix}") as tid:
        with tenant_context(tid):
            with session_scope() as session:
                acquire(session, tenant_id=tid, lane="interactive", holder="dead")
                session.execute(
                    text(
                        "UPDATE llm_lease SET expires_at = :past WHERE tenant_id = :tid"
                    ),
                    {"past": datetime.now(timezone.utc) - timedelta(minutes=5), "tid": tid},
                )
                acquire(session, tenant_id=tid, lane="interactive", holder="alive")
            with session_scope() as session:
                rows = session.execute(
                    text("SELECT holder FROM llm_lease WHERE tenant_id = :tid"), {"tid": tid}
                ).scalars().all()
            assert rows == ["alive"]


def _gateway(handler) -> GatewayClient:
    return GatewayClient(
        base_url="http://gw.test/v1",
        product_key="test-key",
        transport=httpx.MockTransport(handler),
    )


def test_chat_records_model_call_and_forwards_event_id():
    suffix = uuid.uuid4().hex[:8]
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["event_id"] = request.headers.get("X-Event-Id")
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "doubao-pro",
                "choices": [{"message": {"content": "好的"}}],
                "usage": {"total_tokens": 12},
            },
        )

    with _tenant(f"gw-{suffix}") as tid, tenant_context(tid):
        with _gateway(handler) as client:
            result = client.chat_detached(
                    job_id="test-detached",
                    event_id="ln-j1-1-1",
                    messages=[{"role": "user", "content": "你好"}],
                    purpose="chat",
                )
        assert result.content == "好的"
        assert result.usage == {"total_tokens": 12}

        with session_scope() as session:
            row = session.execute(
                text("SELECT event_id, status, usage FROM model_call WHERE tenant_id = :tid"),
                {"tid": tid},
            ).one()
    assert seen["event_id"] == "ln-j1-1-1"
    assert seen["body"]["messages"][0]["content"] == "你好"
    assert row[0] == "ln-j1-1-1"
    assert row[1] == "ok"


def test_gateway_error_is_recorded_and_lease_released():
    suffix = uuid.uuid4().hex[:8]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="too many requests")

    with _tenant(f"gw-err-{suffix}") as tid, tenant_context(tid):
        with _gateway(handler) as client:
            with pytest.raises(GatewayError) as excinfo:
                    client.chat_detached(
                        job_id="test-error", purpose="chat",
                        event_id="ln-j2-1-1",
                        messages=[{"role": "user", "content": "hi"}],
                    )
        assert excinfo.value.status == 429

        with session_scope() as session:
            status = session.execute(
                text("SELECT status FROM model_call WHERE tenant_id = :tid"), {"tid": tid}
            ).scalar_one()
            leases = session.execute(
                text("SELECT count(*) FROM llm_lease WHERE tenant_id = :tid"), {"tid": tid}
            ).scalar_one()
    assert status == "http_429"
    assert leases == 0, "失败的调用也必须释放租约"
