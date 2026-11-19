# 阶段 0 验证报告

日期：2026-11-12
分支：`feat/learn-core-phase0`
对应规划：`.project-to-act/docs/learn-multitenant-plan.md` 阶段 0

## 一、这一阶段交付了什么

新的多租户底座放在仓库根目录，不与旧的「每账号一个进程」代码混在一起：

| 路径 | 内容 |
| --- | --- |
| `learn_core/config.py` | 进程配置，全部来自 `LEARN_*` 环境变量 |
| `learn_core/tenancy/` | 请求级租户上下文；`current_tenant()` 缺失即报错 |
| `learn_core/db/` | 引擎、会话、28 张表（平台表 + 15 张 `le_*` + RAG + Kotaemon 三表） |
| `learn_core/storage/files.py` | 按租户隔离的文件存储，路径穿越与符号链接防护 |
| `learn_core/jobs/` | Procrastinate 应用、通道锁、僵死任务回收 |
| `learn_core/rag/settings.py` | 检索时必须使用的 ANN 参数 |
| `learn_embed/` | 本机嵌入服务（MiniLM，384 维，OpenAI 兼容） |
| `migrations/` | Alembic 基线：建表 + 强制行级安全 + 三角色授权 |
| `scripts/phase0/` | 三条验证的可重复脚本 |
| `tests/learn_core/` | 7 条守卫测试 |

数据访问的硬约束：应用角色 `learn_app` 没有建表权限；所有租户表
`ENABLE` + `FORCE ROW LEVEL SECURITY`，策略统一为
`tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid`。
事务开始时由引擎填入 `app.tenant_id`，忘记设置上下文时读到的是 0 行，而不是全表。

## 二、三条验证的实测结果

### 验证一：Kotaemon 的表能在行级安全下工作

Kotaemon 的表用字符串主键、JSON 列、Python 侧默认值，和我们的 `le_*`
形状不同。它允许通过 `KH_TABLE_CONV` / `KH_TABLE_SETTINGS` /
`KH_TABLE_ISSUE_REPORT` 换成任意 SQLModel 子类，所以新表直接带上
`tenant_id`，不需要改子模块一行代码。

实测（`tests/learn_core/test_ktem_tables.py`）：

- 会话与设置按租户隔离，JSON 列读回内容一致；
- 修改 JSON 后只有本租户可见，另一租户 `session.get()` 返回 `None`；
- dotted path 能被解析到我们的类，可直接写进 `KH_TABLE_CONV`。

### 验证二：队列语义

实现在 `learn_core/jobs/`，验证脚本 `scripts/phase0/validate_queue.py`：

1. **去重**：同一 `queueing_lock` 的第二个在途任务被拒绝，抛 `AlreadyEnqueued`；
2. **串行与公平**：`lock = 租户:通道` 时，甲租户 3 个任务的 start/end 严格交替、不重叠；乙租户的第一个任务在甲租户最后一个任务结束前开始，说明不同租户并行；
3. **崩溃回收**：Procrastinate 只提供「查僵死任务」的接口，不会自动重排，所以补了 `learn_core/jobs/reaper.py`。把任务标成 `doing` 并挂到一个心跳过期 10 分钟的假 worker 上，回收器重排后 worker 重新执行成功。

### 验证三：pgvector 召回

`scripts/phase0/validate_vector.py`，20 400 行向量、384 维，小租户只占 400 行：

| 设置 | top-10 召回 | 延迟 |
| --- | --- | --- |
| 默认 `ef_search=40` | 10% | 3.3 ms |
| `iterative_scan=relaxed_order`, `ef_search=200` | 70% | 10.5 ms |
| `iterative_scan=strict_order`, `ef_search=400`, `max_scan_tuples=40000` | **100%** | 2.9 ms |

结论写进了 `learn_core/rag/settings.py`：检索必须在事务内设置这三个参数，
否则会出现「库里明明有资料，却检索不到」这类最难排查的问题。

### 嵌入服务

`learn_embed/` 用 fastembed + all-MiniLM-L6-v2（384 维，归一化）。
本机实测：模型加载 12 s；8 并发、每请求 16 段文本时 p50 44 ms、p95 53 ms，
单进程吞吐约 360 段/秒。按 200 人在线、单人每分钟几次检索估算，
一个 CPU 进程足够，不需要 GPU。

## 三、踩过的坑

1. **自定义 GUC 在事务结束后变成空串**，不是 `NULL`。策略里直接
   `current_setting(...)::uuid` 会报 `invalid input syntax for type uuid: ""`，
   必须套 `NULLIF(..., '')`。这个坑在本地重现后再写进迁移，避免上线才发现。
2. **`vector` / `pg_trgm` 扩展只有超级用户能建**，迁移角色 `learn_owner` 不行；
   部署流程里要先由 DBA 建扩展。
3. **HuggingFace 直连超时**，`fastembed` 通过 `HF_ENDPOINT=https://hf-mirror.com` 下载。
4. **Procrastinate 3.x 的 API 与旧文档不同**：`app.defer` 已移除，
   要用 `task.configure(lock=..., queueing_lock=...).defer(**args)`；
   且 defer 必须在 `app.open()` 上下文里。

## 四、还没做的（阶段 1 起）

- API 骨架：`/api/v2/*`、SSE、鉴权与短票复核、错误码统一；
- 把 `learning_ext` 的 15 张表读写切到 `learn_core`（旧代码仍在跑，未改一行）；
- 模型网关客户端、`model_call` 写账、租约表；
- Kotaemon 的向量库/文档库适配（`KH_VECTORSTORE` / `KH_DOCSTORE` 的 Postgres 实现）；
- 前端 Vite + React 工程；
- 生产机评估：现有 7.4 GB 内存放不下「旧进程 + Postgres」，需要 8 核 32 GB 新机。

## 五、本地怎么跑

```sh
brew services start postgresql@17
psql -d learn_dev -c "CREATE EXTENSION IF NOT EXISTS vector"
export LEARN_DATABASE_URL=postgresql+psycopg://learn_app:app@127.0.0.1:5432/learn_dev
export LEARN_DATABASE_OWNER_URL=postgresql+psycopg://learn_owner:owner@127.0.0.1:5432/learn_dev

PYTHONPATH=. .venv/bin/alembic upgrade head
PYTHONPATH=. .venv/bin/python scripts/phase0/apply_queue_schema.py
PYTHONPATH=. .venv/bin/python -m pytest tests/learn_core -q
PYTHONPATH=. .venv/bin/python scripts/phase0/validate_queue.py
PYTHONPATH=. .venv/bin/python scripts/phase0/validate_vector.py
```

CI：`.github/workflows/learn-core.yml`，带 `pgvector/pgvector:pg17` 服务容器，
跑同一组测试与脚本。
