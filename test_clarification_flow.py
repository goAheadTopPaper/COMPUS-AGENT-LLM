from datetime import date
import unittest
from unittest.mock import patch

from app.continuation import resume_request
from app.pipeline_engine import simulate
from contracts import StudentProfile
from schedule_agent import ScheduleAgent, SUBJECTS_URL
from supervisor import PLAN_PROMPT
from test_pipeline import FakeModel

QUESTION = "今天hci在哪个教室上课"


class ConversationModel(FakeModel):
    def __init__(self):
        super().__init__()
        self.plans = 0

    def __call__(self, system, payload):
        if system == PLAN_PROMPT:
            self.plans += 1
            return {"branches": ["schedule"], "course_queries": ["HCI"], "policy_query": "",
                    "schedule_scope": {"on_date": "2026-11-23", "needs_clarification": "Please specify the exact course code for HCI."}}
        return super().__call__(system, payload)


def transport(url, payload):
    if url == SUBJECTS_URL:
        return {"status": 200, "value": [{"id": 7884, "subjCode": "COMP5517",
            "subjectTitles": {"UI_LANGUAGE||EN": "HUMAN COMPUTER INTERACTION"}}]}
    return {"status": 200, "value": [[{"subjectCode": "COMP5517", "deliveryTimeFrom": "18:30",
        "deliveryTimeTo": "21:20", "dayOfWeek": 1, "acadWeekFm": 1, "acadWeekTo": 13,
        "roomCodeList": ["HJ305"], "deliveryFrequency": 1, "acadWeekDateMap": {}}]]}


class ClarificationFlowTests(unittest.TestCase):
    def test_choice_resumes_original_question_without_planning_again(self):
        model = ConversationModel()
        schedule = ScheduleAgent(transport=transport, today=date(2026, 11, 23))
        first = simulate(QUESTION, StudentProfile("", "", 0), model=model, schedule_agent=schedule)
        self.assertEqual(first.status, "clarify")
        self.assertEqual({o["value"] for o in first.clarification_options}, {"COMP3423", "COMP5517"})
        second = simulate(QUESTION, StudentProfile("", "", 0), model=model, schedule_agent=schedule,
                          continuation=first.continuation, clarification_reply="COMP5517")
        self.assertEqual(second.status, "ok")
        self.assertIn("HJ305", second.text)
        self.assertEqual(model.plans, 1)
        for _, payload in model.calls:
            self.assertEqual(payload["question"], QUESTION)
            self.assertEqual(payload["schedule_scope"]["on_date"], "2026-11-23")

    def test_invalid_choice_keeps_options_without_network(self):
        state = {"question": QUESTION, "kind": "course", "plan": {},
                 "options": [{"label": "COMP5517 HCI", "value": "COMP5517", "query": "HCI"}]}
        def forbidden(*args):
            self.fail("Invalid choices must not issue model calls")
        result = simulate(QUESTION, StudentProfile("", "", 0), model=forbidden,
                          continuation=state, clarification_reply="COMP9999")
        self.assertEqual(result.status, "clarify")
        self.assertEqual(result.continuation, state)

    def test_generic_clarification_keeps_original_question(self):
        question, plan = resume_request({"question": "退课规则是什么？", "kind": "free_text"}, "2026/27 学年")
        self.assertIn("退课规则", question)
        self.assertIn("2026/27", question)
        self.assertIsNone(plan)


try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Install frontend dependencies")
class ClarificationUITests(unittest.TestCase):
    def run_flow(self, use_button):
        model = ConversationModel()
        def wired(query, student, **kwargs):
            return simulate(query, student, model=model,
                schedule_agent=ScheduleAgent(transport=transport, today=date(2026, 11, 23)), **kwargs)
        with patch("app.pipeline_engine.simulate", side_effect=wired):
            at = AppTest.from_file("app/streamlit_app.py").run(timeout=20)
            [f for f in at.text_input if f.label == "提问"][0].input(QUESTION)
            [b for b in at.button if b.label == "提问"][0].click()
            at.run(timeout=20)
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state.history[0][1].status, "clarify")
            if use_button:
                [b for b in at.button if b.label.startswith("COMP5517")][0].click()
            else:
                [f for f in at.text_input if f.label == "补充信息"][0].input("COMP5517")
                [b for b in at.button if b.label == "继续查询"][0].click()
            at.run(timeout=20)
            self.assertFalse(at.exception)
            self.assertEqual(len(at.session_state.history), 2)
            self.assertEqual(at.session_state.history[0][1].status, "ok")
            self.assertIn("补充：COMP5517", at.session_state.history[0][0])
            self.assertEqual(model.plans, 1)

    def test_candidate_button_continues_query(self):
        self.run_flow(True)

    def test_text_reply_continues_query(self):
        self.run_flow(False)


if __name__ == "__main__":
    unittest.main()
