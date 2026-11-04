# AI Learn 官网适配开发指南

## 范围与入口

此仓库维护 Linux 官网学习应用。上游桌面启动器、便携版打包及历史演示资料由 `HAPPYFAPTAIN/learn-everything` 保留；本仓库不分发 Windows 桌面应用。

- `learning_ext/`：学习页面、课程、资料、复习、测验和共享工具。
- `le_platform/`：官网鉴权、每账号独立 Unix UID/worker、模型网关、空间管理。
- `custom_app.py`：由 broker 为隔离账号启动的应用入口。
- `kotaemon/`：固定只读子模块；禁止直接修改依赖或生成 JS。
- 接口、部署与来源入口见 `docs/README.md`。

## 分支与交付

`origin` 为组织私有 `AetherMindHarness/ai-learn`，`upstream` 为只读参考 `HAPPYFAPTAIN/learn-everything`。改动经功能分支和 PR；不得直接覆盖生产发布、用户数据或密钥。清理当前文件不重写上游历史。

## 本地检查

```sh
python -m pip install -r runtime/requirements-test.txt
python scripts/check_repository.py
python -m pytest -q tests/test_learn_platform.py tests/test_learn_startup.py tests/test_official_release.py
```

浏览器验证见 README；Linux 完整学习回归需要固定运行时。测试和 CI 只证明相应验证范围，不把本地页面截图当成生产验收。

## 源码与发布边界

`runtime/release-policy.json` 列出运行源码目录及必要辅助文件。测试、文档演示图、输出目录、参考 TypeScript、桌面入口不进入发布包。新增运行资源需核对策略、实际读取位置和许可证；打包前运行回归和候选启动验证。

共享模块中的 Windows/桌面兼容分支仍受官网工具门禁保护，不能仅凭文件名删除。先检查实际导入、页面注册和测试，再移除不可达模块。所有新增二进制依赖应通过锁定版本与校验值在仓库外安装。

## 代码约定

业务 service 函数第一参数为 `session: Session`，模型调用走 `learning_ext.llm.chat/chat_json`。新增页面放 `learning_ext/pages/` 并注册到 `app.py`，提示词放相应 `prompts.py`。

CSS 经 `/le-presentation.css` 统一拼装，保留选择器优先级和主题变量。源码预览可刷新 CSS；生产采用不可变发布，不能在运行目录热改。JS 在应用启动时注入，更新需发布重启。离线模型及 NLTK 数据在部署前校验。
