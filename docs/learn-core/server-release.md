# AI Learn v2 公司机部署与发布

本轮维护 React、FastAPI、PostgreSQL 任务 worker 和嵌入服务。使用经批准的 Linux 目标环境、数据库、文件目录和 HTTPS 入口。旧官网服务继续使用既有发布流程。2026-11-20 线上问题对应、资源变化与待验项目见 [online-issues-v2.md](online-issues-v2.md)。文档中的准备命令不代表已经在线上执行。

## 本次模型配置决定

2026-11-20 用户确认官网改为各账号导入自己的 API Key。目标配置为 API 与所有 worker 一致使用 `LEARN_MODEL_SOURCE=personal` 和同一服务端加密密钥；现网旧 gateway 配置不会随代码合并自动改变。切换、编辑/删除验收及回退见 [个人 Key 官网操作单](personal-api-key-production.md)。保留原网关配置供兼容回退，继续沿用官网身份与资格校验。

## 现有线上环境优先处理

先获取服务器的 `ops/core.lock` / `ops/embed.lock`，核查 Linux 版本与哈希后分别收录根目录 `requirements-learn-core.lock` / `requirements-learn-embed.lock`，同时加入 `runtime/learn-v2-release-policy.json` 的文件清单。当前检出尚未取得这两个文件，不能在服务器用版本范围临时解析替代。

迁移和重启前，先完成下述备份、恢复演练和重复章节只读核查。现网使用用户级 `ai-learn-v2-*` unit；`learn-v2-*` 系统级模板用于独立部署，不能仅安装后者就认为已修改现网 unit。下述命令在服务器布局所定义的 `$base` 下运行。

### 备份和内存限制

将 `deploy/learn-v2/user/ai-learn-v2-backup.{service,timer}` 安装到现有服务用户的 `~/.config/systemd/user/`。该用户的 `~/.config/ai-learn-v2/backup.env` 权限为 `0600`，配置 `PGHOST`、`PGPORT`、`PGUSER`、`PGDATABASE=learn_v2`、`PGPASSFILE`、`LEARN_FILES_ROOT=/data/ai-learn-v2/files` 和 `LEARN_BACKUPS_ROOT=/data/ai-learn-v2/backups`。备份角色必须有所有表读取权限及 BYPASSRLS；恢复演练还需要在专用演练环境建临时库的权限。密码仅放在受限的 pgpass 文件，不写进命令或 PR。需预装 PostgreSQL 客户端和 rsync。

首次备份安排暂停上传/删除，数据库与文件快照并非原子操作。以下命令在原服务用户下执行；脚本以当天名称保留备份，成功后重复执行会停止，避免覆盖。

```sh
systemctl --user daemon-reload
systemctl --user start ai-learn-v2-backup.service
# 沿用同一 backup.env；在受控环境注入后执行，不在 shell 打印凭据
"$base/core-venv/bin/python" "$base/src/scripts/learn_v2_backup.py" --restore-drill
systemctl --user enable --now ai-learn-v2-backup.timer
systemctl --user list-timers ai-learn-v2-backup.timer
```

恢复演练仅创建随机命名临时库，校验主要表行数后删除，不覆盖 `learn_v2`。每日 03:30 按服务器当地时区执行，保留 14 天。部署前核实路径及磁盘空间。

把 `deploy/learn-v2/user/*.service.d/limits.conf` 按原目录结构安装到 `~/.config/systemd/user/`；为已存在的 API、DB、llm/IO worker、嵌入服务，以及新 chat worker 添加限制。该目录仅提供 drop-in，不替代现有完整 service。chat 实例复用现网 worker 模板，每实例并发 1。执行 daemon-reload 并在部署窗口重启后运行：

```sh
bash scripts/check_learn_v2_memory.sh
```

要求配置值和实际 cgroup 一致：DB 1G、API 768M、llm 512M、chat 512M、IO 1G、embed 1G。用户级控制器未下放或 `memory.max=max` 时检查失败，需管理员处理；不能宣称内存限制已生效。

## 用户从哪里进入

打开[官网的 Learn Everything 产品页](https://8.130.144.193/official/products/learn-everything/)，登录具有学习产品资格的官网账号，点击 **打开学习工作台**。官网签发短票，浏览器在同源入口换取 `learn_entry` Cookie，再进入 `/official/learn-everything/app/`。书签应保存产品页。直接打开 `/official/learn-everything/`，缺少有效短票或会话时会返回 403。排查时记录路径、时间和状态码，勿复制含 ticket 的完整 URL。

## 切换前生产拓扑与兼容服务

2026-11-20 核对。首次部署源提交为 `8cbe4e441a60`。公司机使用现有官网 Nginx，在同一站点转发 React 静态资源和 FastAPI 请求。工作台通过 API 使用学习库，模型生成由后台 worker 处理，资料索引使用本机嵌入服务。下列端口均监听回环地址。

| 服务 | 地址 / 配置 | 谁负责 |
| --- | --- | --- |
| 登录与资格 | 官网账号服务 `127.0.0.1:18030`，`LEARN_AUTHORIZE_URL` 指向 `/api/v1/console/learn-everything/authorize` | 官网工程的账号服务签发、验证短票，学习 API 复核当前账号 |
| 学习 API / React | `127.0.0.1:18080`，Nginx 将官网工作台及 `/official/learn-everything/api/v2/` 转发到 `/app/`、`/api/v2/` | 公司机现有 Nginx、AI Learn |
| 模型生成 | 官网模型网关 `127.0.0.1:18040/v1`，`LEARN_GATEWAY_URL`、`LEARN_GATEWAY_PRODUCT_KEY` | 学习后端携带学习产品密钥、账号和用量事件调用网关，网关管理供应商凭据与计量 |
| 文档嵌入 | `127.0.0.1:18090`，`LEARN_EMBED_URL` | 独立 embed 进程加载本机缓存的 384 维模型 |
| 数据库与队列 | 独立 PostgreSQL 17，`127.0.0.1:15432/learn_v2`，扩展 `vector`、`pg_trgm` | `learn_app` 执行业务，`learn_owner` 迁移，Procrastinate 使用学习库 |

官网账号服务和模型网关由 [AetherMind-Official-Site](https://github.com/AetherMindHarness/AetherMind-Official-Site) 维护。此次沿用了旧版学习服务对应的**网关产品密钥**。该描述对应切换前的 gateway 模式；切换后用户导入本人供应商 Key，学习后端直接调用供应商，官网网关不参与这些模型请求的积分结算。替换或轮换密钥时，向网关维护方确认学习产品范围和有效性，更新服务器上的 `conf/model-gateway.env` 并重启读取它的学习进程。Nginx 与学习 API 之间另用 `LEARN_INTERNAL_SECRET`；它与产品密钥、登录 Cookie 各有用途。各密钥仅存于服务器受限配置。

## 服务器布局

以部署用户登录，`base="$HOME/data/ai-learn/standalone-v2"`。systemd **用户服务**的工作目录均为 `$base/src`（数据库独立管理），前端构建产物随源码放在 `src/learn_web/dist`。主机使用两个 Python 3.12 环境 `core-venv`、`embed-venv`，依赖记录在 `ops/core.lock`、`ops/embed.lock`。模型缓存为 `state/embed`。运行配置在 `conf/service.env`、`conf/database-runtime.env`、`conf/model-gateway.env`。迁移凭据单独保存在 `conf/database-owner.env`。

数据文件在 `/data/ai-learn-v2/postgres`，用户上传在 `/data/ai-learn-v2/files`。应用发版只交换源码目录，数据库实例和官网 Nginx 单独维护。旧 Gradio 安装仍保留。核查进程和本地服务可执行：

```sh
systemctl --user status ai-learn-v2-{api,embed,db}.service \
  ai-learn-v2-worker@{llm,chat,io}.service ai-learn-v2-reaper.timer
curl -fsS http://127.0.0.1:18080/healthz
curl -fsS http://127.0.0.1:18090/healthz
journalctl --user -u ai-learn-v2-api.service -n 50
```

## 在 GitHub Actions 发布

1. PR 触发 **Learn core (multi-tenant)** 的相关路径测试：PostgreSQL 17 + pgvector 租户/队列测试、前端和浏览器测试、接收脚本回归。前端 job 从同一检出构建并校验 v2 归档，作为 `learn-v2-<完整 SHA>` artifact 保留七天。PR 不连接公司机。
2. PR 审阅并合入后，确认本次窗口内llm、chat、io 三个队列的在途任务已结束。进入 **Actions → Learn core (multi-tenant) → Run workflow**，选 `main`、勾选 `deploy_company`。本次运行重新验证所选提交，两个 job 成功才交付**本次已测试的归档**。未勾选只做验证。旧 `release.yml` 交付 Gradio 包。
3. 发布 job 经 `learn-production` 环境使用专用 SSH 密钥上传归档。接收端核对提交、归档 SHA-256 及逐文件清单，比较运行依赖、迁移、队列初始化和部署模板。兼容时停止应用进程，原子交换源码，再启动 API、嵌入服务、三个 worker（llm、chat、io） 和 reaper timer。它检查两个健康端点、React 首页和 systemd 状态；健康检查失败尝试恢复前一份源码并重启。检查 Actions 日志中的活动提交及保留目录。
4. 从官网产品页用有资格的测试账号打开工作台，检查登录、模型目录、学习记录、生成和资料索引。个人模式的真实生成会消耗本人供应商额度；gateway 兼容模式会产生网关用量。无票的受保护入口 403、未登录的学习 API 401 都不能验证已登录链路。

### 首次启用发布通道（合并后）

- 在公司机核对并安装已审阅的 `scripts/deployment/receive_learn_v2.py` 到 `$base/ops/receive_learn_v2.py`，权限 0700。接收器使用 Python 3.12 标准库、Linux 同一文件系统的目录交换和用户 systemd。更新接收器本身时也需单独安装已审阅版本。无需给流水线 sudo 权限。
- 为此环境单独生成一对 SSH 密钥。只将公钥追加到部署用户的 `authorized_keys`，并在**该公钥同一行**前放置以下选项。保留已有登录配置。先通过可信主机控制台取得 SSH 主机公钥，按实际端口生成 known_hosts 条目。
- 在仓库 **Settings → Environments → learn-production** 限定部署分支为 `main`，按团队流程设置审批。变量填写 `LEARN_SSH_HOST`、`LEARN_SSH_PORT`、`LEARN_SSH_USER`；环境 secrets 填写 `LEARN_SSH_PRIVATE_KEY` 和 `LEARN_SSH_KNOWN_HOSTS`（非 22 端口使用 `[host]:port` 格式）。运行器需能连接公司机 SSH 端口。业务密钥、数据库口令均留在服务器。首次发布时以生产 job 及官网业务验证为准。

```text
restrict,command="/usr/bin/python3.12 -I /home/chenyutong/data/ai-learn/standalone-v2/ops/receive_learn_v2.py" ssh-ed25519 <部署公钥> learn-v2-release
```

### 手动构建与涉及基础设施的版本

在干净的已提交检出、Node.js 22 和已安装 Python 的构建机执行。命令输出完整提交及 SHA-256。

```sh
npm --prefix learn_web ci
python scripts/learn_v2_release.py pack
candidate=output/learn-v2/learn-v2-$(git rev-parse --short=12 HEAD).tar.gz
stage=$(mktemp -d)
tar -xzf "$candidate" -C "$stage"
python scripts/learn_v2_release.py verify "$stage"
```

迁移、依赖或服务模板变化时，接收器在切换前退出。此类版本安排专门的维护窗口：先备份独立学习库与上传文件并验证可恢复，再按目标架构准备经审阅的锁定环境、对照现有用户服务与 Nginx 配置。先以受信 BYPASSRLS 运维角色执行 `scripts/learn_v2_preflight.sql`，有重复章节编号先报告，不自动改数据。需要迁移时，在候选目录使用 `learn_owner` 的受控环境与正确的 `PYTHONPATH`，核对目标为 `127.0.0.1:15432/learn_v2`，依次执行：

```sh
# LEARN_DATABASE_OWNER_URL 指向 learn_owner
"$base/core-venv/bin/python" -m alembic upgrade 0008_model_providers
# 单独换为允许 ALTER ROLE learn_app 的 DBA 连接
"$base/core-venv/bin/python" -m alembic upgrade 0009_runtime_timeouts
# 换回 learn_owner，0010 遇到重复编号停止
"$base/core-venv/bin/python" -m alembic upgrade head
"$base/core-venv/bin/python" scripts/phase0/apply_queue_schema.py
```

队列表由最后一条命令单独初始化。迁移账号与运行账号的配置分别管理；不要全程用 DBA 创建租户表或 SECURITY DEFINER 函数。依赖须通过 `scripts/install_learn_v2_dependencies.sh` 对生产锁以 `--require-hashes` 安装，缺锁停止。完成候选验证后，由运维在同一维护窗口切换源码和所需运行配置，重新核对上述进程与官网业务；留存此次回退所需的源码、环境和备份。

## 本轮业务验收

检查端口 18080 和 18090 的 `/healthz`，确认三个 worker 运行、reaper timer 已启用。用两个测试账号分别创建路线，核对事件编号不同且调用成功。使用已导入的个人 DeepSeek Key 实测三个不同章节，记录推理 token、输出 token、耗时和 finish_reason；有任意 `length` 先不要发布，报告实测数字。验证上传与索引、公式、代码高亮、导图和日夜主题，确认 CSP 已实际由 nginx 和 API 返回。进度推送期间核对 `pg_stat_activity` 没有长时间 idle in transaction。中断测试 worker，核对未知结果停止自动重发，并通过任务记录和供应商用量核对。

本轮含迁移、依赖及服务模板变化，必须安排维护窗口。新 chat worker 并发 1、上限 512 MiB；在主机审查并安装更新的接收器后，后续常规代码发布才会同时管理 chat 进程。

## 回退

- **回到上一个 v2 版本**：从上次成功发布日志取 `previous source` 目录名，核查所选目录、当前活动提交与数据库兼容性。部署用户执行 `python3.12 -I "$base/ops/receive_learn_v2.py" --restore <before-目录名>`。它与发布共用主机锁，交换目录、重启并执行相同检查。交换后该目录保存被替换的版本。首次自动发布也会保留原来的手工部署源码。
- **整个官网入口切回旧 Gradio**：在已确认的故障窗口，由有 Nginx 管理权限的运维核对 `$base/ops/rollback-entry.sh` 和原路由备份后执行。它会核对配置并恢复旧入口。学习库和上传文件继续保留，数据库恢复或跨版本数据迁移须单独处理。

## 模型超时

官网目标为 `LEARN_MODEL_SOURCE=personal`，API 与所有 worker 共享同一个 `LEARN_PROVIDER_ENCRYPTION_KEY`。按 [个人 Key 官网切换](personal-api-key-production.md) 完成后，`GET /models` 应返回 `source=personal`、`providerImportEnabled=true`，弹窗才会开放输入。旧部署可显式保留 gateway 作为兼容/回退模式。`LEARN_GATEWAY_READ_TIMEOUT` 的既有名称同时用于个人供应商请求，不代表这些请求仍经过网关。

所有连接默认 `LEARN_DB_LOCK_TIMEOUT=10000`（毫秒），API service 另设 `LEARN_DB_STATEMENT_TIMEOUT=30000`；worker 默认 0，不共享 API 30 秒语句上限。连接池默认 5 + overflow 5，需结合所有实例核对 PostgreSQL 的 50 连接上限。

嵌入服务以 `LEARN_EMBED_CONCURRENCY=1` 限制同时执行的 CPU 批次，`LEARN_EMBED_QUEUE_SIZE=8` 限制等待请求。队列满时返回可重试的 HTTP 429 和 `Retry-After: 2`，不再让无限请求进入线程池；调大前必须复测主机 CPU、RSS 和其他服务余量。

`LEARN_GATEWAY_READ_TIMEOUT` 为普通模型调用的读取等待时间，单位秒，默认 120，允许大于 0 且不超过 600。生成任务使用独立的 `LEARN_GENERATION_READ_TIMEOUT`，默认 600；个人供应商与网关路径都使用该值。建连和连接池等待各为 5 秒，写入为 10 秒。后台调用的租约至少为 5 分钟，长配置下至少比读取时限多 60 秒。Nginx API 读取时限为 660 秒。

`LEARN_GENERATION_MAX_TOKENS` 控制路线、课文、测验、复习卡和批改的单次输出上限，默认 250000。该值只是请求上限，不表示供应商支持或会返回这么多 token；部署前必须用所选模型做真实预检，供应商拒绝或截断时不能靠继续放大数值解决。课文仍保留 50000 字符的内容校验上限。

已知 GLM-5.3、GLM-5.3-Flash、FlashX 和 FlashX-Legal 按官方 128K 输出上限保守取 128000。超过时在获取租约和发送供应商请求前返回 `MODEL_OUTPUT_LIMIT`，不会静默降低请求值；使用这些模型时应将该环境变量设为 128000 或更低。未知模型不在本地猜测上限，仍须做真实预检。

生成任务最多自动重试两次。建连或连接池超时沿用事件 ID，明确的 HTTP 429 使用新事件 ID。收到响应前断线、读写异常、网关 5xx 或 worker 在已开始请求的阶段退出时，页面提示结果未确认并停止自动重发。运维根据任务 ID 和用量记录确认后再决定是否重新发起。

## 任务事件

每个 API 进程只在有页面订阅时建立一条 PostgreSQL `LISTEN` 连接，所有本进程的 SSE 订阅共享该连接。任务事务提交时通过 `pg_notify` 发送租户和任务 ID，页面按原有 RLS 上下文重新读取任务；通知不包含正文、错误详情或票据。监听断线会自动重连，页面每 15 秒低频核对一次并发送心跳。多进程部署时每个进程各有一条监听连接，不要求粘性会话；调整数据库连接上限时要把这些监听连接计入。
