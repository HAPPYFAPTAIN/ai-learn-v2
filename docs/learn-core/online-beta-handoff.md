# 在线内测交接（2026-11-16）

本文保留 11 月 16 日内测准备时的资源假设和验收清单。公司机现已部署新版，实际官网入口、服务位置、发布与回退流程见[公司机部署与发布](server-release.md)。下文“尚未提供测试机器”等描述均为当时状态。
> 2026-11-20 更新：主题统一为官网青蓝色与深海蓝夜间主题，增加跨页面智能助手及线上问题修复。官网继续走网关，API/worker 明确 `LEARN_MODEL_SOURCE=gateway`；个人 Key 能力保留用于独立本地实验。下文绿色主题属于旧交付记录；最新部署步骤见 [server-release.md](server-release.md)，修复与待验项见 [online-issues-v2.md](online-issues-v2.md)。

目标为 2–3 名受邀用户的完整学习试用。先整理源码和部署说明，用户尚未提供测试机器或域名；本文件不表示已部署或已验收。最终架构继续遵循《ai-learn 多租户架构改造规划》。旧官网 Gradio 服务、broker、发布策略与现有账号保持运行。

## 本次代码范围

- `learn_web/`：React 静态前端，计划列表 → 章节目录 → 单节学习；目标自动提交路线任务、进度估算、完成返回计划列表；公式显示、自测答案按需展开；统一绿色主题和网页下拉控件。
- `learn_api/`、`learn_core/`：学习路线、教材、笔记/进度、资料解析和索引、持久化问答、出题/批改、FSRS 复习、看板及学习工具。复用旧提示词和业务规则，不导入旧 Gradio 运行时。
- 正式模型设置读取官网网关目录并保存账号主模型。供应商卡片和自定义弹窗在正式版仅展示配置预览，不接受个人 Key。
- `scripts/dev/local_provider_*.py` 是明确的本地测试工具，正常 `learn_api.app:app` 不注册它的接口，生产构建也不启用个人 Key。不得将开发认证用于在线站点。

## 先准备的资源和配置

1. 独立测试 PostgreSQL 17 + pgvector/pg_trgm、独立文件目录及独立进程，禁止连接生产账号库或使用生产文件目录。数据库角色、Alembic 和队列初始化参考阶段 0/1 文档与 CI，不使用应用账号建表。
2. 测试域名、HTTPS、官网鉴权可达地址及受控代理，配置 2–3 个测试账号白名单/分流。无测试资格的账号继续进旧系统。协议详见 [official-auth.md](official-auth.md)。
3. 独立服务端环境文件（仓库外，0600），配置数据库/队列 DSN、`LEARN_FILES_ROOT`、`LEARN_EMBED_URL`、`LEARN_AUTHORIZE_URL`、`LEARN_INTERNAL_SECRET`、`LEARN_PUBLIC_ORIGIN`、`LEARN_GATEWAY_URL`、`LEARN_GATEWAY_PRODUCT_KEY`。密钥不进入 Git、构建变量或浏览器。
4. 嵌入模型在部署前离线校验，按独立嵌入依赖/模型锁配置安装。现有本机复用外部虚拟环境不是服务器安装方案。
5. 资源先实测再定。首轮建议模型任务并发 1、IO 并发 1，共享一份嵌入服务；API 连接池/任务额度按测试机器调小，不照搬 50–200 人规划。确认磁盘空间，原规划指出旧机器内存、磁盘不足，不能假设目前已解决。

## 构建与进程

独立候选包、systemd 和 nginx 的实际配置见 [新版服务器发布](server-release.md)。

在隔离候选目录、已准备的锁定运行环境中执行：

```sh
# 仓库根目录；迁移使用独立迁移角色，而非应用角色
python scripts/learn_web/export_openapi.py --check
alembic upgrade head
python scripts/phase0/apply_queue_schema.py

cd learn_web
npm ci
npm run api:check
npm run build
```

默认前端路径为 `/official/learn-everything/app/`，API 路径为 `/official/learn-everything/api/v2`。构建输出 `learn_web/dist/` 作为静态文件服务，不用 Vite 开发服务器提供线上页面。自定义路径必须同时设置 `LEARN_WEB_BASE`、`VITE_API_BASE` 和 nginx 路由。

以下为各 systemd 服务需执行的命令示意，不是自动部署脚本；由同事替换解释器/发布路径、用户、环境文件和资源限制：

```sh
python -m uvicorn learn_api.app:app --host 127.0.0.1 --port 18080
python -m procrastinate --app=learn_core.jobs.app.app worker --queues=llm --concurrency=1
python -m procrastinate --app=learn_core.jobs.app.app worker --queues=io --concurrency=1
python -m learn_embed --port 18090
```

API、worker 和嵌入服务分别管理；配置 `learn-reaper.timer`，见 [ops.md](ops.md)。PostgreSQL 单独管理。在线服务不得设置 `LEARN_DEV_AUTH=1`，不得启动 `local_provider_api` 或 `local_provider_gateway`。

nginx 需要：官网登录校验、覆盖身份/内部密钥头、同源 API 路径重写到 `/api/v2/`、保留 Cookie/Origin/预期账号头、SPA 深链接回退；API/SSE 不缓存，SSE 关闭缓冲并设置足够读取超时；`index.html` 不缓存，哈希静态资源长期缓存。不能直接替换旧站 nginx 配置，先在测试虚拟主机评审。

## 在线验收顺序

1. 测试账号官网登录、资格、过期/续期、换账号后旧标签页停止请求；其他账号不能绕过分流进入。
2. 从网关读取并保存主模型；记录目录获取耗时，以及路线生成的排队/模型/总耗时。进度百分比和剩余时间是估算，不是模型给出的承诺。
3. 目标 → 自动生成路线 → 完成 → 计划列表 → 章节 → 生成教材 → 阅读公式/展开答案 → 笔记/进度；刷新和重新登录后保留。
4. 上传 TXT/MD/PDF/DOCX → 解析索引 → 提取文字/PDF 原件预览和下载 → 指定资料问答及引用 → 单份/批量删除和失败项重试；验证配额及不同账号互不可见。PDF 静态资源需包含 worker 和 `dist/pdfjs-assets/`，核对生产子路径。
5. 按章节生成测验、提交、后台批改、刷新恢复和掌握度；生成复习卡、查看答案、评分和再次进入后的排期。
6. 两人/三人同时生成和上传；记录 RSS/CPU、磁盘、队列等待/错误率；重启 worker 验证任务恢复及防重复提交。真实调用可能收费，需用测试额度。
7. Edge/Safari、窄屏/宽屏、明暗主题体验；这些交互检查按用户要求留到在线环境，自动检查不替代此项。

## 交付与回退

经功能分支和 PR 审查。推送前按仓库要求运行 `scripts/ci-check.sh`；包检查要求已经提交且工作区干净。新版候选包走独立发布清单，见 [新版服务器发布](server-release.md)。

上线测试前做独立数据库和文件备份，并在隔离位置恢复核对。新服务发布后只切测试账号；出现问题撤销测试账号分流，回到旧入口。新站产生的数据另行保存/核对，不能把入口回退等同于数据自动回迁。正式迁移与回退窗口继续以原规划为准。

待完善的全量功能包括流式问答、选区批注、过关诊断/路线调整、完整统计/导入导出、DOCX 原排版预览等；资源公平性、SSE LISTEN/NOTIFY、402 全账号后台暂停和正式迁移演练也未在本次宣称完成。详见 [migration-audit.md](migration-audit.md)。账号后端由同事负责，先按 [前后端衔接说明](frontend-backend-handoff.md) 对齐身份、续期、错误与任务契约，再做真实账号联调。
