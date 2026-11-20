# 开发文档

| 文档 | 用途 |
|---|---|
| [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md) | 官网定位、旧系统冻结、React 重写与 Mac 本地测试边界 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 官网运行层、账户隔离、源码与发布边界 |
| [OFFICIAL_API.md](OFFICIAL_API.md) | 官网入口、授权、网关及空间接口契约 |
| [公司机 v2 部署与发布](learn-core/server-release.md) | 官网用户入口、依赖和产品密钥、Actions 发布、故障回退 |
| [OFFICIAL_DEPLOYMENT.md](OFFICIAL_DEPLOYMENT.md) | 旧版 Gradio 固定运行时、候选构建、发布门禁与回退 |
| [OFFICIAL_MAINTENANCE.md](OFFICIAL_MAINTENANCE.md) | 上游来源、升级、资源保留和首页样式回归 |
| [AGENT_EXECUTION.md](AGENT_EXECUTION.md) | 共享 Agent 与官网工具执行边界 |
| [PREVIEW_COMPONENTS.md](PREVIEW_COMPONENTS.md) | Linux 文档预览与浏览器资源 |
| [TEXT_POLISH.md](TEXT_POLISH.md) | 网页输入润色与过期结果保护 |
| [ACTION_LEARNING.md](ACTION_LEARNING.md) | 课程行动、记录与兼容组件设计 |
| [ACCOUNT_INTEGRATION.md](ACCOUNT_INTEGRATION.md) | 上游账户接口设计；官网实现以 OFFICIAL_API 为准 |
| [local-ui-preview.md](learn-core/local-ui-preview.md) | 仅检查本地 React UI：上传进度、看板图表与课文批注 |
| [frontend-backend-handoff.md](learn-core/frontend-backend-handoff.md) | React 前端与账号后端交接、当前接口契约和联调顺序 |
| [ai-platform-backend-handoff.md](learn-core/ai-platform-backend-handoff.md) | 账号后端与 AI 平台接入、产品密钥和供应商 Key 的边界、网关联调 |
| [personal-api-key.md](learn-core/personal-api-key.md) | 个人 Key 按账号加密存储、编辑、删除及接口 |
| [个人 Key 官网切换](learn-core/personal-api-key-production.md) | 运维从共享网关切换个人 Key、密钥配置、服务重启、验收与回退 |
| [online-issues-v2.md](learn-core/online-issues-v2.md) | v2 线上问题 1–11 修复、侧栏与常驻助手、资源影响及待完成的服务器验收 |
| [CHAT_AUTO_LANGUAGE.md](CHAT_AUTO_LANGUAGE.md) | 对话语言策略 |
| [CHAT_RETRIEVAL_STATUS.md](CHAT_RETRIEVAL_STATUS.md) | 检索状态反馈 |
| [LEARNING_AGENT.md](LEARNING_AGENT.md) | 学习业务基础设计 |

历史验收报告、导出课程、界面重设计草案及桌面安装/打包文档从当前树移除，可从上游固定提交或 Git 历史查阅。许可证与来源声明保留在资源旁及 `third_party/`。
