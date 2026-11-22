"""真实数据引擎：直接调用 Part 1 检索，把结果组装成 FinalAnswer。

这是 ·jx 的 LangGraph pipeline 就绪之前的**保命方案**，也是 5 号位的最小演示路径：
不依赖任何人生效，一条命令就能出一屏像样的 demo 画面。

刻意不做的事：不做生成式改写（答案由证据逐条拼装）、不做多轮、不做中文。
需要真生成时把 graph.pipeline 接上，前端会自动优先用那一个。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_extra = os.environ.get("POLICY_RAG_HOME")
if _extra and _extra not in sys.path:
    sys.path.insert(0, _extra)

from contracts import AgentName, Evidence, FinalAnswer, RunContext, StudentProfile, Usage  # noqa: E402

try:
    from app.retrieval_adapter import search as _search
    import policy_rag.retrieve  # noqa: F401
    HAS_DATA = True
except Exception:  # noqa: BLE001
    HAS_DATA = False

SERVICE_WORDS = ("library", "borrow", "uhs", "counselling", "helpcentre", "help centre",
                 "health", "sport", "hall", "canteen", "it service")
SUBJECT_WORDS = ("comp5", "comp4", "comp3", "comp2", "comp1", "prerequisite", "pre-requisite",
                 "credit value", "subject description", "programme", "jupas", "tuition",
                 "admission", "entry requirement")


def _domain(query: str) -> tuple[str, str]:
    q = query.lower()
    if any(w in q for w in SERVICE_WORDS):
        return "student_services", "学生服务"
    if any(w in q for w in SUBJECT_WORDS):
        return "academic_information", "教务与课程"
    return "policy", "学则与规章"


def simulate(query: str, student: StudentProfile) -> FinalAnswer:
    ctx = RunContext(query=query, student=student)
    t0 = time.time()
    domain, label = _domain(query)

    ctx.emit(AgentName.SUPERVISOR, "delegate",
             f"查询归入「{label}」域，派发检索", latency_ms=60)
    try:
        evs, meta = _search(query, top_k=4, agent="retrieval", knowledge_domain=domain)
    except Exception as exc:  # noqa: BLE001
        ctx.emit(AgentName.SUPERVISOR, "answer", f"检索失败：{type(exc).__name__}", latency_ms=20)
        return FinalAnswer(status="failed", text=f"检索层异常：{exc}", trace=ctx.trace,
                           usage=Usage(latency_ms=int((time.time() - t0) * 1000), agent_calls=1))

    ctx.emit("retrieval", "retrieve",
             f"召回 {len(evs)} 条证据（status={meta.get('status')}）",
             n_evidence=len(evs), latency_ms=int((time.time() - t0) * 1000))

    if not evs:
        status = meta.get("status") or ""
        years = meta.get("available_academic_years") or []
        if status == "no_year_specific_evidence":
            why = "该学年在语料中没有收录对应版本"
        elif status == "no_matching_evidence":
            why = "语料中没有命中相关段落"
        else:
            why = f"检索未返回证据（{status or 'unknown'}）"
        hint = f"当前收录的学年为：{'、'.join(map(str, years))}。" if years else ""
        ctx.emit(AgentName.VERIFIER, "reject", f"0 条证据（{status}），禁止生成答案", latency_ms=30)
        ctx.emit(AgentName.SUPERVISOR, "answer", "输出拒答与下一步建议", latency_ms=40)
        return FinalAnswer(
            status="refused",
            text=(f"**没有找到可靠依据，我不回答。**\n\n"
                  f"原因：{why}（status=`{status}`）。\n\n"
                  f"{hint}\n\n"
                  "**你可以：** 核对年份与科目/项目编号；换用英文关键词；"
                  "或在 eStudent 自行确认个人记录。"),
            trace=ctx.trace,
            usage=Usage(latency_ms=int((time.time() - t0) * 1000), agent_calls=2))

    cited = [e for e in evs if e.quote and (e.page or e.source_id)]
    ctx.emit(AgentName.VERIFIER, "result",
             f"通过：{len(cited)}/{len(evs)} 条证据带原文与来源；"
             f"{sum(1 for e in evs if e.warnings)} 条带适用性警告",
             latency_ms=40)

    lines = [f"**在{label}语料中检索到以下依据：**", ""]
    for i, e in enumerate(evs, 1):
        sect = f"（{e.section}）" if e.section else ""
        lines.append(f"- {e.claim} [{i}]{sect}")
    if evs and evs[0].warnings:
        lines += ["", f"⚠️ 适用性提示：{evs[0].warnings[0]}"]
    lines += ["", f"*共 {len(evs)} 条证据，来源覆盖 {len({e.source_id for e in evs})} 份文件。*"]
    ctx.emit(AgentName.ANSWERER, "answer", "按证据逐条拼装答案（提取式，未改写）", latency_ms=80)

    return FinalAnswer(
        status="ok", text="\n".join(lines), evidence=evs,
        confidence=round(sum(e.confidence for e in evs) / len(evs), 3),
        trace=ctx.trace,
        usage=Usage(latency_ms=int((time.time() - t0) * 1000),
                    tokens=0, cost_usd=0.0, agent_calls=4))
