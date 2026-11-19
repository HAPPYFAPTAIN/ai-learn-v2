# learn-core 运维手册

这一页只讲「部署之后要盯着什么」。开发与接口见 `phase1-report.md`。

## 僵死任务回收（必须有）

Procrastinate 只在任务被**正常处理**时改状态。worker 被 OOM、被 `systemctl stop`
或机器重启打断时，「执行中」的任务会一直挂着；更麻烦的是它占着
`lock = tenant:channel`，同一租户同一通道后面的任务全部排队等它 ——
表现为「某个用户的生成一直不出结果，其他人正常」。

`learn_core/jobs/reaper.py` 会查心跳超过阈值的 worker，把它名下的任务重新入队。
需要一个定时器每 10 分钟跑一次：

```sh
# 沿用新版发布约定中的服务账号、目录和环境文件
cp deploy/learn-reaper.service deploy/learn-reaper.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now learn-reaper.timer
```

验证：

```sh
systemctl list-timers learn-reaper.timer        # NEXT 应该在 10 分钟内
journalctl -u learn-reaper.service -n 20        # 每次输出 reaped N job(s): ...
```

正常情况是 `reaped 0 job(s): -`。出现具体 id 说明有 worker 死过，
去 `journalctl -u learn-worker` 找它最后一次心跳前在干什么。

阈值默认 120 秒：worker 心跳 10 秒一次，留 12 倍余量，避免把「刚好在跑
长任务」的 worker 误判为死。任务本身超过 2 分钟没心跳才该被杀。

## 其它需要定时跑的

| 事项 | 频率 | 说明 |
|---|---|---|
| `learn-reaper.timer` | 10 分钟 | 上面这个，唯一必须的 |
| 备份 | 每天 | `pg_dump` + `SET row_security=off`，否则导出会按租户过滤 |
| 磁盘水位 | 每天 | `/data` 只有 3.2 G 余量时，先在管理后台降配额 |
| 过期租约清理 | 随请求 | `llm_lease` 在 `acquire()` 里顺手删，不需要定时 |

## 备份要点

RLS 对超级用户和 `BYPASSRLS` 角色不生效，但 `learn_owner` 是普通角色，
直接 `pg_dump` 会只导出「当前租户」——备份脚本必须先 `SET row_security = off`，
或者用 `learn_ops`（`BYPASSRLS`）连。

```sh
PGOPTIONS='-c row_security=off' pg_dump -U learn_ops -d learn_dev -Fc \
  -f /backup/learn-$(date +%F).dump
```
