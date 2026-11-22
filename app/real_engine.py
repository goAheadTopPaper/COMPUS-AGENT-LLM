"""真实引擎适配层 —— 这是前端唯一需要改的地方。

·jx(2) 交付 `graph/pipeline.py` 里的 `run_pipeline(query, student) -> FinalAnswer`
之后，把下面的 import 打开即可，前端其余代码一行都不用动。
"""

from __future__ import annotations

from contracts import FinalAnswer, StudentProfile

try:  # 真实 pipeline 就绪后自动生效
    from graph.pipeline import run_pipeline  # type: ignore
    HAS_REAL = True
except Exception:  # noqa: BLE001  —— 还没交付时退回 mock
    run_pipeline = None  # type: ignore
    HAS_REAL = False


def simulate(query: str, student: StudentProfile) -> FinalAnswer:
    """与 mock_engine.simulate 同签名，前端直接替换 import 即可。"""
    if not HAS_REAL or run_pipeline is None:
        raise RuntimeError("graph.pipeline.run_pipeline 尚未就绪")
    return run_pipeline(query, student)
