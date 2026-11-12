# 阶段 1 后端进展（2026-11-12）

阶段 0 把地基打好了（Postgres + pgvector、RLS、队列、嵌入服务、CI）。阶段 1 在这上面长出第一片真正的业务接口。目标是：**一个新租户从「登录官网」到「项目里能检索资料、能调模型」这条最短路全部打通**，其余页面按同样形状往上叠。

## 已经能跑通的链路

```
官网短票 ──▶ learn_api 复核 ──▶ 建/取租户 ──▶ 事务里设 app.tenant_id
                                                   │
        项目 CRUD / 检索 / 对话 / 资料索引 ◀────────┘
                     │                │
              嵌入服务 18090      模型网关（租约 + 事件 id + 记账）
                     │
              提交资料 → 202 + jobId → worker 索引 → job_progress → SSE 推给页面
```

本机用真实 worker + 真实嵌入服务跑过一次完整索引（1 块文本 / 1 条向量 / `job_progress.state=done`），脚本化的假实现只用于 CI。

## 这一片定下的几个细节

**索引任务放在 `io` 通道，不放 `cpu`。** 索引的耗时主要在嵌入 HTTP 和写库，放 `io` 才能和 CPU 密集的解析、渲染错峰；同租户同通道仍然串行（`lock = tenant:io`），避免一个用户连续拖十份资料把嵌入服务打满。

**事件 id 用每租户计数器，不用 sequence。** 租户是运行时建的，为每个租户建 sequence 会污染 schema；`llm_event_counter` 一行一个 `(tenant, kind)`，`INSERT ... ON CONFLICT DO UPDATE ... RETURNING` 天然原子。业务重试取新号（`ln-j000042`），传输重试复用同号（`ln-j000042-1-2`）——网关按 id 幂等扣费，这个区分直接决定账能不能对上。

**租约写表，不写进程内信号量。** API 和 worker 是不同进程，只有数据库能同时约束两边。租约带 `expires_at`，进程崩了会自动过期被下一次 `acquire` 清掉，不会永久占坑。交互通道每租户 2、后台 1，防止批量生成把页面挤死。

**SSE 用 1 秒轮询 `job_progress`，不做 LISTEN/NOTIFY。** 多进程部署不需要粘性会话，代价是每个订阅者一秒一次查询；规模上来再换，换的时候只改 `routers/jobs.py` 一个文件。

**检索的降级是显式的。** 嵌入服务挂掉时 `/search` 返回 `degraded: true` 的纯全文结果，而不是 500 —— 资料检索在模型不可用时仍然应该能用。

## 接口清单（都是 `/official/learn-everything/api/v2` 下的相对路径）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET/POST | `/projects` | 列表 / 新建 |
| GET/PATCH/DELETE | `/projects/{id}` | 单个项目 |
| POST | `/projects/{id}/sources` | 提交资料文本，202 + jobId |
| POST | `/projects/{id}/chat` | 一次对话，返回 eventId |
| POST | `/search` | 向量 + 全文混合检索（RRF） |
| GET | `/jobs/{id}` | 任务状态 |
| GET | `/jobs/{id}/events` | SSE 进度流 |
| GET/POST | `/projects/{id}/nodes` | 学习节点列表 / 新建 |
| PATCH/DELETE | `/nodes/{id}` | 节点更新 / 删除 |
| POST/GET | `/projects/{id}/progress` | 记录 / 列出学习进度 |
| GET | `/projects/{id}/summary` | 项目概览（节点状态、掌握率、学时） |
| POST | `/cards` | 新建复习卡片 |
| GET | `/projects/{id}/cards` | 项目下卡片 |
| GET | `/review/due` | 到期待复习卡片 |
| POST | `/review/{id}` | 评分 1..4，推进排程 |

错误体统一 `{"error":{"code","message","retryable","retryAfterSeconds"}}`，错误码见 `learn_api/errors.py`。

## 测试

`pytest tests/learn_core -q` → 34 passed。覆盖：租户隔离（读写双向）、RLS 全表强制、切块与重切块清理、混合检索与降级、索引任务、对话事件 id 递增、网关 429 记账与租约释放、短票缺失/无效、跨租户读不到别人数据。

## 还没做

- 迁移工具：从旧 SQLite/Chroma 按账号搬进新表，需要 `migration_run` / `migration_orphan` 的完整实现；
- 复习排程目前是阶梯间隔（`learn_core/review/scheduler.py`），FSRS 参数化待做；
- 测验、路径生成等学习业务的 service 层与接口；
- 前端（Vite + React，9 个页面）；
- 生产部署清单：新机器规格、网关并发份额、异地备份；
- 分支 `feat/learn-core-phase0` 尚未开 PR（等用户确认由谁创建）。
