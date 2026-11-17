# 本地演示

React 新前端可直接执行 `cd learn_web && npm ci && npm run dev:demo`，用 Edge/Safari 打开 <http://127.0.0.1:5173/>。内存演示不会连接数据库和模型，见 [前端说明](../../learn_web/README.md)。

以下为后端数据库测试环境准备，不是免登录的生产启动方式。

这段只用于自己看效果，**不要**在生产机上开 `LEARN_DEV_AUTH`。

## 1. 起数据库和 API

```sh
cd ai-learn
export PYTHONPATH=.
export LEARN_DEV_AUTH=1                      # 演示用：任何 ticket 都当独立租户
export LEARN_DATABASE_URL=postgresql+psycopg://learn_app:app@127.0.0.1:5432/learn_dev
.venv/bin/python -m uvicorn learn_api.app:app --host 127.0.0.1 --port 8000
```

## 2. 灌一份演示数据（另开一个终端）

```sh
cd ai-learn
export PYTHONPATH=. LEARN_DEV_AUTH=1
export LEARN_DATABASE_URL=postgresql+psycopg://learn_app:app@127.0.0.1:5432/learn_dev
.venv/bin/python scripts/dev/seed_demo.py
```

## 3. 打开页面

浏览器联调见 [前端说明](../../learn_web/README.md)。新客户端不再保存 URL 中的 ticket；真实 API 模式需要先通过同源官网入口获得 Cookie，不能通过 `?ticket=demo` 在浏览器中切换账号。

- `LEARN_DEV_AUTH` 只供隔离测试库的 API 调试；测试客户端可用不同 `X-Learn-Ticket` 检查租户隔离，不能在生产启用。
- 页面右上角没有登录按钮是正常的，正式环境由官网发真票。

![项目列表](images/demo-projects.png)

## 4. 看点

- **知识节点**：四行节点，掌握度滑杆直接改（PATCH 落库）。
- **今日复习**：两张卡，翻面后点 1/2/3/4，下次到期时间会按阶梯间隔往后走。
- **测验**：点开「第一章小测」，交卷后看分数与讲评；答案在交卷前不会下发。
- **学习路径**：填周数/每周学时，生成按依赖排好的周计划。
- **每日报告**：生成当天报告，句子由当天的进度记录拼出来。
- **对话**：需要配置真实模型网关（`LEARN_GATEWAY_URL` / `LEARN_GATEWAY_PRODUCT_KEY`），否则会报网关不可达。

## 5. 想确认「租户真的隔离」

使用 `tests/learn_core/test_api_v2.py` 与租户隔离用例，在独立测试库中给不同测试客户端传不同 ticket，验证跨账号不可读写。前端旧标签页遇到账号变化会停止请求，不能跟随新账号继续操作。
