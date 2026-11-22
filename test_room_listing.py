from datetime import date
import unittest

from agents import collect_evidence, answer, verify, ANSWER_PROMPT, VERIFY_PROMPT
from schedule_agent import ScheduleAgent
from test_pipeline import FakeTransport, meeting


class RoomListingTests(unittest.TestCase):
    def test_all_rooms_preserved_and_quotable_as_normal_alternatives(self):
        row = {**meeting(), "roomCodeList": ["Z504", "Z512"]}
        report = ScheduleAgent(9134, transport=FakeTransport([row]), today=date(2026, 11, 23)).search(["COMP5926"])
        record = next(r for r in report["results"] if "roomCodeList" in r)
        self.assertEqual(record["roomCodeList"], ["Z504", "Z512"])
        self.assertEqual(record["roomDisplay"], "Z504 或 Z512")
        self.assertIn("Z504 或 Z512", record["text"])
        bundle = collect_evidence(schedule=report["results"])
        def model(system, payload):
            if system == ANSWER_PROMPT:
                return {"claims": [{"text": "教室为 Z504 或 Z512。", "supports": [{
                    "evidence_id": record["evidence_id"], "quote": "Z504 或 Z512"}]}]}
            self.assertEqual(system, VERIFY_PROMPT)
            return {"checks": [{"index": 0, "status": "supported", "reason": "Both rooms are listed"}],
                    "unanswered": [], "needs_clarification": False}
        result = verify("在哪个教室上课？", bundle, answer("在哪个教室上课？", bundle, model), model)
        self.assertTrue(result["approved"])
        self.assertIn("Z504 或 Z512", result["answer"])

    def test_missing_room_does_not_create_a_room(self):
        row = {**meeting(), "roomCodeList": []}
        report = ScheduleAgent(9134, transport=FakeTransport([row]), today=date(2026, 11, 23)).search(["COMP5926"])
        record = next(r for r in report["results"] if "roomCodeList" in r)
        self.assertNotIn("roomDisplay", record)


if __name__ == "__main__":
    unittest.main()
