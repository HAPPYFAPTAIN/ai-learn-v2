# RAG 存储：按租户分区的取舍

## 现在怎么做

`rag_chunk` / `rag_embedding` 是 `PARTITION BY LIST (tenant_id)` 的分区表，
每个租户一个分区，分区上各带一份 HNSW 索引。

- 写入前调用 `ensure_rag_partition(tenant_id)`（SECURITY DEFINER，owner 权限建分区，
  应用角色只有 EXECUTE）。分区不存在时 `upsert_chunks` 会先补建。
- 查询固定带 `tenant_id`，规划器裁剪到单分区，只扫该租户的 HNSW。
- 父表 `FORCE ROW LEVEL SECURITY`，策略用 `NULLIF(current_setting('app.tenant_id', true), '')::uuid`。

为什么做这件事：pgvector 官方 README 的 Multitenancy 一节写得很直白——
多租户共享一个近似索引，别人的向量会挤占你的召回率，也会拖慢你的查询。
我们原先是一张表一个 HNSW，等于所有租户共用一个索引。

## 实测数据（本机）

`scripts/bench/vector_recall.py`：6 租户 × 每租户 1 万块 = 6 万行、384 维。

| 查询方式 | 延迟 | 召回 |
|---|---|---|
| 精确扫描（计划器默认选择） | 10.9 ms | 100% |
| HNSW 默认 `ef_search=40` | 9.5 ms | 100% |
| HNSW + `iterative_scan=strict_order` | 4.4 ms | 100% |

关键结论：单租户万级块时，规划器根本没用 HNSW，直接走精确扫描。
所以「召回不全」在这个量级不会出现，跨租户干扰也还显现不出来。
分区是在为十万级以后做准备，现在的成本主要是每次建租户多一次 DDL。

## 但要提前说清：分区不是免费午餐

外部调研（`docs/learn-core/research/multitenant-postgres.md`）里有两条与直觉相反的事实：

1. PostgreSQL 官方口径是分区只在「表大到超过物理内存」时才划算；
   分区太多会让规划时间和每个会话的内存都上升。
2. Toggl 的生产经验（PGConf.EU 2026）：用 `PARTITION BY HASH` 做多租户，
   最后因为一个 noisy tenant 拖垮全体而放弃，结论是「租户隔离别指望分区」。

所以我们的做法是**只对 RAG 两张表分区**，理由是这两张表的索引质量直接受
其他租户数据影响（pgvector 的特性），而普通业务表（`le_*`、`tenant`、`model_call`）
继续单表 + RLS——那里分区的收益远小于运维成本。

如果将来租户数涨到几千、或者单租户数据到百万块级，再评估：
- 分区数过多 → 改成 `PARTITION BY HASH` 桶化，或干脆按租户分表；
- 单分区过大 → `halfvec` 降精度、二值量化重排。

## 迁移

`migrations/versions/0006_rag_tenant_partition.py`：

1. 旧表改名 `*_legacy`，并把旧索引/约束改名让位；
2. 建分区父表（主键含 `tenant_id`，满足分区表约束）与 HNSW/GIN 索引；
3. 建 `ensure_rag_partition(uuid)`；
4. 为已有租户建分区，把数据搬过来，删旧表；
5. 父表开 FORCE RLS，授权应用角色 DML。

回滚是破坏性的（分区数据不迁回），只在开发环境用。
