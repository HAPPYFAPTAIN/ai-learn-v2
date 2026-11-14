# 本地开发与变更边界

本仓库保持官网入口定位。本轮仅补充开发约束与本地验证说明，不引入桌面分发、Mac 安装器、本机钥匙串存储或新的 Gradio 样式覆盖层。

## 两条开发线

- 旧 Gradio 系统保持原样；已有 Linux 官网入口与隔离机制继续按现有发布流程维护。此前 PR 中的助教流式输出、备课队列、Mac 兼容与 UI 改动均从本轮交付撤回，不作为服务端性能优化一并上线。
- 新页面按多租户规划在 React 工程实施，不经过 Gradio 过渡。当前 `feat/learn-core-phase0` 分支包含 `learn_web/`、`learn_api/` 与 `learn_core/`，其本地演示说明为该分支的 `docs/learn-core/local-demo.md`。该分支尚未合并时，不把演示命令用于当前 main，也不将它的功能夹带到本 PR。

后续涉及模型调用次数、预生成范围、并发、任务队列、嵌入服务或新依赖的变更，分别说明预算、验证结果与回退方式，经审查后交付。页面观赏性调整不能证明服务器容量足够。

## macOS 本地验证当前官网源码

macOS 可以运行开发检查和已有的无数据组件预览；这不要求在官网源码中分发 Mac 桌面程序。先在独立目录检出本仓库，Python 使用 3.11，Node 版本与 CI 一致：

```sh
git clone --recurse-submodules git@github.com:AetherMindHarness/ai-learn.git ai-learn-review
cd ai-learn-review
python3.11 -m venv .venv
.venv/bin/python -m pip install -r runtime/requirements-browser.txt
source .venv/bin/activate
npm ci
npx playwright install chromium
scripts/ci-check.sh
```

平台打包检查要求改动已提交、工作区干净、子模块位于固定提交。脚本检查的是现有平台与浏览器回归，不等同于 macOS 完整学习业务或 Linux 生产验收。

手动看已有首页组件（不接账号、不调模型、不访问学习资料）：

```sh
.venv/bin/python scripts/preview_home_rail.py --port 7863
```

浏览器打开 <http://127.0.0.1:7863>，结束后按 Control+C。自动浏览器回归会自行占用相同端口，运行前先关闭手动预览。此页仅验证现有首页组件，不是完整课程、资料库或 API Key 功能测试入口。

## 本地完整学习测试

此前已验证的 Mac 学习版本应保留在独立本地分支与原目录，继续使用它自己的虚拟环境、启动脚本及数据；不要用官网 main 覆盖该目录。官网修订在另一个工作树进行，撤回 PR 改动不等于删除本地测试版本。

测试 React 版本时另行检出 `feat/learn-core-phase0`，按该分支的演示文档建立独立 PostgreSQL 数据库并初始化角色、扩展和迁移；构建 `learn_web` 后再启动 API。开发认证仅限本机回环地址，测试租户、数据库、文件存储及模型网关凭据均与生产隔离，不能复用生产数据库或向生产开放开发票据。

本地测试通过后，仍需分别审查 React 功能、租户隔离及服务器资源上限。本说明不修改现有鉴权、模型计费、存储隔离、依赖锁或部署配置。
