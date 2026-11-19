"""把旧单进程数据按账号搬进新库。

旧的 `data/user_data/sql.db` 是每个账号一份 SQLite，主键从 1 开始；
搬进共享库后主键会撞车，所以每条记录都重新分配 id，并维护
「旧 id → 新 id」的映射改写子表引用。

孤儿行（旧库没开外键，一定存在）不静默删除：先记进 `migration_orphan`，
再由人决定丢弃还是补录。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlmodel import Session

from learn_core.db.models import MigrationOrphan, MigrationRun


@dataclass(frozen=True)
class TableSpec:
    name: str
    # 子表外键列 → 父表名；写入前把旧 id 换成新 id
    parents: dict[str, str] = field(default_factory=dict)
    json_columns: tuple[str, ...] = ()
    # jsonb 数组列，元素是旧 id，需要整体重映射
    id_array_columns: tuple[str, ...] = ()
    array_parent: str | None = None


SPECS: tuple[TableSpec, ...] = (
    TableSpec("le_project", json_columns=("roadmap_json",)),
    TableSpec("le_knode", parents={"project_id": "le_project"}),
    TableSpec("le_knode_collection"),
    TableSpec("le_kedge", parents={"project_id": "le_project", "source_id": "le_knode", "target_id": "le_knode"}),
    TableSpec("le_card", parents={"project_id": "le_project", "node_id": "le_knode"}),
    TableSpec("le_reviewlog", parents={"card_id": "le_card"}),
    TableSpec(
        "le_quiz",
        parents={"project_id": "le_project", "node_id": "le_knode"},
        id_array_columns=("scope_node_ids",),
        array_parent="le_knode",
    ),
    TableSpec("le_quiz_question", parents={"quiz_id": "le_quiz", "node_id": "le_knode"}),
    TableSpec("le_quiz_attempt", parents={"question_id": "le_quiz_question"}),
    TableSpec("le_progress", parents={"project_id": "le_project", "node_id": "le_knode"}),
    TableSpec("le_task", parents={"project_id": "le_project", "node_id": "le_knode"}),
    TableSpec("le_note", parents={"project_id": "le_project", "node_id": "le_knode"}),
    TableSpec("le_annotation", parents={"project_id": "le_project", "node_id": "le_knode"}),
    TableSpec("le_resource", parents={"project_id": "le_project", "node_id": "le_knode"}),
    TableSpec("le_gate", parents={"project_id": "le_project", "node_id": "le_knode"}),
    TableSpec("le_daily_report", parents={"project_id": "le_project"}),
)

# 旧库里 FSRS 状态是字符串，新表用整数。
CARD_STATE = {"new": 0, "learning": 1, "review": 2, "relearning": 3}

# 只在新库里存在、不来自旧库的列。
SERVER_COLUMNS = {"tenant_id", "created_at", "updated_at"}
SKIP_COLUMNS = {"id"}


@dataclass
class ImportReport:
    tables: dict[str, dict[str, int]] = field(default_factory=dict)
    orphans: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"tables": self.tables, "orphans": self.orphans}


class LegacyDB:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)

    def tables(self) -> set[str]:
        with closing(sqlite3.connect(self.path)) as conn:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {r[0] for r in rows}

    def rows(self, table: str) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(f'SELECT * FROM "{table}"').fetchall()]


def _coerce(value: Any, *, as_json: bool) -> Any:
    if value is None:
        return None
    if as_json and isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _columns(session: Session, table: str) -> set[str]:
    from sqlalchemy import text

    rows = session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t"
        ),
        {"t": table},
    ).scalars().all()
    return set(rows)


def import_tenant(
    session: Session,
    *,
    legacy: LegacyDB,
    tenant_id: UUID,
    source: str = "sql.db",
    dry_run: bool = False,
) -> ImportReport:
    """导入一个账号；重跑前先删掉该租户已导入的行。"""
    from sqlalchemy import delete, text

    report = ImportReport()
    existing = legacy.tables()

    run = MigrationRun(tenant_id=tenant_id, source=source, status="running")
    if not dry_run:
        session.add(run)
        session.flush()
        for spec in reversed(SPECS):
            session.execute(text(f'DELETE FROM "{spec.name}" WHERE tenant_id = :tid'), {"tid": tenant_id})
        session.execute(text("DELETE FROM migration_orphan WHERE tenant_id = :tid"), {"tid": tenant_id})

    id_maps: dict[str, dict[int, int]] = {}

    for spec in SPECS:
        if spec.name not in existing:
            continue
        target_cols = _columns(session, spec.name)
        mapping: dict[int, int] = {}
        inserted = 0
        for row in legacy.rows(spec.name):
            payload: dict[str, Any] = {}
            orphan_reason: str | None = None

            for key, value in row.items():
                if key in SKIP_COLUMNS or key not in target_cols:
                    continue
                if key in SERVER_COLUMNS and key != "created_at":
                    continue
                if key in spec.json_columns:
                    # 走 raw SQL，jsonb 需要字符串；None 保持 NULL。
                    parsed = _coerce(value, as_json=True)
                    payload[key] = None if parsed is None else json.dumps(parsed, ensure_ascii=False)
                    continue
                if key in spec.parents:
                    parent = spec.parents[key]
                    new_id = id_maps.get(parent, {}).get(value)
                    if value is not None and new_id is None:
                        orphan_reason = f"{key}={value} 在 {parent} 中不存在"
                        break
                    payload[key] = new_id
                    continue
                if spec.name == "le_card" and key == "state" and isinstance(value, str):
                    value = CARD_STATE.get(value, 0)
                payload[key] = value

            if orphan_reason:
                report.orphans[spec.name] = report.orphans.get(spec.name, 0) + 1
                if not dry_run:
                    session.add(MigrationOrphan(tenant_id=tenant_id, table_name=spec.name, row=row))
                continue

            if spec.id_array_columns and spec.array_parent:
                for col in spec.id_array_columns:
                    if col in row and col in target_cols:
                        old = row[col]
                        values = json.loads(old) if isinstance(old, str) else (old or [])
                        mapped = [id_maps.get(spec.array_parent, {}).get(v) for v in values]
                        payload[col] = [v for v in mapped if v is not None]

            payload["tenant_id"] = tenant_id
            if dry_run:
                # 演练时不写库，但要给子表一个非空映射，否则统计会误报孤儿。
                if "id" in row:
                    mapping[row["id"]] = -int(row["id"])
                inserted += 1
                continue

            cols = ", ".join(f'"{c}"' for c in payload)
            vals = ", ".join(f":{c}" for c in payload)
            statement = f'INSERT INTO "{spec.name}" ({cols}) VALUES ({vals})'
            if "id" in target_cols:
                statement += " RETURNING id"
                new_id = session.execute(text(statement), payload).scalar_one()
            else:
                session.execute(text(statement), payload)
                new_id = None
            if "id" in row:
                mapping[row["id"]] = new_id
            inserted += 1

        id_maps[spec.name] = mapping
        report.tables[spec.name] = {"legacy": len(legacy.rows(spec.name)), "imported": inserted}

    if not dry_run:
        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        run.report = report.as_dict()
    return report
