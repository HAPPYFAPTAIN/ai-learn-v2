"""旧 SQLite → 新表：主键重分配、孤儿入库、可重跑。"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid

import pytest
from sqlalchemy import text

from learn_core.db.engine import reset_engine, session_scope
from learn_core.db.models import Tenant
from learn_core.tenancy.context import tenant_context
from learn_migrate.legacy_import import LegacyDB, import_tenant

pytestmark = pytest.mark.skipif(
    os.getenv("LEARN_DATABASE_URL") is None,
    reason="需要 LEARN_DATABASE_URL 指向测试库",
)


def _legacy_db(tmp_path):
    path = tmp_path / "sql.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE le_project (id INTEGER PRIMARY KEY, user_id TEXT, title TEXT,
                                     topic TEXT, background TEXT, goal TEXT, weekly_hours REAL,
                                     roadmap_json TEXT, status TEXT, created_at TEXT);
            CREATE TABLE le_knode (id INTEGER PRIMARY KEY, project_id INTEGER, code TEXT,
                                   title TEXT, description TEXT, stage TEXT, est_hours REAL,
                                   difficulty REAL, mastery REAL, status TEXT, content_version INTEGER);
            CREATE TABLE le_quiz (id INTEGER PRIMARY KEY, project_id INTEGER, user_id TEXT,
                                  node_id INTEGER, title TEXT, quiz_type TEXT,
                                  scope_node_ids TEXT, created_at TEXT);
            CREATE TABLE le_card (id INTEGER PRIMARY KEY, project_id INTEGER, node_id INTEGER,
                                  user_id TEXT, front TEXT, back TEXT, card_type TEXT,
                                  stability REAL, difficulty REAL, state TEXT);
            """
        )
        conn.execute(
            "INSERT INTO le_project VALUES (1,'default','旧项目','主题','','',10.0,?, 'active','2026-01-01')",
            (json.dumps({"weeks": 4}),),
        )
        conn.execute(
            "INSERT INTO le_knode VALUES (10,1,'K1','节点一','', 'stage1', 2.0, 1.0, 0.0, 'todo', 1)"
        )
        conn.execute(
            "INSERT INTO le_knode VALUES (11,1,'K2','节点二','', 'stage1', 2.0, 1.0, 0.0, 'todo', 1)"
        )
        conn.execute("INSERT INTO le_quiz VALUES (5,1,'default',10,'小测','info',?,'2026-01-02')", (json.dumps([10, 11]),))
        conn.execute("INSERT INTO le_card VALUES (7,1,10,'default','正面','背面','basic',1.0,5.0,'new')")
        conn.execute("INSERT INTO le_card VALUES (8,1,999,'default','孤儿','孤儿','basic',1.0,5.0,'new')")
    return path


def test_import_remaps_ids_and_keeps_orphans(tmp_path):
    reset_engine()
    path = _legacy_db(tmp_path)
    legacy = LegacyDB(path)

    with session_scope() as session:
        tenant = Tenant(official_user_id=f"mig-{uuid.uuid4().hex[:8]}")
        session.add(tenant)
        session.flush()
        tid = tenant.id

    with tenant_context(tid):
        with session_scope() as session:
            report = import_tenant(session, legacy=legacy, tenant_id=tid)
        assert report.tables["le_project"] == {"legacy": 1, "imported": 1}
        assert report.tables["le_card"] == {"legacy": 2, "imported": 1}
        assert report.orphans == {"le_card": 1}

        with session_scope() as session:
            project_id = session.execute(text("SELECT id FROM le_project")).scalar_one()
            nodes = session.execute(text("SELECT id, code FROM le_knode ORDER BY code")).all()
            cards = session.execute(text("SELECT node_id FROM le_card")).all()
            quiz_scope = session.execute(text("SELECT scope_node_ids FROM le_quiz")).scalar_one()
            orphans = session.execute(text("SELECT table_name, row FROM migration_orphan")).all()
            run = session.execute(text("SELECT status FROM migration_run")).scalars().all()

        assert project_id not in (1,), "主键必须重新分配"
        new_node_ids = {code: nid for nid, code in nodes}
        assert cards[0][0] == new_node_ids["K1"], "子表引用要跟着换"
        assert quiz_scope == [new_node_ids["K1"], new_node_ids["K2"]]
        assert orphans and orphans[0][0] == "le_card" and orphans[0][1]["id"] == 8
        assert run == ["success"]

        # 重跑：删掉已导入的行再导，数量不能涨
        with session_scope() as session:
            import_tenant(session, legacy=legacy, tenant_id=tid)
        with session_scope() as session:
            counts = session.execute(
                text("SELECT (SELECT count(*) FROM le_knode), (SELECT count(*) FROM le_card), (SELECT count(*) FROM migration_orphan)")
            ).one()
        assert counts == (2, 1, 1)
    reset_engine()
