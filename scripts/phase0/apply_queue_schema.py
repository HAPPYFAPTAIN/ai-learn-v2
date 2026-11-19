"""把 Procrastinate 的表建到库里，并给应用角色授权。

只做一次性 bootstrap：生产上由发布流程调用，本地由 CI / dev 脚本调用。
Procrastinate 自己的迁移表（procrastinate_jobs 等）不归 Alembic 管，
避免两套迁移互相打架。
"""

from __future__ import annotations

import argparse

from sqlalchemy import create_engine, text

from learn_core.config import get_settings
from procrastinate import App, PsycopgConnector

APP_ROLE = "learn_app"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner-url", default=None, help="建表用的超级用户/所有者连接串")
    args = parser.parse_args()

    settings = get_settings()
    owner_url = args.owner_url or settings.database_owner_url.replace("+psycopg", "")

    engine = create_engine(owner_url.replace("postgresql://", "postgresql+psycopg://"), future=True)
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT to_regclass('public.procrastinate_jobs')")).scalar()
    if exists is None:
        app = App(connector=PsycopgConnector(conninfo=owner_url))
        with app.open():
            app.schema_manager.apply_schema()

    with engine.begin() as conn:
        conn.execute(text("GRANT USAGE ON SCHEMA public TO " + APP_ROLE))
        conn.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "
                + APP_ROLE
            )
        )
        conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO " + APP_ROLE))
    print("procrastinate schema ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
