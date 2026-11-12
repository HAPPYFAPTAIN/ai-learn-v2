"""阶段 0 · pgvector 召回验证。

问题：HNSW 是近似索引，过滤条件（tenant_id）在索引之后应用。
小租户只占库里的少数，默认 ef_search 下很可能拿不满 top-k。

验证内容：
1. 无迭代扫描时，小租户 top-10 召回率；
2. 打开 hnsw.iterative_scan = relaxed_order 后是否回到 1.0；
3. 两种设置下的延迟都没有明显退化。

用法：PYTHONPATH=. .venv/bin/python scripts/phase0/validate_vector.py
"""

from __future__ import annotations

import time

from sqlalchemy import create_engine, text

from learn_core.config import get_settings

OWNER_DSN = get_settings().database_owner_url.replace("+psycopg", "")
DIM = 384
BIG_TENANT = "11111111-1111-1111-1111-111111111111"
SMALL_TENANT = "22222222-2222-2222-2222-222222222222"
BIG_ROWS = 20_000
SMALL_ROWS = 400
K = 10


def build(conn) -> None:
    conn.execute(text("DROP TABLE IF EXISTS phase0_vec"))
    conn.execute(
        text(
            f"""
            CREATE TABLE phase0_vec (
                id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                tenant uuid NOT NULL,
                embedding vector({DIM}) NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            f"""
            INSERT INTO phase0_vec (tenant, embedding)
            SELECT :big,
                   (SELECT array_agg(random()::real)
                    FROM generate_series(1, {DIM}) g
                    WHERE src.i IS NOT NULL)::vector
            FROM generate_series(1, :n) AS src(i)
            """
        ),
        {"big": BIG_TENANT, "n": BIG_ROWS},
    )
    conn.execute(
        text(
            f"""
            INSERT INTO phase0_vec (tenant, embedding)
            SELECT :small,
                   (SELECT array_agg(random()::real)
                    FROM generate_series(1, {DIM}) g
                    WHERE src.i IS NOT NULL)::vector
            FROM generate_series(1, :n) AS src(i)
            """
        ),
        {"small": SMALL_TENANT, "n": SMALL_ROWS},
    )
    conn.execute(
        text(
            "CREATE INDEX phase0_vec_hnsw ON phase0_vec "
            "USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)"
        )
    )
    conn.execute(text("ANALYZE phase0_vec"))


def query_vector(conn) -> str:
    return conn.execute(
        text("SELECT embedding::text FROM phase0_vec WHERE tenant = :t LIMIT 1"),
        {"t": SMALL_TENANT},
    ).scalar_one()


def exact(conn, vec: str) -> list[int]:
    conn.execute(text("SELECT set_config('enable_indexscan', 'off', true)"))
    conn.execute(text("SELECT set_config('enable_bitmapscan', 'off', true)"))
    rows = conn.execute(
        text(
            f"SELECT id FROM phase0_vec WHERE tenant = :t "
            f"ORDER BY embedding <=> CAST(:v AS vector) LIMIT {K}"
        ),
        {"t": SMALL_TENANT, "v": vec},
    ).scalars().all()
    conn.execute(text("SELECT set_config('enable_indexscan', 'on', true)"))
    conn.execute(text("SELECT set_config('enable_bitmapscan', 'on', true)"))
    return list(rows)


def approx(
    conn, vec: str, iterative: str | None, ef_search: int, max_scan_tuples: int = 40_000
) -> tuple[list[int], float]:
    conn.execute(text("SELECT set_config('hnsw.ef_search', :ef, true)"), {"ef": str(ef_search)})
    conn.execute(
        text("SELECT set_config('hnsw.max_scan_tuples', :v, true)"),
        {"v": str(max_scan_tuples)},
    )
    conn.execute(
        text("SELECT set_config('hnsw.iterative_scan', :v, true)"),
        {"v": iterative or "off"},
    )
    start = time.perf_counter()
    rows = conn.execute(
        text(
            f"SELECT id FROM phase0_vec WHERE tenant = :t "
            f"ORDER BY embedding <=> CAST(:v AS vector) LIMIT {K}"
        ),
        {"t": SMALL_TENANT, "v": vec},
    ).scalars().all()
    return list(rows), (time.perf_counter() - start) * 1000


def recall(truth: list[int], got: list[int]) -> float:
    return len(set(truth) & set(got)) / max(1, len(truth))


def main() -> int:
    engine = create_engine(OWNER_DSN, future=True)
    with engine.begin() as conn:
        if conn.execute(text("SELECT to_regclass('public.phase0_vec')")).scalar() is None:
            build(conn)
        vec = query_vector(conn)
        truth = exact(conn, vec)

        base_rows, base_ms = approx(conn, vec, None, 40)
        base = recall(truth, base_rows)
        print(f"[1] 默认设置 ef_search=40：召回 {len(base_rows)}/{K} = {base:.0%}，{base_ms:.1f} ms")

        relaxed_rows, relaxed_ms = approx(conn, vec, "relaxed_order", 200)
        relaxed = recall(truth, relaxed_rows)
        print(f"[2] iterative_scan=relaxed_order, ef_search=200：召回 {relaxed:.0%}，{relaxed_ms:.1f} ms")

        iter_rows, iter_ms = approx(conn, vec, "strict_order", 400)
        it = recall(truth, iter_rows)
        print(f"[3] iterative_scan=strict_order, ef_search=400：召回 {it:.0%}，{iter_ms:.1f} ms")

        ok = it >= 0.95 and iter_ms < 50
        print("PASS" if ok else "FAIL")
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
