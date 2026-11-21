"""Part 1 PolicyRetriever adapter for the Supervisor's policy_search slot.

Two integration requirements from the Part 1 handoff (START_HERE.md,
PART1_GUIDE.md, examples/policy_agent_example.py):

1. Hand the FULL ``PolicyRetriever.search()`` dictionary downstream. ``status``,
   ``year_filters`` and every ``requires_*_clarification`` flag must survive,
   because they drive the Supervisor's follow-up questions about academic year
   and admission cohort. Passing only ``results`` loses that information.
2. Where a rule's applicability continues across a page boundary, include the
   adjacent passages from ``retriever.context(evidence_id)`` together with
   their evidence IDs, so the Answerer/Verifier can see the full clause.

The adapter uses duck typing (any object with ``search`` and optional
``context``), so it does not import ``policy_rag`` or require the Part 1 index
to be installed. It never rewrites ``status``, ``year_filters`` or any
``requires_*_clarification`` flag.

Usage:
    from policy_adapter import build_policy_search
    from supervisor import run

    policy_search = build_policy_search(
        retriever, search_kwargs={"academic_year": "2026/27", "top_k": 3})
    result = run(plan, model, policy_search=policy_search, policy_gate=verify_claims)

Run offline tests: python3 -B -m unittest test_policy_adapter -v
"""
import copy

_CONTEXT_WARNING = (
    "Adjacent passage from retriever.context(); an applicability condition "
    "may continue across the page boundary."
)


def build_policy_search(retriever, search_kwargs=None, context_limit=3,
                        include_context=True):
    """Wrap a Part 1 retriever into a Supervisor-compatible policy_search.

    Args:
        retriever: object exposing ``search(query, **kwargs) -> dict`` and,
            optionally, ``context(evidence_id) -> list[dict]``.
        search_kwargs: forwarded unchanged to ``retriever.search`` (e.g.
            ``student_type``, ``academic_year``, ``entry_year``, ``top_k``).
        context_limit: how many top-ranked results get adjacent passages.
        include_context: set False to pass ``search()`` through unchanged.

    Returns:
        callable ``(query) -> dict`` with every original field preserved and
        ``results`` possibly extended by de-duplicated context passages.
    """
    if not hasattr(retriever, "search") or not callable(retriever.search):
        raise ValueError("retriever must provide a callable search()")
    if search_kwargs is None:
        search_kwargs = {}
    if not isinstance(search_kwargs, dict):
        raise ValueError("search_kwargs must be a dict or None")
    if not isinstance(context_limit, int) or context_limit < 0:
        raise ValueError("context_limit must be a nonnegative integer")

    def policy_search(query):
        response = retriever.search(query, **search_kwargs)
        if not isinstance(response, dict):
            raise ValueError("retriever.search() must return a dict")

        result = dict(response)  # shallow copy: every original key survives
        results = list(response.get("results") or [])
        limitations = list(response.get("limitations") or [])

        if include_context and context_limit and hasattr(retriever, "context"):
            seen = {row.get("evidence_id") for row in results
                    if isinstance(row, dict) and row.get("evidence_id")}
            context_failures = 0
            added = 0

            for row in results[:context_limit]:
                if not isinstance(row, dict):
                    continue
                anchor = row.get("evidence_id")
                if not anchor:
                    continue
                try:
                    neighbours = retriever.context(anchor) or []
                except Exception:  # context is optional enrichment, not fatal
                    context_failures += 1
                    continue
                for item in neighbours:
                    if not isinstance(item, dict):
                        continue
                    evidence_id = item.get("evidence_id")
                    text = item.get("text")
                    citation = item.get("citation")
                    if (not evidence_id or evidence_id in seen
                            or not isinstance(text, str) or not text.strip()
                            or not isinstance(citation, dict)
                            or not citation.get("title")):
                        continue  # dedupe + collect_evidence's required fields
                    record = {
                        "evidence_id": evidence_id,
                        "text": text,
                        "citation": copy.deepcopy(citation),
                        "warnings": list(item.get("warnings") or []) + [_CONTEXT_WARNING],
                        "origin": "context",
                        "anchor_evidence_id": anchor,
                    }
                    results.append(record)
                    seen.add(evidence_id)
                    added += 1

            if added:
                limitations.append(
                    "%d adjacent passage(s) from retriever.context() were added "
                    "with their evidence IDs for cross-page clauses." % added)
            if context_failures:
                limitations.append(
                    "%d context() call(s) failed; adjacent passages may be missing."
                    % context_failures)

        result["results"] = results
        result["limitations"] = limitations
        return result

    policy_search.__name__ = "policy_search"
    return policy_search
