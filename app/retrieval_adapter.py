"""Part 1 适配层：henry 的 PolicyRetriever 返回结构 -> 组内统一 Evidence 契约。

这是 5 号位（前端+测试）的集成界面：上层 agent 只认 Evidence，
下层怎么检索、用哪个模型、索引怎么建，全部封在这里。

用法：
    from app.retrieval_adapter import search
    evs = search("Can I retake a subject to improve my grade?",
                 top_k=5, source_types=["handbook"], agent="policy")

若 policy_rag 不在同一仓库，设置环境变量 POLICY_RAG_HOME 指向 part1 解压目录。
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_EXTRA = os.environ.get("POLICY_RAG_HOME")
if _EXTRA and _EXTRA not in sys.path:
    sys.path.insert(0, _EXTRA)

from contracts import Evidence  # noqa: E402

# ---------------------------------------------------------------- 来源 -> 权威等级
# 依据 contracts.AUTHORITY_PRIORITY：学则 > 培养方案 > 课程目录 > 官网 > 第三方
SOURCE_TYPE_TO_AUTHORITY = {
    "handbook": "regulation",
    "procedure": "regulation",
    "programme_requirements": "programme_requirement",
    "programme_requirement": "programme_requirement",
    "programme_information": "programme_requirement",
    "programme_catalogue": "programme_requirement",
    "programme_directory": "programme_requirement",
    "programme_guidance": "programme_requirement",
    "subject_description": "course_catalogue",
    "faq": "official_web",
    "student_service": "official_web",
    "academic_unit_information": "official_web",
    "research_programme_information": "official_web",
}


def _first_sentence(text: str, limit: int = 160) -> str:
    """占位 claim。

    注意：retriever 的 passage 常以章节标题开头（"C. Retaking of Failed Subjects"），
    直接取首句会得到 "C." 这种垃圾。所以先丢掉开头的短标题行，再取第一个够长的句子。
    真实 claim 仍应由 agent 基于证据重写，这里只是保证前端不会显示半句话。
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    while lines and len(lines[0]) < 60 and not lines[0].endswith((".", "?", "!", "。")):
        lines.pop(0)
    flat = " ".join(lines) if lines else " ".join(text.split())
    for sent in re.split(r"(?<=[.!?。])\s+", flat):
        if len(sent) >= 40:
            return sent[:limit].strip()
    return flat[:limit].strip()


def to_evidence(result: dict, agent: str = "", confidence: float | None = None) -> Evidence:
    """单条 retriever 结果 -> Evidence。"""
    citation = result.get("citation") or {}
    source_type = (result.get("source_type") or "").lower()
    return Evidence(
        claim=_first_sentence(result.get("text", "")),
        source_id=result.get("source_id", ""),
        quote=result.get("text", ""),
        page=citation.get("pdf_page"),
        authority=SOURCE_TYPE_TO_AUTHORITY.get(source_type, "official_web"),
        confidence=confidence if confidence is not None else 0.0,
        agent=agent,
        evidence_id=result.get("evidence_id", ""),
        title=citation.get("title", ""),
        section=citation.get("section", ""),
        warnings=list(result.get("warnings") or []),
    )


def _normalize_scores(evidence: list[Evidence]) -> None:
    """BM25/余弦原始分不是概率，直接当 confidence 会显示成 18.37。
    组内约定：按本批最高分归一化到 (0,1]，并压低到 0.45 以下区间以外的最小值。"""
    if not evidence:
        return
    top = max((e.confidence for e in evidence), default=0.0)
    if top <= 0:
        return
    for e in evidence:
        e.confidence = round(max(e.confidence / top, 0.45) * 0.95, 3)


_RETRIEVER = None


def _default_method() -> str:
    """没有 sentence-transformers 时，hybrid 会静默返回 0 条（已实测）。
    这里显式探测：装了就 hybrid，没装就退回 bm25，避免"明明有数据却查不到"。"""
    try:
        import sentence_transformers  # noqa: F401
        return "hybrid"
    except Exception:  # noqa: BLE001
        return "bm25"


def _get_retriever():
    """索引加载约 1s，全局复用一次即可，否则每条查询都要重新加载。"""
    global _RETRIEVER
    if _RETRIEVER is None:
        from policy_rag.retrieve import PolicyRetriever
        _RETRIEVER = PolicyRetriever()
    return _RETRIEVER


def search_full(query: str, top_k: int = 5, agent: str = "", **filters) -> tuple[list[Evidence], dict]:
    """返回 (Evidence, 完整原始响应)。

    第二条返回值**原样保留 results 及 status / year_filters / limitations /
    requires_*_clarification** —— 因为 Answerer/Verifier 的 `collect_evidence()`
    直接吃这个原始字典。只传 results 会丢掉"需要追问学年/入学批次"的信号。
    """
    filters.setdefault("method", _default_method())
    resp = _get_retriever().search(query=query, top_k=top_k, **filters)
    raw = resp.get("results") or []
    evs = [to_evidence(r, agent=agent, confidence=float(r.get("score") or 0.0)) for r in raw]
    _normalize_scores(evs)
    return evs, resp


def adjacent(evidence_id: str, agent: str = "") -> list[Evidence]:
    """取同源相邻段落（跨页条款用），保留 evidence_id 以便 Verifier 回溯。"""
    rows = _get_retriever().context(evidence_id)
    return [to_evidence(r, agent=agent, confidence=0.0) for r in rows]


def search(query: str, top_k: int = 5, agent: str = "", **filters) -> tuple[list[Evidence], dict]:
    """只要 UI 用的 Evidence 和元信息时用这个；需要喂 Answerer 请用 search_full。

    常用 filters（透传给 retriever）：
        method="hybrid"|"bm25"|"semantic"（不传则自动探测）
        knowledge_domain="policy"|"academic_information"|"student_services"|"all"
        academic_year="2026/27"
        student_type="undergraduate"
        source_types=["handbook"]
        programme_code=..., entry_year=..., subject_codes=[...]
    """
    evs, resp = search_full(query, top_k=top_k, agent=agent, **filters)
    meta = {k: v for k, v in resp.items() if k != "results"}
    return evs, meta
