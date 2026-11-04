# 官网接口与所有权

本仓库提供学习应用及适配层。官网账号服务继续负责登录、资格、短票签名和续期；模型网关继续负责模型权限和积分计量。本仓库不复制官网用户库、不接收供应商密钥的浏览器配置。

## 请求链路

浏览器 → 官网 Nginx → 官网鉴权子请求 → 学习 broker → 独立账号 worker。broker 每次独立校验短票，并核对 Nginx 给出的用户标识，不能只相信浏览器请求头。

| 接口 | 所有方 | 请求与响应 |
|---|---|---|
| `POST /official-api/api/v1/console/learn-everything/entry` | 官网 | Bearer 官网会话；无 body；有效资格返回 `{url, expiresAtEpochMs}`，url 含短票；401 登录过期，403 无产品资格 |
| `GET /api/v1/console/learn-everything/authorize` | 官网内部 | Cookie 或 `X-Original-URI` 中短票；有效返回 204、`X-Learn-User`、`X-Learn-Entry-Cookie`；无效返回403 |
| `POST /official-api/api/v1/auth/refresh` | 官网 | `{refreshToken}`；返回官网 access/refresh token 与到期时间；仅既有会话续期 |
| `GET /official/learn-everything/` | broker/worker | 经官网短票鉴权；HTML 入口冷启动先显示准备页，其他调用仍等待进程就绪 |
| `GET /official/learn-everything/platform/ready` | broker | 同一鉴权链；只返回本人 `{state: starting\|ready\|failed}`，禁止公共缓存 |
| `GET /official/learn-everything/api/v1/account/context` | worker | 官网身份、个人空间和功能能力；不返回任何 token 或密钥 |
| `GET /official/learn-everything/platform/activity` | worker | 模型与备课状态；用于回收及发布前排空检查 |
| `GET /official/learn-everything/platform/storage` | worker | 本人配额、用量分类与可管理项 |
| `POST /official/learn-everything/platform/storage/download` | worker | 管理面板选项，返回受限本人单文件或ZIP流；具体结构以 `le_platform/storage_api.py` 为准 |
| `POST /official/learn-everything/platform/storage/delete` | worker | 管理面板确认后的项及版本；本人归属、路径与版本校验；具体结构同上 |
| `GET /v1/models`、`POST /v1/chat/completions` | 模型网关 | 服务端 Bearer、`X-End-User`、每次调用唯一 `X-Event-Id`；401/403 权限失败、402 积分不足不做收费重试 |

浏览器 `server_session.js` 每 120 秒通过现有官网会话获取新的5分钟短票；Nginx 写入 HttpOnly、Secure、SameSite Cookie。不要把短票 URL 写入日志、文档或截图。

worker 仅监听回环地址，并要求 `X-Learn-User` 与 `X-Learn-Worker-Key` 同时匹配；broker 去除客户端伪造的同名头后重新设置。每账号独立 Unix UID、数据库、向量库、资料、临时目录与5GiB空间。桌面操作、宿主命令、剪贴板及任意文件路径不能通过网页调用。

## 兼容性

沿用官网现有接口及 Gradio 4.44.1。学习服务的 `default` 身份仅存在于单个隔离 worker 的私有数据库内部，不代表跨账号共享身份。SSE 保持流式传输，不缓存、不聚合。静态代码允许按版本缓存，个人 HTML、配置、资料和学习记录不得公开缓存。
