"""最小评测：24 条查询，只测两件事 —— 检索有没有命中、该拒绝时有没有拒绝。

用法（只需一条命令）：
    POLICY_RAG_HOME=/path/to/part1 python3 eval/run_eval.py

输出：
    eval/results.md      可直接粘进 slides 的表
    eval/results.json    原始结果

刻意不做的事（时间不够就别做）：
    不做四组消融、不做 LLM-as-judge、不做中文。这些在 slides 里用一段 limitation 交代即可。
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_extra = os.environ.get("POLICY_RAG_HOME")
if _extra:
    sys.path.insert(0, _extra)

from app.retrieval_adapter import search  # noqa: E402

K = 5
BENCH = ROOT / "eval" / "benchmark.jsonl"
OUT_MD = ROOT / "eval" / "results.md"
OUT_JSON = ROOT / "eval" / "results.json"


def hit(evs, keywords) -> bool:
    if not keywords:
        return False
    blob = " ".join(e.quote.lower() for e in evs)
    return any(k.lower() in blob for k in keywords)


def main() -> None:
    rows, raw = [], []
    for line in BENCH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        q = json.loads(line)
        t0 = time.time()
        try:
            evs, meta = search(q["query"], top_k=K, agent="eval", **q.get("filters", {}))
            err = ""
        except Exception as exc:  # noqa: BLE001
            evs, meta, err = [], {}, f"{type(exc).__name__}: {exc}"
        dt = int((time.time() - t0) * 1000)

        if q["expect"] == "answerable":
            ok = hit(evs, q["keywords"])
        elif q["expect"] == "verifier":
            # 语义型无解题：检索仍会返回相邻证据，拒答只能由 Verifier 判定。
            # 这里只验证"检索确实给了可判定的材料"，不计入拒答率。
            ok = len(evs) > 0
        else:
            ok = len(evs) == 0 or meta.get("status") == "no_matching_evidence"

        rows.append({
            "id": q["id"], "category": q["category"], "query": q["query"],
            "expect": q["expect"], "n": len(evs), "ok": ok, "ms": dt, "error": err,
        })
        raw.append({**rows[-1], "status": meta.get("status"),
                    "top": (evs[0].source_id if evs else "")})
        print(f"{q['id']:<4} {'PASS' if ok else 'FAIL'}  n={len(evs)}  {dt:>5}ms  {q['query'][:64]}")

    ans = [r for r in rows if r["expect"] == "answerable"]
    un = [r for r in rows if r["expect"] == "unanswerable"]
    ver = [r for r in rows if r["expect"] == "verifier"]
    rec = sum(r["ok"] for r in ans) / max(len(ans), 1)
    ref = sum(r["ok"] for r in un) / max(len(un), 1)
    ms = sorted(r["ms"] for r in rows)
    p50 = ms[len(ms) // 2] if ms else 0

    md = [
        "# 检索层评测结果", "",
        f"- 查询数：{len(rows)}（可答 {len(ans)} / 可拒答 {len(un)} / 需 Verifier {len(ver)}）",
        f"- **证据命中率 Recall@{K}**：{sum(r['ok'] for r in ans)}/{len(ans)} = **{rec:.1%}**",
        f"- **正确拒答率**（年份/编号不存在时返回空）：{sum(r['ok'] for r in un)}/{len(un)} = **{ref:.1%}**",
        f"- 中位延迟：{p50} ms（本地 BM25，无网络）", "",
        "| ID | 类别 | 查询 | 期望 | 返回证据 | 结果 |",
        "|---|---|---|---|---:|---|",
    ]
    for r in rows:
        exp = {"answerable": "可答", "unanswerable": "不可答", "verifier": "需校验"}[r["expect"]]
        md.append(f"| {r['id']} | {r['category']} | {r['query'][:58]} | {exp} | "
                  f"{r['n']} | {'PASS' if r['ok'] else 'FAIL'} |")
    md += ["", "> 说明：本表只测检索层与拒答，不评价生成答案的事实正确性；"
               "BM25 词频基线，未启用神经向量；中文查询不在本表范围内（见 limitation）。",
           "> 语义型无解题（如预测给分）检索仍会返回相邻证据，拒答须由 Verifier 判定，不计入上表拒答率。"]

    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    OUT_JSON.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nRecall@{K} = {rec:.1%}   拒答准确率 = {ref:.1%}   p50 = {p50}ms")
    print(f"已写出 {OUT_MD}")


if __name__ == "__main__":
    main()
