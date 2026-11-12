"""验证一：Kotaemon 核心表在行级安全下可用。

Kotaemon 的表用字符串主键、JSON 列、Python 侧默认值；这里确认这套形状
在 tenant_id + FORCE RLS 下读写正常，且 `KH_TABLE_CONV` 的替换机制能指到我们的类。
"""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import text
from sqlmodel import select

from learn_core.db.engine import reset_engine, session_scope
from learn_core.db.ktem import KtemConversation, KtemSettings
from learn_core.db.models import Tenant
from learn_core.tenancy.context import tenant_context

pytestmark = pytest.mark.skipif(
    os.getenv("LEARN_DATABASE_URL") is None,
    reason="需要 LEARN_DATABASE_URL 指向测试库",
)


@contextmanager
def _tenant():
    with session_scope() as session:
        tenant = Tenant(official_user_id=f"ktem-{uuid.uuid4().hex[:10]}")
        session.add(tenant)
        session.flush()
        tid = tenant.id
    yield tid
    with session_scope() as session:
        session.execute(text("DELETE FROM tenant WHERE id = :t"), {"t": tid})


def test_conversation_and_settings_roundtrip_per_tenant():
    reset_engine()
    with _tenant() as ta, _tenant() as tb:
        with tenant_context(ta):
            with session_scope() as session:
                conv = KtemConversation(
                    name="甲的第一课",
                    user="default",
                    data_source={"messages": [{"role": "user", "content": "什么是能量最小化"}]},
                )
                session.add(conv)
                session.add(KtemSettings(setting={"chat_model": "doubao-seed-1.6"}))
        with tenant_context(tb):
            with session_scope() as session:
                session.add(KtemConversation(name="乙的对话", data_source={"messages": []}))

        with tenant_context(ta):
            with session_scope() as session:
                convs = session.execute(select(KtemConversation)).scalars().all()
                assert [c.name for c in convs] == ["甲的第一课"]
                assert convs[0].data_source["messages"][0]["content"] == "什么是能量最小化"
                setting = session.execute(select(KtemSettings)).scalar_one()
                assert setting.setting["chat_model"] == "doubao-seed-1.6"

        with tenant_context(tb):
            with session_scope() as session:
                convs = session.execute(select(KtemConversation)).scalars().all()
                assert [c.name for c in convs] == ["乙的对话"]
                assert session.execute(select(KtemSettings)).scalars().all() == []


def test_json_column_update_is_visible_only_to_owner():
    reset_engine()
    with _tenant() as ta, _tenant() as tb:
        with tenant_context(ta):
            with session_scope() as session:
                conv = KtemConversation(name="改 JSON")
                session.add(conv)
                session.flush()
                conv.data_source = {"messages": [{"role": "assistant", "content": "ok"}]}
                conv_id = conv.id

        with tenant_context(tb):
            with session_scope() as session:
                assert session.get(KtemConversation, conv_id) is None

        with tenant_context(ta):
            with session_scope() as session:
                conv = session.get(KtemConversation, conv_id)
                assert conv is not None
                assert conv.data_source["messages"][0]["role"] == "assistant"


def test_kotaemon_can_be_pointed_at_our_tables():
    """KH_TABLE_CONV 用 dotted path 替换表类；这里只验证路径可解析。"""
    import importlib

    module_name, _, attr = "learn_core.db.ktem.KtemConversation".rpartition(".")
    cls = getattr(importlib.import_module(module_name), attr)
    assert cls is KtemConversation
