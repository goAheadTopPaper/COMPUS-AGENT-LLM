"""联调验收：用真实检索 + 面包的 Answerer/Verifier 跑通整条链。

目的不是评质量，是**证明接口对得上** —— 这是周一之前最该先做的事，
否则集成到最后一晚才发现字段名不一致。

用法：
    POLICY_RAG_HOME=/path/to/part1 [REPO=/path/to/cloned-repo] python3 scripts/check_integration.py

没有配 LLM 时用 stub 模型（返回固定结构），只验证数据通路；
接了真实模型请改用组内 model 适配器。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
for p in (os.environ.get("POLICY_RAG_HOME"), os.environ.get("REPO")):
    if p and p not in sys.path:
        sys.path.insert(0, p)

from app.retrieval_adapter import search_full  # noqa: E402

PART1 = os.environ.get("POLICY_RAG_HOME", "")


def _norm(t: str) -> str:
    return " ".join(t.split())


def stub_model(system: str, payload: dict) -> dict:
    """代替 LLM：Answerer 取前两条证据原文做逐字引用，Verifier 一律 supported。"""
    if "supports" in system:
        claims = []
        for key, row in list(payload.get("evidence", {}).items())[:2]:
            quote = _norm(row["text"])[:140]
            claims.append({"text": quote[:70], "supports": [{"evidence_id": key, "quote": quote}]})
        return {"claims": claims}
    n = len(payload.get("claims") or [])
    return {"checks": [{"index": i, "status": "supported", "reason": "stub"}
                       for i in range(n)],
            "unanswered": [], "needs_clarification": False}


def main() -> None:
    from agents import answer, collect_evidence, verify  # 面包的交付

    cases = [
        ("规章单查", "Can I retake a subject I have already passed to improve my grade?", {}),
        ("年份不存在", "What are the subject withdrawal rules in 2020/21?",
         {"academic_year": "2020/21"}),
    ]
    schedule = [{
        "evidence_id": "schedule:mock-event-1",
        "text": "COMP5926 exam: 2026-11-23 14:00 Asia/Hong_Kong; room A101.",
        "citation": {"title": "Mock schedule"},
        "warnings": ["Synthetic demo data"],
    }]

    for name, q, filters in cases:
        print(f"\n{'=' * 76}\n[{name}] {q}")
        evs, resp = search_full(q, top_k=5, agent="policy", knowledge_domain="policy", **filters)
        print(f"  检索: {len(evs)} 条 | status={resp.get('status')} | "
              f"澄清标志={[k for k, v in resp.items() if v is True and k.startswith('requires_')]}")

        bundle = collect_evidence(resp, schedule)
        print(f"  bundle: {len(bundle['evidence'])} 条证据 | "
              f"policy_status={bundle['policy_status']} | flags={bundle['clarification_flags']}")

        draft = answer(q, bundle, stub_model)
        report = verify(q, bundle, draft, stub_model)
        print(f"  Allower: {len(draft.get('claims', []))} claims | "
              f"Verifier: {report['status']} approved={report['approved']}")
        if report.get("issues"):
            print(f"  issues: {report['issues'][:2]}")
        if report.get("answer"):
            print(f"  answer: {report['answer'][:160]}")

        if PART1:
            try:
                from policy_rag.verify import verify_claims
                gate = verify_claims({**{k: v for k, v in json.loads(json.dumps(draft)).items()},
                                      "retrieved_evidence_ids": list(bundle["evidence"])},
                                     db_path=os.path.join(PART1, "data", "policy_index.sqlite"),
                                     source_root=PART1)
                print(f"  Part1 证据门: {gate.get('status')}")
            except Exception as exc:  # noqa: BLE001
                print(f"  Part1 证据门失败: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
