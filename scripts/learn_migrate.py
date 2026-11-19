#!/usr/bin/env python3
"""按账号迁移旧数据。

    python scripts/learn_migrate.py --db /path/to/sql.db --user tianyiyang
    python scripts/learn_migrate.py --db ... --user tianyiyang --dry-run

`--user` 是官网账号（official_user_id）。租户不存在时会先建出来。
脚本可重复执行：每次先删该租户已导入的行，再整份导入；孤儿行进
`migration_orphan`，不静默丢弃。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from learn_core.db.engine import session_scope  # noqa: E402
from learn_core.tenancy.context import tenant_context  # noqa: E402
from learn_core.tenancy.service import get_or_create_tenant  # noqa: E402
from learn_migrate.legacy_import import LegacyDB, import_tenant  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="迁移一个账号的旧数据")
    parser.add_argument("--db", required=True, help="旧 sql.db 路径")
    parser.add_argument("--user", required=True, help="官网账号 official_user_id")
    parser.add_argument("--source", default="sql.db", help="记录在 migration_run.source")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    parser.add_argument("--scan", action="store_true", help="只列出旧库有哪些表")
    args = parser.parse_args(argv)

    legacy = LegacyDB(args.db)
    if args.scan:
        print(json.dumps({"tables": sorted(legacy.tables())}, ensure_ascii=False, indent=2))
        return 0

    with session_scope() as session:
        tenant = get_or_create_tenant(session, args.user)
        tenant_id = tenant.id

    with tenant_context(tenant_id):
        with session_scope() as session:
            report = import_tenant(
                session,
                legacy=legacy,
                tenant_id=tenant_id,
                source=args.source,
                dry_run=args.dry_run,
            )

    print(json.dumps({"tenantId": str(tenant_id), "dryRun": args.dry_run, **report.as_dict()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
