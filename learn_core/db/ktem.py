"""Kotaemon 核心表的租户化版本。

Kotaemon 允许通过 `KH_TABLE_CONV` / `KH_TABLE_SETTINGS` / `KH_TABLE_ISSUE_REPORT`
把它的表换成任意 SQLModel 子类（见 `kotaemon/libs/ktem/ktem/db/models.py`）。
这里给出带 `tenant_id` 的替代实现，策略与其它表一致：FORCE ROW LEVEL SECURITY。

只保留 Learn Everything 真正会用的三张表；`ktem_user` 不复用，
账号以官网 official_user_id 为准。
"""

from __future__ import annotations

import datetime
import uuid
from typing import Optional

from uuid import UUID

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from learn_core.db.models import tenant_column


class KtemConversation(SQLModel, table=True):
    __tablename__ = "ktem_conversation"

    tenant_id: UUID = Field(sa_column=tenant_column())

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    name: str = Field(default="Untitled")
    user: str = Field(default="")
    is_public: bool = Field(default=False)
    data_source: dict = Field(default={}, sa_column=Column(JSON))
    date_created: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    date_updated: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class KtemSettings(SQLModel, table=True):
    __tablename__ = "ktem_settings"

    tenant_id: UUID = Field(sa_column=tenant_column())

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    user: str = Field(default="")
    setting: dict = Field(default={}, sa_column=Column(JSON))


class KtemIssueReport(SQLModel, table=True):
    __tablename__ = "ktem_issue_report"

    tenant_id: UUID = Field(sa_column=tenant_column())

    id: Optional[int] = Field(default=None, primary_key=True)
    issues: dict = Field(default={}, sa_column=Column(JSON))
    chat: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    settings: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    user: Optional[str] = Field(default=None)
