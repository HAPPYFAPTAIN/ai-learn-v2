"""多租户过滤下的向量召回对照：全局 HNSW + tenant 过滤 vs 提高扫描量。

造数据 → 建索引 → 对同一批查询分别用「精确扫描」和几种 HNSW 设置跑，
比较召回率与耗时。用法：

    LEARN_DATABASE_URL=... python scripts/bench/vector_recall.py
"""

from __future__ import annotations

import os
import random
import statistics
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import create_engine, text  # noqa: E402

DIM = 384
TENANTS = 6
PER_TENANT = 10000
PROBES = 20
TOP_K = 10


def main() -> None:
    url = os.environ["LEARN_DATABASE_URL"]
    engine = create_engine(url)
    rng = random.Random(7)

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS bench_rag"))
        conn.execute(
            text(
                f"""
                CREATE TABLE bench_rag (
                    id bigserial PRIMARY KEY,
                    tenant_id uuid NOT NULL,
                    chunk text NOT NULL,
                    embedding vector({DIM})
                )
                """
            )
        )

    tenants = [uuid.uuid4() for _ in range(TENANTS)]
    rows = []
    for tenant in tenants:
        for i in range(PER_TENANT):
            vec = [rng.uniform(-1, 1) for _ in range(DIM)]
            rows.append({"t": str(tenant), "c": f"chunk-{i}", "e": "[" + ",".join(f"{x:.4f}" for x in vec) + "]"})

    t0 = time.time()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO bench_rag (tenant_id, chunk, embedding) VALUES (:t, :c, CAST(:e AS vector))"),
            rows,
        )
        conn.execute(text("CREATE INDEX bench_rag_hnsw ON bench_rag USING hnsw (embedding vector_cosine_ops)"))
        conn.execute(text("CREATE INDEX bench_rag_tenant ON bench_rag (tenant_id)"))
    print(f"rows={len(rows)} build={time.time()-t0:.1f}s")

    queries = []
    for tenant in tenants[:5]:
        q = [rng.uniform(-1, 1) for _ in range(DIM)]
        queries.append((tenant, "[" + ",".join(f"{x:.4f}" for x in q) + "]"))

    def run(tenant, vec, setting=None, exact=False) -> tuple[list[int], float]:
        with engine.connect() as conn:
            if exact:
                conn.execute(text("SET enable_indexscan = off"))
                conn.execute(text("SET enable_bitmapscan = off"))
            else:
                conn.execute(text("SET enable_indexscan = on"))
                conn.execute(text("SET enable_bitmapscan = on"))
            if setting:
                for stmt in setting:
                    conn.execute(text(stmt))
            started = time.perf_counter()
            ids = [
                r[0]
                for r in conn.execute(
                    text(
                        """
                        SELECT id FROM bench_rag
                         WHERE tenant_id = :t
                         ORDER BY embedding <=> CAST(:v AS vector)
                         LIMIT :k
                        """
                    ),
                    {"t": str(tenant), "v": vec, "k": TOP_K},
                )
            ]
            return ids, (time.perf_counter() - started) * 1000

    def recall(found: list[int], truth: list[int]) -> float:
        return len(set(found) & set(truth)) / len(truth)

    configs = {
        "精确扫描（基准）": (True, None),
        "默认 ef=40": (False, None),
        "iterative strict": (False, ["SET hnsw.iterative_scan = strict_order"]),
        "strict + ef=200": (False, ["SET hnsw.iterative_scan = strict_order", "SET hnsw.ef_search = 200"]),
        "strict + ef=200 + scan=40000": (
            False,
            ["SET hnsw.iterative_scan = strict_order", "SET hnsw.ef_search = 200", "SET hnsw.max_scan_tuples = 40000"],
        ),
    }

    truth = {}
    for tenant, vec in queries:
        truth[(tenant, vec)], _ = run(tenant, vec, exact=True)

    with engine.connect() as conn:
        plan = conn.execute(
            text(
                """
                EXPLAIN SELECT id FROM bench_rag
                 WHERE tenant_id = :t ORDER BY embedding <=> CAST(:v AS vector) LIMIT :k
                """
            ),
            {"t": str(queries[0][0]), "v": queries[0][1], "k": TOP_K},
        ).scalars().all()
    print("\n查询计划:", " | ".join(plan))
    print(f"\n{'配置':<32}{'平均召回':>10}{'p50 耗时':>12}")
    for label, (exact, setting) in configs.items():
        recalls, times = [], []
        for tenant, vec in queries:
            found, ms = run(tenant, vec, setting=setting, exact=exact)
            recalls.append(recall(found, truth[(tenant, vec)]))
            times.append(ms)
        print(f"{label:<32}{statistics.mean(recalls):>9.0%}{statistics.median(times):>10.1f} ms")

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE bench_rag"))


if __name__ == "__main__":
    main()
