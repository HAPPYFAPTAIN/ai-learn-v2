# 新版 AI Learn 候选发布

本流程部署 React、FastAPI、PostgreSQL 任务 worker 和嵌入服务。使用独立的 Linux 测试环境、数据库、文件目录和 HTTPS 入口。旧官网服务继续使用既有发布流程。

## 构建候选包

在干净、已提交的源码检出中运行。构建机使用 Python 3.11 和与新版 CI 一致的 Node.js。部署目标无需 Node.js。

```sh
npm --prefix learn_web ci
python scripts/learn_v2_release.py pack
```

命令重建生产前端，输出 `output/learn-v2/learn-v2-<commit>.tar.gz` 和 SHA-256。候选包包含运行源码、迁移、部署模板、静态前端及其 PDF 资源。Python 环境、模型缓存、开发代理和密钥在包外。将压缩包传到目标服务器前记录 SHA-256。在目标服务器核对 SHA-256，再解压到全新的 `/opt/ai-learn-v2/releases/<candidate>`；从受信任的源码检出也可用 `python scripts/learn_v2_release.py verify <解压目录>` 校验包内文件。发布目录由管理员管理，服务账号只读。

## 准备目标环境

- 建立无登录权限的 `learn-v2` 系统用户和同名组。准备 `/opt/ai-learn-v2/core-venv` 和 `/opt/ai-learn-v2/embed-venv` 两个 Python 3.11 环境。包里的 `requirements-learn-core.txt` 和 `requirements-learn-embed.txt` 是依赖输入。在发布准备阶段为目标 Linux 架构解析版本和哈希，审查后使用各自的锁文件和 wheel 安装，保留 `procrastinate==3.11.0`。运行时从已验收的环境启动。
- 为 `learn_v2` 独立数据库准备 PostgreSQL 17、`vector`、`pg_trgm`、`learn_owner` 和 `learn_app`，权限结构见新版 CI。将 `deploy/learn-v2/service.env.example` 复制为 `/etc/ai-learn-v2/service.env`，由 root 持有，权限 `0600`。填写应用角色 DSN、官网鉴权和网关地址以及密钥。跨机器部署时按实际地址配置回环服务的远端依赖。
- 按验收过的模型版本和校验清单，将 FastEmbed 的 384 维模型缓存放在 `/var/lib/ai-learn-v2/embed`，给予 `learn-v2` 读取权限。启动时使用本地模型文件。文件持久化目录默认为 `/var/lib/ai-learn-v2/files`，由同一服务用户写入。

在候选目录中使用受控的迁移环境注入 `LEARN_DATABASE_OWNER_URL` 后执行以下命令。迁移账号与服务账号的环境文件分别管理。

```sh
/opt/ai-learn-v2/core-venv/bin/python -m alembic upgrade head
/opt/ai-learn-v2/core-venv/bin/python scripts/phase0/apply_queue_schema.py
```

## 启动与验收

1. 为本次独立部署创建 `/opt/ai-learn-v2/current` 链接，使其指向已解压的候选目录。将包中的 `deploy/learn-v2/*.service` 和 `deploy/learn-reaper.{service,timer}` 安装到 systemd，执行 `systemctl daemon-reload`，再启用并启动 `learn-v2-embed.service`、`learn-v2-api.service`、`learn-v2-worker@llm.service`、`learn-v2-worker@io.service` 和 `learn-reaper.timer`。
2. 在独立测试虚拟主机中加载 `deploy/learn-v2/locations.nginx.conf`，配套官网账号入口、短票 Cookie 和测试账号分流。创建仅管理员可读的 `/etc/ai-learn-v2/nginx-secret.conf`，内容为 `proxy_set_header X-Learn-Internal-Secret "<与 LEARN_INTERNAL_SECRET 相同的随机值>";`。通过 `nginx -t` 后再加载测试站配置。
3. 检查端口 18080 和 18090 的 `/healthz`，确认两个 worker 运行、`learn-reaper.timer` 已启用。用测试账号从浏览器验证登录、创建路线、完整教材生成、上传与索引，并用同一任务的事件 ID 核对网关用量。中断测试 worker，核对已发出但结果未知的生成任务结束且未自动再发，以及后续任务能够运行。
4. 出现问题时撤销测试账号分流。回退新版二进制包前，先确认旧候选与当前数据库结构兼容。数据目录和数据库单独保留。

## 模型超时

`LEARN_GATEWAY_READ_TIMEOUT` 为网关读取等待时间，单位秒，默认 120，允许大于 0 且不超过 600。建连和连接池等待各为 5 秒，写入为 10 秒。后台调用的租约至少为 5 分钟，长配置下至少比读取时限多 60 秒。Nginx API 读取时限为 660 秒。按真实教材耗时核对网关内层时限后再调整。

生成任务最多自动重试两次。建连或连接池超时沿用事件 ID，明确的 HTTP 429 使用新事件 ID。收到响应前断线、读写异常、网关 5xx 或 worker 在已开始请求的阶段退出时，页面提示结果未确认并停止自动重发。运维根据任务 ID 和用量记录确认后再决定是否重新发起。
