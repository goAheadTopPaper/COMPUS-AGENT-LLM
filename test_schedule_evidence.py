"""Offline tests for schedule_evidence.py.

Run: python3 -B -m unittest test_schedule_evidence -v

No Canvas token, network call or LLM endpoint is involved: raw events are
fixtures and the model is scripted.
"""
import json
import unittest

from agents import collect_evidence
from schedule_evidence import (DEFAULT_OFFSET, PREFIX, build_schedule_rows,
                               build_schedule_search)
from supervisor import run

EXAM = {"courseCode": "COMP5926", "type": "Exam",
        "start": "2026-11-23T14:00:00+08:00",
        "end": "2026-11-23T17:00:00+08:00", "room": "A101"}
LECTURE = {"courseCode": "COMP5926", "type": "Lecture", "date": "2026-11-24",
           "time": "09:30-11:20", "venue": "TU201"}


def rows(*events, **kwargs):
    return build_schedule_rows(list(events), **kwargs)


class ScheduleContractTests(unittest.TestCase):
    def test_required_fields_and_prefix(self):
        record, = rows(EXAM)
        self.assertTrue(record["evidence_id"].startswith(PREFIX))
        self.assertTrue(record["text"].strip())
        self.assertTrue(record["citation"]["title"].strip())
        self.assertEqual(record["citation"]["title"], "Timetable")

    def test_text_carries_course_date_time_timezone_location(self):
        record, = rows(EXAM)
        for fragment in ("COMP5926", "Exam", "2026-11-23", "14:00-17:00",
                         "Asia/Hong_Kong", "location A101"):
            self.assertIn(fragment, record["text"])
        self.assertEqual(record["start_at"], "2026-11-23T14:00:00+08:00")
        self.assertEqual(record["end_at"], "2026-11-23T17:00:00+08:00")
        self.assertEqual(record["location"], "A101")

    def test_date_and_time_fields_are_combined(self):
        record, = rows(LECTURE)
        self.assertIn("2026-11-24 09:30-11:20", record["text"])
        self.assertEqual(record["start_at"], "2026-11-24T09:30:00+08:00")
        self.assertEqual(record["end_at"], "2026-11-24T11:20:00+08:00")

    def test_naive_timezone_is_declared_in_warnings(self):
        stats = {}
        record, = rows({"courseCode": "COMP5926", "type": "Seminar",
                        "start": "2026-11-26T10:00"}, stats=stats)
        self.assertTrue(record["start_at"].endswith(DEFAULT_OFFSET))
        self.assertTrue(any("Timezone is not stated" in w for w in record["warnings"]))
        self.assertEqual(stats["assumed_timezone"], 1)

    def test_date_only_event_invents_no_time(self):
        record, = rows({"courseCode": "COMP5926", "type": "Exam",
                        "date": "2026-11-25", "location": "B203"})
        self.assertIn("2026-11-25 Asia/Hong_Kong", record["text"])
        self.assertNotIn("00:00", record["text"])
        self.assertNotIn("start_at", record)  # omitted, not a fabricated midnight
        self.assertTrue(any("Time of day is not recorded" in w
                            for w in record["warnings"]))
        self.assertIn("20261125", record["evidence_id"])

    def test_missing_optional_fields_are_omitted(self):
        record, = rows({"courseCode": "COMP5926", "type": "Lecture",
                        "start": "2026-11-27T08:30:00+08:00"})
        for key in ("location", "end_at"):
            self.assertNotIn(key, record)
        self.assertNotIn("location", record["text"])

    def test_ids_are_stable_across_calls_and_queries(self):
        first = [r["evidence_id"] for r in rows(EXAM, LECTURE)]
        again = build_schedule_search(lambda q: [EXAM, LECTURE])(EXAM["courseCode"])
        self.assertEqual(first, [r["evidence_id"] for r in again])
        other_query = build_schedule_search(lambda q: [EXAM, LECTURE])("exam timetable")
        self.assertEqual(first, [r["evidence_id"] for r in other_query])
        self.assertEqual(len(first), len(set(first)))

    def test_same_event_twice_is_deduplicated(self):
        stats = {}
        result = rows(EXAM, dict(EXAM), stats=stats)
        self.assertEqual(len(result), 1)
        self.assertEqual(stats["duplicates"], 1)

    def test_distinct_events_never_share_an_id(self):
        twin = dict(EXAM, room="B203")  # same course/time, different room
        result = rows(EXAM, twin)
        ids = [r["evidence_id"] for r in result]
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2)
        self.assertTrue(any("location B203" in r["text"] for r in result))

    def test_native_event_id_wins(self):
        record, = rows(dict(EXAM, event_id="canvas-778"))
        self.assertEqual(record["evidence_id"], "schedule:canvas-778")

    def test_tokens_and_personal_fields_never_reach_the_model(self):
        stats = {}
        dirty = dict(EXAM, token="sk-live-abc123", access_token="t0ken",
                     student_id="22001234", email="s@connect.polyu.hk",
                     canvas_user_id="9911")
        result = rows(dirty, stats=stats)
        payload = json.dumps(collect_evidence(None, result), ensure_ascii=False)
        for secret in ("sk-live-abc123", "t0ken", "22001234",
                       "s@connect.polyu.hk", "9911"):
            self.assertNotIn(secret, payload)
        self.assertEqual(stats["stripped"], 1)

    def test_unusable_row_is_skipped_with_a_note(self):
        stats = {}
        result = rows({"courseCode": "COMP5926"}, EXAM, stats=stats)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(stats["skipped"]), 1)

    def test_invalid_input_raises(self):
        with self.assertRaises(ValueError):
            build_schedule_rows(EXAM)  # a bare dict is not a list of events
        with self.assertRaises(ValueError):
            build_schedule_rows([EXAM], source_title="  ")
        with self.assertRaises(ValueError):
            build_schedule_rows(["not a dict"])
        with self.assertRaises(ValueError):
            build_schedule_rows([dict(EXAM, start="next Tuesday 2pm")])

    def test_empty_sources_return_an_empty_list(self):
        self.assertEqual(build_schedule_rows([]), [])
        self.assertEqual(build_schedule_search(lambda q: [])("anything"), [])
        self.assertEqual(build_schedule_search(lambda q: None)("anything"), [])

    def test_fetch_error_propagates(self):
        def fetch(_):
            raise TimeoutError("timetable gateway timeout")

        with self.assertRaises(TimeoutError):
            build_schedule_search(fetch)("COMP5926")

    def test_source_title_and_url_are_configurable(self):
        record, = rows(EXAM, source_title="Mock schedule (synthetic)",
                       source_url="https://example.edu/timetable")
        self.assertEqual(record["citation"]["title"], "Mock schedule (synthetic)")
        self.assertEqual(record["citation"]["source_url"],
                         "https://example.edu/timetable")
        self.assertTrue(any("Synthetic" in w for w in rows(
            dict(EXAM, warnings=["Synthetic demo data"]))[0]["warnings"]))


class ScheduleSupervisorTests(unittest.TestCase):
    """The Supervisor slot receives a plain list, per INTEGRATION.md."""

    def draft(self, evidence_id, text, quote):
        return {"claims": [{"text": text,
                            "supports": [{"evidence_id": evidence_id, "quote": quote}]}]}

    def review(self, status="supported"):
        return {"checks": [{"index": 0, "status": status, "reason": "fixture"}],
                "unanswered": [], "needs_clarification": False}

    def test_schedule_only_query_passes_with_schedule_citation(self):
        schedule = build_schedule_search(
            lambda q: [EXAM], source_title="Mock schedule (synthetic)")
        question = "When is the COMP5926 exam?"
        quote = "COMP5926 Exam: 2026-11-23 14:00-17:00 Asia/Hong_Kong; location A101."
        evidence_id = schedule("COMP5926")[0]["evidence_id"]
        model = _ScriptedModel(self.draft(evidence_id, "The exam is on 23 November 2026.", quote),
                               self.review())
        result = run({"question": question, "branches": ["schedule"]}, model,
                     schedule_search=schedule)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(list(result["sources"]), [evidence_id])
        self.assertEqual(result["branches"]["policy"]["state"], "not_called")

    def test_mixed_query_shows_both_citation_kinds(self):
        policy = {"status": "candidates_found",
                  "results": [{"evidence_id": "policy:p1",
                               "text": "Pre-requisite: COMP5925 Metaverse Project I",
                               "citation": {"title": "Handbook 2026/27"}}],
                  "year_filters": {}, "limitations": []}
        schedule = build_schedule_search(lambda q: [EXAM], source_title="Mock schedule")
        question = "What is the prerequisite for COMP5926 and when is its exam?"
        row = schedule("COMP5926")[0]
        model = _ScriptedModel(
            {"claims": [
                {"text": "COMP5926 requires COMP5925.",
                 "supports": [{"evidence_id": "policy:p1",
                               "quote": "Pre-requisite: COMP5925 Metaverse Project I"}]},
                {"text": "The exam runs 14:00-17:00 in A101.",
                 "supports": [{"evidence_id": row["evidence_id"],
                               "quote": row["text"]}]}]},
            {"checks": [{"index": 0, "status": "supported", "reason": "fixture"},
                        {"index": 1, "status": "supported", "reason": "fixture"}],
             "unanswered": [], "needs_clarification": False})
        result = run({"question": question, "branches": ["policy", "schedule"]}, model,
                     policy_search=lambda q: policy, schedule_search=schedule)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(set(result["sources"]), {"policy:p1", row["evidence_id"]})
        self.assertIn("[policy:p1]", result["answer"])
        self.assertIn("[%s]" % row["evidence_id"], result["answer"])

    def test_correct_quote_but_wrong_time_is_rejected(self):
        schedule = build_schedule_search(lambda q: [EXAM], source_title="Mock schedule")
        row = schedule("COMP5926")[0]
        model = _ScriptedModel(self.draft(row["evidence_id"], "The exam starts at 15:00.",
                                          row["text"]),
                               self.review("contradicted"))
        result = run({"question": "When is the COMP5926 exam?", "branches": ["schedule"]},
                     model, schedule_search=schedule, max_retries=0)

        self.assertEqual(result["status"], "rejected")
        self.assertNotIn("answer", result)

    def test_failed_schedule_branch_is_reported_not_fatal(self):
        def fetch(_):
            raise ConnectionError("timetable unavailable")

        model = _ScriptedModel(self.review("insufficient_evidence"))
        result = run({"question": "When is the exam?", "branches": ["schedule"]}, model,
                     schedule_search=build_schedule_search(fetch), max_retries=0)

        self.assertEqual(result["branches"]["schedule"]["state"], "failed")
        self.assertTrue(any("日程查询失败" in n for n in result["notices"]))
        self.assertNotIn("answer", result)


class _ScriptedModel:
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


if __name__ == "__main__":
    unittest.main()
