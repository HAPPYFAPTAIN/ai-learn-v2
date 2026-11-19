"""进程配置。

只从环境变量 / .env 读取，不在 import 时连接任何外部服务。
租户相关的值（账号、目录）一律不放在这里，统一由 TenantContext 提供。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LEARN_", env_file=".env", extra="ignore"
    )

    # 应用角色连接串：受行级安全约束，没有建表权限。
    database_url: str = (
        "postgresql+psycopg://learn_app:app@127.0.0.1:5432/learn_dev"
    )
    # 迁移角色连接串：只给 Alembic 用。
    database_owner_url: str = (
        "postgresql+psycopg://learn_owner:owner@127.0.0.1:5432/learn_dev"
    )

    # 连接池：每个 API 进程 10 个，溢出 5 个。
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_recycle: int = 1800

    # 官网内部密钥：nginx 转发时注入，API 先校验它再复核短票。
    internal_secret: str = ""
    # Exact public origin, e.g. https://example.com; never inferred from forwarded headers.
    public_origin: str = ""
    # 官网鉴权子请求地址，用于 API 侧二次复核。
    authorize_url: str = "http://127.0.0.1:18030/api/v1/console/learn-everything/authorize"

    # 文件存储根目录：{files_root}/{tenant_id}/{kind}/{sha256}
    files_root: str = "/tmp/learn-everything/files"

    # 本机嵌入服务
    embed_url: str = "http://127.0.0.1:18090"
    embed_dim: int = 384

    # 官网模型网关
    gateway_url: str = "http://127.0.0.1:18040/v1"
    gateway_product_key: str = ""
    gateway_read_timeout: float = Field(default=120, gt=0, le=600)
    gateway_concurrency: int = 16
    tenant_interactive_leases: int = 2
    background_llm_concurrency: int = 6

    # 任务队列
    procrastinate_dsn: str = "postgresql://learn_app:app@127.0.0.1:5432/learn_dev"

    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
