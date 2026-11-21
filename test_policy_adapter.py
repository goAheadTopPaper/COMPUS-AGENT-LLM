"""Offline tests for policy_adapter.py. Run: python3 -B -m unittest test_policy_adapter -v

Fake Part 1 retrievers only: no index, model weights or network needed.
"""
import copy
import unittest

from agents import collect_evidence
from policy_adapter import build_policy_search
from supervisor import run

QUESTION = "Can I withdraw before the deadline in 2026/27?"


class FakeRetriever:
    """Minimal duck-typed Part 1 retriever."""

    def __init__(self, response, contexts=None, context_error=False):
        self.response = response
        self.contexts = contexts or {}
        self.context_error = context_error
        self.search_calls = []
        self.context_calls = []

    def search(self, query, **kwargs):
        self.search_calls.append((query, kwargs))
        return copy.deepcopy(self.response)

    def context(self, evidence_id):
        self.context_calls.append(evidence_id)
        if self.context_error:
            raise KeyError(evidence_id)
        return copy.deepcopy(self.contexts.get(evidence_id, []))


def row(eid, text):
    return {
        "evidence_id": eid,
        "text": text,
        "citation": {"title": "Handbook 2026/27", "pdf_page": 7},
    }


def response():
    return {
        "query": "withdrawal",
        "method": "hybrid",
        "status": "candidates_found",
        "year_filters": {"academic_year": "2026/27", "entry_year": None,
                         "entry_term": None, "strict_year": True},
        "requires_year_clarification": True,
        "requires_entry_term_clarification": False,
        "requires_programme_clarification": True,
        "requires_admission_pathway_clarification": False,
        "requires_policy_clarification": False,
        "available_academic_years": ["2025/26", "2026/27"],
        "results": [row("chunk-1", "A student may withdraw by week 4.")],
        "limitations": ["Scores are relevance measures."],
    }


class PolicyAdapterTests(unittest.TestCase):
    def test_full_search_fields_are_preserved(self):
        source = response()
        retriever = FakeRetriever(source)
        result = build_policy_search(retriever)(QUESTION)

        for key, value in source.items():
            if key in ("results", "limitations"):
                continue
            self.assertEqual(result[key], value, key)
        self.assertEqual(result["status"], "candidates_found")
        self.assertEqual(result["year_filters"]["academic_year"], "2026/27")
        self.assertTrue(result["requires_year_clarification"])
        self.assertTrue(result["requires_programme_clarification"])
        self.assertFalse(result["requires_entry_term_clarification"])

    def test_search_kwargs_forwarded_unchanged(self):
        retriever = FakeRetriever(response())
        build_policy_search(
            retriever,
            search_kwargs={"academic_year": "2026/27", "student_type": "taught_postgraduate",
                           "top_k": 3})("withdraw")
        self.assertEqual(
            retriever.search_calls,
            [("withdraw", {"academic_year": "2026/27",
                           "student_type": "taught_postgraduate", "top_k": 3})])

    def test_context_passages_added_with_evidence_ids(self):
        neighbour = row("chunk-2", "After week 4 a withdrawal requires approval.")
        retriever = FakeRetriever(response(), {"chunk-1": [
            row("chunk-1", "A student may withdraw by week 4."),  # self, must dedupe
            neighbour,
        ]})
        result = build_policy_search(retriever)(QUESTION)

        ids = [r["evidence_id"] for r in result["results"]]
        self.assertEqual(ids, ["chunk-1", "chunk-2"])
        added = result["results"][1]
        self.assertEqual(added["origin"], "context")
        self.assertEqual(added["anchor_evidence_id"], "chunk-1")
        self.assertTrue(any("Adjacent passage" in w for w in added["warnings"]))
        self.assertTrue(any("1 adjacent passage" in x for x in result["limitations"]))
        self.assertEqual(retriever.context_calls, ["chunk-1"])

    def test_context_is_deduplicated_across_anchors(self):
        source = response()
        source["results"] = [row("a", "Rule part one."), row("b", "Rule part two.")]
        retriever = FakeRetriever(source, {
            "a": [row("a", "Rule part one."), row("shared", "Shared clause.")],
            "b": [row("shared", "Shared clause."), row("c", "Final clause.")],
        })
        result = build_policy_search(retriever)(QUESTION)

        ids = [r["evidence_id"] for r in result["results"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, ["a", "b", "shared", "c"])
        bundle = collect_evidence(result, [])  # no Conflicting evidence ID
        self.assertEqual(len(bundle["evidence"]), 4)

    def test_context_failure_is_downgraded(self):
        retriever = FakeRetriever(response(), context_error=True)
        result = build_policy_search(retriever)(QUESTION)

        self.assertEqual(result["status"], "candidates_found")
        self.assertEqual(len(result["results"]), 1)
        self.assertTrue(any("context() call(s) failed" in x
                            for x in result["limitations"]))

    def test_include_context_false_passes_through(self):
        retriever = FakeRetriever(response(), {"chunk-1": [row("chunk-2", "Extra.")]})
        result = build_policy_search(retriever, include_context=False)(QUESTION)

        self.assertEqual(retriever.context_calls, [])
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["status"], "candidates_found")

    def test_invalid_retriever_rejected(self):
        with self.assertRaises(ValueError):
            build_policy_search(object())
        with self.assertRaises(ValueError):
            build_policy_search(FakeRetriever(response()), context_limit=-1)

    def test_supervisor_receives_flags_scope_status_and_context(self):
        neighbour = row("chunk-2", "After week 4 a withdrawal requires approval.")
        retriever = FakeRetriever(response(), {"chunk-1": [
            row("chunk-1", "A student may withdraw by week 4."), neighbour]})
        policy_search = build_policy_search(retriever)
        seen = []

        def model(system, payload):
            seen.append(copy.deepcopy(payload))
            if "Use only the supplied evidence" in system:
                return {"claims": [{
                    "text": "Withdrawal by week 4 is allowed.",
                    "supports": [{"evidence_id": "chunk-1",
                                  "quote": "A student may withdraw by week 4."}],
                }]}
            return {"checks": [{"index": 0, "status": "supported",
                                "reason": "fixture"}],
                    "unanswered": [], "needs_clarification": False}

        result = run({"question": QUESTION, "branches": ["policy"],
                      "sub_queries": {"policy": "withdrawal rule"}},
                     model, policy_search=policy_search)

        # Clarification flags force clarification_required instead of exposing
        # an answer -- exactly the follow-up signal the Part 1 team asked to keep.
        self.assertEqual(result["status"], "clarification_required")
        self.assertFalse(result["approved"])
        self.assertNotIn("answer", result)
        self.assertEqual(result["clarification_flags"],
                         ["requires_programme_clarification", "requires_year_clarification"])
        answer_payload, verify_payload = seen[0], seen[1]
        self.assertEqual(answer_payload["policy_status"], "candidates_found")
        self.assertEqual(answer_payload["policy_scope"]["academic_year"], "2026/27")
        self.assertEqual(answer_payload["clarification_flags"],
                         ["requires_programme_clarification", "requires_year_clarification"])
        self.assertIn("chunk-2", answer_payload["evidence"])
        self.assertIn("chunk-2", verify_payload["evidence"])
        self.assertTrue(any("Adjacent passage" in w
                            for w in answer_payload["evidence"]["chunk-2"]["warnings"]))


if __name__ == "__main__":
    unittest.main()
