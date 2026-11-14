# AI Learn · 官网接入版

Learn Everything 的独立官网适配仓库。上游来自 [HAPPYFAPTAIN/learn-everything](https://github.com/HAPPYFAPTAIN/learn-everything)，完整保留上游 Git 历史；Kotaemon 以固定子模块管理。上游提交、子模块与官网适配来源见 [INTEGRATION.json](INTEGRATION.json)。

本仓库负责学习页面、学习业务和 Linux 官网运行适配；官网账号服务继续负责登录/资格/短票，统一模型网关继续负责模型权限和积分。当前适配面向 Ubuntu 24.04、Python 3.11、Gradio 4.44.1。创建仓库和通过 CI 不等于已切换生产服务。

## 获取与开发

```sh
git clone --recurse-submodules git@github.com:AetherMindHarness/ai-learn.git
cd ai-learn
git remote add upstream https://github.com/HAPPYFAPTAIN/learn-everything.git
python3.11 -m venv .venv
.venv/bin/python -m pip install -r runtime/requirements-test.txt
.venv/bin/python -m pytest -q tests/test_learn_platform.py tests/test_learn_startup.py tests/test_official_release.py
```

私有仓库需本人已有 GitHub 访问权限；不要在 remote URL 中嵌入 token。服务器无 GitHub 凭据时可用 `git bundle` 传递经过审阅的分支，服务器的 origin 仍指向本仓库。使用 `git clone --branch <审阅分支> <bundle> <目录>` 后设置 origin；不向服务器复制个人 GitHub token。

## 目录与边界

| 目录 | 内容 |
|---|---|
| `learning_ext/`、`custom_app.py` | 学习业务及必要官网适配；仅提供官网运行入口 |
| `kotaemon/` | 固定上游子模块；禁止修改运行时依赖与生成 JS |
| `le_platform/` | 官网鉴权代理、每账号独立 UID/worker、模型归属、5GiB空间及管理界面 |
| `runtime/` | 已验证 Linux 依赖锁、向量模型和 NLTK 校验数据、轻量测试依赖 |
| `deploy/` | 学习服务单元及官网反向代理模板 |
| `scripts/official_release.py` | 从已提交源码构建、核验、安装不可变候选发布 |
| `scripts/activate_official.py` | 复用既有学习服务的备份、切换、回退流程；显式指定目标及主机名 |
| `scripts/preview_home_rail.py` | 真实 Gradio 首页组件复现；无账号、模型或资料访问 |
| `tests/browser/` | 首页列表、链接、响应式的真实浏览器回归 |

本地 macOS 开发的检查范围、React 重写分支与旧版测试隔离见 [本地开发与变更边界](docs/LOCAL_DEVELOPMENT.md)。

## 接入与发布

- [接口契约](docs/OFFICIAL_API.md)：接口所有方、请求响应、资格/身份、模型与存储边界。
- [部署与回退](docs/OFFICIAL_DEPLOYMENT.md)：依赖、候选包、服务器检出、正式切换、验证与回退。
- [来源与升级](docs/OFFICIAL_MAINTENANCE.md)：与官网单仓副本关系、上游更新、页面异常根因及检查。
- [上游架构](docs/ARCHITECTURE.md)、[原账户接入设计](docs/ACCOUNT_INTEGRATION.md)：桌面主体与原接口预留；官网模式以本仓库的接口契约为准。

官网模式保持账号数据库、资料和模型计量隔离；网页不能控制共享服务器桌面或安装软件。`default` 只表示一个隔离 worker 内的单用户，不是官网共享身份。Windows 启动和打包入口在上游固定版本维护，本仓库不分发桌面应用。

## 首页布局与浏览器验证

```sh
.venv/bin/python -m pip install -r runtime/requirements-browser.txt
.venv/bin/python scripts/preview_home_rail.py --port 7863
# 另一个终端，或让 playwright.config.mjs 自动启动测试页：
npm ci
npx playwright install chromium
PATH="$PWD/.venv/bin:$PATH" npm run test:browser
```

手动启动的复现页请先退出，再运行自动浏览器测试。CI 在独立环境中启动它，不访问生产。完整学习业务回归需要 Linux 完整运行时；轻量平台测试不冒充完整业务验收。

## 源码和发布包范围

运行包由 `runtime/release-policy.json` 选择运行目录和辅助文件，排除测试、演示图、导出资料、参考 TypeScript 及开发产物。Kotaemon 子模块保持原提交；仅选择其必要运行内容发布，不修改子模块。CI 用 `scripts/check_repository.py` 防止输出、缓存、数据库和安装二进制重新入库。浏览器依赖、图片、字体及许可证按运行引用保留。

[文档索引](docs/README.md) 与 [维护边界](docs/OFFICIAL_MAINTENANCE.md) 解释仍保留的共享桌面兼容依赖。
