"""Supervisor scheduler tests. Run: python3 -B -m unittest test_supervisor -v

All agents are scripted fixtures: no LLM endpoint, Canvas token or Part 1 index
is needed. Verifies the joint-acceptance list in INTEGRATION.md.
"""
import unittest

from supervisor import run

QUESTION = "What is the prerequisite for COMP5926 and when is its exam?"
PREREQ = "Pre-requisite: COMP5925 Metaverse Project I"
EXAM = "COMP5926 exam: 2026-11-23 14:00 Asia/Hong_Kong; room A101."

POLICY = {
    "status": "candidates_found",
    "results": [{"evidence_id": "policy:p1", "text": PREREQ,
                 "citation": {"title": "Handbook 2026/27", "source_url": "https://example.edu/hb"},
                 "academic_year": "2026/27", "page": 12}],
    "year_filters": {"year": "2026/27"},
    "limitations": ["only 2026/27 indexed"],
    "requires_year_clarification": False,
}
SCHEDULE = [{"evidence_id": "schedule:e1", "text": EXAM,
             "citation": {"title": "Mock schedule"}, "course_code": "COMP5926"}]


def claim(text, evidence_id, quote):
    return {"text": text, "supports": [{"evidence_id": evidence_id, "quote": quote}]}


def review(statuses, unanswered=(), needs_clarification=False):
    return {"checks": [{"index": i, "status": status, "reason": "fixture"}
                       for i, status in enumerate(statuses)],
            "unanswered": list(unanswered),
            "needs_clarification": needs_clarification}


class ScriptedModel:
    """Answers in call order; an Exception entry simulates a model outage."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.index = 0

    def __call__(self, system, payload):
        self.calls.append((system, payload))
        response = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        if isinstance(response, Exception):
            raise response
        return response


class SupervisorTests(unittest.TestCase):
    def test_policy_only_keeps_full_search_dict_and_same_question(self):
        seen = []

        def policy_search(query):
            seen.append(query)
            return POLICY

        draft = {"claims": [claim("COMP5926 requires COMP5925.", "policy:p1", PREREQ)]}
        model = ScriptedModel(draft, review(["supported"]))
        result = run({"question": QUESTION, "branches": ["policy"],
                      "sub_queries": {"policy": "COMP5926 prerequisite"}},
                     model, policy_search=policy_search)

        self.assertEqual(seen, ["COMP5926 prerequisite"])
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["approved"])
        self.assertIn("COMP5926 requires COMP5925.", result["answer"])
        self.assertEqual(list(result["sources"]), ["policy:p1"])
        self.assertEqual(result["branches"]["policy"]["state"], "ok")
        self.assertEqual(result["branches"]["schedule"]["state"], "not_called")
        self.assertEqual(len(model.calls), 2)
        for _, payload in model.calls:
            self.assertEqual(payload["question"], QUESTION)  # same full question
        answer_payload = model.calls[0][1]
        self.assertEqual(answer_payload["policy_scope"], POLICY["year_filters"])
        self.assertEqual(answer_payload["limitations"], POLICY["limitations"])
        self.assertEqual(answer_payload["evidence"]["policy:p1"]["citation"]["title"],
                         "Handbook 2026/27")

    def test_schedule_only_and_evidence_list_contract(self):
        draft = {"claims": [claim("Exam is 14:00 on 2026-11-23.", "schedule:e1", EXAM)]}
        model = ScriptedModel(draft, review(["supported"]))
        result = run({"question": QUESTION, "branches": ["schedule"]}, model,
                     schedule_search=lambda q: SCHEDULE)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(list(result["sources"]), ["schedule:e1"])
        self.assertEqual(result["branches"]["policy"]["state"], "not_called")
        self.assertIn(EXAM, model.calls[0][1]["evidence"]["schedule:e1"]["text"])

    def test_mixed_query_displays_both_citation_kinds(self):
        draft = {"claims": [claim("Prerequisite is COMP5925.", "policy:p1", PREREQ),
                            claim("Exam is at 14:00.", "schedule:e1", EXAM)]}
        model = ScriptedModel(draft, review(["supported", "supported"]))
        result = run({"question": QUESTION, "branches": ["policy", "schedule"]}, model,
                     policy_search=lambda q: POLICY, schedule_search=lambda q: SCHEDULE)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(set(result["sources"]), {"policy:p1", "schedule:e1"})
        self.assertIn("[policy:p1]", result["answer"])
        self.assertIn("[schedule:e1]", result["answer"])

    def test_insufficient_evidence_never_exposes_draft(self):
        draft = {"claims": [claim("Guessed answer.", "policy:p1", PREREQ)]}
        model = ScriptedModel(draft, review([]))
        result = run({"question": QUESTION, "branches": []}, model, max_retries=0)

        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertFalse(result["approved"])
        self.assertNotIn("answer", result)
        self.assertNotIn("sources", result)

    def test_correct_quote_but_wrong_time_is_rejected(self):
        draft = {"claims": [claim("Exam is at 15:00.", "schedule:e1", EXAM)]}
        model = ScriptedModel(draft, review(["contradicted"]))
        result = run({"question": QUESTION, "branches": ["schedule"]}, model,
                     schedule_search=lambda q: SCHEDULE, max_retries=0)

        self.assertEqual(result["status"], "rejected")
        self.assertNotIn("answer", result)
        self.assertTrue(result["issues"])

    def test_clarification_required_surfaces_flags(self):
        policy = dict(POLICY, requires_year_clarification=True)
        draft = {"claims": [claim("Prerequisite is COMP5925.", "policy:p1", PREREQ)]}
        model = ScriptedModel(draft, review(["supported"], needs_clarification=True))
        result = run({"question": QUESTION, "branches": ["policy"]}, model,
                     policy_search=lambda q: policy, max_retries=0)

        self.assertEqual(result["status"], "clarification_required")
        self.assertEqual(result["clarification_flags"], ["requires_year_clarification"])
        self.assertNotIn("answer", result)

    def test_branch_failure_is_reported_not_fatal_and_masks_secrets(self):
        def policy_search(_):
            raise RuntimeError("token=sk-super-secret-12345 rejected")

        draft = {"claims": [claim("Exam is at 14:00.", "schedule:e1", EXAM)]}
        model = ScriptedModel(draft, review(["supported"]))
        result = run({"question": QUESTION, "branches": ["policy", "schedule"]}, model,
                     policy_search=policy_search, schedule_search=lambda q: SCHEDULE,
                     max_retries=0)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["branches"]["policy"]["state"], "failed")
        self.assertTrue(any("规章检索失败" in n for n in result["notices"]))
        self.assertNotIn("sk-super-secret-12345", str(result))

    def test_retry_only_re_calls_failed_branch_and_keeps_notice(self):
        calls = []

        def policy_search(_):
            calls.append(1)
            if len(calls) == 1:
                raise TimeoutError("gateway timeout")
            return POLICY

        draft = {"claims": [claim("Prerequisite is COMP5925.", "policy:p1", PREREQ)]}
        model = ScriptedModel(draft, review(["supported"]))
        result = run({"question": QUESTION, "branches": ["policy"]}, model,
                     policy_search=policy_search)

        self.assertEqual(calls, [1, 1])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["branches"]["policy"]["state"], "ok")
        self.assertTrue(any("规章检索失败" in n for n in result["notices"]))

    def test_rejected_draft_is_rewritten_once(self):
        model = ScriptedModel(
            {"claims": [claim("Wrong time.", "schedule:e1", EXAM)]},
            review(["contradicted"]),
            {"claims": [claim("Right time 14:00.", "schedule:e1", EXAM)]},
            review(["supported"]),
        )
        result = run({"question": QUESTION, "branches": ["schedule"]}, model,
                     schedule_search=lambda q: SCHEDULE)

        self.assertEqual(result["attempts"], 2)
        self.assertEqual(result["status"], "passed")
        self.assertIn("Right time 14:00.", result["answer"])

    def test_model_exception_has_no_draft_and_bounded_retry(self):
        model = ScriptedModel(RuntimeError("model down"), RuntimeError("model down"))
        result = run({"question": QUESTION, "branches": ["policy"]}, model,
                     policy_search=lambda q: POLICY)

        self.assertEqual(result["status"], "model_error")
        self.assertEqual(result["attempts"], 2)
        self.assertNotIn("answer", result)
        self.assertEqual(model.index, 2)

    def test_policy_gate_is_forwarded(self):
        gate_calls = []

        def gate(payload):
            gate_calls.append(payload)
            return {"status": "pending_semantic_review"}

        draft = {"claims": [claim("Prerequisite is COMP5925.", "policy:p1", PREREQ)]}
        model = ScriptedModel(draft, review(["supported"]))
        run({"question": QUESTION, "branches": ["policy"]}, model,
            policy_gate=gate, policy_search=lambda q: POLICY)

        self.assertEqual(len(gate_calls), 1)
        self.assertEqual(gate_calls[0]["retrieved_evidence_ids"], ["policy:p1"])

    def test_invalid_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            run({"branches": []}, ScriptedModel())
        with self.assertRaises(ValueError):
            run({"question": QUESTION}, object())


if __name__ == "__main__":
    unittest.main(verbosity=2)
