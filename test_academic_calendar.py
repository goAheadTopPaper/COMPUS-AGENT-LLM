from datetime import date
import unittest

from academic_calendar import teaching_week
from schedule_agent import ScheduleAgent
from test_pipeline import FakeTransport, meeting


class CalendarTests(unittest.TestCase):
    def week(self, day, semester="1"):
        return teaching_week(date.fromisoformat(day), "2026", semester)

    def test_first_last_teaching_dates(self):
        for day, expected in [("2026-08-31", 1), ("2026-11-22", 12),
                              ("2026-11-23", 13), ("2026-11-28", 13)]:
            self.assertEqual(self.week(day)["week"], expected)

    def test_revision_and_exam_periods_do_not_become_week_14(self):
        self.assertEqual(self.week("2026-12-03")["teaching_status"], "outside_teaching_period")
        self.assertIsNone(self.week("2026-12-03")["week"])

    def test_lunar_new_year_pauses_numbering(self):
        self.assertEqual(self.week("2027-02-05", "2")["week"], 4)
        self.assertEqual(self.week("2027-02-08", "2")["teaching_status"], "teaching_break")
        self.assertEqual(self.week("2027-02-15", "2")["week"], 5)
        self.assertEqual(self.week("2027-04-17", "2")["week"], 13)

    def test_summer(self):
        self.assertEqual(self.week("2027-05-24", "3")["week"], 1)
        self.assertEqual(self.week("2027-07-10", "3")["week"], 7)

    def test_unknown_year_not_extrapolated(self):
        result = teaching_week(date(2030, 11, 1), "2030", "1")
        self.assertIsNone(result["week"])
        self.assertEqual(result["teaching_status"], "calendar_unavailable")

    def test_no_configuration_automatically_filters_week_13(self):
        agent = ScheduleAgent(9134, today=date(2026, 11, 23), transport=FakeTransport([
            meeting("A", fm=1, to=12), meeting("B", fm=13, to=13)]))
        result = agent.search(["COMP5926"])
        self.assertEqual(result["query_scope"]["week"], 13)
        self.assertEqual([r["quotaGroupCode"] for r in result["results"] if "quotaGroupCode" in r], ["B"])

    def test_manual_week_takes_precedence(self):
        agent = ScheduleAgent(9134, today=date(2026, 11, 23), transport=FakeTransport())
        self.assertEqual(agent.search(["COMP5926"], week=2)["query_scope"]["week"], 2)

    def test_unsupported_year_warns_and_preserves_rows(self):
        agent = ScheduleAgent(9134, today=date(2030, 11, 1), transport=FakeTransport())
        result = agent.search(["COMP5926"])
        self.assertIsNone(result["query_scope"]["week"])
        self.assertTrue(result["warnings"])
        self.assertTrue(any("deliveryTimeFrom" in r for r in result["results"]))


if __name__ == "__main__":
    unittest.main()
