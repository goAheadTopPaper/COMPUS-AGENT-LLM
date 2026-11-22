"""Public eStudent course lookup, following interface.md (not an exam API)."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
from difflib import SequenceMatcher
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from programme_resolver import ProgrammeResolver
from academic_calendar import term_for_date, teaching_week
from course_matcher import match_courses
from subject_catalogue import discover_subjects, is_code


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
    official = term_for_date(today)
    if official:
        return official
    if today.month >= 9:
        return str(today.year), "1"
    semester = "1" if today.month == 1 else "2" if today.month <= 6 else "3"
    return str(today.year - 1), semester


def course_key(value):
    return re.sub(r"[\s-]+", "", "" if value is None else str(value)).casefold()


def _course_name_matches(query, subject):
    """Match aliases against actual returned titles, never invent a course ID."""
    titles = [subject.get(field) or "" for field in
              ("subjectName", "subjectTitle", "title", "name", "subjectNameEn")]
    key = course_key(query)
    # This bilingual alias targets a title; the course code/ID must still come
    # from the selected programme's real API result.
    bilingual = {"人机交互": "humancomputerinteraction", "人機交互": "humancomputerinteraction",
                 "人機互動": "humancomputerinteraction"}
    for title in titles:
        title_key = course_key(title)
        if any(alias in query and title_key == target for alias, target in bilingual.items()):
            return True
        words = re.findall(r"[A-Za-z]+", title)
        acronym = "".join(w[0] for w in words if w.casefold() not in {"and", "of", "the", "in"}).casefold()
        tokens = [t.casefold() for t in re.findall(r"[A-Za-z]+", query)]
        if len(acronym) >= 3 and acronym in tokens:
            return True
        if len(key) >= 6 and title_key and SequenceMatcher(None, key, title_key).ratio() >= .85:
            return True
    return False


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
                 queries_as_list=True, today=None, programme_resolver=None, model=None):
        self.programme_id = programme_id
        self.semester_start = semester_start
        self.transport = transport
        # Live public API verification: queries must be an array (object -> HTTP 400).
        self.queries_as_list = queries_as_list
        self.today = today
        self.programme_resolver = programme_resolver or ProgrammeResolver()
        self.model = model

    def search(self, course_queries, *, programme_id=None, acad_year=None, semester=None,
               on_date=None, semester_start=None, week=None, programme=None):
        if not isinstance(course_queries, (list, tuple)) or not all(isinstance(q, str) and q.strip() for q in course_queries):
            raise ValueError("course_queries must be a list of course codes or full names")
        day = date.fromisoformat(on_date) if on_date else self.today or datetime.now(timezone(timedelta(hours=8))).date()
        default_year, default_semester = current_term(day)
        year, sem = str(acad_year or default_year), str(semester or default_semester)
        if not re.fullmatch(r"20\d{2}", year) or sem not in {"1", "2", "3"}:
            raise ValueError("acad_year must be YYYY and semester must be 1, 2 or 3")
        if programme:
            resolution = self.programme_resolver.resolve(programme, acad_year=year)
            if resolution["status"] != "resolved":
                return {**resolution, "results": []}
            programme_id = resolution["programme_id"]
        else:
            programme_id = programme_id if programme_id is not None else self.programme_id
        missing = []
        if not course_queries:
            missing.append("要查询的课程代码或完整课程名称")
        if missing:
            return {"status": "clarification_required", "results": [], "missing": missing}
        if programme_id is not None and (not str(programme_id).isdigit() or int(programme_id) <= 0):
            raise ValueError("programmeId must be a positive integer")
        programme_id = int(programme_id) if programme_id is not None else None
        warnings = []
        start = semester_start or self.semester_start
        week_scope = {"teaching_status": "manual_week" if week is not None else "manual_start"}
        if week is None and start:
            start = date.fromisoformat(start)
            # The official 2026/27 Semester 1 starts on 31 August 2026.
            # The API's coarse month rule must not reject an explicit August
            # teaching-week anchor for Semester 1 of that academic year.
            start_matches = current_term(start) == (year, sem) or (
                sem == "1" and start.year == int(year) and start.month == 8)
            if not start_matches or day < start:
                return {"status": "clarification_required", "results": [],
                        "missing": ["与查询学期一致、且不晚于查询日期的 semester_start；或直接指定 week"]}
            week = (day - start).days // 7 + 1
            week_scope["semester_start"] = start.isoformat()
        elif week is None:
            week_scope = teaching_week(day, year, sem)
            week = week_scope["week"]
        if week is not None:
            if type(week) is not int or week < 1:
                raise ValueError("week must be a positive integer")
        else:
            reason = {"calendar_unavailable": "尚无该学年的已核实官方校历",
                      "outside_teaching_period": "查询日期不在该学期教学期内",
                      "teaching_break": "查询日期处于学校停课假期"}.get(week_scope["teaching_status"], "无法确认教学周")
            warnings.append(reason + "；返回学期全部周次，不能断言这些安排在当前日期生效。")
        cached = False
        if programme_id is None:
            try:
                response, cached = discover_subjects(course_queries, year + sem, self.transport, self.model)
            except ValueError as exc:
                raise ScheduleError(str(exc)) from None
        else:
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
        # First resolve exact names/codes and simple abbreviations. Use a model
        # only for remaining natural names, grounded in this actual catalogue.
        query_candidates = {}
        for query in dict.fromkeys(course_queries):
            key = course_key(query)
            candidates = [s for s in subjects.values() if key in {
                course_key(s.get(field, "")) for field in
                ("subjectCode", "subjectName", "subjectTitle", "title", "name", "subjectNameEn")}]
            if not candidates and not is_code(query):
                candidates = [s for s in subjects.values() if _course_name_matches(query, s)]
            query_candidates[query] = candidates
        unresolved = [q for q, candidates in query_candidates.items() if not candidates
                      and not is_code(q)]
        if unresolved and self.model is not None:
            try:
                query_candidates.update(match_courses(unresolved, subjects, self.model))
            except ValueError as exc:
                raise ScheduleError(str(exc)) from None
        matched, unmatched, ambiguous = {}, [], []
        for query, candidates in query_candidates.items():
            if not candidates:
                unmatched.append(query)
            elif len(candidates) > 1:
                ambiguous.append({"query": query, "candidates": candidates})
            else:
                subject = candidates[0]
                matched[str(subject.get("id", subject.get("subjectId")))] = subject
        if ambiguous:
            descriptions = [f"“{item['query']}”：" + "、".join(
                str(s["subjectCode"]) + " " + str(s.get("subjectTitle") or s.get("subjectName") or "")
                for s in item["candidates"][:6]) for item in ambiguous]
            return {"status": "clarification_required", "results": [], "missing": [
                    "课程名称对应多个课程，请选择或补充课程代码。" + "；".join(descriptions)],
                    "clarification_options": [{"label": str(s["subjectCode"]) + " · " + str(s.get("subjectTitle") or s.get("subjectName") or ""),
                        "value": str(s["subjectCode"]), "query": ambiguous[0]["query"],
                        "queries": [item["query"] for item in ambiguous if
                            {str(c.get("id", c.get("subjectId"))) for c in item["candidates"]} ==
                            {str(c.get("id", c.get("subjectId"))) for c in ambiguous[0]["candidates"]}]}
                        for s in ambiguous[0]["candidates"][:12]],
                    "ambiguous": ambiguous}
        evidence = []
        for sid, subject in matched.items():
            if cached:
                live = self.transport(SUBJECTS_URL, {"acadYearSem": year + sem, "subjCode": subject["subjectCode"]})
                _check_response(live)
                if not any(str(r.get("id", r.get("subjectId"))) == sid for r in _nodes(live)):
                    return {"status": "clarification_required", "results": [],
                            "missing": ["课程清单中的版本与本学期实时结果不一致，请确认课程代码或更新全校课程清单。"]}
            base = {"subjectId": subject.get("id", subject.get("subjectId")),
                    "subjectCode": subject["subjectCode"], "acadYear": year, "acadSemester": sem,
                    "lookupScope": "programme" if programme_id is not None else "university"}
            if programme_id is not None:
                base["programmeId"] = programme_id
            if programme:
                base["programmeName"] = resolution["programme"]
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
                rooms = data.get("roomCodeList")
                if isinstance(rooms, list) and rooms and all(isinstance(room, str) for room in rooms):
                    data["roomDisplay"] = " 或 ".join(dict.fromkeys(room.strip() for room in rooms if room.strip()))
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
            # The API returns weekly patterns. For an explicit target date,
            # record the deterministic weekday comparison as quotable evidence.
            # Do not infer a daily result for exception dates/unknown frequencies.
            if (on_date and week is not None and week_scope.get("teaching_status") == "teaching"
                    and rows and all(str(d.get("dayOfWeek", "")) in {str(i) for i in range(1, 8)}
                                     and d.get("deliveryFrequency", 1) == 1
                                     and not d.get("acadWeekDateMap") for d, _ in rows)):
                patterns = {json.dumps({k: v for k, v in d.items() if k != "quotaGroupCode"}, sort_keys=True): d
                            for d, _ in rows}
                matching = [d for d in patterns.values() if int(d["dayOfWeek"]) == day.isoweekday()]
                summary = {**base, "queryDate": day.isoformat(), "queryDayOfWeek": day.isoweekday(),
                           "queryWeek": week, "matchingWeeklyPatterns": len(matching),
                           "lookupResult": "matching_weekly_pattern" if matching else "no_matching_weekday",
                           "recordedWeekdays": sorted({int(d["dayOfWeek"]) for d, _ in rows})}
                evidence.append(_evidence(summary, ARRANGEMENTS_URL,
                    ["由公开课表的星期与查询日期计算；非个人选课确认，临时停课或补课以学校通知为准。"]))
            evidence.append(_evidence(details, SUBJECTS_URL, warnings + (
                ["未找到符合查询周次的上课安排。"] if not rows else [])))
            if not rows and not any("deliveryTimeFrom" in r or "cttDayOfWeekTk" in r for r in _objects(raw)):
                # Do not mistake an undocumented response structure for no classes.
                if not _empty_response(raw):
                    raise ScheduleError("Cannot parse timetable response; supply a real JSON response sample")
        unique = {row["evidence_id"]: row for row in evidence}
        return {"status": "partial" if unmatched and evidence else "candidates_found" if evidence else "no_results",
                "results": list(unique.values()), "unmatched": unmatched, "warnings": warnings,
                "query_scope": {**week_scope, "acadYear": year, "acadSemester": sem,
                                "week": week, "on_date": day.isoformat(),
                                "on_date_is_resolved": True,
                                "today": (self.today or datetime.now(timezone(timedelta(hours=8))).date()).isoformat(),
                                "programme": resolution["programme"] if programme else None}}
