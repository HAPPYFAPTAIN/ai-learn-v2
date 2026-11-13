# Mac 使用说明

## 当前电脑

在项目目录双击 `run_macos.command`。现有 Python 3.11 环境已可复用，无需再次安装依赖。

启动器会检测依赖、选择空闲的本地端口，等待网页配置真正可读后再打开浏览器。安装了 Microsoft Edge 时优先使用 Edge。终端会显示实际网址，不要始终假定端口是 7860。

保持终端窗口打开。按 Control+C 停止本次启动的后端；启动失败时查看项目下 `.tmp/macos-server.log`。

## 从新下载的源码安装

先准备 Git 和 uv，或 Python 3。然后双击 `setup_macos.command`。安装器会初始化 Kotaemon 子模块，在项目内建立 Python 3.11 环境，安装 `learning_ext/requirements-macos.txt` 中的固定依赖、仓库内的 ktem/kotaemon，以及 NLTK 数据。

安装可能需要数分钟和网络访问。下载失败时可重新运行；安装器不删除现有虚拟环境和学习数据。如果已有 `.venv` 使用其他 Python 版本，会提示手动备份并移开该目录。

终端用法：

```zsh
./setup_macos.command
./run_macos.command
./run_macos.command --check
./run_macos.command --no-browser --port 7870
```

安装固定版本来自当前 Apple Silicon Mac 上的依赖快照；Intel Mac 需要进一步实机验证。

## 配置模型

在「模型配置」选择平台、填写密钥和模型 ID。

- 保存连接：在本机记住配置，不需要请求云模型。
- 测试连接：访问模型平台，验证网络、密钥、模型权限。
- 启用连接：验证后写入运行配置并切换当前模型。

Mac 的连接列表存放在 `ktem_app_data/model_connections.macos.enc`，加密密钥保存在登录钥匙串中。首次访问若 macOS 询问授权，确认发起者为本项目使用的 Python。拒绝或锁定钥匙串时会显示提示，解锁并允许后重试。

现有应用的运行配置仍位于 `kotaemon/.env`，包括当前启用的密钥。本次在 Mac 上将其访问权限限制为当前用户可读写，不能将其当作可公开分享的文件。无需把密钥发给开发助手。

Hugging Face 离线开关只控制模型下载。保存本机连接不依赖它；使用 DeepSeek 等云模型仍需要网络。

## 兼容范围

浏览器中的学习流程、复习、测验及模型配置使用现有跨平台后端。Mac 终端命令走 zsh，文件打开走系统 `open`，剪贴板走 `pbcopy/pbpaste`。本地 Ollama 可从应用目录、Homebrew 或 PATH 查找；检索模型本身仍需事先安装。

Windows UI Automation、桌面控件读取和自动点击尚未移植。工具清单会排除这些不兼容能力，课程提示应引导用户手动完成。不要将教程中的 Windows 命令直接放到 Mac 执行。

## 验证状态

启动入口在当前 Mac 上通过 `--check` 检查，依赖一致性检查通过。170 项相关自动化测试通过，4 项 Windows 专用测试跳过，覆盖平台提示、进程启动与停止、端口选择、HTTP 就绪判断、Mac 命令执行、加密保存与钥匙串错误处理。进程和钥匙串接口测试使用模拟，POSIX 命令退出码测试使用实际终端进程。

真实钥匙串写入、服务启动及 Edge 视觉验收仍需在允许这些操作的运行环境中完成。Codex 的自动审批服务当前返回 404（`codex-auto-review` 模型不可用），它与本应用的密钥保存逻辑无关。
