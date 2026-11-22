"""Frontend contract and form submission tests; models/HTTP are fixtures."""
from pathlib import Path
import unittest
from unittest.mock import patch

from app.pipeline_engine import simulate, _prettify
from app.settings import read_settings, configuration_issues
from contracts import StudentProfile
from schedule_agent import ScheduleAgent
from test_pipeline import FakeModel, FakePolicy, FakeTransport
from supervisor import PLAN_PROMPT


class PolicyModel(FakeModel):
    def __call__(self, system, payload):
        if system == PLAN_PROMPT:
            return {"branches": ["policy"], "policy_query": payload["question"], "course_queries": []}
        return super().__call__(system, payload)


class FrontendContractTests(unittest.TestCase):
    student = StudentProfile("", "", 0)

    def test_approved_answer_and_card_numbers_agree(self):
        result = simulate("prerequisite", self.student, model=PolicyModel(), policy_agent=FakePolicy())
        self.assertEqual(result.status, "ok")
        self.assertIn("[1]", result.text)
        self.assertEqual(result.evidence[0].evidence_id, "policy:1")
        self.assertTrue(any(ev.agent == "verifier" for ev in result.trace))

    def test_missing_programme_can_answer_public_course(self):
        result = simulate("COMP5926 classroom", self.student, model=FakeModel(), policy_agent=FakePolicy(),
                          schedule_agent=ScheduleAgent(transport=FakeTransport()))
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.evidence)

    def test_unknown_programme_is_configuration_failure(self):
        result = simulate("COMP5926 classroom", StudentProfile("", "Unknown MSc", 0),
                          model=FakeModel(), policy_agent=FakePolicy(),
                          schedule_agent=ScheduleAgent(transport=FakeTransport()))
        self.assertEqual(result.status, "failed")
        self.assertNotIn("[1]", result.text)

    def test_no_model_config_does_not_fall_back_to_mock(self):
        settings = read_settings()
        settings.update(LLM_ENDPOINT="", LLM_MODEL="", LLM_API_KEY="")
        result = simulate("prerequisite", self.student, settings=settings)
        self.assertEqual(result.status, "failed")
        self.assertIn("LLM_API_KEY", result.text)

    def test_citation_order_follows_sources(self):
        self.assertEqual(_prettify("second [b] first [a]", {"b": {}, "a": {}}), "second [1] first [2]")

    def test_default_handoff_exists_and_is_not_local_empty_repo(self):
        settings = read_settings()
        if not Path(settings["PART1_HANDOFF_PATH"]).is_dir():
            self.skipTest("Part 1 handoff is not installed on this machine")
        self.assertFalse(any("Part 1 路径缺少" in issue for issue in configuration_issues(settings)))


try:
    from streamlit.testing.v1 import AppTest
except ImportError:
    AppTest = None


@unittest.skipIf(AppTest is None, "Install requirements.txt to test Streamlit forms")
class StreamlitFormTests(unittest.TestCase):
    def test_real_mode_loads_and_configuration_failure_is_visible(self):
        at = AppTest.from_file("app/streamlit_app.py").run(timeout=20)
        self.assertFalse(at.exception)
        self.assertEqual(at.selectbox[0].value, "真实 Agent")
        self.assertTrue(any(e.label == "所属项目（可留空）" for e in at.text_input))

    def test_form_to_actual_supervisor_to_rendered_answer(self):
        original = simulate
        def wired(query, student, **kwargs):
            return original(query, student, model=PolicyModel(), policy_agent=FakePolicy(), **kwargs)
        with patch("app.pipeline_engine.simulate", side_effect=wired):
            at = AppTest.from_file("app/streamlit_app.py").run(timeout=20)
            [field for field in at.text_input if field.label == "提问"][0].input("COMP5926 prerequisite")
            [button for button in at.button if button.label == "提问"][0].click()
            at.run(timeout=20)
            self.assertFalse(at.exception)
            result = at.session_state.history[0][1]
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.evidence[0].evidence_id, "policy:1")
            self.assertTrue(any("已通过校验" in item.value for item in at.markdown))

    def test_configuration_change_clears_old_failure_without_resubmitting(self):
        from app.settings import read_settings
        settings = read_settings()
        with patch("app.settings.read_settings", return_value=settings):
            at = AppTest.from_file("app/streamlit_app.py").run(timeout=20)
            at.session_state.history = [("old question", simulate("old", FrontendContractTests.student,
                settings={**settings, "LLM_API_KEY": ""}))]
            new_settings = {**settings, "SEMESTER_START": "2026-08-31"}
            with patch("app.settings.read_settings", return_value=new_settings):
                with patch("app.pipeline_engine.simulate") as run:
                    at.run(timeout=20)
                    self.assertFalse(at.exception)
                    self.assertEqual(at.session_state.history, [])
                    run.assert_not_called()
                    self.assertTrue(any("配置已更新" in item.value for item in at.info))


if __name__ == "__main__":
    unittest.main()
