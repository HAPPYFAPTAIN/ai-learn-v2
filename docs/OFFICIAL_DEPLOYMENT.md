# 官网部署与回退

本文适用于保留的旧 Gradio 服务。当前官网工作台运行 React/FastAPI v2，见[公司机部署与发布](learn-core/server-release.md)。

## 既有部署兼容

部署布局继续使用独立不可变 release：`source/` 放主体和 Kotaemon，`platform/le_platform/` 放适配，`product/` 放运行锁和单元模板。Git checkout 仅为维护输入；运行中的用户进程不直接引用可变 checkout。

当前实现约定数据卷挂在 `/data`，产品根目录为 `/data/learn-everything`，Python 为 `runtime/python311/bin/python`。账户数据、私有环境文件、模型缓存和发布目录保持分开。迁移到新主机时必须先按这一布局初始化，不能仅执行 `python custom_app.py` 后直接开放公网。

配置文件只保存在服务器私有目录，示例见 `deploy/service.env.example`。以原有服务为迁移来源时，激活器复用现有网关配置和账号数据，不导出密钥、不重建账号库。不得把客户资料复制进 Git checkout。

## 运行时

Python 3.11 虚拟环境使用 `runtime/requirements-linux-py311.lock`，并从固定 Kotaemon 子模块安装 `kotaemon/libs/kotaemon` 与 `kotaemon/libs/ktem`（`pip install --no-deps`）。系统软件见 `runtime/apt-packages.txt`。不要在运行中的环境升级依赖。

MiniLM 模型按 `runtime/model.json` 的 repository、revision 和逐文件 SHA256 下载到 `runtime/models/multilingual-minilm`。NLTK 按 `runtime/nltk.json` 下载并校验后展开到 `runtime/nltk`。运行默认离线，缺文件应在发布前处理，不允许每次开户临时联网下载。

```sh
/data/learn-everything/runtime/python311/bin/python scripts/verify_runtime.py
```

此命令检查268个锁定包、模型及152个NLTK解压文件的SHA256，不修改运行时。解压数据清单从 `nltk.json` 中已验证SHA256的原始压缩包生成；原压缩包可清理，若仍保留则同时校验。新环境先独立初始化，验证通过再投入使用。

## 从源码生成候选

```sh
git submodule update --init --recursive
python3 scripts/official_release.py pack --output output/official
```

要求源码已提交、工作区干净、子模块提交一致。`runtime/release-policy.json` 只选择运行目录及必要辅助文件；测试应从开发 checkout 运行，不再随生产包发布。输出 archive、SHA256、源提交和所有输入摘要。`.pyi` 原始声明另存 `input-stubs`，发布安装时正常构建两份运行声明，不把生成文件当作手工源码修改。

将包复制到已确认服务器，先核对传输前后的 SHA256，再在服务器 checkout 中执行：

```sh
sudo python3 scripts/official_release.py install /path/to/reviewed-release.tar.gz
python3 scripts/official_release.py verify /data/learn-everything/releases/RELEASE_ID
```

install 只创建新版本和构建声明，不切换服务、不创建客户实例、不修改 Nginx。它不覆盖已存在的 release。失败的 `.preparing` 目录保留用于排查，不自动删客户路径。

## 切换门禁

正式切换需先核对主机、运行版本、活动请求/生成任务、容量和备份空间，并完成候选账号、模型、资料和隔离验收。给维护者列明仅学习服务的影响范围及回退点，获得部署授权后再执行：

```sh
python3 scripts/activate_official.py --host USER@HOST --expected-hostname VERIFIED_HOSTNAME --release /data/learn-everything/releases/RELEASE_ID
```

该脚本由官网原激活流程迁移而来：持有发布锁、校验输入和构建、检查后台生成、备份单元和数据、仅切换学习服务、验证 broker 健康，失败回退。它不部署官网静态站；不会自动安装本仓库 `deploy/official-integration.nginx.conf` 替换共享站点配置。修改 Nginx 时只合并学习相关 location，先备份、`nginx -t`，再按窗口 reload。

```sh
python3 scripts/activate_official.py --host USER@HOST --expected-hostname VERIFIED_HOSTNAME --rollback /data/learn-everything/backups/BACKUP_ID
```

回退恢复旧服务和配置，保留新账号数据；不自动反向迁移数据库。Nginx 若被其他维护任务改动，拒绝覆盖，需人工合并。正式发布不应使用测试复现页代替真实学习服务。

## 上线核验

- 官网普通账号进入、无资格与过期资格拒绝、短票续期；冷启动准备页及热进入。
- 两账号同名课程/资料不能互读，单账号只启动一个 worker，容量满与后台生成保护。
- 真实模型目录及一次受控问答，计量归属正确；402/403 不重复扣费重试。
- 资料上传、检索、原件下载、空间分类；SSE持续流式；本人确认删除与错误账号拒绝。
- 首页在390/1280/1920 CSS像素下编号同线、导航无默认下划线，宽屏双栏、窄屏堆叠。
- 记录实际源码提交、release ID、回退点、测试结果；候选通过不能标记“已上线”。
