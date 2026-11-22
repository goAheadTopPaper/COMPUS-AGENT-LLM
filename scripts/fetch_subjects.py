"""Export all subjects exposed by public offering departments for one term."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import sys

from fetch_programmes import fetch, DROPDOWN, BASE

ROOT = Path(__file__).resolve().parents[1]
SEARCH = BASE + "/subjects/search"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year-sem", default="20261")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    captured = datetime.now(timezone.utc).isoformat()
    departments = fetch(DROPDOWN + "?yearSem=" + args.year_sem)["value"]["subjectOfferingDepartments"]
    target = ROOT / ".local" / "subject_discovery" / args.year_sem
    target.mkdir(parents=True, exist_ok=True)

    def query(department):
        error = None
        for _ in range(2):
            try:
                result = fetch(SEARCH, {"acadYearSem": args.year_sem, "orgUnitId": int(department["value"])})
                if not isinstance(result["value"], list) or result.get("size") != len(result["value"]):
                    raise ValueError("Unexpected subject response")
                (target / (department["value"] + ".json")).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
                return result["value"]
            except Exception as exc:
                error = exc
        raise RuntimeError(f"{department['label']}: {type(error).__name__}")

    records, counts, errors, capped = {}, [], [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(query, d): d for d in departments}
        for future in as_completed(jobs):
            department = jobs[future]
            try:
                rows = future.result()
            except Exception as exc:
                errors.append(str(exc))
                continue
            counts.append({**department, "count": len(rows)})
            if len(rows) >= 1000:
                capped.append(department["label"])
            for row in rows:
                sid = row["id"]
                if sid not in records:
                    records[sid] = {"id": sid, "subjCode": row.get("subjCode"),
                        "subjectTitles": row.get("subjectTitles", {}), "subjCredit": row.get("subjCredit"),
                        "implYear": row.get("implYear"), "endYear": row.get("endYear"), "departments": []}
                records[sid]["departments"].append(department["label"])
            print(department["label"], len(rows), flush=True)
    ordered = sorted(records.values(), key=lambda row: (row["subjCode"] or "", row["id"]))
    data = {"acad_year_sem": args.year_sem, "source_url": SEARCH, "retrieved_at": captured,
            "complete_for_returned_departments": not errors and not capped, "subjects": ordered}
    (ROOT / "subjects.discovered.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with (ROOT / "subjects.discovered.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["subjectId", "subjectCode", "subjectTitle", "implementationYear"])
        writer.writerows([r["id"], r["subjCode"], r["subjectTitles"].get("UI_LANGUAGE||EN", ""), r["implYear"]] for r in ordered)
    report = {"acad_year_sem": args.year_sem, "department_count": len(departments),
              "unique_ids": len(records), "unique_codes": len({r["subjCode"] for r in ordered}),
              "counts": counts, "failures": errors, "possibly_capped_departments": capped,
              "complete_for_returned_departments": data["complete_for_returned_departments"],
              "source_url": SEARCH, "retrieved_at": captured}
    (ROOT / "subjects.discovered.report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY", json.dumps({k: report[k] for k in ("department_count", "unique_ids", "unique_codes", "failures", "possibly_capped_departments")}), flush=True)
    return 0 if data["complete_for_returned_departments"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
