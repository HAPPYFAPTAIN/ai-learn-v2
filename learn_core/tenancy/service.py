"""租户的创建与查找。

第一次访问时按官网用户 id 自动建租户；重复请求用 ON CONFLICT 收敛，
并发进来也只会有一行。
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from learn_core.db.models import Tenant


def get_or_create_tenant(session: Session, official_user_id: str) -> Tenant:
    row = session.execute(
        text(
            """
            INSERT INTO tenant (official_user_id)
            VALUES (:uid)
            ON CONFLICT (official_user_id)
            DO UPDATE SET last_seen_at = now()
            RETURNING id, official_user_id, status, quota_bytes, created_at, last_seen_at
            """
        ),
        {"uid": official_user_id},
    ).one()
    session.flush()
    return Tenant(
        id=row[0],
        official_user_id=row[1],
        status=row[2],
        quota_bytes=row[3],
        created_at=row[4],
        last_seen_at=row[5],
    )


def get_tenant(session: Session, tenant_id: UUID) -> Tenant | None:
    return session.get(Tenant, tenant_id)


def require_active(tenant: Tenant) -> Tenant:
    if tenant.status != "active":
        raise PermissionError(f"tenant {tenant.id} is {tenant.status}")
    return tenant
