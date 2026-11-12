# 本地演示：三分钟把页面跑起来

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

浏览器访问 <http://127.0.0.1:8000/app/?ticket=demo>。

- `?ticket=demo` 只是一张「我是 demo 用户」的假票，页面会把它存进 sessionStorage 并从地址栏抹掉；
- 换 `ticket=别的名字` 就是另一个租户，两边数据互不可见（这就是行级安全在起作用）；
- 页面右上角没有登录按钮是正常的，正式环境由官网发真票。

## 4. 看点

- **知识节点**：四行节点，掌握度滑杆直接改（PATCH 落库）。
- **今日复习**：两张卡，翻面后点 1/2/3/4，下次到期时间会按阶梯间隔往后走。
- **测验**：点开「第一章小测」，交卷后看分数与讲评；答案在交卷前不会下发。
- **学习路径**：填周数/每周学时，生成按依赖排好的周计划。
- **每日报告**：生成当天报告，句子由当天的进度记录拼出来。
- **对话**：需要配置真实模型网关（`LEARN_GATEWAY_URL` / `LEARN_GATEWAY_PRODUCT_KEY`），否则会报网关不可达。

## 5. 想确认「租户真的隔离」

用两个浏览器窗口分别打开 `?ticket=alice` 和 `?ticket=bob`，各建一个项目，互相看不到；再打开 `?ticket=demo` 又是另一套数据。
