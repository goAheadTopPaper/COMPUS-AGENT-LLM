import unittest
from supervisor import SupervisorAgent, PlanValidationError, validate_plan
from schedule_agent import ScheduleAgent
from test_pipeline import FakeTransport


class PlannerTests(unittest.TestCase):
    question = "明天hci人机交互课几点上课"

    def test_schedule_only_null_policy_query_is_unused(self):
        plan = {"branches": ["schedule"], "policy_query": None,
                "course_queries": "HCI 人机交互", "schedule_scope": {"on_date": "2026-11-24"},
                "programme": None, "programme_quote": None}
        transport = FakeTransport()
        result = SupervisorAgent(lambda *args: plan, schedule_agent=ScheduleAgent(transport=transport)).run(self.question)
        self.assertEqual(result["status"], "clarification_required")
        self.assertIn("课程", result["missing"][0])
        self.assertNotIn("哪个项目", result["missing"][0])
        self.assertEqual(transport.calls, [])

    def test_empty_optional_fields_are_normalized(self):
        plan = validate_plan({"branches": ["schedule"], "course_queries": None,
                              "schedule_scope": None, "programme": "", "programme_quote": ""}, self.question)
        self.assertEqual(plan["course_queries"], [])
        self.assertEqual(plan["schedule_scope"], {})
        self.assertIsNone(plan["programme"])

    def test_required_policy_query_is_not_invented(self):
        with self.assertRaises(PlanValidationError):
            validate_plan({"branches": ["policy"], "policy_query": None}, self.question)

    def test_invalid_plan_retried_once_with_field_feedback(self):
        calls = []
        def model(system, payload):
            calls.append(payload)
            return {"branches": "schedule"} if len(calls) == 1 else {"branches": ["schedule"]}
        agent = SupervisorAgent(model)
        self.assertEqual(agent.plan(self.question)["branches"], ["schedule"])
        self.assertEqual(len(calls), 2)
        self.assertIn("branches", calls[1]["validation_error"])

    def test_persistent_schema_failure_shows_field_and_stops(self):
        calls = []
        def model(*args):
            calls.append(1)
            return {"branches": ["made-up"]}
        result = SupervisorAgent(model).run(self.question)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(calls), 2)
        self.assertIn("branches", result["issues"][0])

    def test_project_grounding_cannot_be_bypassed(self):
        with self.assertRaises(PlanValidationError):
            validate_plan({"branches": ["schedule"], "programme": "MSc Invented",
                           "programme_quote": "我是MSc Invented学生"}, self.question)


if __name__ == "__main__":
    unittest.main()
