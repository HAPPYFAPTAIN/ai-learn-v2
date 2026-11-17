# 8d0500a 后端接手与本地验证

核对日期：2026-11-18。基线固定为 `8d0500a4fc14ec7716d5810cd0058fadae076eb6`，修复分支为 `codex/backend-handoff-8d0500a`。

本轮复用已有 React / FastAPI / learn_core 实现，完成代码修复、接口同步和独立测试库验证。尚未完成真实官网登录、收费模型/积分联调、Linux 候选部署或 2GB 主机验收。

## 需求与旧版规则依据

- 用户已确认的 `docs/plans/2026-11-17-frontend-backend-alignment.md`（原检出中的未提交规划文件，本轮保留原样）；核心目标是一个官网账号对应私人租户，先用新数据验证核心闭环。
- 旧版 `learning_ext/progress/service.py` 的掌握度权重：测验 0.4、记忆 0.3、进度 0.3；阅读完成不能直接写入 100% 掌握度。
- 旧版 `learning_ext/fsrs_review/service.py` 与新版 FSRS 6.3.1 对照；保留 UTC 排期、实际 FSRS 算法、日志与掌握度联动。
- 路线结构/依赖、数值章节排序、已有教材保护、测验判分和问答规则沿用 `migration-audit.md` 记录的来源，依靠现有对应回归核对，没有另写一套业务服务。
- 旧 Gradio 与只读 `kotaemon` 未改动；本轮没有迁移或改写旧用户数据。

## Standards

此轴按仓库的调用者管理事务、租户隔离和模型事件规范核对，共确认并修复 3 类实现问题。

| 问题及影响 | 修复 | 验证证据 |
| --- | --- | --- |
| 文本来源索引通过另一连接先入队，业务事务尚未提交；回滚后仍可能留下任务 | `enqueue_index(session, ...)` 与 `job_progress` 共用事务；去重键包含租户、索引和来源 | 独立观察连接在提交前看不到队列/进度；请求回滚后两者都不存在；已有真实索引 worker 测试通过 |
| worker 崩溃恢复用队列重试次数重新生成计费事件，可能让同一调用变成新事件 | 持久化逻辑 `eventAttempt` 和模型消息快照；未知结果/崩溃重放使用相同事件与输入，明确可重试 HTTP 拒绝才推进逻辑事件 | HTTP 成功后、结果保存前注入进程退出，再以新队列次数执行，事件头与请求体逐字一致；已完成任务仍直接返回 |
| 混合检索最后合并漏掉索引过滤，相同来源/块 ID 可混入其他索引文本 | 最终查询同时限制当前 `index_id` 并明确排名条件分组 | 同租户两个索引使用相同块 ID，只返回指定索引；原租户隔离回归通过 |

消息快照仅保存在后台任务中用于恢复，不再通过任务轮询或 SSE 返回，避免每次发送完整提示词。数据库快照不会因序列化被修改，已用 API 与事件流回归验证。此机制只验证发送的事件与输入一致，不能替代上游真实计费幂等验收。

## Spec

此轴按完成/掌握度分离、跨账号隔离、持久化与重复提交要求核对，共确认并修复 4 类业务问题。

| 问题及影响 | 修复 | 验证证据 |
| --- | --- | --- |
| 点击“已学完”直接写 `mastery=1`，统计又把全部 done 计为掌握 | PATCH 禁止客户端写 mastery；done 保留为阅读完成，掌握度由证据计算；新增完成统计，前端同步 | 仅完成阅读得到 0.3；新会话仍为 done/0.3；加入测验与记忆证据后可达 1 且保留完成；前端提交仅有 status |
| 复习允许省略 expectedReps，重复提交可重复累计；预加载 ORM 卡片还可能保留旧计数 | expectedReps 必填且非空；取行锁时刷新对象，再比对数据库计数 | 缺失/空值拒绝；双线程均先加载卡片后评分，只保存一次日志，另一请求冲突；FSRS 原回归通过 |
| RLS 不会自动验证整数关联 ID 的业务归属，可能写入指向其他账号或其他计划章节的记录 | 统一校验当前租户下项目/章节关系；父级 SHARE 锁保护写入，等待锁后重新校验章节 | 笔记、任务、卡片、测验、进度的跨账号及错项目写入全部 404；删除与等待写入并发时不留孤儿 |
| 删除项目/章节遗留卡片、复习日志、测验、笔记等，后台任务可能写回；单章删除误取消其他章批改 | 统一取消关联任务、按固定锁顺序清理学习记录并失效日报；单章只处理关联批改 | 项目删除清理记录并取消任务；单章删除保留其他章、笔记与批改，保留的批改仍可完成 |

删除语义：涉及被删除章节的测验作为完整评估快照删除，包括跨章节的混合测验，避免静默改变半份试卷。账号共享资料/原件和模型调用审计保留；终态任务记录也保留，本操作不是账户隐私数据全量擦除。原有数据若已经错误写入满掌握度，本轮不会擅自批量修正，须另做迁移审计。

两轮独立静态复核后，锁后章节重验、预加载卡片计数和无关批改保留均未发现剩余阻断问题。以上结论限本次修复范围，不代表 `migration-audit.md` 中所有历史功能均已完整移植。

## 前端接口交接

实际契约为 `learn_web/openapi.json` 与 `learn_web/src/api/schema.d.ts`；路由清单由 `tests/learn_core/test_api_contract.py` 约束。以下路径均省略 `/api/v2`，官网入口还需保留 `/official/learn-everything` 前缀。

| 功能 | 方法与路径 | 关键输入/输出与恢复方式 |
| --- | --- | --- |
| 身份 | `GET /me` | 官网 Cookie + 可信入口校验；业务请求绑定预期账号，账号变化须清空旧界面；不传客户端自选 tenantId |
| 计划 | `GET/POST /projects`，`GET/PATCH/DELETE /projects/{id}` | 创建含 title/topic/goal/weeklyHours，可选 generateRoadmap；201 返回计划及可选任务；列表/详情恢复持久化记录；删除 204 |
| 章节 | `GET/POST /projects/{id}/nodes`，`PATCH/DELETE /nodes/{id}` | 创建 201；PATCH 200；删除 204；**mastery 为只读**；可写 status 仅 pending/learning/reviewing/done，省略不改，null 非法 |
| 阅读完成 | `PATCH /nodes/{id}` | 发送 `{"status":"done"}`；不传 mastery，不传 mastered/weak；刷新通过节点列表恢复 |
| 概览 | `GET /projects/{id}/summary` | **completedNodes/completionRatio 是阅读完成**；masteredNodes/masteryRatio 按数值 mastery >= 0.85 统计；另有 totalNodes/nodesByStatus/studyMinutes |
| 路线与教材 | `POST /projects/{id}/roadmap-jobs`，`POST /nodes/{id}/lesson-jobs` | 202 返回 jobId/state；教材可传 force，已有内容/版本冲突受保护；完成后重取节点，不能把 202 当生成完成 |
| 笔记与任务 | `GET/POST /projects/{id}/notes`、`/tasks`，`PATCH /notes/{id}`、`/tasks/{id}` | 笔记含 nodeId/content；任务含 title、可选 nodeId/taskType；创建 201、修改 200；错账号/错项目关联 404 |
| 问答 | `POST /projects/{id}/chat-jobs`，`GET /projects/{id}/conversation` | content、UUID requestId、可选 nodeId/useMaterials/materialIds；202；重发相同 requestId 恢复同一请求，已有在途任务冲突；历史恢复问答及任务 |
| 资料 | `POST/GET /projects/{id}/materials`，`GET /materials/{id}/preview`、`/download` | 上传 multipart file/index，202 返回 fileId/sha256/sizeBytes/jobId；账号内共享；文字预览并非 PDF 原版渲染；尚未索引成功的预览 422 |
| 资料重建与删除 | `POST /materials/{id}/index`，`DELETE /materials/{id}` | 重建 202；删除 204；缺失或其他账号 404；上传配额不足 507 |
| 测验生成/恢复 | `POST /projects/{id}/quiz-jobs`，`GET /projects/{id}/quizzes`，`GET /quizzes/{id}` | nodeIds/count/qtype；生成 202；完成后重新查询试卷 |
| 批改/结果 | `POST /quizzes/{id}/grade-jobs`，`GET /quizzes/{id}/grade-job`、`/result` | answers 为题号到答案映射；提交 202；通过任务和结果接口恢复；同份已完成试卷不表示可重考，旧 /submit 已弃用 |
| 卡片/复习 | `POST /projects/{id}/card-jobs`，`GET /review/due`，`POST /review/{cardId}` | 生卡 202；评分发送 rating 1–4 与**必填 expectedReps**，取当前卡片 reps；成功 200，旧计数 409 后刷新卡片，不盲目重复评分 |
| 模型选择 | `GET /models`，`PATCH /models/selection` | 读取官网网关允许的模型，发送 model；结果按账号持久化，不在此保管个人 API Key |
| 后台任务 | `GET /jobs/{id}`，`GET /jobs/{id}/events` | 轮询/SSE 都受账号约束；queued/running/done/failed/cancelled；SSE progress/end/gone；重连后读取持久化状态；失败不能按 done 显示，内部 prepared 输入不公开 |

统一错误体为 `{"error":{"code":"…","message":"…","retryable":false}}`，限流可带 retryAfterSeconds。重点处理：401 UNAUTHENTICATED、403 ENTITLEMENT_REQUIRED、402 INSUFFICIENT_CREDITS、404 NOT_FOUND、409 ACCOUNT_CHANGED/CONFLICT/JOB_RUNNING、422 INVALID_ARGUMENT、429 TENANT_BUSY、503 GATEWAY_UNAVAILABLE、507 STORAGE_FULL。未知对象、他人对象和错误项目关联统一返回 404，不向前端透露对象存在性。

Workbench、Roadmap、Dashboard、演示数据及类型已随契约一起修改。前端同学后续重构应基于此分支同步这部分改动，特别避免重新加入 mastery 写入。业务 PATCH 的 status 只有显式提供时才更新，OpenAPI 中的默认值不表示每次 PATCH 重置状态。

## 本轮运行结果

使用独立 Docker 容器 `ai-learn-handoff-8d0500a`，仅监听 `127.0.0.1:55432`，数据库 `learn_handoff`。没有挂载旧用户数据目录。

- PostgreSQL 17、pgvector 0.8.1、pg_trgm，六个 Alembic 迁移及 Procrastinate schema 从空测试库建立。
- 镜像 `pgvector/pgvector:0.8.1-pg17`，核验 digest：`sha256:3e8b3adfd27b5707128f60956f62a793c3c9326ea8cfaf0eab7adccb5d700b21`。
- 独立 Python 3.11.17 环境，现有 requirements 经带哈希的临时锁定文件安装；FastAPI 0.163.1、SQLAlchemy 2.1.9、Procrastinate 3.11.0、psycopg 3.3.9、Pydantic 2.14.3、FSRS 6.3.1。未修改运行依赖清单。

| 检查 | 实测结果 | 证明范围 |
| --- | --- | --- |
| 原基线 + 首批新回归 | 13 项失败 | 用未修改的 git archive 基线复现缺陷，非仅凭静态推断 |
| 补充并发回归，修复前 | 9 项通过、3 项失败 | 复现旧 ORM 快照、锁后失效节点及误取消无关批改 |
| 完整 `pytest -q tests/learn_core` | **149 通过，0 跳过**（42.59 秒） | 真数据库/RLS/事务与真实队列 worker，模型/官网身份响应隔离模拟 |
| `export_openapi.py --check` | 通过 | 实际 API 与契约快照一致 |
| `validate_queue.py` | PASS | 在途去重、同租户同通道串行、跨租户并行、失活任务回收后真实 worker 重跑 |
| `validate_vector.py` | PASS | 20,400 条合成向量；本次默认召回 10%，relaxed/ef=200 为 80%，strict/ef=400 为 100% |
| `scripts/ci-check.sh web` | 通过 | 提供商 33 项对齐；TS API 类型；17 项 Vitest；生产构建；84 项普通浏览器 + 10 项演示浏览器通过 |
| 仓库产物检查、`git diff --check` | 通过 | 没有混入生成/私有产物，补丁空白检查通过；未运行旧平台完整打包验收 |

Windows 本地 worker 子进程使用忽略目录中的 test-only `sitecustomize.py` 选择 Selector event loop；否则 psycopg async 在默认 Proactor 下拒绝运行。这个测试启动辅助没有加入产品运行源码，目标部署仍为 Linux。测试存在一条 Starlette TestClient 关于 httpx 的弃用提示，未为消除提示新增依赖。本轮新增 17 项后端回归；完成状态的会话恢复及证据更新也纳入其中。

测试结束后停止上述专用容器并保留测试库；需要复跑时用 `docker start ai-learn-handoff-8d0500a` 启动，按本节端口设置测试 DSN。没有停止 Docker Desktop 或操作其他容器。

队列失活恢复门禁在数据库构造失活 worker 场景，不等同于目标 Linux 上真实 SIGKILL/机器断电演练。向量毫秒耗时与召回来自单次合成测试，不作为生产性能或 2GB 容量承诺。浏览器使用真实 Chromium 运行 React，但通过 route/demo 模拟 API；后端由 TestClient、真实数据库和子进程 worker 独立验证，尚未做浏览器到真实官网整链路。

## 资源与发布交接

本轮没有新增模型调用入口、预生成、worker 并发或运行二进制依赖。恢复用消息快照每任务最多受原有 120,000 字符输入限制，增加 JSON 存储及一次短事务；任务终态清理/保留策略仍须部署评估。快照不进入每次轮询和 SSE，避免重复传输。归属保护增加短事务内锁和查询，删除串行化同项目写入；未持锁等待模型 HTTP。

后续真实官网与候选部署所需条件：

1. 官网负责人提供可信代理、authorize 测试环境、Cookie 续期、资格变化和预期账号协议配置；共享 FastAPI 按 `official-auth.md` 部署，不沿用旧每账号 worker 入口承载新后端。
2. 网关负责人提供受限测试账号/额度，验证 X-End-User、X-Event-Id 与实际积分扣除；检查网络未知结果、明确拒绝和崩溃恢复，确认服务端幂等保存周期。没有进行收费调用。
3. 发布负责人准备独立 Linux 候选、PostgreSQL 角色/RLS、文件与嵌入服务路径、持久 worker/reaper、HTTPS 入口、日志与备份；配置 LEARN_DATABASE_URL、LEARN_DATABASE_OWNER_URL、LEARN_PROCRASTINATE_DSN，其他可信入口/网关参数按现有运维文档设置，不把开发默认口令带到候选环境。
4. 在实际共用 2 核/2GB 主机用 2–3 个独立账号测上传解析、向量索引、生成与学习混合负载的峰值 RSS/CPU/磁盘及队列积压；确定上传上限、嵌入部署和进程数量。当前 50MiB 上传限制不代表该主机可安全承载。
5. 完成备份恢复、按账号分流/回退和真实重登/交叉访问验收。先用新测试数据；旧用户数据迁移另排演练与审核。

交付保留在隔离功能分支，原检出的规划改动未动。未推送、未创建 PR、未合并或发布；旧平台完整 `scripts/ci-check.sh`（含固定子模块/打包和干净提交要求）尚未运行，不能将 web 子集通过写成完整仓库发布检查通过。正式推送前应按仓库要求完成该检查并经 PR 审查。
