"""University-wide discovery: course IDs are scoped by term, not programme."""
import json
from pathlib import Path
import re
from course_matcher import search_terms

SEARCH_URL = "https://estudent.polyu.edu.hk/proxy/e-public/srs-api/student-portal/public/subjects/search"
CODE = re.compile(r"[A-Za-z]{2,6}[\s-]*\d[A-Za-z0-9]{2,7}")
DEFAULT_PATH = Path(__file__).with_name("subjects.discovered.json")


def is_code(query):
    return CODE.fullmatch(query.strip()) is not None


def discover_subjects(queries, year_sem, transport, model=None, catalogue_path=None):
    names = [q for q in queries if not is_code(q)]
    rows, cached = [], False
    path = Path(catalogue_path) if catalogue_path is not None else DEFAULT_PATH
    if names and path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if (data.get("acad_year_sem") == year_sem and data.get("complete_for_returned_departments") is True
                and isinstance(data.get("subjects"), list)):
            rows.extend(data["subjects"])
            cached = True
    terms = search_terms(names, model) if names and not cached else {}
    payloads = [{"acadYearSem": year_sem, "subjCode": re.sub(r"[\s-]", "", q).upper()}
                for q in queries if is_code(q)]
    payloads += [{"acadYearSem": year_sem, "term": word} for words in terms.values() for word in words]
    for payload in payloads:
        result = transport(SEARCH_URL, payload)
        if not isinstance(result, dict) or result.get("status", 200) != 200 or not isinstance(result.get("value", result.get("data")), list):
            raise ValueError("全校课程搜索接口返回结构无效。")
        found = result.get("value", result.get("data"))
        if len(found) >= 1000:
            raise ValueError("全校课程候选过多，请补充更完整的课程名称或代码。")
        if "subjCode" in payload:
            found = [r for r in found if str(r.get("subjCode", r.get("subjectCode", ""))).upper() == payload["subjCode"]]
        rows.extend(found)
    unique = {str(row.get("id", row.get("subjectId"))): row for row in rows}
    return {"status": 200, "value": list(unique.values())}, cached
