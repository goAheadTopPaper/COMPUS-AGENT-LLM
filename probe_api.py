"""Inspect public API contracts without an LLM; saves public responses locally."""
import argparse
import json
from pathlib import Path

from schedule_agent import ARRANGEMENTS_URL, SUBJECTS_URL, post_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--programme-id", type=int, required=True)
    parser.add_argument("--acad-year", required=True)
    parser.add_argument("--semester", required=True, choices=["1", "2", "3"])
    parser.add_argument("--subject-id", type=int)
    parser.add_argument("--queries-as-list", action="store_true")
    parser.add_argument("--output-dir", default=".local/api_probe")
    args = parser.parse_args()
    target = Path(args.output_dir)
    target.mkdir(parents=True, exist_ok=True)
    subjects = post_json(SUBJECTS_URL, {"acadYearSem": args.acad_year + args.semester,
                                      "programmeId": args.programme_id})
    (target / "subjects.json").write_text(json.dumps(subjects, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Subject response:", list(subjects) if isinstance(subjects, dict) else type(subjects).__name__)
    if args.subject_id:
        query = {"acadYear": args.acad_year, "acadSemester": args.semester, "subjectId": args.subject_id}
        result = post_json(ARRANGEMENTS_URL, {"queries": [query] if args.queries_as_list else query})
        (target / "arrangements.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Arrangement response:", str(result)[:3500])


if __name__ == "__main__":
    main()
