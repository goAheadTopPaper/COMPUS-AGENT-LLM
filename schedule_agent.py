"""Public eStudent course lookup, following interface.md (not an exam API)."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from programme_resolver import ProgrammeResolver


BASE_URL = "https://estudent.polyu.edu.hk/proxy/e-public/srs-api/student-portal/public"
SUBJECTS_URL = BASE_URL + "/subjects/search"
ARRANGEMENTS_URL = BASE_URL + "/subject-component-quota-groups/search/batch"


class ScheduleError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def post_json(url, payload):
    request = Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                      headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        raise ScheduleError(f"eStudent HTTP {exc.code}; check API access and request format") from None
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        raise ScheduleError(f"eStudent request failed ({type(exc).__name__})") from None


def current_term(today):
    if today.month >= 9:
        return str(today.year), "1"
    semester = "1" if today.month == 1 else "2" if today.month <= 6 else "3"
    return str(today.year - 1), semester


def course_key(value):
    return re.sub(r"[\s-]+", "", str(value)).casefold()


def _objects(value):
    """Traverse JSON wrappers; retain parent identifiers on nested timetable rows."""
    if isinstance(value, list):
        for item in value:
            yield from _objects(item)
    elif isinstance(value, dict):
        inherited = {k: v for k, v in value.items() if not isinstance(v, (list, dict))}
        # roomCodeList is itself evidence, not a wrapper.
        if "roomCodeList" in value:
            inherited["roomCodeList"] = value["roomCodeList"]
        for key in ("acadWeekDateMap", "subjectTitles"):
            if key in value:
                inherited[key] = value[key]
        yield inherited
        if "deliveryTimeFrom" in value or "cttDayOfWeekTk" in value:
            return
        for key, child in value.items():
            if isinstance(child, (list, dict)) and key != "roomCodeList":
                for row in _objects(child):
                    yield {**inherited, **row}


def _check_response(response):
    if not isinstance(response, (list, dict)):
        raise ScheduleError("Expected JSON array/object; please supply a real API response sample")
    if isinstance(response, dict) and (response.get("success") is False or response.get("error")
            or ("status" in response and str(response["status"]).isdigit()
                and not 200 <= int(response["status"]) < 300)):
        raise ScheduleError("eStudent returned an error; check API access and request parameters")


def _empty_response(response):
    if isinstance(response, list):
        return all(_empty_response(item) for item in response)
    if isinstance(response, dict):
        return any(key in response and _empty_response(response[key])
                   for key in ("value", "data", "content", "results", "records", "items"))
    return False


def _nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nodes(child)


def _evidence(data, url, warnings):
    text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(text.encode()).hexdigest()[:24]
    return {"evidence_id": "schedule:" + digest, "text": text,
            "citation": {"title": "PolyU eStudent course information", "source_url": url,
                         "retrieved_at": datetime.now(timezone.utc).isoformat()},
            "warnings": list(warnings), **data}


class ScheduleAgent:
    def __init__(self, programme_id=None, semester_start=None, transport=post_json,
                 queries_as_list=True, today=None, programme_resolver=None):
        self.programme_id = programme_id
        self.semester_start = semester_start
        self.transport = transport
        # Live public API verification: queries must be an array (object -> HTTP 400).
        self.queries_as_list = queries_as_list
        self.today = today or datetime.now(timezone(timedelta(hours=8))).date()
        self.programme_resolver = programme_resolver or ProgrammeResolver()

    def search(self, course_queries, *, programme_id=None, acad_year=None, semester=None,
               on_date=None, semester_start=None, week=None, programme=None):
        if not isinstance(course_queries, (list, tuple)) or not all(isinstance(q, str) and q.strip() for q in course_queries):
            raise ValueError("course_queries must be a list of course codes or full names")
        if programme:
            resolution = self.programme_resolver.resolve(programme)
            if resolution["status"] != "resolved":
                return {**resolution, "results": []}
            programme_id = resolution["programme_id"]
        else:
            programme_id = programme_id if programme_id is not None else self.programme_id
        missing = []
        if programme_id is None:
            missing.extend(self.programme_resolver.resolve(None)["missing"])
        if not course_queries:
            missing.append("要查询的课程代码或完整课程名称")
        if missing:
            return {"status": "clarification_required", "results": [], "missing": missing}
        if not str(programme_id).isdigit() or int(programme_id) <= 0:
            raise ValueError("programmeId must be a positive integer")
        programme_id = int(programme_id)
        day = date.fromisoformat(on_date) if on_date else self.today
        default_year, default_semester = current_term(day)
        year, sem = str(acad_year or default_year), str(semester or default_semester)
        if not re.fullmatch(r"20\d{2}", year) or sem not in {"1", "2", "3"}:
            raise ValueError("acad_year must be YYYY and semester must be 1, 2 or 3")
        warnings = []
        start = semester_start or self.semester_start
        if week is None and start:
            start = date.fromisoformat(start)
            if current_term(start) != (year, sem) or day < start:
                return {"status": "clarification_required", "results": [],
                        "missing": ["与查询学期一致、且不晚于查询日期的 semester_start；或直接指定 week"]}
            week = (day - start).days // 7 + 1
        if week is not None:
            if type(week) is not int or week < 1:
                raise ValueError("week must be a positive integer")
        else:
            warnings.append("未提供该学期教学周起算日；返回全部周次，不能断言这些安排在当前周生效。")
        response = self.transport(SUBJECTS_URL, {"acadYearSem": year + sem, "programmeId": programme_id})
        _check_response(response)
        subjects = {}
        for row in _nodes(response):
            code = row.get("subjCode", row.get("subjectCode"))
            sid = row.get("id", row.get("subjectId"))
            if code and sid is not None:
                titles = row.get("subjectTitles", {})
                subjects[str(sid)] = {**row, "subjectCode": code,
                    "subjectTitle": (titles.get("UI_LANGUAGE||EN") if isinstance(titles, dict) else None)
                                    or row.get("subjectTitle") or row.get("subjectName"),
                    **({"credits": row["subjCredit"]} if "subjCredit" in row else {})}
        if not subjects:
            # An explicit empty collection is a successful query with no offerings.
            if _empty_response(response):
                return {"status": "no_results", "results": [], "unmatched": list(course_queries)}
            raise ScheduleError("Cannot locate id/subjCode in course list; supply a real JSON response sample")
        matched, unmatched, ambiguous = {}, [], []
        for query in course_queries:
            key = course_key(query)
            candidates = [s for s in subjects.values() if key in {
                course_key(s.get(field, "")) for field in
                ("subjectCode", "subjectName", "subjectTitle", "title", "name", "subjectNameEn")}]
            if not candidates:
                unmatched.append(query)
            elif len(candidates) > 1:
                ambiguous.append({"query": query, "candidates": candidates})
            else:
                subject = candidates[0]
                matched[str(subject.get("id", subject.get("subjectId")))] = subject
        if ambiguous:
            return {"status": "clarification_required", "results": [], "missing": ["课程名称对应多个课程，请指定课程代码"],
                    "ambiguous": ambiguous}
        evidence = []
        for sid, subject in matched.items():
            base = {"subjectId": subject.get("id", subject.get("subjectId")),
                    "subjectCode": subject["subjectCode"], "acadYear": year, "acadSemester": sem,
                    "programmeId": programme_id}
            query = {"acadSemester": sem, "acadYear": year, "subjectId": base["subjectId"]}
            raw = self.transport(ARRANGEMENTS_URL, {"queries": [query] if self.queries_as_list else query})
            _check_response(raw)
            rows = []
            for row in _objects(raw):
                if "deliveryTimeFrom" not in row and "cttDayOfWeekTk" not in row:
                    continue
                if row.get("subjectCode") and course_key(row["subjectCode"]) != course_key(subject["subjectCode"]):
                    raise ScheduleError("Timetable response contains a different course; refusing to mix evidence")
                if ((row.get("acadYear") is not None and str(row["acadYear"]) != year)
                        or (row.get("acadSemester") is not None and str(row["acadSemester"]) != sem)):
                    raise ScheduleError("Timetable response does not match the requested academic term")
                fields = ("quotaGroupCode", "deliveryTimeFrom", "deliveryTimeTo", "acadWeekFm", "acadWeekTo",
                          "roomCodeList", "cttDayOfWeekTk", "subjectComponentId", "componentCode", "componentType",
                          "componentId", "dayOfWeek", "deliveryFrequency", "acadWeekDateMap", "sectionRemarks")
                data = {**base, **{f: row[f] for f in fields if f in row}}
                data["timezone"] = "Asia/Hong_Kong"
                row_warnings = list(warnings)
                if week is not None:
                    try:
                        if not int(data["acadWeekFm"]) <= week <= int(data["acadWeekTo"]):
                            continue
                    except (KeyError, TypeError, ValueError):
                        row_warnings.append("该安排缺少有效周次范围，无法确认查询周是否适用。")
                rows.append((data, row_warnings))
            # Discard only groups whose COMPLETE set of meetings is identical.
            # Different component types or genuinely different groups are retained.
            groups = {}
            for data, row_warnings in rows:
                groups.setdefault(data.get("quotaGroupCode"), []).append((data, row_warnings))
            seen = set()
            for group_rows in groups.values():
                signature = tuple(sorted(set(json.dumps({k: v for k, v in d.items() if k != "quotaGroupCode"},
                                                        sort_keys=True, ensure_ascii=False) for d, _ in group_rows)))
                if signature in seen:
                    continue
                seen.add(signature)
                for data, row_warnings in group_rows:
                    if len(groups) > 1:
                        row_warnings = row_warnings + ["相同安排的分组已去重；保留的分组不是个人选课确认。"]
                    evidence.append(_evidence(data, ARRANGEMENTS_URL, row_warnings))
            details = {**base, **{k: v for k, v in subject.items()
                                 if k in {"subjectName", "subjectTitle", "title", "name", "subjectNameEn", "credits", "credit"}}}
            evidence.append(_evidence(details, SUBJECTS_URL, warnings + (
                ["未找到符合查询周次的上课安排。"] if not rows else [])))
            if not rows and not any("deliveryTimeFrom" in r or "cttDayOfWeekTk" in r for r in _objects(raw)):
                # Do not mistake an undocumented response structure for no classes.
                if not _empty_response(raw):
                    raise ScheduleError("Cannot parse timetable response; supply a real JSON response sample")
        unique = {row["evidence_id"]: row for row in evidence}
        return {"status": "partial" if unmatched and evidence else "candidates_found" if evidence else "no_results",
                "results": list(unique.values()), "unmatched": unmatched, "warnings": warnings,
                "query_scope": {"acadYear": year, "acadSemester": sem, "week": week, "on_date": day.isoformat()}}
