from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from course_matcher import COURSE_MATCH_PROMPT, COURSE_SEARCH_PROMPT, match_courses
from schedule_agent import ScheduleAgent, SUBJECTS_URL
from subject_catalogue import discover_subjects, is_code

AF = {"id": 41243, "subjCode": "AF5640", "subjectTitles": {"UI_LANGUAGE||EN": "METAVERSE ECONOMICS AND ECOSYSTEMS"}}


class UniversityCatalogueTests(unittest.TestCase):
    def test_mixed_letter_number_course_codes_use_direct_search(self):
        for code in ("AAE1Q01", "ABCT1D11D", "COMP5517", "AF5640"):
            self.assertTrue(is_code(code))
        calls = []
        def fetch(url, payload):
            calls.append(payload)
            return {"status": 200, "value": [{"id": 1, "subjCode": "AAE1Q01"}]}
        result, cached = discover_subjects(["AAE1Q01"], "20261", fetch)
        self.assertEqual(result["value"][0]["id"], 1)
        self.assertEqual(calls, [{"acadYearSem": "20261", "subjCode": "AAE1Q01"}])

    def transport(self, calls, sid=41243):
        def fetch(url, payload):
            calls.append((url, payload))
            if url == SUBJECTS_URL:
                return {"status": 200, "value": [{**AF, "id": sid}]}
            return {"status": 200, "value": [[{"subjectCode": "AF5640", "dayOfWeek": 2,
                "deliveryTimeFrom": "08:30", "deliveryTimeTo": "11:20", "roomCodeList": ["Z504", "Z512"],
                "acadWeekFm": 1, "acadWeekTo": 13, "deliveryFrequency": 1, "acadWeekDateMap": {}}]]}
        return fetch

    def model(self, system, payload):
        if system == COURSE_SEARCH_PROMPT:
            return {"searches": [{"query": q, "keywords": ["metaverse economics"]} for q in payload["queries"]]}
        self.assertEqual(system, COURSE_MATCH_PROMPT)
        return {"matches": [{"query": q, "subject_ids": ["41243"]} for q in payload["queries"]]}

    def test_code_lookup_has_no_programme_parameter(self):
        calls = []
        result = ScheduleAgent(transport=self.transport(calls), today=date(2026, 11, 23)).search(["AF5640"])
        self.assertEqual(result["status"], "candidates_found")
        self.assertEqual(calls[0][1], {"acadYearSem": "20261", "subjCode": "AF5640"})
        self.assertTrue(all(r["lookupScope"] == "university" for r in result["results"]))
        self.assertTrue(all("programmeId" not in r for r in result["results"]))

    def test_chinese_name_from_cache_is_verified_live_before_timetable(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "subjects.json"
            path.write_text(json.dumps({"acad_year_sem": "20261", "complete_for_returned_departments": True,
                                        "subjects": [AF]}), encoding="utf-8")
            calls = []
            with patch("subject_catalogue.DEFAULT_PATH", path):
                result = ScheduleAgent(transport=self.transport(calls), model=self.model,
                    today=date(2026, 11, 23)).search(["元宇宙经济"], on_date="2026-11-24")
            self.assertEqual(result["status"], "candidates_found")
            self.assertEqual(calls[0][1]["subjCode"], "AF5640")
            self.assertEqual(calls[1][1]["queries"][0]["subjectId"], 41243)

    def test_no_cache_falls_back_to_live_keyword_search(self):
        with TemporaryDirectory() as folder:
            calls = []
            response, cached = discover_subjects(["元宇宙经济"], "20271", self.transport(calls),
                                                 self.model, Path(folder) / "absent.json")
            self.assertFalse(cached)
            self.assertEqual(response["value"][0]["id"], 41243)
            self.assertEqual(calls[0][1], {"acadYearSem": "20271", "term": "metaverse economics"})

    def test_stale_course_id_does_not_reach_timetable(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "subjects.json"
            path.write_text(json.dumps({"acad_year_sem": "20261", "complete_for_returned_departments": True,
                                        "subjects": [AF]}), encoding="utf-8")
            calls = []
            with patch("subject_catalogue.DEFAULT_PATH", path):
                result = ScheduleAgent(transport=self.transport(calls, sid=999), model=self.model,
                    today=date(2026, 11, 23)).search(["元宇宙经济"])
            self.assertEqual(result["status"], "clarification_required")
            self.assertEqual(len(calls), 1)

    def test_large_catalogue_is_shortlisted_before_semantic_matching(self):
        subjects = {str(i): {"subjectCode": f"TEST{i}", "subjectTitle": f"Unrelated subject {i}"} for i in range(200)}
        subjects["41243"] = {"subjectCode": "AF5640", "subjectTitle": "METAVERSE ECONOMICS AND ECOSYSTEMS"}
        seen = []
        def model(system, payload):
            seen.append((system, payload))
            return self.model(system, payload)
        result = match_courses(["元宇宙经济"], subjects, model)
        self.assertEqual(result["元宇宙经济"][0]["subjectCode"], "AF5640")
        self.assertLessEqual(len(seen[-1][1]["candidates"]), 40)

    def test_cap_is_not_treated_as_a_complete_list(self):
        with self.assertRaises(ValueError):
            discover_subjects(["AF5640"], "20261", lambda *args: {"value": [AF] * 1000})


if __name__ == "__main__":
    unittest.main()
