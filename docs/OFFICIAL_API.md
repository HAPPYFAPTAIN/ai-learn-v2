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
| `POST /official/learn-everything/platform/storage/download` | worker | `{expectedAccount, items:[item]}`；返回本人单文件或ZIP流，最多100项、批量512MiB |
| `POST /official/learn-everything/platform/storage/delete` | worker | `{expectedAccount, confirm:true, item}`；本人归属、路径与版本校验；生成中返回409 |
| `GET /v1/models`、`POST /v1/chat/completions` | 模型网关 | 服务端 Bearer、`X-End-User`、每次调用唯一 `X-Event-Id`；401/403 权限失败、402 积分不足不做收费重试 |

浏览器 `server_session.js` 每 120 秒通过现有官网会话获取新的5分钟短票；Nginx 写入 HttpOnly、Secure、SameSite Cookie。不要把短票 URL 写入日志、文档或截图。

每份学习HTML固定其渲染时的官网账号。浏览器访问 `config`、`info`、`upload`、`queue/*`、`api/*`、`run/*`、`call/*` 和 `platform/storage*` 时，必须带 `X-Learn-Expected-User`；EventSource通过 `__le_owner` 查询参数传递同一值。该字段只是页面归属约束，不能替代短票授权；broker仍独立验证Cookie并比较账号。缺少约束或不匹配返回409及 `X-Learn-Error: ACCOUNT_CHANGED`，在创建/选择worker前终止。broker转发时去除内部查询参数，个人HTML/配置/数据禁止缓存。

续期前通过既有 `/console/me` 核对账号；另一个标签页换号、退出，或后台刷新返回前账号已变化时，旧页停止续期和业务请求、关闭队列流/弹窗并隐藏旧内容，引导重新进入。部署此版本后，未带页面归属约束的旧标签页需刷新。自动化/受控API客户端应在已知验证账号下附带相同字段，不能从用户输入任意指定账号。

worker 仅监听回环地址，并要求 `X-Learn-User` 与 `X-Learn-Worker-Key` 同时匹配；broker 去除客户端伪造的同名头后重新设置。每账号独立 Unix UID、数据库、向量库、资料、临时目录与5GiB空间。桌面操作、宿主命令、剪贴板及任意文件路径不能通过网页调用。

## 兼容性

沿用官网现有接口及 Gradio 4.44.1。学习服务的 `default` 身份仅存在于单个隔离 worker 的私有数据库内部，不代表跨账号共享身份。SSE 保持流式传输，不缓存、不聚合。静态代码允许按版本缓存，个人 HTML、配置、资料和学习记录不得公开缓存。

## 存储请求对象

先 GET storage 取得 `accountId`、`storage`、`items`；后续请求的 `expectedAccount` 必须等于本次返回的 accountId，切换账号后旧页操作返回409。item 从当前列表选取：

- 文件：`{kind:"file", path, version}`，仅允许 workspace/tmp 下本人文件，version 不匹配拒绝。
- 索引资料：`{kind:"source", index, id}`，复用当前账号索引的实际删除/下载。
- 课程：`{kind:"project", id}`，导出 Markdown 或执行本人课程级联删除。
- 问答：`{kind:"conversation", id}`，导出 JSON 或执行本人历史删除。

非法 JSON、数量或未确认删除返回400；账号变化、文件变化或后台生成返回409；同账号已有下载准备返回429。超出空间额度时 broker 对新上传/生成返回507，但保留空间查看、下载和清理入口。删除不能盲目重放，客户端须展示明确确认并刷新列表。

## 真实接口契约测试

`OFFICIAL_SITE_SOURCE` 指向官网仓库后，运行 `pytest tests/test_official_contract.py`。测试使用官网实际 FastAPI 账号/短票代码与临时 SQLite，再经过本仓库实际 broker 校验授权、匿名拒绝、伪造用户头、篡改票据和资格撤销。测试不连接生产数据库，也不调用收费模型。未提供官网源码时明确跳过，不能宣称真实接口验证通过。
