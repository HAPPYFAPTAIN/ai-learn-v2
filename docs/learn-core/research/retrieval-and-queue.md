# 调研：PG17 + pgvector 0.8 的检索与队列效率

> 来源：外部调研子任务（2026-11-12），逐条核对过官方文档与源码；查不到的项目单列在末尾。
> 结论按我们自己的量级（384 维、单租户几千到几万块、总量百万内、50–200 租户、单机）取舍。

## 结论先行

1. **HNSW 内存不是瓶颈**：1 万条 384 维 raw 向量约 15 MB，pgvectorscale 这个量级不需要。
2. **真正的坑是「过滤后召回」**：共享 HNSW + 高选择性 tenant 过滤会返回不足 k 条。
   官方态度是租户分区/分表，迭代扫描只作兜底。我们已经做了 LIST 分区。
3. **Procrastinate 的 lock/queueing_lock 覆盖「同租户串行 + 去重」**，但必须自己重扫
   stalled job，否则僵尸任务会永久卡死该租户。我们已经写了 `learn_core/jobs/reaper.py`，
   还缺一个定时调用它的入口。

## 向量检索

- 机制：近似索引先扫描、后过滤。`hnsw.ef_search` 默认 40，过滤命中 10% 行时平均只匹配 4 行。
- 0.8 新增 `SET hnsw.iterative_scan = strict_order | relaxed_order`；
  `hnsw.max_scan_tuples` 默认 20000，`hnsw.scan_mem_multiplier` 默认 1（× work_mem）。
  relaxed 允许轻微乱序换召回；要严格序用 MATERIALIZED CTE（PG17+ 加 `distance + 0`）。
- 384 维字节数：`vector` 1544 B、`halfvec` 776 B、`bit` 56 B —— halfvec 省约 2×，二值省 27×。
- 二值量化官方写法：`hnsw ((binary_quantize(embedding)::bit(384)) bit_hamming_ops)`，
  用 `<~>` 检索后拿原向量 re-rank（先取 20 再取 5）。官方只说用于「at scale 把索引塞进内存」，
  没给召回数字。
- 第三方实测（2 万条 16 维合成、PG17.8 + 0.8.1、2C2G、strict_order）：
  命中 10.06% 时普通 HNSW 返回 4/6/4 条 → 迭代 10/10/10，延迟 0.803→1.442 ms；
  命中 2.14% 时 0/2/0 → 10/10/10，3.415 ms（精确全扫 0.912 ms）；
  命中 0.44% 时 0/1/0 → 10/10/10，8.673 ms（精确 0.854 ms）。
  **选择性越极端，迭代扫描越不如直接精确扫描**；作者声明是合成数据、无并发。

## 过滤 + ANN

- 官方推荐顺序：过滤列建 B-tree（低选择性时精确检索已够快）→ 近似索引 → 开迭代扫描；
  过滤值少用 partial index，过滤值多用 LIST 分区。
- 多租户专节：共享一个近似索引时，某租户向量会影响其他租户的召回与速度。
- RLS 的 tenant 谓词在计划中等价于普通 WHERE 过滤，同样「先扫描后过滤」，
  不会因为 RLS 变快（机制推论，未见 benchmark）。
- 取舍（推断）：租户数百以内 → LIST 分区 + 每分区 HNSW；上千 → 单表 + tenant_id B-tree + 迭代扫描。

## 任务队列对比

| 方案 | 同租户串行 | 去重 | 崩溃恢复 |
|---|---|---|---|
| Procrastinate | `lock=tenant_id` 原生 | `queueing_lock`，重复 defer 抛 AlreadyEnqueued | heartbeat 10s，30s 判 stalled，**需自己 retry_job** |
| pgmq | 仅 FIFO/group keys | 无 | visibility timeout 到期重投 |
| Graphile Worker | 无原语 | `job_key` + mode | 行删即完成 |
| River | Sequences（Pro） | 按 args/period 跳过 | JobStuckHandler |
| Celery + Redis | 无 | 无内置 | visibility_timeout 默认 3600s |

关键坑：Procrastinate 官方原文——带 lock 的任务被杀且未置 failed/succeeded，
同 lock 后续**永久不跑**；最老任务 scheduled_at 在未来或无 worker 消费，同 lock 也全堵。
连接默认 pool 10 + LISTEN/NOTIFY 1 条，pool 建议 ≥ 并发 + 1，可 `listen_notify=False`。

## 嵌入服务

- fastembed 0.9.1：ONNX Runtime、无 PyTorch，面向 serverless；文案称比 PyTorch 快，无吞吐数字。
- TEI：Rust/Candle、token 级动态批处理；默认 max-batch-tokens 16384、max-client-batch-size 32。
- Infinity：v3 需 SM80+；只有「decoder 模型比 bert-small 大且慢 20–100×」这类口径。
- CPU 量级（二手博客，非官方）：MiniLM 级「每核每秒数十到数百条」；
  建议 int8/OpenVINO、ONNX 导出 O3、在线查询做 10–50 ms 微批。
  二值 top-k + float32 rescore 可保留约 96% 检索效果、内存省 32×（引 sbert）。

## 增量索引

- LlamaIndex IngestionPipeline 默认 `DocstoreStrategy.UPSERTS`：按 `ref_doc_id` 比对
  `get_document_hash()`；无记录重跑、hash 变了先删再重跑、hash 相同跳过。
  局限：去重粒度是整篇文档，不是 chunk 级 diff。
- chunk 级要自建 `(doc_id, chunk_index, content_sha256)` 表；现成库未查到。

## 值得做的小投入大收益

1. 过滤列（tenant_id、单租户常用过滤列）建 B-tree/复合索引 —— 我们已有主键与 `(tenant_id, source_id)`。
2. 会话内开 `hnsw.iterative_scan=relaxed_order`，按需调 `max_scan_tuples` —— 已在
   `learn_core/rag/settings.py` 的 `apply_ann_settings()`。
3. 先换 halfvec（776 B/行）—— 十万块以上再说。
4. Procrastinate：`lock` + `queueing_lock` + 定时扫 stalled —— 前三项已有，**缺定时入口**。
5. 每 chunk 存 `content_sha256`，只重嵌变化块 —— 未做，收益随资料更新频率放大。

## 未查到

pgvector 分区/分表的大规模生产 benchmark、Aurora pgvector 0.8.0 具体数字、
pgvectorscale vs pgvector 同口径对比、fastembed/TEI/Infinity/vLLM 的 CPU 绝对吞吐对比、
chunk 级增量索引现成库。
