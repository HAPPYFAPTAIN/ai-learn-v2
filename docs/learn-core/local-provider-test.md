# 本地个人供应商测试入口

这套工具仅用于本机隔离数据库。官网及在线测试统一走官网账号和模型网关；正常 API 不注册供应商添加接口，生产前端不启用该能力。

实现为 `scripts/dev/local_provider_gateway.py`（单进程内存代理）与 `scripts/dev/local_provider_api.py`（明确的开发 API 入口）。Key 只保留在代理进程内存，不写浏览器存储/业务库/配置文件，不回传 Key。刷新页面保留，重启代理清空；此前选择的本地模型会提示不可用，需要重新添加并选择。暂支持公开 HTTPS（443）的 OpenAI 兼容 `/models`、`/chat/completions`；不支持 Ollama、本机或内网服务，也不代表全部预设平台协议都已兼容。

先用已有流程准备独立数据库、迁移、队列和嵌入服务；在所有本地进程的受控环境中设置：

- `LEARN_DEV_AUTH=1`，数据库与文件目录必须是本地测试专用。
- `LEARN_LOCAL_PROXY_TOKEN`：本次会话临时随机值，至少 32 字符。
- `LEARN_GATEWAY_PRODUCT_KEY`：与上述临时值相同（不是供应商 Key）。
- `LEARN_GATEWAY_URL=http://127.0.0.1:18091/v1`。
- 可选 `DEEPSEEK_API_KEY` 供既有本地配置；也可不设，打开页面后添加供应商。

不要把实际值写进命令参数、Git 或前端环境文件。各终端共享同一次临时代理 token；重启整套本地进程时重新生成。

分别启动（仓库根目录，使用已安装依赖的解释器）：

```sh
python -m uvicorn scripts.dev.local_provider_gateway:factory --factory --host 127.0.0.1 --port 18091 --no-access-log
python -m uvicorn scripts.dev.local_provider_api:factory --factory --host 127.0.0.1 --port 8000
python -m procrastinate --app=learn_core.jobs.app.app worker --queues=llm --concurrency=1
python -m procrastinate --app=learn_core.jobs.app.app worker --queues=io --concurrency=1
npm --prefix learn_web run dev
```

通过 `http://127.0.0.1:8000/local-test/start` 进入，模型设置 → 自定义/预设 → 填 Key、地址和当前可用模型 ID → 验证并添加 → 上方设为主模型 → 创建学习计划。目录验证不发起付费生成，不代表已经验证每个模型都支持课程任务。生成时才会使用对应供应商额度。验证失败不会保存 Key；不直接返回供应商原始错误内容。

当前已编写隔离和模拟供应商回归；按用户要求，本轮没有个人 Key 真实调用或本地人工浏览器验收，不能标记为真实供应商兼容性验证通过。
