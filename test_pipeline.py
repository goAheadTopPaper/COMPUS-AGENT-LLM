"""Contract tests with synthetic HTTP/model outputs; no network or credentials."""
from datetime import date
import unittest

from agents import ANSWER_PROMPT, VERIFY_PROMPT
from schedule_agent import (ScheduleAgent, ScheduleError, SUBJECTS_URL,
                            ARRANGEMENTS_URL, current_term)
from supervisor import SupervisorAgent, PLAN_PROMPT
from programme_resolver import ProgrammeResolver


def meeting(group="A", start="09:00", fm=1, to=15, component="LEC"):
    return {"quotaGroupCode": group, "deliveryTimeFrom": start, "deliveryTimeTo": "10:00",
            "acadWeekFm": fm, "acadWeekTo": to, "roomCodeList": ["A101"],
            "cttDayOfWeekTk": "MON", "componentType": component, "subjectCode": "COMP5926"}


class FakeTransport:
    def __init__(self, rows=None):
        self.rows = rows if rows is not None else [meeting()]
        self.calls = []

    def __call__(self, url, payload):
        self.calls.append((url, payload))
        if url == SUBJECTS_URL:
            return {"data": [{"id": 41243, "subjectCode": "COMP5926", "subjectTitle": "Metaverse Project II"}]}
        return {"data": self.rows}


class FakePolicy:
    def __init__(self, fail=False):
        self.fail = fail

    def search(self, question, **kwargs):
        if self.fail:
            raise OSError("offline")
        return {"status": "candidates_found", "results": [{"evidence_id": "policy:1",
                "text": "Pre-requisite: COMP5925", "citation": {"title": "Synthetic policy"}}]}

    def verify_claims(self, payload):
        return {"status": "pending_semantic_review"}


class FakeModel:
    def __init__(self, verdicts=None):
        self.verdicts = list(verdicts or ["supported"])
        self.calls = []

    def __call__(self, system, payload):
        self.calls.append((system, payload))
        if system == PLAN_PROMPT:
            return {"branches": ["policy", "schedule"], "policy_query": "COMP5926 prerequisite",
                    "course_queries": ["COMP5926"]}
        if system == ANSWER_PROMPT:
            return {"claims": [{"text": row["text"], "supports": [{"evidence_id": key, "quote": row["text"]}]}
                               for key, row in payload["evidence"].items()]}
        if system == VERIFY_PROMPT:
            verdict = self.verdicts.pop(0) if len(self.verdicts) > 1 else self.verdicts[0]
            return {"checks": [{"index": i, "status": verdict, "reason": "Synthetic verdict"}
                               for i in range(len(payload["claims"]))],
                    "unanswered": [], "needs_clarification": False}
        raise AssertionError("Unexpected model prompt")


class ScheduleTests(unittest.TestCase):
    def agent(self, rows=None):
        return ScheduleAgent(9134, transport=FakeTransport(rows), today=date(2026, 11, 22))

    def test_term_boundaries(self):
        for day, expected in [(date(2027, 1, 31), ("2026", "1")),
                              (date(2027, 2, 1), ("2026", "2")),
                              (date(2027, 7, 1), ("2026", "3")),
                              (date(2027, 9, 1), ("2027", "1"))]:
            self.assertEqual(current_term(day), expected)

    def test_missing_configuration_does_not_call_api(self):
        transport = FakeTransport()
        result = ScheduleAgent(transport=transport).search(["COMP5926"])
        self.assertEqual(result["status"], "clarification_required")
        self.assertEqual(transport.calls, [])

    def test_course_name_and_payload(self):
        agent = self.agent()
        result = agent.search(["Metaverse Project II"])
        self.assertEqual(result["status"], "candidates_found")
        self.assertEqual(agent.transport.calls[0], (SUBJECTS_URL, {"acadYearSem": "20261", "programmeId": 9134}))
        self.assertEqual(agent.transport.calls[1], (ARRANGEMENTS_URL, {"queries": [{
            "acadYear": "2026", "acadSemester": "1", "subjectId": 41243}]}))
        self.assertTrue(result["warnings"])
        self.assertTrue(all(r["evidence_id"].startswith("schedule:") for r in result["results"]))

    def test_all_sessions_and_components_retained_groups_deduplicated(self):
        rows = [meeting("A"), meeting("B"), meeting("A", "11:00", component="TUT"),
                meeting("B", "11:00", component="TUT")]
        result = self.agent(rows).search(["COMP 5926"])
        sessions = [r for r in result["results"] if "deliveryTimeFrom" in r]
        self.assertEqual(len(sessions), 2)
        self.assertEqual({r["componentType"] for r in sessions}, {"LEC", "TUT"})

    def test_week_range_is_inclusive(self):
        agent = self.agent([meeting("A", fm=1, to=3), meeting("B", fm=4, to=8)])
        result = agent.search(["COMP5926"], week=3)
        self.assertEqual([r["quotaGroupCode"] for r in result["results"] if "quotaGroupCode" in r], ["A"])
        result = agent.search(["COMP5926"], semester_start="2026-09-01", on_date="2026-09-22")
        self.assertEqual(result["query_scope"]["week"], 4)
        self.assertEqual([r["quotaGroupCode"] for r in result["results"] if "quotaGroupCode" in r], ["B"])

    def test_missing_week_range_is_preserved_with_warning(self):
        row = meeting()
        del row["acadWeekFm"]
        result = self.agent([row]).search(["COMP5926"], week=3)
        self.assertTrue(result["results"][0]["warnings"])

    def test_wrong_term_week_start_requests_clarification(self):
        self.assertEqual(self.agent().search(["COMP5926"], semester_start="2027-02-01")["status"],
                         "clarification_required")

    def test_unmatched_course_does_not_fetch_other_courses(self):
        agent = self.agent()
        result = agent.search(["COMP9999"])
        self.assertEqual(result["status"], "no_results")
        self.assertEqual(len(agent.transport.calls), 1)

    def test_unknown_response_fails_instead_of_inventing_schedule(self):
        agent = ScheduleAgent(9134, transport=lambda *a: {"unexpected": 1})
        with self.assertRaises(ScheduleError):
            agent.search(["COMP5926"])

    def test_nested_rows_inherit_group(self):
        row = meeting()
        del row["quotaGroupCode"]
        result = self.agent([{"quotaGroupCode": "A", "meetings": [row]}]).search(["COMP5926"])
        self.assertEqual(result["results"][0]["quotaGroupCode"], "A")

    def test_distinct_groups_not_lost(self):
        result = self.agent([meeting("A"), meeting("B", "12:00")]).search(["COMP5926"])
        self.assertEqual(len([r for r in result["results"] if "deliveryTimeFrom" in r]), 2)

    def test_empty_response(self):
        result = ScheduleAgent(9134, transport=lambda *a: {"data": []}).search(["COMP5926"])
        self.assertEqual(result["status"], "no_results")

    def test_verified_api_contract(self):
        def transport(url, payload):
            if url == SUBJECTS_URL:
                return {"status": 200, "size": 1, "value": [{"id": 41243, "subjCode": "AF5640",
                    "subjCredit": 3, "subjectTitles": {"UI_LANGUAGE||EN": "METAVERSE ECONOMICS AND ECOSYSTEMS"},
                    "nature": [{"id": 266}]}]}
            row = {**meeting(), "subjectCode": "AF5640", "componentCode": "SEM001"}
            return {"status": 200, "size": 1, "value": [[row]]}
        result = ScheduleAgent(9134, transport=transport).search(["AF5640"])
        self.assertEqual(len(result["results"]), 2)
        self.assertTrue(all(r["subjectId"] == 41243 for r in result["results"]))
        self.assertEqual(result["results"][-1]["credits"], 3)

    def test_nested_empty_timetable_is_valid(self):
        def transport(url, payload):
            return FakeTransport()(url, payload) if url == SUBJECTS_URL else {"status": 200, "value": [[]]}
        result = ScheduleAgent(9134, transport=transport).search(["COMP5926"])
        self.assertEqual(len(result["results"]), 1)
        self.assertTrue(result["results"][0]["warnings"])


class SupervisorTests(unittest.TestCase):
    def run_agent(self, model=None, policy=None, schedule=None, **kwargs):
        agent = SupervisorAgent(model or FakeModel(), policy or FakePolicy(),
                                schedule or ScheduleAgent(9134, transport=FakeTransport()))
        return agent.run("COMP5926 的先修要求及上课地点？", **kwargs)

    def test_mixed_question_preserved_and_both_sources_returned(self):
        model = FakeModel()
        result = self.run_agent(model)
        self.assertTrue(result["approved"])
        self.assertIn("policy:1", result["sources"])
        self.assertTrue(any(k.startswith("schedule:") for k in result["sources"]))
        for system, payload in model.calls:
            self.assertEqual(payload["question"], "COMP5926 的先修要求及上课地点？")

    def test_bad_draft_retries_once_with_feedback(self):
        model = FakeModel(["contradicted", "supported"])
        result = self.run_agent(model)
        self.assertTrue(result["approved"])
        self.assertEqual(len(result["attempts"]), 2)
        self.assertTrue([p for s, p in model.calls if s == ANSWER_PROMPT][-1]["retry_feedback"])

    def test_failed_branch_never_exposes_partial_answer(self):
        result = self.run_agent(policy=FakePolicy(fail=True))
        self.assertEqual(result["status"], "retrieval_failed")
        self.assertFalse(result["approved"])
        self.assertNotIn("answer", result)
        self.assertEqual(len(result["attempts"]), 2)

    def test_missing_programme_requests_clarification(self):
        result = self.run_agent(schedule=ScheduleAgent(transport=FakeTransport()))
        self.assertEqual(result["status"], "clarification_required")
        self.assertTrue(result["missing"])

    def test_unmatched_course_cannot_be_approved_by_model(self):
        result = self.run_agent(branches=["schedule"], course_queries=["COMP5926", "COMP9999"])
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertNotIn("answer", result)

    def test_policy_only_does_not_need_programme_id(self):
        result = self.run_agent(branches=["policy"])
        self.assertTrue(result["approved"])

    def test_schedule_only_does_not_need_policy(self):
        agent = SupervisorAgent(FakeModel(), schedule_agent=ScheduleAgent(9134, transport=FakeTransport()))
        self.assertTrue(agent.run("COMP5926", branches=["schedule"], course_queries=["COMP5926"])["approved"])

    def test_model_failure_is_bounded(self):
        def broken(*args):
            raise RuntimeError("unavailable")
        agent = SupervisorAgent(broken, FakePolicy())
        result = agent.run("prerequisite", branches=["policy"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["attempts"]), 2)
        self.assertNotIn("answer", result)


class ProgrammeTests(unittest.TestCase):
    def resolver(self, extra=None):
        # Synthetic mappings, not real institutional IDs.
        rows = [{"name": "MSc Test Computing", "aliases": ["测试计算硕士", "Test COMP"],
                 "programme_code": "TEST01", "programme_id": 111}]
        return ProgrammeResolver(records=rows + (extra or []))

    def test_missing_programme_asks_for_name_not_internal_id(self):
        transport = FakeTransport()
        result = ScheduleAgent(transport=transport).search(["COMP5926"])
        self.assertIn("哪个项目", result["missing"][0])
        self.assertNotIn("programmeId", result["missing"][0])
        self.assertEqual(transport.calls, [])

    def test_name_alias_and_programme_code_resolve(self):
        for name in ("MSc Test Computing", "测试计算硕士", "test comp", "TEST01"):
            transport = FakeTransport()
            result = ScheduleAgent(transport=transport, programme_resolver=self.resolver()).search(
                ["COMP5926"], programme=name)
            self.assertEqual(result["status"], "candidates_found")
            self.assertEqual(transport.calls[0][1]["programmeId"], 111)

    def test_changed_programme_cannot_use_previous_id(self):
        transport = FakeTransport()
        agent = ScheduleAgent(9134, transport=transport, programme_resolver=self.resolver())
        result = agent.search(["COMP5926"], programme="Unknown MSc")
        self.assertEqual(result["status"], "configuration_required")
        self.assertEqual(transport.calls, [])

    def test_ambiguous_alias_asks_for_full_name(self):
        resolver = self.resolver([{"name": "MSc Other Computing", "aliases": ["Test COMP"], "programme_id": 222}])
        result = resolver.resolve("Test COMP")
        self.assertEqual(result["status"], "clarification_required")

    def test_name_from_question_reaches_resolver(self):
        question = "我是测试计算硕士的学生，查 COMP5926 上课信息"
        base_model = FakeModel()
        def model(system, payload):
            if system == PLAN_PROMPT:
                return {"branches": ["schedule"], "policy_query": "", "course_queries": ["COMP5926"],
                        "programme": "测试计算硕士", "programme_quote": "我是测试计算硕士的学生"}
            return base_model(system, payload)
        transport = FakeTransport()
        agent = SupervisorAgent(model, schedule_agent=ScheduleAgent(
            transport=transport, programme_resolver=self.resolver()))
        self.assertTrue(agent.run(question)["approved"])
        self.assertEqual(transport.calls[0][1]["programmeId"], 111)
        self.assertTrue(agent.run(question, branches=["schedule"], course_queries=["COMP5926"])["approved"])
        self.assertTrue(agent.run(question, context={"programme": "Unknown MSc", "programme_id": 9134})["approved"])
        self.assertEqual(transport.calls[-2][1]["programmeId"], 111)

    def test_profile_is_used_across_queries(self):
        agent = SupervisorAgent(FakeModel(), schedule_agent=ScheduleAgent(
            transport=FakeTransport(), programme_resolver=self.resolver()))
        result = agent.run("查课程", branches=["schedule"], course_queries=["COMP5926"],
                           context={"programme": "测试计算硕士"})
        self.assertTrue(result["approved"])

    def test_unknown_mapping_is_not_retried_or_answered(self):
        model = FakeModel()
        agent = SupervisorAgent(model, schedule_agent=ScheduleAgent(
            transport=FakeTransport(), programme_resolver=self.resolver()))
        result = agent.run("查课程", branches=["schedule"], course_queries=["COMP5926"],
                           context={"programme": "Unknown MSc"})
        self.assertEqual(result["status"], "configuration_required")
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(model.calls, [])
        self.assertNotIn("answer", result)

    def test_model_cannot_invent_name_or_internal_id(self):
        def model(*args):
            return {"branches": ["schedule"], "policy_query": "", "course_queries": ["COMP5926"],
                    "programme": "测试计算硕士", "programme_quote": "我是测试计算硕士的学生",
                    "programme_id": 9134}
        transport = FakeTransport()
        result = SupervisorAgent(model, schedule_agent=ScheduleAgent(transport=transport)).run("查 COMP5926")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(transport.calls, [])


if __name__ == "__main__":
    unittest.main()
