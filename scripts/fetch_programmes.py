"""Export the public eStudent programme->ID mapping, partitioned by department.

Endpoints and request fields were observed in the public subject-search client.
No login, personal records or credentials are used. Does not overwrite the
production programmes.json: historical versions/modes may share a title/code.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://estudent.polyu.edu.hk/proxy/e-public/srs-api/student-portal/public"
SEARCH = BASE + "/programmes/search"
DROPDOWN = BASE + "/system/dropdown-options/public"


def fetch(url, body=None):
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    with urlopen(request, timeout=45) as response:
        result = json.load(response)
    if result.get("status") != 200 or not isinstance(result.get("value"), (list, dict)):
        raise ValueError("Invalid API response")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year-sem", default="20261")
    parser.add_argument("--output", default="programmes.discovered.json")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    captured = datetime.now(timezone.utc).isoformat()
    departments = fetch(DROPDOWN + "?yearSem=" + args.year_sem)["value"]["programmeHostingDepartments"]
    raw_dir = ROOT / ".local" / "programme_discovery" / args.year_sem
    raw_dir.mkdir(parents=True, exist_ok=True)

    def query(department):
        payload = {"yearSem": args.year_sem, "orgUnitId": int(department["value"])}
        last_error = None
        for _ in range(2):
            try:
                result = fetch(SEARCH, payload)
                rows = result["value"]
                if not isinstance(rows, list) or result.get("size") != len(rows):
                    raise ValueError("Unexpected size/value contract")
                (raw_dir / (department["value"] + ".json")).write_text(
                    json.dumps(result, ensure_ascii=False), encoding="utf-8")
                return department, rows
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"{department['label']}: {type(last_error).__name__}")

    records, counts, failures, capped = {}, [], [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(query, department): department for department in departments}
        for future in as_completed(jobs):
            department = jobs[future]
            try:
                _, rows = future.result()
            except Exception as exc:
                failures.append(str(exc))
                print("FAILED", str(exc), flush=True)
                continue
            count = len(rows)
            counts.append({**department, "count": count})
            if count >= 1000:
                capped.append(department["label"])
            for row in rows:
                key = row["id"]
                if key not in records:
                    records[key] = {"raw": row, "departments": []}
                records[key]["departments"].append(department["label"])
            print(department["label"], count, flush=True)

    mappings = []
    for programme_id, record in sorted(records.items()):
        row = record["raw"]
        titles = [t for t in row.get("programmeTitles", [])
                  if t.get("mdmTitleTypeTk") == "MDM_TITLE_TYPE||PROG_TITLE" and t.get("title")]
        english = next((t["title"] for t in titles if t.get("uiLanguageTk") == "UI_LANGUAGE||EN"), None)
        title = english or next((t["title"] for t in titles), None)
        if not title:
            failures.append(f"programme {programme_id}: no programme title")
            continue
        code, subcode = str(row.get("progCode") or "").strip(), str(row.get("subCode") or "").strip()
        mode = (row.get("progModeTk") or "").split("||")[-1]
        full_code = code + ("-" + subcode if subcode else "")
        mappings.append({"name": f"{title} [{full_code}; {mode}; impl={row.get('implYear')}]",
            "aliases": list(dict.fromkeys([t["title"] for t in titles] + [full_code])),
            "programme_code": code, "programme_id": programme_id,
            "programme_subcode": subcode, "programme_title": title, "mode": mode,
            "implementation_year": row.get("implYear"), "last_admission_year": row.get("lastAdmYear"),
            "last_operation_year": row.get("lastOperationYear"), "level": row.get("progLevelTk"),
            "departments": record["departments"], "source_url": SEARCH,
            "queried_year_sem": args.year_sem, "retrieved_at": captured})
    output = ROOT / args.output
    output.write_text(json.dumps(mappings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    csv_path = output.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["programme_id", "programme_code", "programme_subcode", "programme_title", "mode", "implementation_year"]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(mappings)
    report = {"source_url": SEARCH, "dropdown_url": DROPDOWN, "retrieved_at": captured,
        "year_sem": args.year_sem, "department_count": len(departments), "counts": counts,
        "unique_ids": len(records), "exported_mappings": len(mappings), "failures": failures,
        "possibly_capped_departments": capped,
        "complete_for_returned_departments": not failures and not capped,
        "limitations": ["Covers departments exposed by the public subject-search dropdown for the requested term.",
                        "Records include programme versions; not proof that each programme currently admits students.",
                        "No guarantee of all historical programmes, other PolyU institutions or future offerings."]}
    output.with_suffix(".report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY", json.dumps({k: report[k] for k in ("department_count", "unique_ids", "exported_mappings", "failures", "possibly_capped_departments")}), flush=True)
    return 0 if report["complete_for_returned_departments"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
