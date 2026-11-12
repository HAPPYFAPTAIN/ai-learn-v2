"""行级安全与租户隔离的守卫测试。

需要本地 Postgres（见 scripts/dev_postgres.sh）。没有配置数据库时整体跳过。
"""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from learn_core.db.engine import get_engine, reset_engine, session_scope
from learn_core.db.models import Project, Tenant
from learn_core.tenancy.context import (
    TenantMissingError,
    current_tenant,
    tenant_context,
)

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
    yield tenant_id
    with session_scope() as session:
        session.execute(text("DELETE FROM tenant WHERE id = :tid"), {"tid": tenant_id})


def test_missing_tenant_is_an_error():
    with pytest.raises(TenantMissingError):
        current_tenant()


def test_rows_are_invisible_across_tenants():
    suffix = uuid.uuid4().hex[:8]
    with _tenant(f"iso-a-{suffix}") as ta, _tenant(f"iso-b-{suffix}") as tb:
        with tenant_context(ta):
            with session_scope() as session:
                session.add(Project(topic="甲的项目"))
        with tenant_context(tb):
            with session_scope() as session:
                session.add(Project(topic="乙的项目"))

        with tenant_context(ta):
            with session_scope() as session:
                rows = session.execute(text("SELECT topic FROM le_project")).scalars().all()
            assert rows == ["甲的项目"]

        with tenant_context(tb):
            with session_scope() as session:
                rows = session.execute(text("SELECT topic FROM le_project")).scalars().all()
            assert rows == ["乙的项目"]

        # 没有租户上下文时读不到任何行。
        with session_scope() as session:
            rows = session.execute(text("SELECT topic FROM le_project")).scalars().all()
            assert rows == []


def test_writes_into_another_tenant_are_rejected():
    suffix = uuid.uuid4().hex[:8]
    with _tenant(f"iso-a-{suffix}") as ta, _tenant(f"iso-b-{suffix}") as tb:
        with tenant_context(tb):
            with pytest.raises((DBAPIError, IntegrityError)):
                with session_scope() as session:
                    session.add(Project(topic="越权写入", tenant_id=ta))


def test_every_tenant_table_has_forced_row_level_security():
    with session_scope() as session:
        rows = session.execute(
            text(
                """
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public' AND c.relkind = 'r'
                  AND EXISTS (
                    SELECT 1 FROM information_schema.columns col
                    WHERE col.table_schema = 'public'
                      AND col.table_name = c.relname
                      AND col.column_name = 'tenant_id'
                  )
                ORDER BY 1
                """
            )
        ).fetchall()
    assert rows, "应该至少有一张带 tenant_id 的表"
    missing = [name for name, enabled, forced in rows if not (enabled and forced)]
    assert not missing, f"这些表没有强制行级安全: {missing}"
