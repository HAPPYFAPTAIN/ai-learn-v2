"""检索时的 ANN 参数。

`scripts/phase0/validate_vector.py` 的实测结论（20 400 行、小租户 400 行）：
- 默认 ef_search=40：小租户 top-10 召回 10%；
- iterative_scan=relaxed_order + ef_search=200：70%；
- iterative_scan=strict_order + ef_search=400 + max_scan_tuples=40000：100%，约 3 ms。

过滤条件是 tenant_id，索引本身不包含租户列，所以必须开迭代扫描；
关闭它时 HNSW 可能拿不满 k 条，表现为「明明有资料却检索不到」。
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

DEFAULT_EF_SEARCH = 400
DEFAULT_MAX_SCAN_TUPLES = 40_000
DEFAULT_ITERATIVE_SCAN = "strict_order"


def apply_ann_settings(
    session: Session,
    ef_search: int = DEFAULT_EF_SEARCH,
    max_scan_tuples: int = DEFAULT_MAX_SCAN_TUPLES,
    iterative_scan: str = DEFAULT_ITERATIVE_SCAN,
) -> None:
    """在事务内设置 pgvector 会话参数，事务结束自动失效。"""
    if iterative_scan not in ("off", "relaxed_order", "strict_order"):
        raise ValueError(f"unknown iterative_scan mode: {iterative_scan}")
    session.execute(text("SELECT set_config('hnsw.ef_search', :v, true)"), {"v": str(ef_search)})
    session.execute(
        text("SELECT set_config('hnsw.max_scan_tuples', :v, true)"),
        {"v": str(max_scan_tuples)},
    )
    session.execute(
        text("SELECT set_config('hnsw.iterative_scan', :v, true)"),
        {"v": iterative_scan},
    )
