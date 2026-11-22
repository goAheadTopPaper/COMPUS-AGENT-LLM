"""真实 pipeline 引擎：Supervisor 调度 + Answerer/Verifier（DeepSeek），policy 分支。

与 demo_engine 的区别：这里不自己拼流程，完全交给 supervisor.run()，
前端 trace 展示的是**真实调度记录**（分支状态、重试次数、notices、Verifier 结论）。

只跑 policy 分支：Schedule 目前没有可靠的课表数据源，不引入合成数据。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PART1 = os.environ.get("POLICY_RAG_HOME", "")
if PART1 and PART1 not in sys.path:
    sys.path.insert(0, PART1)

from contracts import AgentName, Evidence, FinalAnswer, RunContext, StudentProfile, Usage  # noqa: E402
from app.retrieval_adapter import to_evidence  # noqa: E402


# ---------------------------------------------------------------- 配置探测
def _read_env() -> dict:
    path = ROOT / ".env"
    values = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, val = line.partition("=")
            if sep and not key.lstrip().startswith("#"):
                values[key.strip()] = val.strip()
    for name in ("LLM_ENDPOINT", "LLM_MODEL", "LLM_API_KEY"):
        if os.environ.get(name):
            values[name] = os.environ[name]
    return values


def _part1_ready() -> bool:
    if not PART1:
        return False
    base = Path(PART1)
    return (base / "data" / "policy_index.sqlite").is_file() and (base / "files").is_dir()


_CFG = _read_env()
HAS_PIPELINE = bool(_CFG.get("LLM_ENDPOINT") and _CFG.get("LLM_MODEL")
                    and _CFG.get("LLM_API_KEY") and _part1_ready())

_RETRIEVER = None

_STATUS_TEXT = {
    "no_year_specific_evidence": "该学年在语料中没有收录对应版本",
    "no_matching_evidence": "语料中没有命中相关段落",
    "candidates_found": "证据不足以支撑完整结论",
}


def _retriever():
    global _RETRIEVER
    if _RETRIEVER is None:
        from policy_rag.retrieve import PolicyRetriever
        _RETRIEVER = PolicyRetriever()
    return _RETRIEVER


def _method() -> str:
    try:
        import sentence_transformers  # noqa: F401
        return "hybrid"
    except Exception:  # noqa: BLE001
        return "bm25"


def _gate():
    """Part 1 的证据门：校验原始文件哈希与引文。缺原始文件时返回 None。"""
    if not _part1_ready():
        return None

    def policy_gate(payload):
        from policy_rag.verify import verify_claims
        return verify_claims(payload,
                             db_path=os.path.join(PART1, "data", "policy_index.sqlite"),
                             source_root=PART1)

    return policy_gate


def _model_factory():
    endpoint = _CFG["LLM_ENDPOINT"]
    model_name = _CFG["LLM_MODEL"]
    key = _CFG["LLM_API_KEY"]
    opener = build_opener()
    usage = {"tokens": 0, "calls": 0}

    def model(system: str, payload: dict) -> dict:
        body = json.dumps({
            "model": model_name,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        })
        req = Request(endpoint, data=body.encode(), headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + key})
        with opener.open(req, timeout=60) as resp:
            result = json.loads(resp.read())
        usage["calls"] += 1
        usage["tokens"] += int((result.get("usage") or {}).get("total_tokens") or 0)
        return json.loads(result["choices"][0]["message"]["content"])

    return model, usage


# ---------------------------------------------------------------- 文本整理
def _prettify(answer: str, sources: dict) -> str:
    """把 "claim [evidence_id]" 重排成带 [1][2] 角标的条目。"""
    order = {eid: i + 1 for i, eid in enumerate(sources)}
    lines = []
    for raw in answer.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"\[([^\]]+)\]",
                      lambda m: f"[{order[m.group(1)]}]" if m.group(1) in order else "",
                      line)
        lines.append("- " + re.sub(r"\s+", " ", line).strip())
    return "\n".join(lines)


def simulate(query: str, student: StudentProfile) -> FinalAnswer:
    from supervisor import run
    from policy_adapter import build_policy_search

    ctx = RunContext(query=query, student=student)
    t0 = time.time()
    captured: dict = {}

    def policy_search(sub_query: str) -> dict:
        began = time.time()
        resp = build_policy_search(_retriever(), {"top_k": 4, "method": _method()},
                                   context_limit=1)(sub_query)
        captured["resp"] = resp
        captured["ms"] = int((time.time() - began) * 1000)
        return resp

    plan = {"question": query, "branches": ["policy"], "sub_queries": {"policy": query}}
    model, usage = _model_factory()

    ctx.emit(AgentName.SUPERVISOR, "delegate", "派发分支：policy（规章与教务语料）", latency_ms=10)
    try:
        out = run(plan, model, policy_gate=_gate(), policy_search=policy_search)
    except Exception as exc:  # noqa: BLE001
        ctx.emit(AgentName.SUPERVISOR, "answer", f"调度异常：{type(exc).__name__}", latency_ms=10)
        return FinalAnswer(status="failed", text=f"调度异常：{exc}", trace=ctx.trace,
                           usage=Usage(latency_ms=int((time.time() - t0) * 1000), agent_calls=1))

    # --- 分支状态 -> trace
    state = (out.get("branches") or {}).get("policy", {})
    resp = captured.get("resp") or {}
    rows = resp.get("results") or []
    label = {"ok": f"命中 {len(rows)} 条证据", "empty": "返回 0 条证据",
             "failed": "分支失败", "not_called": "未调用"}.get(state.get("state"), "未知")
    ctx.emit("policy", "retrieve",
             f"{label}（status={resp.get('status', 'n/a')}）",
             n_evidence=len(rows), latency_ms=captured.get("ms", 0))
    for notice in out.get("notices") or []:
        ctx.emit(AgentName.SUPERVISOR, "reject", notice, latency_ms=5)

    attempts = out.get("attempts") or 1
    if attempts > 1:
        ctx.emit(AgentName.SUPERVISOR, "retry", f"第 {attempts} 次尝试（上一轮未通过）", latency_ms=5)

    ctx.emit(AgentName.ANSWERER, "answer", "基于证据生成逐条带引文的草稿", latency_ms=1)

    status = out.get("status")
    if status == "passed":
        ctx.emit(AgentName.VERIFIER, "result", "通过：引用、引文与年份范围均核对一致", latency_ms=5)
        prov = out.get("provenance")
        if prov:
            ctx.emit(AgentName.VERIFIER, "result", f"证据门：{prov}（原始文件哈希与索引一致）",
                     latency_ms=5)
    else:
        issues = out.get("issues") or []
        note = issues[0] if issues else ""
        if not isinstance(note, str):
            note = json.dumps(note, ensure_ascii=False)
        if not note.strip():
            note = _STATUS_TEXT.get(resp.get("status"), "证据不足，未给出可核验的结论")
        ctx.emit(AgentName.VERIFIER, "reject", f"{status}：{note[:140]}", latency_ms=5)

    # --- 证据卡片（无论是否通过都展示已检索到的证据）
    evs = [to_evidence(r, agent="policy", confidence=float(r.get("score") or 0.0)) for r in rows]
    if evs:
        top = max(e.confidence for e in evs) or 1.0
        for e in evs:
            e.confidence = round(max(e.confidence / top, 0.45) * 0.95, 3)

    # --- 答案文本
    if status == "passed" and out.get("answer"):
        sources = out.get("sources") or {}
        body = _prettify(out["answer"], sources)
        text = f"**依据官方资料，回答如下：**\n\n{body}"
        if out.get("unanswered"):
            text += "\n\n仍未能回答：" + "；".join(out["unanswered"])
        evs = [e for e in evs if e.evidence_id in sources] or evs
        return FinalAnswer(status="ok", text=text, evidence=evs,
                           confidence=round(sum(e.confidence for e in evs) / max(len(evs), 1), 3),
                           trace=ctx.trace,
                           usage=Usage(latency_ms=int((time.time() - t0) * 1000),
                                       tokens=usage["tokens"], cost_usd=0.0,
                                       agent_calls=usage["calls"] + 2))

    if status in ("insufficient_evidence", "clarification_required"):
        missing = "；".join(out.get("unanswered") or []) or \
                  _STATUS_TEXT.get(resp.get("status"), "问题所需的关键信息")
        flags = out.get("clarification_flags") or []
        head = "**现有资料不足以回答完整问题。**" if status == "insufficient_evidence" else \
               "**需要先澄清范围才能回答。**"
        extra = f"\n\n需要确认的限定条件：{', '.join(flags)}" if flags else ""
        return FinalAnswer(
            status="refused",
            text=f"{head}\n\n缺少：{missing}{extra}\n\n"
                 "按设计规则，证据不足时不给出推测性答案。可换用更具体的年份、"
                 "科目编号或项目编号再问一次。",
            evidence=evs, confidence=0.0, trace=ctx.trace,
            usage=Usage(latency_ms=int((time.time() - t0) * 1000), tokens=usage["tokens"],
                        agent_calls=usage["calls"] + 2))

    issue = out.get("issues")
    detail = issue[0] if isinstance(issue, list) and issue else issue
    return FinalAnswer(
        status="refused",
        text=f"**未通过校验，本条答案不展示。**\n\n原因：{detail}\n\n"
             "系统宁可拒答，也不输出未经核验的内容。",
        evidence=evs, confidence=0.0, trace=ctx.trace,
        usage=Usage(latency_ms=int((time.time() - t0) * 1000), tokens=usage["tokens"],
                    agent_calls=usage["calls"] + 2))
