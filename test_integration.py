"""Joint acceptance: Part 1 Policy + Schedule + Supervisor + Answerer/Verifier.

Run: python3 -B -m unittest test_integration -v

Implements the minimum joint-acceptance list at the end of INTEGRATION.md:
policy-only, schedule-only, mixed query, insufficient evidence, and a draft
whose quote is correct but whose time is wrong.

Everything is offline: the Part 1 retriever is duck-typed, the timetable is a
fixture, and the model is scripted. The model is the only place that would be
replaced by a real LLM adapter.
"""
import copy
import unittest

from policy_adapter import build_policy_search
from schedule_evidence import build_schedule_search
from supervisor import run

QUESTION = "What is the prerequisite for COMP5926 and when is its exam?"
PREREQ_TEXT = "Pre-requisite: COMP5925 Metaverse Project I"
EXAM_EVENT = {"courseCode": "COMP5926", "type": "Exam",
              "start": "2026-11-23T14:00:00+08:00",
              "end": "2026-11-23T17:00:00+08:00", "room": "A101",
              "warnings": ["Synthetic demo data"]}


class FakePolicyRetriever:
    """Duck-typed Part 1 retriever: search() plus optional context()."""

    def __init__(self, response, contexts=None):
        self.response = response
        self.contexts = contexts or {}

    def search(self, query, **kwargs):
        return copy.deepcopy(self.response)

    def context(self, evidence_id):
        return copy.deepcopy(self.contexts.get(evidence_id, []))


def policy_response(flags=None):
    response = {
        "query": "COMP5926 prerequisite",
        "method": "bm25",
        "status": "candidates_found",
        "year_filters": {"academic_year": "2026/27", "entry_year": None,
                         "entry_term": None, "strict_year": False},
        "available_academic_years": ["2025/26", "2026/27"],
        "results": [{
            "evidence_id": "policy:comp5926:prereq",
            "text": PREREQ_TEXT,
            "citation": {"title": "COMP5926 Subject Description",
                         "pdf_page": 1, "source_url": "https://example.edu/comp5926.pdf"},
            "academic_year": "2026/27",
            "warnings": [],
        }],
        "limitations": ["Scores are relevance measures."],
        "requires_year_clarification": False,
        "requires_programme_clarification": False,
        "requires_entry_term_clarification": False,
        "requires_admission_pathway_clarification": False,
        "requires_policy_clarification": False,
    }
    response.update(flags or {})
    return response


class ScriptedModel:
    """Answerer and Verifier responses in call order."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, system, payload):
        self.calls.append((system, copy.deepcopy(payload)))
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]

    @property
    def answer_payload(self):
        return self.calls[0][1]

    @property
    def verify_payload(self):
        return self.calls[1][1]


def claim(text, evidence_id, quote):
    return {"text": text, "supports": [{"evidence_id": evidence_id, "quote": quote}]}


def review(statuses, unanswered=(), needs_clarification=False):
    return {"checks": [{"index": i, "status": status, "reason": "fixture"}
                       for i, status in enumerate(statuses)],
            "unanswered": list(unanswered),
            "needs_clarification": needs_clarification}


def wiring(flags=None):
    policy_search = build_policy_search(
        FakePolicyRetriever(policy_response(flags)),
        search_kwargs={"academic_year": "2026/27", "top_k": 3})
    schedule_search = build_schedule_search(
        lambda query: [EXAM_EVENT], source_title="Mock schedule (synthetic)")
    return policy_search, schedule_search


class JointAcceptanceTests(unittest.TestCase):
    def test_policy_only_query(self):
        policy_search, schedule_search = wiring()
        model = ScriptedModel(
            {"claims": [claim("COMP5926 requires COMP5925.",
                              "policy:comp5926:prereq", PREREQ_TEXT)]},
            review(["supported"]))
        result = run({"question": QUESTION, "branches": ["policy"]}, model,
                     policy_search=policy_search, schedule_search=schedule_search)

        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["approved"])
        self.assertEqual(list(result["sources"]), ["policy:comp5926:prereq"])
        self.assertEqual(result["sources"]["policy:comp5926:prereq"]["citation"]["title"],
                         "COMP5926 Subject Description")
        self.assertEqual(result["branches"]["schedule"]["state"], "not_called")

    def test_schedule_only_query(self):
        policy_search, schedule_search = wiring()
        row = schedule_search("COMP5926")[0]
        model = ScriptedModel(
            {"claims": [claim("The exam runs 14:00-17:00 in room A101 on 23 November 2026.",
                              row["evidence_id"], row["text"])]},
            review(["supported"]))
        result = run({"question": "When is the COMP5926 exam?", "branches": ["schedule"]},
                     model, policy_search=policy_search, schedule_search=schedule_search)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(list(result["sources"]), [row["evidence_id"]])
        self.assertTrue(row["evidence_id"].startswith("schedule:"))
        self.assertEqual(result["branches"]["policy"]["state"], "not_called")

    def test_mixed_query_displays_both_citation_kinds(self):
        policy_search, schedule_search = wiring()
        row = schedule_search("COMP5926")[0]
        model = ScriptedModel(
            {"claims": [claim("COMP5926 requires COMP5925.",
                              "policy:comp5926:prereq", PREREQ_TEXT),
                        claim("The exam is on 2026-11-23 from 14:00 to 17:00.",
                              row["evidence_id"], row["text"])]},
            review(["supported", "supported"]))
        result = run({"question": QUESTION, "branches": ["policy", "schedule"]}, model,
                     policy_search=policy_search, schedule_search=schedule_search)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(set(result["sources"]), {"policy:comp5926:prereq",
                                                  row["evidence_id"]})
        self.assertIn("[policy:comp5926:prereq]", result["answer"])
        self.assertIn("[%s]" % row["evidence_id"], result["answer"])
        # One full question, both branches in the same bundle.
        for payload in (model.answer_payload, model.verify_payload):
            self.assertEqual(payload["question"], QUESTION)
            self.assertIn("policy:comp5926:prereq", payload["evidence"])
            self.assertIn(row["evidence_id"], payload["evidence"])
            self.assertEqual(payload["evidence"][row["evidence_id"]]["kind"], "schedule")

    def test_insufficient_evidence_hides_the_draft(self):
        policy_search, schedule_search = wiring()
        model = ScriptedModel(
            {"claims": [claim("COMP5926 requires COMP5925.",
                              "policy:comp5926:prereq", PREREQ_TEXT)]},
            review(["supported"], unanswered=["exam room"]))
        result = run({"question": QUESTION + " Which room is it in?",
                      "branches": ["policy", "schedule"]}, model,
                     policy_search=policy_search, schedule_search=schedule_search)

        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertFalse(result["approved"])
        self.assertEqual(result["unanswered"], ["exam room"])
        self.assertNotIn("answer", result)
        self.assertNotIn("sources", result)

    def test_correct_quote_with_wrong_draft_time_is_rejected(self):
        policy_search, schedule_search = wiring()
        row = schedule_search("COMP5926")[0]
        model = ScriptedModel(
            {"claims": [claim("The exam starts at 15:00.",
                              row["evidence_id"], row["text"])]},  # quote is verbatim
            review(["contradicted"]))
        result = run({"question": "When is the COMP5926 exam?", "branches": ["schedule"]},
                     model, policy_search=policy_search, schedule_search=schedule_search,
                     max_retries=0)

        self.assertEqual(result["status"], "rejected")
        self.assertNotIn("answer", result)
        self.assertTrue(result["issues"])

    def test_policy_flags_force_clarification_not_an_answer(self):
        policy_search, schedule_search = wiring({"requires_year_clarification": True})
        model = ScriptedModel(
            {"claims": [claim("COMP5926 requires COMP5925.",
                              "policy:comp5926:prereq", PREREQ_TEXT)]},
            review(["supported"]))
        result = run({"question": QUESTION, "branches": ["policy"]}, model,
                     policy_search=policy_search, schedule_search=schedule_search,
                     max_retries=0)

        self.assertEqual(result["status"], "clarification_required")
        self.assertEqual(result["clarification_flags"], ["requires_year_clarification"])
        self.assertNotIn("answer", result)

    def test_part1_gate_is_wired_through(self):
        policy_search, schedule_search = wiring()
        gate_calls = []

        def gate(payload):
            gate_calls.append(payload)
            return {"status": "pending_semantic_review"}

        model = ScriptedModel(
            {"claims": [claim("COMP5926 requires COMP5925.",
                              "policy:comp5926:prereq", PREREQ_TEXT)]},
            review(["supported"]))
        result = run({"question": QUESTION, "branches": ["policy"]}, model,
                     policy_search=policy_search, schedule_search=schedule_search,
                     policy_gate=gate)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["provenance"], "pending_semantic_review")
        self.assertEqual(len(gate_calls), 1)
        self.assertEqual(gate_calls[0]["retrieved_evidence_ids"],
                         ["policy:comp5926:prereq"])


if __name__ == "__main__":
    unittest.main()
