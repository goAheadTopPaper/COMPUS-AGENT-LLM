"""端到端验收：真实索引 + 真实课表接口 + Supervisor + Answerer/Verifier。

用法：
    POLICY_RAG_HOME=/path/to/part1 python3 scripts/check_pipeline.py

未配置 LLM 时用 stub 模型，只验证**数据通路与状态机**；
接了真实模型（DeepSeek）后再验语义质量。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PART1 = os.environ.get("POLICY_RAG_HOME", "")
for p in (str(REPO), PART1):
    if p and p not in sys.path:
        sys.path.insert(0, p)
if PART1:
    sys.path.insert(0, PART1)  # 让 policy_rag 命中带索引的那一份

from policy_adapter import build_policy_search  # noqa: E402
from policy_rag.retrieve import PolicyRetriever  # noqa: E402
from supervisor import run  # noqa: E402


def _norm(t: str) -> str:
    return " ".join(t.split())


def stub_model(system: str, payload: dict) -> dict:
    if "supports" in system:
        claims = []
        for key, row in list(payload.get("evidence", {}).items())[:2]:
            quote = _norm(row["text"])[:140]
            claims.append({"text": quote[:70], "supports": [{"evidence_id": key, "quote": quote}]})
        return {"claims": claims}
    n = len(payload.get("claims") or [])
    return {"checks": [{"index": i, "status": "supported", "reason": "stub"} for i in range(n)],
            "unanswered": [], "needs_clarification": False}


def main() -> None:
    # 关键：Part 1 的 search() 默认 method="hybrid"，没有 sentence-transformers 时
    # 会在查询阶段抛 ModuleNotFoundError，整个 policy 分支直接变 failed。
    # 这里显式探测依赖，缺了就退回 bm25（纯标准库）。
    try:
        import sentence_transformers  # noqa: F401
        method = "hybrid"
    except Exception:  # noqa: BLE001
        method = "bm25"
    print(f"检索后端: {method}")
    policy_search = build_policy_search(PolicyRetriever(), {"top_k": 4, "method": method},
                                        context_limit=1)

    def schedule_empty(_q):
        return []

    def schedule_broken(_q):
        raise RuntimeError("timetable endpoint unreachable")

    cases = [
        ("规章单查", "Can I retake a subject I have already passed to improve my grade?",
         ["policy"], None),
        ("年份不存在", "What are the subject withdrawal rules in 2020/21?", ["policy"], None),
        ("混合查询（日程为空）", "Can I retake a subject I have already passed?", ["policy", "schedule"],
         schedule_empty),
        ("日程分支失败", "Can I retake a subject I have already passed?", ["policy", "schedule"],
         schedule_broken),
    ]

    for name, q, branches, sched in cases:
        plan = {"question": q, "branches": branches,
                "sub_queries": {"policy": q, "schedule": q}}
        t0 = time.time()
        try:
            out = run(plan, stub_model, policy_search=policy_search, schedule_search=sched)
        except Exception as exc:  # noqa: BLE001
            print(f"[{name}] 崩溃: {type(exc).__name__}: {exc}")
            continue
        dt = int((time.time() - t0) * 1000)
        states = {k: v["state"] for k, v in out["branches"].items()}
        print(f"[{name}] {dt} ms")
        print(f"  status={out['status']}  approved={out['approved']}  分支={states}")
        if out.get("notices"):
            print(f"  notices={out['notices']}")
        if out.get("answer"):
            print(f"  answer: {out['answer'][:110]}")


if __name__ == "__main__":
    main()
