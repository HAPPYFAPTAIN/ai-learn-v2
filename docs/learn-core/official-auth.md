# 复用官网登录的新版 API 边界

公司机已接入官网。[官网产品页](https://8.130.144.193/official/products/learn-everything/)是用户入口，登录并取得资格后点击“打开学习工作台”。无有效票据直接访问受保护入口会返回 403。当前反向代理、服务地址及运行配置见[公司机部署与发布](server-release.md)。

## 协议

1. 官网原入口负责换短票与设置 `learn_entry`；新版前端不保存 URL ticket。
2. 可信 nginx 覆盖写入 `X-Learn-Internal-Secret`，保留浏览器 Cookie 与预期账号头；API 只监听回环/受控内网。
3. API 使用官网已有 `GET http://127.0.0.1:18030/api/v1/console/learn-everything/authorize`，传 `Cookie: learn_entry=...` 和学习产品 `X-Original-URI`。只接受 204 与合法 `X-Learn-User`；401/403 分别表示登录/资格问题，其余视为上游不可用。
4. API 用此官网返回的账号查租户。客户端 `X-Learn-User` 无法代替复核；其与复核结果不符也拒绝。
5. `/api/v2/me` 初始化不要求预期账号；其余接口要求 `X-Learn-Expected-User`，SSE 可用 `__le_owner`。不符/缺失即 409，发生在业务数据库访问之前。
6. 非只读请求检查显式配置的公开 Origin 和 `Sec-Fetch-Site`，不从可伪造的转发头推断可信站点。
7. 官网返回的 `X-Learn-Entry-Cookie` 作为 Set-Cookie 透传，保留 HttpOnly/Secure/SameSite/Path；仅接受名为 learn_entry 的 Cookie。API 响应统一 no-store。

新版前端每 120 秒复用官网已有续期流程，账号变化时清缓存、停止请求。正常模式不接受 `X-Learn-Ticket` 或旧 `le_ticket` 开发票。

## 候选部署所需配置

- `LEARN_INTERNAL_SECRET`：至少 32 字符的独立随机代理密钥，以受控环境文件注入，不能放入 Git 或前端构建参数。
- `LEARN_PUBLIC_ORIGIN`：确切公开站点，例如 `https://example.com`，无路径。
- `LEARN_AUTHORIZE_URL`：默认上述官网内部地址；跨机器部署需受控内网路由。
- nginx 必须覆盖内部密钥/身份头，转发 Host/Origin/浏览器 Cookie；禁止客户端自带内部头被直接透传。
- API 的 `/api/v2` 与前端构建 API 前缀应由同源代理对应，静态深链接需回退，API/SSE 不缓存。
- 测试账号需白名单或原规划的账号映射分流；未经迁移的账号继续走旧 broker。静态资源不含个人数据，业务 API 始终复核身份。

生产站点复用官网已有路由；调整前核对当前 Nginx 配置和独立保存的代理密钥。

`LEARN_DEV_AUTH=1` 仅用于隔离本地库，不能用于服务器试用站；本机 loopback 启动器不进入发布包。

## 验证

`tests/learn_core/test_official_auth.py` 在无数据库条件下验证现有 GET/204/header 协议、续期 Cookie、伪造头、缺失密钥、跨站写入、预期账号缺失/切换与官网异常，无任何本地鉴权降级。仍需真实官网两到三个账号、产品资格、失效/续期、nginx 头覆盖和 HTTPS 浏览器验收。
