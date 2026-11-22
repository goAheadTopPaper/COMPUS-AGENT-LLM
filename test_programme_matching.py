from datetime import date
from pathlib import Path
import unittest

from programme_resolver import ProgrammeResolver
from schedule_agent import ScheduleAgent, SUBJECTS_URL
from test_pipeline import FakeTransport


class FuzzyProgrammeTests(unittest.TestCase):
    def resolver(self):
        return ProgrammeResolver(records=[
            {"name": "MSc METAVERSE TECHNOLOGY [61038; FT; impl=2023]", "programme_id": 9134,
             "aliases": ["元宇宙科技理學碩士", "MSc METAVERSE TECHNOLOGY", "61038"],
             "programme_code": "61038", "implementation_year": "2023"},
            {"name": "MSc METAVERSE TECHNOLOGY [61038-FMT; MF; impl=2027]", "programme_id": 12494,
             "aliases": ["元宇宙科技理學碩士", "MSc METAVERSE TECHNOLOGY", "61038-FMT"],
             "programme_code": "61038", "implementation_year": "2027"}])

    def test_simplified_traditional_short_name_and_technology_synonym(self):
        resolver = self.resolver()
        for name in ("元宇宙科技项目", "元宇宙技术项目", "元宇宙科技理學碩士", "元宇宙科技理学硕士", "元宇宙", "MSc Metaverse Technlogy"):
            with self.subTest(name=name):
                self.assertEqual(resolver.resolve(name, acad_year="2026")["programme_id"], 9134)

    def test_future_variants_not_arbitrarily_chosen(self):
        result = self.resolver().resolve("元宇宙科技项目", acad_year="2027")
        self.assertEqual(result["status"], "clarification_required")
        self.assertEqual(len(result["candidates"]), 2)

    def test_explicit_future_code_asks_about_year(self):
        result = self.resolver().resolve("61038-FMT", acad_year="2026")
        self.assertEqual(result["status"], "clarification_required")

    def test_project_codes_not_fuzzy_corrected(self):
        self.assertEqual(self.resolver().resolve("61039", acad_year="2026")["status"], "configuration_required")

    def test_generic_name_not_matched_to_random_programme(self):
        self.assertEqual(self.resolver().resolve("硕士", acad_year="2026")["status"], "clarification_required")

    def test_user_screenshot_reaches_correct_course_api(self):
        transport = FakeTransport()
        result = ScheduleAgent(programme_resolver=self.resolver(), transport=transport,
                               today=date(2026, 11, 23)).search(["COMP5926"], programme="元宇宙技术项目")
        self.assertEqual(result["status"], "candidates_found")
        self.assertEqual(transport.calls[0][1]["programmeId"], 9134)

    def test_real_discovered_mapping(self):
        path = Path(__file__).with_name("programmes.discovered.json")
        if not path.is_file():
            self.skipTest("Discovered mapping not installed")
        result = ProgrammeResolver(path=path).resolve("元宇宙科技项目", acad_year="2026")
        self.assertEqual(result["programme_id"], 9134)

    def test_hci_acronym_and_chinese_title_use_actual_api_id(self):
        calls = []
        def transport(url, payload):
            calls.append((url, payload))
            if url == SUBJECTS_URL:
                return {"value": [{"id": 7884, "subjCode": "COMP5517",
                    "subjectTitles": {"UI_LANGUAGE||EN": "HUMAN COMPUTER INTERACTION"}}]}
            return {"value": [[]]}
        for queries in (["HCI"], ["人机交互"], ["HCI 人机交互"], ["HCI", "人机交互"]):
            with self.subTest(queries=queries):
                calls.clear()
                result = ScheduleAgent(programme_resolver=self.resolver(), transport=transport,
                    today=date(2026, 11, 23)).search(queries, programme="元宇宙科技项目")
                self.assertEqual(result["unmatched"], [])
                self.assertEqual(calls[1][1]["queries"][0]["subjectId"], 7884)
                self.assertEqual(len(calls), 2)

    def test_explicit_tuesday_does_not_turn_monday_into_tomorrows_class(self):
        from test_pipeline import meeting
        row = {**meeting(), "dayOfWeek": 1, "deliveryFrequency": 1, "acadWeekDateMap": {}}
        transport = FakeTransport([row])
        result = ScheduleAgent(programme_resolver=self.resolver(), transport=transport,
            today=date(2026, 11, 23)).search(["COMP5926"], programme="元宇宙科技项目", on_date="2026-11-24")
        summaries = [r for r in result["results"] if r.get("lookupResult")]
        self.assertEqual(summaries[0]["lookupResult"], "no_matching_weekday")
        self.assertEqual(summaries[0]["queryDate"], "2026-11-24")
        self.assertEqual(result["query_scope"]["today"], "2026-11-23")
        self.assertIn("programmeName", summaries[0])


if __name__ == "__main__":
    unittest.main()
