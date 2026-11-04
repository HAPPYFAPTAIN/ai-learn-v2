# 官网运行架构

浏览器通过官网产品页取得短票，经 Nginx 鉴权进入学习 broker。broker 再调用官网现有授权接口，确认账号后复用或创建该账号的独立 Unix worker。worker 加载 `custom_app.py → LearningApp → Kotaemon`，提供 Gradio 页面、队列、学习业务和资料处理。

## 责任边界

| 层 | 责任 |
|---|---|
| 官网账号服务 | 登录、产品资格、短票签名和续期 |
| `le_platform/broker.py` | 身份复核、实例准入、冷启动状态、代理与空闲回收 |
| `le_platform/worker.py` | 私有传输头校验、账号目录与环境、模型归属及工具边界 |
| `learning_ext/` | 学习路线、课程、复习、测验、笔记、看板、资料与网页交互 |
| Kotaemon | RAG、索引、原始页面组件和基础数据库接口 |
| 统一模型网关 | 模型权限、供应商调用和积分计量 |

## 运行与维护输入

Git checkout 是维护输入。已提交源码按 `runtime/release-policy.json` 生成不可变 release，布局保持 `source/`、`platform/`、`product/` 与原始组件声明 `input-stubs/`。运行时正常生成声明并记录摘要。

Kotaemon 仍以固定子模块获取；只有两个运行包、迁移文件、构建元数据、必要配置/帮助文本及许可证进入 release。上游测试、演示图片与独立 CLI 文档不属于官网运行包。本仓库测试和维护脚本在 CI/开发 checkout 使用，不复制到客户实例。

## 状态与权限

每个账号拥有独立数据库、向量资料、临时文件、缓存和5GiB个人空间。`default` 只在单个隔离进程内部表示本账号，不能混用为共享官网身份。网页工具受白名单和本人路径约束；宿主命令、桌面控制和软件安装不能执行。

部分学习模块还导入桌面兼容组件，因此保留其依赖和回归测试；完整 Windows 启动/安装/便携版入口不在此仓库。独立桌面实践演示页未注册到线上页面，已移除；课程中的网页实践组件保留。

详见 [接口契约](OFFICIAL_API.md)、[部署回退](OFFICIAL_DEPLOYMENT.md) 和 [维护与源码边界](OFFICIAL_MAINTENANCE.md)。
