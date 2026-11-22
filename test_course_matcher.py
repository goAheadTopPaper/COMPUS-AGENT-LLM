from datetime import date
import unittest

from course_matcher import match_courses, COURSE_MATCH_PROMPT
from schedule_agent import ScheduleAgent, ScheduleError, SUBJECTS_URL
from test_pipeline import meeting


SUBJECTS = [{"id": 41243, "subjCode": "AF5640", "subjectTitles": {
    "UI_LANGUAGE||EN": "METAVERSE ECONOMICS AND ECOSYSTEMS"}},
    {"id": 41273, "subjCode": "COMP5140", "subjectTitles": {"UI_LANGUAGE||EN": "METAVERSE FUNDAMENTALS"}}]


class CourseNameTests(unittest.TestCase):
    def transport(self, calls):
        def fetch(url, payload):
            calls.append((url, payload))
            if url == SUBJECTS_URL:
                return {"value": SUBJECTS}
            return {"value": [[{**meeting(), "subjectCode": "AF5640", "dayOfWeek": 2,
                                "deliveryFrequency": 1, "acadWeekDateMap": {}}]]}
        return fetch

    def test_chinese_short_name_grounded_in_programme_catalogue(self):
        calls, models = [], []
        def model(system, payload):
            models.append(payload)
            self.assertEqual(system, COURSE_MATCH_PROMPT)
            self.assertEqual(payload["queries"], ["元宇宙经济"])
            self.assertEqual(payload["candidates"][0]["title"], "METAVERSE ECONOMICS AND ECOSYSTEMS")
            return {"matches": [{"query": "元宇宙经济", "subject_ids": [41243]}]}
        agent = ScheduleAgent(9134, model=model, transport=self.transport(calls), today=date(2026, 11, 23))
        result = agent.search(["元宇宙经济"], on_date="2026-11-24")
        self.assertEqual(result["status"], "candidates_found")
        self.assertEqual(calls[1][1]["queries"][0]["subjectId"], 41243)
        self.assertEqual(len(models), 1)
        self.assertTrue(any(r.get("lookupResult") == "matching_weekly_pattern" for r in result["results"]))

    def test_unknown_id_never_reaches_timetable_api(self):
        calls = []
        def model(*args):
            return {"matches": [{"query": "元宇宙经济", "subject_ids": [999999]}]}
        agent = ScheduleAgent(9134, model=model, transport=self.transport(calls))
        with self.assertRaises(ScheduleError):
            agent.search(["元宇宙经济"])
        self.assertEqual(len(calls), 1)

    def test_broad_name_surfaces_multiple_actual_courses(self):
        calls = []
        model = lambda *args: {"matches": [{"query": "元宇宙", "subject_ids": [41243, 41273]}]}
        result = ScheduleAgent(9134, model=model, transport=self.transport(calls)).search(["元宇宙"])
        self.assertEqual(result["status"], "clarification_required")
        self.assertIn("AF5640", result["missing"][0])
        self.assertIn("COMP5140", result["missing"][0])
        self.assertEqual(len(calls), 1)

    def test_explicit_unknown_code_is_not_rewritten_by_model(self):
        def forbidden(*args):
            self.fail("Unknown explicit codes must not be silently changed")
        result = ScheduleAgent(9134, model=forbidden, transport=self.transport([])).search(["AF9999"])
        self.assertEqual(result["unmatched"], ["AF9999"])

    def test_unmatched_name_remains_unmatched(self):
        model = lambda *args: {"matches": [{"query": "古代天文", "subject_ids": []}]}
        result = ScheduleAgent(9134, model=model, transport=self.transport([])).search(["古代天文"])
        self.assertEqual(result["unmatched"], ["古代天文"])

    def test_duplicate_query_output_is_rejected(self):
        model = lambda *args: {"matches": [{"query": "a", "subject_ids": []}, {"query": "a", "subject_ids": []}]}
        with self.assertRaises(ValueError):
            match_courses(["a", "b"], {"1": {"subjectCode": "TEST1001", "subjectTitle": "TEST"}}, model)


if __name__ == "__main__":
    unittest.main()
