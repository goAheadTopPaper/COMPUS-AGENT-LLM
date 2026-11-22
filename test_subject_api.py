"""Offline tests for subject_api.py. Run: python3 -B -m unittest test_subject_api -v

Uses injected fetchers; no campus network, Canvas token or LLM needed.
"""
import copy
import json
import unittest

from agents import collect_evidence
from subject_api import search
from supervisor import run

CODE = "COMP5926"
TITLE = "METAVERSE PROJECT II"
DETAIL = {
    "id": 41275,
    "subjCode": CODE,
    "subjectTitles": {"UI_LANGUAGE||EN": TITLE},
    "subjCredit": 3,
    "subjLevel": 5,
    "mediumOfInstruction": "PRIM_MOI||ENG",
    "implYear": "2023",
    "nature": [{"description": "Dissertation"}],
    "preRequisitesConstraintMap": {
        "47596": [{"subjCode": "COMP5925", "effAcadYear": "2023",
                   "effAcadSemester": "1", "expiryAcadYearSem": "9999-9"}]
    },
    "coRequisitesConstraintMap": {},
    "exclusionConstraintMap": {},
    "subjectOfferDepts": [{"organizationUnit": {"orgUnitTitles": [
        {"language": "UI_LANGUAGE||EN", "titleType": "ABBR", "titleName": "COMP"},
        {"language": "UI_LANGUAGE||EN", "titleType": "NAME",
         "titleName": "DEPARTMENT OF COMPUTING"},
    ]}}],
    "synopsisUrl": "https://www38.polyu.edu.hk/ePublic/subject-search.jsf",
}
SUMMARY = {k: v for k, v in DETAIL.items()
           if k in ("id", "subjCode", "subjectTitles", "subjCredit")}
SUMMARY["preRequisitesConstraintMap"] = {}


def fetcher_for(rows, detail=None, fail_detail=False):
    """Scripted fetcher recording calls; returns search rows and optional detail."""
    calls = []

    def fetch(method, url, payload):
        calls.append((method, url, payload))
        if method == "POST":
            return {"status": 200, "value": copy.deepcopy(rows)}
        if fail_detail:
            raise OSError("detail unavailable")
        return {"status": 200, "value": copy.deepcopy(detail if detail is not None else rows[0])}

    return fetch, calls


class SubjectApiTests(unittest.TestCase):
    def test_subject_code_query_uses_detail_and_returns_full_contract(self):
        fetch, calls = fetcher_for([SUMMARY], DETAIL)
        result = search("COMP5926", fetcher=fetch)

        self.assertEqual(result["status"], "candidates_found")
        for key in ("results", "year_filters", "limitations",
                    "requires_subject_clarification", "requires_year_clarification"):
            self.assertIn(key, result)
        self.assertEqual(result["year_filters"], {})
        self.assertFalse(result["requires_subject_clarification"])
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[0][2], {"subjCode": "COMP5926"})
        self.assertEqual(calls[1][0], "GET")
        self.assertIn("/public/subjects/41275", calls[1][1])

        ids = [row["evidence_id"] for row in result["results"]]
        self.assertEqual(len(ids), len(set(ids)))  # no duplicate/conflicting IDs
        by_id = dict(zip(ids, result["results"]))
        self.assertIn("policy:estudent:COMP5926:requires:COMP5925", by_id)
        self.assertIn("COMP5925", by_id["policy:estudent:COMP5926:requires:COMP5925"]["text"])
        self.assertIn("academic year 2023 semester 1",
                      by_id["policy:estudent:COMP5926:requires:COMP5925"]["text"])
        self.assertIn("DEPARTMENT OF COMPUTING",
                      by_id["policy:estudent:COMP5926:department"]["text"])
        self.assertNotIn("COMP is offered by", json.dumps(result["results"]))

    def test_evidence_fields_and_stable_ids(self):
        fetch, _ = fetcher_for([SUMMARY], DETAIL)
        first = search("comp5926", fetcher=fetch)
        second = search("COMP5926", fetcher=fetch)

        self.assertEqual([r["evidence_id"] for r in first["results"]],
                         [r["evidence_id"] for r in second["results"]])
        for row in first["results"]:
            self.assertTrue(row["text"].strip())
            self.assertTrue(row["citation"]["title"])
            self.assertTrue(row["citation"]["source_url"].startswith("https://estudent.polyu.edu.hk/"))
            self.assertIn("warnings", row)
        # must be accepted by the teammate's collect_evidence()
        bundle = collect_evidence(first, [])
        self.assertEqual(len(bundle["evidence"]), len(first["results"]))

    def test_acad_year_sem_is_forwarded_and_recorded(self):
        fetch, calls = fetcher_for([SUMMARY], DETAIL)
        result = search("COMP5926", acad_year_sem="20261", fetcher=fetch)

        self.assertEqual(calls[0][2]["acadYearSem"], "20261")
        self.assertEqual(result["year_filters"], {"acadYearSem": "20261"})
        self.assertTrue(all(row["academic_year"] == "20261" for row in result["results"]))

    def test_no_results_keeps_status_and_empty_results(self):
        fetch, calls = fetcher_for([])
        result = search("COMP9999", fetcher=fetch)

        self.assertEqual(result["status"], "no_results")
        self.assertEqual(result["results"], [])
        self.assertEqual(len(calls), 1)  # no detail calls
        self.assertTrue(any("No subject matched" in x for x in result["limitations"]))
        self.assertFalse(result["requires_subject_clarification"])

    def test_ambiguous_title_sets_clarification_and_caps_candidates(self):
        rows = [{"id": i, "subjCode": "COMP5%04d" % i,
                 "subjectTitles": {"UI_LANGUAGE||EN": "Metaverse %d" % i}}
                for i in range(8)]
        fetch, calls = fetcher_for(rows)
        result = search("Metaverse", fetcher=fetch, max_candidates=2)

        self.assertTrue(result["requires_subject_clarification"])
        self.assertEqual(len(calls), 3)  # 1 search + 2 details
        self.assertTrue(any("Multiple subjects matched" in x for x in result["limitations"]))
        self.assertTrue(any("first 2" in x for x in result["limitations"]))

    def test_empty_constraint_maps_do_not_invent_a_requirement(self):
        empty = copy.deepcopy(DETAIL)
        empty["preRequisitesConstraintMap"] = {}
        fetch, _ = fetcher_for([SUMMARY], empty)
        result = search("COMP5926", fetcher=fetch)
        text = json.dumps(result["results"], ensure_ascii=False)

        self.assertNotIn("COMP5925", text)
        self.assertFalse(any("requires" in r["evidence_id"] for r in result["results"]))

    def test_detail_failure_is_downgraded_not_fatal(self):
        fetch, _ = fetcher_for([SUMMARY], fail_detail=True)
        result = search("COMP5926", fetcher=fetch)

        self.assertEqual(result["status"], "candidates_found")
        self.assertTrue(any("detail request(s) failed" in x for x in result["limitations"]))
        self.assertTrue(any(r["evidence_id"].endswith(":title") for r in result["results"]))

    def test_search_failure_propagates_to_supervisor(self):
        def broken(method, url, payload):
            raise OSError("network down")

        with self.assertRaises(OSError):
            search("COMP5926", fetcher=broken)

        def policy_search(query):
            return search(query, fetcher=broken)

        def model(system, payload):
            return {"claims": []}

        result = run({"question": "What is COMP5926?", "branches": ["policy"],
                      "sub_queries": {"policy": "COMP5926"}},
                     model, policy_search=policy_search, max_retries=0)
        self.assertEqual(result["branches"]["policy"]["state"], "failed")
        self.assertIn("规章检索失败", result["notices"][0])
        self.assertNotIn("answer", result)

    def test_missing_optional_fields_are_tolerated(self):
        sparse = {"subjCode": "COMP0001", "id": 1}
        fetch, _ = fetcher_for([sparse], sparse)
        result = search("COMP0001", fetcher=fetch)

        self.assertEqual(result["status"], "candidates_found")
        self.assertTrue(any("no-structured-evidence" in r["evidence_id"]
                            for r in result["results"]))

    def test_invalid_inputs_are_rejected(self):
        for query in ("", "   ", 123, "x" * 201):
            with self.assertRaises(ValueError):
                search(query, fetcher=fetcher_for([])[0])
        with self.assertRaises(ValueError):
            search("COMP5926", fetcher=fetcher_for([])[0], max_candidates=0)

    def test_end_to_end_with_supervisor_approved_answer(self):
        fetch, _ = fetcher_for([SUMMARY], DETAIL)

        def model(system, payload):
            if "Use only the supplied evidence" in system:  # ANSWER_PROMPT
                return {"claims": [{
                    "text": "COMP5926 requires COMP5925.",
                    "supports": [{"evidence_id": "policy:estudent:COMP5926:requires:COMP5925",
                                  "quote": "COMP5926 requires COMP5925"}],
                }]}
            return {"checks": [{"index": 0, "status": "supported", "reason": "fixture"}],
                    "unanswered": [], "needs_clarification": False}

        result = run(
            {"question": "What is the prerequisite for COMP5926?",
             "branches": ["policy"], "sub_queries": {"policy": "COMP5926"}},
            model, policy_search=lambda q: search(q, fetcher=fetch))
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["approved"])
        self.assertIn("COMP5925", result["answer"])
        self.assertIn("policy:estudent:COMP5926:requires:COMP5925", result["sources"])


if __name__ == "__main__":
    unittest.main()
