# 中等规模 SaaS 多租户隔离：选型与性能（FastAPI + PostgreSQL，单机 50–200 并发）

## 0. 结论
50–200 用户是「单库 + 共享表 + tenant_id + RLS 兜底」的甜蜜区。这个量级没人因性能在三种模式间切换；切换动机是合规或「单租户可独立备份/恢复」。分区和 PgBouncer 现在都还不该上。

## 1. 三种模式的取舍与真实切换点

- **共享表 + tenant_id**：资源池化（共享 shared_buffers/连接/进程）、一次 DDL 全租户生效、连接数可控。代价是隔离全靠代码自觉。
- **schema-per-tenant**：单租户可独立 dump/restore/删库，靠 `search_path` 切租户。代价是 DDL 要遍历 N 个 schema、`pg_class`/`pg_attribute` 膨胀、连接池必须重置 `search_path`。
- **database-per-tenant**：最强隔离，最贵的运维。

Citus/Microsoft 官方文档给的判据很直接：**5 个或 50 个租户、单库遇到扩展瓶颈时，可以一租户一库；上千租户才该在 `tenant_id` 上分片**。它点名 database-per-tenant 的真正杀手不是性能而是运维——「给 10K 租户改表，改到第 5000 个失败怎么办」。另一条有用口径：数据量在几十 GB 时，纵向扩硬件就够了。

[MVP Factory](https://mvpfactory.io/blog/postgresql-multitenancy-without-row-level-security-partition-based-isolation) 的经验上限（咨询博客，非基准）：共享表 ~500 租户，schema-per-tenant ~1,000–2,000，一租户一分区 ~5,000–10,000。

来源：[Citus: Design your SaaS database for scale](https://learn.microsoft.com/en-us/postgresql/citus/designing-saas)

## 2. 真实项目到底用没用 RLS

| 项目 | 用 PG RLS？ | 实际做法 |
|---|---|---|
| Supabase | 是，平台核心机制 | 策略 + `auth.uid()`，有官方性能 KB（见 §3） |
| エムスリー m3 | **是，生产环境** | 共享表 + `current_setting('app.tenant_id')` 策略 |
| Langfuse | 否 | 应用层强制 `project_id` 过滤；traces 在 ClickHouse，`WHERE project_id` 必填 |
| GitLab | 否，评估中 | 为 Cells 的 Org 隔离研究 RLS，尚未落地（未查到稳定直链，故不引用） |
| Cal.com | 否 | Prisma 模型 + PBAC（PR #21296） |
| Chatwoot | 否 | Rails 层 `account_id` 作用域 |
| Metabase | 否 | 行级安全是应用层把表替换成按 user attribute 过滤的视图，对 native SQL 无效 |
| Twenty | 否 | 它叫 "RLS" 的是 Row Level Permission **Predicate**，应用层谓词渲染成 SQL filter |

唯一找到的完整可抄生产案例是 [m3 tech blog（2025-03-28）](https://www.m3tech.blog/entry/2025/03/28/180000)：

```sql
ALTER TABLE my_table ENABLE ROW LEVEL SECURITY;
CREATE POLICY my_table__tenant_id__policy ON my_table
  USING (tenant_id = current_setting('app.tenant_id')::integer);
-- 每个请求：BEGIN; SET LOCAL app.tenant_id = '1234'; ... COMMIT;
```

他们踩的坑：切到 RLS 后查询变慢，靠「`tenant_id` + 检索字段」复合索引救回。结论是要让 tenant_id 参与索引设计。

**BYPASSRLS 相关的三个必知坑**（[PG 官方](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)）：表 owner 默认绕过策略，必须 `ALTER TABLE ... FORCE ROW LEVEL SECURITY`；superuser 和 `BYPASSRLS` 角色永远绕过；开了 RLS 但没策略 = 默认全拒。另外外键/唯一约束检查总是绕过 RLS。

## 3. RLS 的性能代价（有数字）

[Supabase 官方 KB](https://supabase.com/kb/troubleshooting/rls-performance-and-best-practices-Z5Jjwv) 在 100K 行表上实测：

- `auth.uid() = user_id` 无索引：**171ms**；建索引后 **<0.1ms**（官方称 100x+）
- 把函数包成 `(select auth.uid()) = user_id`：179ms → **9ms**（initPlan 缓存，避免逐行调用）
- `has_role() = role`：178,000ms → **12ms**
- `team_id = ANY(user_teams())` 在 1M 行表上**无论有无索引都 >2 分钟**；改成 `team_id = ANY(ARRAY(select user_teams()))` + 索引后 **2–3ms**
- 策略加 `TO authenticated`：170ms → <0.1ms（anon 直接被排除）

可迁移的结论：`current_setting` 本身不贵，**贵的是策略里的函数被逐行求值、以及策略列没进索引**。所以 `(select current_setting('app.tenant_id')::int)` 值得抄，`tenant_id` 必须是复合索引首列。官方还明确建议：**不要靠 RLS 做过滤，只当安全网**，应用层照样带 tenant 条件。

## 4. 连接池：200 并发怎么定

200 在线用户 ≠ 200 并发 SQL，按 5–10% 估算峰值也就 10–20 个活跃语句。SQLAlchemy 默认 `pool_size=5`、`max_overflow=10`；`create_async_engine` 用 `AsyncAdaptedQueuePool`（`QueuePool` 不兼容 asyncio）。参考配置：**每 worker `pool_size=10, max_overflow=5`，4 个 worker 上限 60 条连接**，PG 默认 `max_connections=100`，给迁移/监控留余量。

**PgBouncer 不是必须**：单机单应用自己的池已经够用，它的价值在多实例/多语言客户端/serverless。

真上 PgBouncer 时的冲突（[官方 features 表](https://www.pgbouncer.org/features.html)、[config](https://www.pgbouncer.org/config.html)）：transaction pooling 下 `SET`/`RESET` 兼容性为 **"Never"**，租户 GUC 只能用 **`SET LOCAL` 且必须在显式事务内**，绝不能用普通 `SET`；自定义 GUC 不在 `track_extra_parameters` 默认列表（默认只有 application_name、client_encoding、DateStyle、TimeZone、search_path 等），普通 `SET` 会泄漏给下一个客户端。默认值 `max_client_conn=100`、`default_pool_size=20`。

## 5. 大表策略：什么时候分区

PG 官方口径：分区收益「only when a table would otherwise be very large」，经验法则是**表超过数据库服务器物理内存**。分区过多会导致 planning 时间与每个 session 的内存上升；官方还建议若未来从小租户变多，用 `HASH` 而不是一租户一个 `LIST` 分区。限制：分区表的主键/唯一约束必须包含分区键，且不能 `CREATE INDEX CONCURRENTLY`（需 `ON ONLY` + 逐分区 + `ATTACH PARTITION`）。

真实案例 [Toggl(PGConf.EU 2026)](https://www.postgresql.eu/events/pgconfeu2026/sessions/session/8016-workspace_id-n-war-stories-on-building-resilience-through-application-level-sharding/)：多年用 `PARTITION BY HASH (workspace_id)` 跑多租户分析管道，最终放弃、转应用层分片，根因是 ingest/transform 串行导致一个 noisy tenant 拖垮全体——**分区的收益不在隔离，租户隔离别指望分区**。

结论：50–200 租户、单表几十 GB 以内，不要分区。

## 6. 值得抄的 5 条

1. 策略里把 `current_setting` 包进 `(select ...)`，利用 initPlan 缓存避免逐行求值——[Supabase KB](https://supabase.com/kb/troubleshooting/rls-performance-and-best-practices-Z5Jjwv)。
2. RLS 只当安全网，应用层（SQLAlchemy session 级 hook / 全局 where）仍强制带 `tenant_id`——同上。
3. 迁移用 owner 角色、运行用非 owner 角色，并对业务表 `FORCE ROW LEVEL SECURITY`，否则 owner 账号静默绕过——[PG 文档](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)。
4. 备份/分析脚本里 `SET row_security = off`，让被策略过滤的查询**直接报错**而不是静默少行——同上，专治「RLS 泄露了但没人发现」。
5. 上 RLS 前先做一次策略 on/off 的 `EXPLAIN` 对比（Supabase 那份 KB 就是这么做出来的），把「每表策略 + tenant_id 首列索引」当成可回归的基线。

## 未查到
- 50–200 用户量级的公开基准（只有经验博客，无实测数据）。
- Langfuse / Cal.com / Chatwoot 关于「拒绝 RLS」的官方设计文档，只能从代码与 issue 反推。
