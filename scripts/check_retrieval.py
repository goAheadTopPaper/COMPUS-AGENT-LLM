"""检索探针：验证 Part 1 能否直接喂给前端，并检查中英文差异。

运行：
    POLICY_RAG_HOME=/path/to/part1 python3 scripts/check_retrieval.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_extra = os.environ.get("POLICY_RAG_HOME")
if _extra:
    sys.path.insert(0, _extra)

from app.retrieval_adapter import search  # noqa: E402

PROBES = [
    ("EN/policy", "Can I retake a subject to improve my grade?",
     {"knowledge_domain": "policy", "method": "bm25"}),
    ("EN/programme", "What are the graduation credit requirements for programme 46010 in 2026/27?",
     {"knowledge_domain": "academic_information", "method": "bm25", "academic_year": "2026/27"}),
    ("EN/subject", "What are the credit value and prerequisites for COMP5926?",
     {"knowledge_domain": "academic_information", "method": "bm25"}),
    ("ZH/policy", "我可以重修已经及格的科目来提高成绩吗？",
     {"knowledge_domain": "policy", "method": "bm25"}),
    ("ZH/deadline", "退课的最后期限是什么时候？",
     {"knowledge_domain": "policy", "method": "bm25"}),
]


def main() -> None:
    for tag, q, filters in PROBES:
        print(f"\n{'=' * 78}\n[{tag}] {q}")
        try:
            evs, meta = search(q, top_k=3, agent="probe", **filters)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            continue
        print(f"  status={meta.get('status')}  n={len(evs)}  backend={meta.get('vector_backend')}")
        for i, e in enumerate(evs, 1):
            print(f"  [{i}] conf={e.confidence:<5} auth={e.authority:<20} p.{e.page}")
            print(f"      {e.title[:60]}")
            print(f"      {e.section[:70]}")
            print(f"      claim: {e.claim[:90]}")
            if e.warnings:
                print(f"      warn: {e.warnings[0][:80]}")


if __name__ == "__main__":
    main()
