# AI Learn v2 公司机部署与发布

## 用户从哪里进入

打开[官网的 Learn Everything 产品页](https://8.130.144.193/official/products/learn-everything/)，登录具有学习产品资格的官网账号，点击 **打开学习工作台**。官网签发短票，浏览器在同源入口换取 `learn_entry` Cookie，再进入 `/official/learn-everything/app/`。书签应保存产品页。直接打开 `/official/learn-everything/`，缺少有效短票或会话时会返回 403。排查时记录路径、时间和状态码，勿复制含 ticket 的完整 URL。

## 当前生产拓扑

2026-11-20 核对。首次部署源提交为 `8cbe4e441a60`。公司机使用现有官网 Nginx，在同一站点转发 React 静态资源和 FastAPI 请求。工作台通过 API 使用学习库，模型生成由后台 worker 处理，资料索引使用本机嵌入服务。下列端口均监听回环地址。

| 服务 | 地址 / 配置 | 谁负责 |
| --- | --- | --- |
| 登录与资格 | 官网账号服务 `127.0.0.1:18030`，`LEARN_AUTHORIZE_URL` 指向 `/api/v1/console/learn-everything/authorize` | 官网工程的账号服务签发、验证短票，学习 API 复核当前账号 |
| 学习 API / React | `127.0.0.1:18080`，Nginx 将官网工作台及 `/official/learn-everything/api/v2/` 转发到 `/app/`、`/api/v2/` | 公司机现有 Nginx、AI Learn |
| 模型生成 | 官网模型网关 `127.0.0.1:18040/v1`，`LEARN_GATEWAY_URL`、`LEARN_GATEWAY_PRODUCT_KEY` | 学习后端携带学习产品密钥、账号和用量事件调用网关，网关管理供应商凭据与计量 |
| 文档嵌入 | `127.0.0.1:18090`，`LEARN_EMBED_URL` | 独立 embed 进程加载本机缓存的 384 维模型 |
| 数据库与队列 | 独立 PostgreSQL 17，`127.0.0.1:15432/learn_v2`，扩展 `vector`、`pg_trgm` | `learn_app` 执行业务，`learn_owner` 迁移，Procrastinate 使用学习库 |

官网账号服务和模型网关由 [AetherMind-Official-Site](https://github.com/AetherMindHarness/AetherMind-Official-Site) 维护。此次沿用了旧版学习服务对应的**网关产品密钥**。用户在官网选择有权使用的模型，无需填写个人供应商 Key。替换或轮换密钥时，向网关维护方确认学习产品范围和有效性，更新服务器上的 `conf/model-gateway.env` 并重启读取它的学习进程。Nginx 与学习 API 之间另用 `LEARN_INTERNAL_SECRET`；它与产品密钥、登录 Cookie 各有用途。各密钥仅存于服务器受限配置。

## 服务器布局

以部署用户登录，`base="$HOME/data/ai-learn/standalone-v2"`。systemd **用户服务**的工作目录均为 `$base/src`（数据库独立管理），前端构建产物随源码放在 `src/learn_web/dist`。主机使用两个 Python 3.12 环境 `core-venv`、`embed-venv`，依赖记录在 `ops/core.lock`、`ops/embed.lock`。模型缓存为 `state/embed`。运行配置在 `conf/service.env`、`conf/database-runtime.env`、`conf/model-gateway.env`。迁移凭据单独保存在 `conf/database-owner.env`。

数据文件在 `/data/ai-learn-v2/postgres`，用户上传在 `/data/ai-learn-v2/files`。应用发版只交换源码目录，数据库实例和官网 Nginx 单独维护。旧 Gradio 安装仍保留。核查进程和本地服务可执行：

```sh
systemctl --user status ai-learn-v2-{api,embed,db}.service \
  ai-learn-v2-worker@{llm,io}.service ai-learn-v2-reaper.timer
curl -fsS http://127.0.0.1:18080/healthz
curl -fsS http://127.0.0.1:18090/healthz
journalctl --user -u ai-learn-v2-api.service -n 50
```

## 在 GitHub Actions 发布

1. PR 触发 **Learn core (multi-tenant)** 的相关路径测试：PostgreSQL 17 + pgvector 租户/队列测试、前端和浏览器测试、接收脚本回归。前端 job 从同一检出构建并校验 v2 归档，作为 `learn-v2-<完整 SHA>` artifact 保留七天。PR 不连接公司机。
2. PR 审阅并合入后，确认本次窗口内两个队列的在途任务已结束。进入 **Actions → Learn core (multi-tenant) → Run workflow**，选 `main`、勾选 `deploy_company`。本次运行重新验证所选提交，两个 job 成功才交付**本次已测试的归档**。未勾选只做验证。旧 `release.yml` 交付 Gradio 包。
3. 发布 job 经 `learn-production` 环境使用专用 SSH 密钥上传归档。接收端核对提交、归档 SHA-256 及逐文件清单，比较运行依赖、迁移、队列初始化和部署模板。兼容时停止应用进程，原子交换源码，再启动 API、嵌入服务、两个 worker 和 reaper timer。它检查两个健康端点、React 首页和 systemd 状态；健康检查失败尝试恢复前一份源码并重启。检查 Actions 日志中的活动提交及保留目录。
4. 从官网产品页用有资格的测试账号打开工作台，检查登录、模型目录、学习记录、生成和资料索引。真实生成会产生网关用量。无票的受保护入口 403、未登录的学习 API 401 都不能验证已登录链路。

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

迁移、依赖或服务模板变化时，接收器在切换前退出。此类版本安排专门的维护窗口：先备份独立学习库与上传文件并验证可恢复，再按目标架构准备经审阅的锁定环境、对照现有用户服务与 Nginx 配置。需要迁移时，在候选目录使用 `learn_owner` 的受控环境与正确的 `PYTHONPATH`，核对目标为 `127.0.0.1:15432/learn_v2`，依次执行：

```sh
"$base/core-venv/bin/python" -m alembic upgrade head
"$base/core-venv/bin/python" scripts/phase0/apply_queue_schema.py
```

队列表由第二条命令单独初始化。完成候选验证后，由运维在同一维护窗口切换源码和所需运行配置，重新核对上述进程与官网业务；留存此次回退所需的源码、环境和备份。

## 回退

- **回到上一个 v2 版本**：从上次成功发布日志取 `previous source` 目录名，核查所选目录、当前活动提交与数据库兼容性。部署用户执行 `python3.12 -I "$base/ops/receive_learn_v2.py" --restore <before-目录名>`。它与发布共用主机锁，交换目录、重启并执行相同检查。交换后该目录保存被替换的版本。首次自动发布也会保留原来的手工部署源码。
- **整个官网入口切回旧 Gradio**：在已确认的故障窗口，由有 Nginx 管理权限的运维核对 `$base/ops/rollback-entry.sh` 和原路由备份后执行。它会核对配置并恢复旧入口。学习库和上传文件继续保留，数据库恢复或跨版本数据迁移须单独处理。

## 模型超时

`LEARN_GATEWAY_READ_TIMEOUT` 为网关读取等待时间，单位秒，默认 120，允许大于 0 且不超过 600。建连和连接池等待各为 5 秒，写入为 10 秒。后台调用的租约至少为 5 分钟，长配置下至少比读取时限多 60 秒。Nginx API 读取时限为 660 秒。按真实教材耗时核对网关内层时限后再调整。

生成任务最多自动重试两次。建连或连接池超时沿用事件 ID，明确的 HTTP 429 使用新事件 ID。收到响应前断线、读写异常、网关 5xx 或 worker 在已开始请求的阶段退出时，页面提示结果未确认并停止自动重发。运维根据任务 ID 和用量记录确认后再决定是否重新发起。
