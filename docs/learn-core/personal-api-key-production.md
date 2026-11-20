# 官网切换为用户个人 API Key：运维操作单

2026-11-20 用户确认：官网账号各自导入、编辑和删除自己的 API Key，模型调用使用本人供应商额度。沿用官网登录与资格校验，不开启开发认证。截图仍显示“由官网网关管理”意味着运行 API 仍在 gateway 模式；前端禁用输入框是服务器返回能力的结果，不能只删除 disabled。

## 1. 准备与维护窗口

- 部署包含个人 Key 和编辑接口的已审阅提交，记录完整 SHA。现有依赖、数据库迁移、备份恢复、chat worker 和发布接收器准备仍按 [server-release.md](server-release.md) 完成；此文不替代这些前置项。编辑功能没有新增数据库迁移、第三方依赖、worker 或并发。
- 核对 `0008_model_providers` 已应用；未应用则按部署文档分角色升级至 head。已到 head 的数据库不要再次向旧 revision 执行 upgrade。运行账号仍为受 RLS 限制的 `learn_app`。
- 备份数据库、上传文件、原服务配置，以及已存在的个人 Key 加密密钥。保留上一版本源码与环境。若已有个人连接，必须复用原加密密钥。
- 暂停新的学习生成请求，等待 llm/chat/io 的排队及执行中任务处理完，再统一切换；不要让 API 与旧 worker 分别运行不同模式。原网关任务不会自动迁移为个人任务。

## 2. 服务端加密配置

公司机布局：`base="$HOME/data/ai-learn/standalone-v2"`。官网用户的供应商 Key 经 HTTPS 表单送至学习 API，由 `model_provider` 按账号加密保存，不放在运维环境文件；下面配置的是用于加解密的服务密钥，二者不同。

若从未配置过个人 Key 加密密钥，部署用户在服务器执行以下命令。它以 0600 权限新建文件，不将密钥打印到终端；文件已存在时停止，避免覆盖。不要在已有个人连接但丢失原加密密钥时生成替代值。

```sh
base="$HOME/data/ai-learn/standalone-v2"
"$base/core-venv/bin/python" - <<'PY'
import os
from pathlib import Path
from cryptography.fernet import Fernet

target = Path.home() / 'data/ai-learn/standalone-v2/conf/personal-models.env'
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as stream:
    stream.write('LEARN_MODEL_SOURCE=personal\n')
    stream.write('LEARN_PROVIDER_ENCRYPTION_KEY=' + Fernet.generate_key().decode() + '\n')
print('个人模型配置文件已创建；请安全备份，不要复制到聊天或 Git。')
PY
```

若原加密配置在其他文件，由运维安全复用原值，不执行生成步骤。密钥单独安全备份并纳入恢复演练，发布、重启时绝不重新生成。

为现有用户服务创建或审查对应 drop-in，API、worker@llm、worker@chat、worker@io、reaper 使用同一配置。在 `~/.config/systemd/user/<完整服务名>.service.d/90-personal-models.conf` 放置：

```ini
[Service]
EnvironmentFile=%h/data/ai-learn/standalone-v2/conf/personal-models.env
```

这里完整服务名示例为 `ai-learn-v2-api`，worker 为 `ai-learn-v2-worker@llm` 等，reaper 为 `ai-learn-v2-reaper`。在服务器本机通过 `systemctl --user cat <unit>` 核查加载次序，确保没有更晚的 EnvironmentFile 将其覆盖为 gateway；不要将含凭据的配置输出外发。不要直接输出 `systemctl show -p Environment`。

出站网络需允许供应商公网 HTTPS 443 及 DNS。仅支持 OpenAI 兼容的 `/models`、`/chat/completions`，不支持内网、本机、重定向或需要原生协议的接口。官网入口继续使用有效 HTTPS。

## 3. 切换与核验

在已完成备份、队列排空和候选验证的维护窗口，按部署文档切换源码，然后：

```sh
systemctl --user daemon-reload
systemctl --user restart ai-learn-v2-api.service \
  ai-learn-v2-worker@llm.service ai-learn-v2-worker@chat.service \
  ai-learn-v2-worker@io.service
systemctl --user is-active ai-learn-v2-api.service \
  ai-learn-v2-worker@llm.service ai-learn-v2-worker@chat.service \
  ai-learn-v2-worker@io.service ai-learn-v2-reaper.timer
curl -fsS http://127.0.0.1:18080/healthz
```

使用真实官网登录后的浏览器，检查 `/official/learn-everything/api/v2/models`：`source` 为 `personal`、`providerImportEnabled` 为 `true`。只检查这些非敏感字段，不复制登录 Cookie。健康检查成功只能证明进程运行，不能替代下面验收。

- `source=gateway`：加载的配置或服务进程仍未切换，核查所有环境文件及重启结果。
- `source=personal` 但 `providerImportEnabled=false`：密钥为空、格式无效或 cryptography 依赖缺失，输入仍会禁用，修正服务端配置再重启。
- API 可导入但生成不能解密：核查 worker 与 API 是否加载同一密钥，不要重新生成密钥。

## 4. 两账号验收

1. 未导入的账号看到“暂无可用模型”，上方不出现旧网关 DeepSeek；旧课程、资料和笔记仍在。
2. 用本人 Key 添加供应商，验证、选择主模型、刷新后仍保留。目录验证不发起生成；实际生成消耗供应商额度，不通过官网积分网关扣费，官网访问资格仍须满足。
3. 编辑供应商：名称、备注、模型列表可保存；Key 输入不回显，留空保留，填写后替换。更换 API 地址必须填写对应 Key；无效 Key 或目录验证失败保留原配置。
4. 移除原主模型后要求重新选择；打开两个编辑窗口，过期版本保存返回冲突，不覆盖新值。删除供应商需确认，已有学习内容保留。
5. 两账号互相看不到、不能编辑或删除对方的连接。分别生成路线、章节、问答、测验和复习，核对任务结果及供应商用量；记录耗时和 finish_reason，不记录 Key。

资源：供应商表与加密逻辑已存在。编辑最多触发一次用户主动的 `/models` 校验，复用账号交互租约，不新增常驻进程、生成请求、后台轮询或预生成；使用现有 llm/chat 队列并发。供应商自身限流、余额与调用费用由用户承担。

## 5. 回退

先暂停新请求并处理在途任务，再让 API 与所有 worker 一致恢复原 gateway 配置并重启。保留个人连接表和原加密密钥，不删除用户数据。网关模式下需从网关目录重新选择主模型：保存个人主模型可能已覆盖旧偏好，不能承诺自动恢复旧选择。源码与数据库兼容性、完整发布回退仍按主部署文档执行。

本说明不是已执行的生产记录；实际部署需反馈活动提交、两个非敏感能力字段和两账号验收结果。
