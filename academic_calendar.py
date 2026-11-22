"""Date-based teaching weeks from a verified official PolyU calendar snapshot.

Whole non-teaching weeks pause the week counter. Individual public holidays do
not renumber weeks. This is a teaching-week filter, not a daily cancellation API.
"""
from datetime import date
import json
from pathlib import Path


def _calendar():
    return json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))


def term_for_date(day):
    for year in _calendar()["academic_years"]:
        if date.fromisoformat(year["start"]) <= day <= date.fromisoformat(year["end"]):
            terms = [t for t in year["terms"] if date.fromisoformat(t["start"]) <= day]
            if terms:
                return year["acad_year"], terms[-1]["semester"]
    return None


def teaching_week(day, acad_year, semester):
    data = _calendar()
    scope = {"week": None, "teaching_status": "calendar_unavailable",
             "calendar_source": data["source_url"], "calendar_verified_on": data["verified_on"]}
    for year in data["academic_years"]:
        for term in year["terms"]:
            if (year["acad_year"], term["semester"]) != (str(acad_year), str(semester)):
                continue
            start, end = date.fromisoformat(term["start"]), date.fromisoformat(term["teaching_end"])
            scope["semester_start"] = start.isoformat()
            if not start <= day <= end:
                return {**scope, "teaching_status": "outside_teaching_period"}
            if any(date.fromisoformat(a) <= day <= date.fromisoformat(b) for a, b in term["breaks"]):
                return {**scope, "teaching_status": "teaching_break"}
            excluded = sum(date.fromisoformat(week) <= day for week in term["excluded_weeks"])
            return {**scope, "week": (day - start).days // 7 + 1 - excluded,
                    "teaching_status": "teaching"}
    return scope
