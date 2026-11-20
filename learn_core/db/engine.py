"""数据库引擎与会话。

关键点是事务钩子：每个事务开始时把当前租户写进 `app.tenant_id`，
行级安全策略据此过滤。没有租户上下文时不设置变量，
结果是读不到任何行、写入也被策略拒绝。
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from learn_core.config import get_settings
from learn_core.tenancy.context import current_tenant_or_none

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _apply_tenant(conn) -> None:
    tenant_id = current_tenant_or_none()
    if tenant_id is None:
        return
    conn.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            connect_args={"options": (
                f"-c lock_timeout={settings.db_lock_timeout} "
                f"-c statement_timeout={settings.db_statement_timeout}"
            )},
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle,
            future=True,
        )
        # 事务开始时写租户变量；`true` 表示只在本事务内生效。
        event.listen(_engine, "begin", _apply_tenant)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), expire_on_commit=False, class_=Session
        )
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """一个请求 / 一个任务用一次，出错回滚。"""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """测试用：丢弃缓存的引擎与工厂。"""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
