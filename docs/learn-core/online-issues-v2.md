# v2 线上问题修复与本轮界面交接

依据 2026-11-20 的《ai-learn交接文档-v2线上问题》和《AI learning修改》。前者的审计基线是 `66baa57`；后者要求恢复旧版侧栏顺序和跨页面智能助手。旧 Gradio 和 `kotaemon` 未修改，功能移植到 React/FastAPI。

## 修复与验证对应

| 问题 | 实现 | 回归位置 |
| --- | --- | --- |
| 1 账号事件撞号 | UUID 事件编号，保留步骤后缀与旧计数表 | `test_online_handoff_v2.py`：两个账号首次生成、问答事件不同 |
| 2 提交与阻塞 | `SessionDep` 在响应前提交；SSE 查库进线程池；同步上传；连接和语句超时 | 同上：真实提交约束失败返回 500、6 路 SSE、同账号双上传 |
| 3 运维兜底 | 每日备份及恢复演练脚本、用户级 timer、内存 drop-in、安全错误日志 | 同上：日志脱敏；本机临时 PostgreSQL 已执行备份恢复；服务器 cgroup 待验 |
| 4 输出截断 | 生成 16000、问答 8000、润色 4000–16000；问答/润色保留部分正文，结构化生成失败保护旧内容 | 同上及 `test_llm_gateway.py`、`test_conversation_jobs.py` |
| 5 崩溃后重发 | 问答/润色持久化 `gatewayCallPending`，未知结果停止重发 | 同上：模拟写库前崩溃，第二次执行不再请求模型 |
| 6 悬挂任务 | 按租户对账超时 running 和缺失队列任务 | 同上及 `test_reaper_cli.py` |
| 7 问答排队 | 问答、助教、润色和全局助手走 `chat`；生成、批改走 `llm` | `test_conversation_jobs.py`、`test_global_assistant.py`；部署需额外 chat worker |
| 8 错误可理解 | 缺模型预检/跳转、409 原文、中文字段提示、任务 errorCode 映射、同参数复用/异参数冲突 | 同上及浏览器 `frontend.spec.ts`、前端 `generation.test.ts` |
| 9 安全头与图片 | API/nginx CSP 等安全头、外置主题脚本、屏蔽 Markdown 外链图片、开发鉴权限制回环来源 | 同上及浏览器图片/主题/公式/导图回归 |
| 10 输入与解析 | 长度/枚举限制、删除未用原文上传入口；PDF/DOCX 子进程限制 120 秒、Linux 1 GiB | 同上及 `test_library_workflow.py`；Linux 实际资源限制由 Linux 环境验收 |
| 11 数据正确性 | 拒绝非法 null、编号 32 字、重复编号 409、可见课程页学习分钟、完成章节 mastery | 同上及 `test_progress_api.py`、浏览器分钟回归 |
| 顺手修 | 0006 降级恢复 RLS/授权；0007 索引幂等；删除旧同步问答；索引失败脱敏；项目更新时间 | 迁移与现有后端回归 |

测试文件位于 `tests/learn_core/` 和 `learn_web/tests/`。模型网关使用模拟响应测试，没有消耗官网积分。完整命令见下文；具体结果以本轮实际执行日志和 PR CI 为准。

### 本轮本机验证（2026-11-20）

- 真实隔离 PostgreSQL 后端回归：208 项通过。旧平台相关回归 40 项、账号前端隔离测试 6 项通过。
- `scripts/ci-check.sh web`：API 类型校验、53 项前端单测、生产构建、188 项浏览器回归和 13 项演示回归通过。
- 生产静态构建加正式 CSP：188 项通用浏览器用例通过，包括新增安全策略专项；原本仅适用开发环境的本机供应商用例已区分运行模式，并单独复测生产入口关闭。未因此放宽生产门禁或 CSP。
- 全新临时数据库按 owner → DBA → owner 执行迁移通过；强制 RLS 下有重复编号时升级停止，保留两条原数据，修复测试数据后升级成功。临时迁移库已清理。
- 本机备份和临时库恢复演练行数一致；生产备份、服务器内存限制和真实 deepseek 用量仍待前述线上验收。格式、OpenAPI 快照、仓库产物与 diff 检查通过。

以上不包含干净提交后的最终候选打包，也不替代 Linux/官网真实账号验收。

## 侧栏与智能助手

侧栏按截图排列：首页、路线、工作台、间隔复习、查漏测验、看板、问答、资料库，保留已有的学习工具与模型设置。

右下角对话气泡打开“以太小助”。跨页面保留当前草稿和对话，支持清空确认、课程/卡片/当前题目上下文及“将最近回复加入课程”。追加课文需要确认并校验课文版本，不能覆盖别人刚保存的内容。未创建学习计划时也能提问；账号切换后隔离历史和组件状态。题目上下文不提前传递隐藏答案。

旧实现参考 `learning_ext/assistant.py` 和 `learning_ext/assets/assistant.js`，新版代码在 `learn_web/src/components/GlobalAssistant.tsx`、`learn_api/routers/assistant.py`。对话存储复用租户隔离的 conversation，每账号使用独立全局对话 ID。仅用户发送时调用模型，不在后台自动预生成。

## 资源变化

- 新增 `chat` worker，并发 1、内存上限 512 MiB。生成/批改仍为并发 1，IO 仍为并发 1，不增设其他常驻模型服务。总模型请求并发上限由 1 增至 2，需要上线审核。
- token 上限提高会增加单次请求的潜在耗时和费用；没有自动多生成一份。未知结果不自动重试，避免重复扣费。
- API 连接池 5 + overflow 5；API 语句 30 秒、所有连接锁等待 10 秒、空闲事务 5 分钟。worker 的语句默认不设 30 秒上限，避免截断正常长任务。
- PDF/DOCX 子进程受 IO 服务的总内存 cgroup 约束，子进程优先成为 OOM 目标。不能把 1 GiB 子进程上限理解为额外可用内存。
- 学习计时只在已打开且可见的课程页每满一分钟写一次，不在侧栏列表、后台标签页或全站逐秒写库。
- 备份保留 14 天；资料采用硬链接快照，但修改、删除和新增文件仍需要磁盘余量。数据库和文件快照不是跨系统原子事务，上线前首次备份应暂停上传/删除。
- 没有增加 Python/Node 二进制依赖；FastAPI 下限改为支持 `scope="function"` 的 0.121。已有个人 Key 改动独立保留，官网部署明确 `LEARN_MODEL_SOURCE=gateway`。

## 仍须服务器完成的事项

1. 本机仓库、项目与下载目录未找到生产 `ops/core.lock` / `ops/embed.lock`，没有服务器连接，因此没有伪造或用 macOS 的 freeze 替代。应从受控服务器取得锁，审查后收录为根目录 `requirements-learn-{core,embed}.lock`，并补入发布清单。安装脚本缺锁会明确停止。若原锁没有哈希，需在目标 Linux 平台生成带哈希的锁，经审查后安装。
2. 正式迁移前以受信运维角色执行 `scripts/learn_v2_preflight.sql`，确认没有重复章节编号。有重复先报告负责人，不自动删除或改编号。0010 再检查并遇重复停止。
3. 生产先备份、临时库恢复并对比行数，再发布；本机的演练不能替代生产备份。
4. 检查用户级 systemd 的 `MemoryMax` 和实际 `memory.max`，若没下放控制器应停止验收并报告。不能仅以 unit 文件已写入判定生效。
5. 测试网关用 deepseek 生成三个不同章节，记录推理/输出 token、finish_reason 和耗时。任何一章为 `length`，先不发布，报告数字。不能用模拟响应证明真实模型不截断。
6. 两个实际账号各生成一条路线，核对 `model_call.event_id` 不同、`status=ok`；检查进度推送期间没有长时间 idle in transaction；验证主模型、积分不足和未知结果提示。

## 交付与检查

原交接要求两个 PR：先 1–3，后 4–11 和低优先级。当前工作区还包含此前授权的个人 Key、主题、删除计划等未提交改动，尚未拆成两个 PR。0009 当前接在个人 Key 的 0008 后；拆分时须核对迁移链，不能把当前混合工作区直接描述成独立 PR 1。

```sh
python scripts/learn_web/export_openapi.py --check
python -m pytest tests/learn_core -q  # 独立真实 PostgreSQL + 已迁移的测试库
scripts/ci-check.sh web
# 生产静态包 + 与 nginx 相同的 CSP；仍使用模拟 API，不调用线上模型
cd learn_web
LEARN_WEB_BASE=/ VITE_API_BASE=/api/v2 npm run build
LEARN_WEB_TEST_PREVIEW=1 npm run test:browser
```

推送前仍须按 AGENTS 执行完整 `scripts/ci-check.sh`；平台打包要求已提交且工作区干净。CSP 本地预览构建不作为发布包；正式打包脚本会以官网路径重新构建。

部署顺序和命令见 [server-release.md](server-release.md)。本轮未操作线上服务、用户数据或生产密钥。
