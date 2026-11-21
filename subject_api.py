"""Public eStudent subject-search adapter for the Policy branch.

Converts the Hong Kong PolyU public subject catalogue into the full
``PolicyRetriever.search()`` dictionary required by INTEGRATION.md:8.

Two public endpoints are used, both anonymous and read-only:
  POST /proxy/e-public/srs-api/student-portal/public/subjects/search
  GET  /proxy/e-public/srs-api/student-portal/public/subjects/{id}

The search endpoint returns summaries (the constraint maps are always empty
there); the detail endpoint carries the real prerequisite/corequisite data.
No Canvas token, personal data or write operation is involved.

Run offline tests: python3 -B -m unittest test_subject_api -v
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://estudent.polyu.edu.hk"
API_ROOT = BASE_URL + "/proxy/e-public/srs-api/student-portal"
SEARCH_PATH = "/public/subjects/search"
DETAIL_PATH = "/public/subjects/{id}"
LISTING_URL = BASE_URL + "/e-public/subject-search/listing?mode=subject"

_SUBJECT_CODE = re.compile(r"^[A-Z]{2,6}\d{3,5}[A-Z]?$", re.I)
_EN_TITLE = "UI_LANGUAGE||EN"
_DEFAULT_MAX_CANDIDATES = 5


def _default_fetcher(method, url, payload=None):
    """Minimal urllib fetcher. Returns a parsed dict; raises on network/HTTP errors."""
    data = None
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Origin": BASE_URL,
        "Referer": LISTING_URL,
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.loads(response.read().decode("utf-8", "ignore"))


def _en_title(row):
    titles = row.get("subjectTitles") or {}
    if not isinstance(titles, dict):
        return None
    if _EN_TITLE in titles and titles[_EN_TITLE]:
        return str(titles[_EN_TITLE])
    for value in titles.values():
        if value:
            return str(value)
    return None


def _neutralise(value):
    """Strip control characters that could break verbatim quoting."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(value)).strip()


def _evidence(evidence_id, text, row, source_url, warnings=None, academic_year=None):
    """Build one evidence record matching collect_evidence()'s required fields."""
    return {
        "evidence_id": evidence_id,
        "text": _neutralise(text),
        "citation": {
            "title": "eStudent Subject Search — %s" % (row.get("subjCode") or "subject"),
            "source_url": source_url,
        },
        "academic_year": academic_year,
        "warnings": list(warnings or []),
    }


def _value_text(value):
    """Render a scalar API value as readable English without inventing facts."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return _neutralise(value)


def _constraint_rows(row, key, prefix, source_url, warnings, academic_year):
    """Render one constraint map into evidence records.

    The API shape is ``{group_id: [ {subjCode, effAcadYear, effAcadSemester,
    expiryAcadYearSem, ...}, ... ]}``. Group IDs are opaque; only explicit
    subject codes are quoted, so nothing is inferred from the ID.
    """
    mapping = row.get(key) or {}
    records = []
    if not isinstance(mapping, dict):
        return records
    seen = set()
    for items in mapping.values():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            code = _value_text(item.get("subjCode"))
            if not code or code in seen:
                continue
            seen.add(code)
            evidence_id = "policy:estudent:%s:%s:%s" % (
                row.get("subjCode", "subject"), prefix, code)
            text = "%s %s %s" % (row.get("subjCode", "This subject"), prefix, code)
            year = _value_text(item.get("effAcadYear"))
            semester = _value_text(item.get("effAcadSemester"))
            if year and semester:
                text += ", effective from academic year %s semester %s" % (year, semester)
            elif year:
                text += ", effective from academic year %s" % year
            expiry = _value_text(item.get("expiryAcadYearSem"))
            if expiry and expiry != "9999-9":
                text += ", expiry academic year/semester %s" % expiry
            records.append(_evidence(
                evidence_id, text + ".",
                row, source_url, warnings, academic_year))
    return records


def _subject_evidence(row, source_url, warnings, academic_year):
    """Turn one subject detail record into atomic, quotable evidence."""
    code = row.get("subjCode") or "subject"
    records = []

    title = _en_title(row)
    if title:
        records.append(_evidence(
            "policy:estudent:%s:title" % code,
            'The eStudent title of %s is "%s".' % (code, _neutralise(title)),
            row, source_url, warnings, academic_year))

    credit = _value_text(row.get("subjCredit"))
    if credit:
        records.append(_evidence(
            "policy:estudent:%s:credit" % code,
            "%s carries %s credit%s." % (code, credit, "" if credit == "1" else "s"),
            row, source_url, warnings, academic_year))

    level = _value_text(row.get("subjLevel"))
    if level:
        records.append(_evidence(
            "policy:estudent:%s:level" % code,
            "The eStudent subject level of %s is %s." % (code, level),
            row, source_url, warnings, academic_year))

    natures = row.get("nature")
    if isinstance(natures, list):
        for nature in natures:
            label = _value_text(nature.get("description")) if isinstance(nature, dict) else _value_text(nature)
            if label:
                records.append(_evidence(
                    "policy:estudent:%s:nature:%s" % (code, re.sub(r"\W+", "-", label.lower()).strip("-")),
                    "The nature of %s is %s." % (code, label),
                    row, source_url, warnings, academic_year))

    medium = _value_text(row.get("mediumOfInstruction"))
    if medium:
        records.append(_evidence(
            "policy:estudent:%s:medium" % code,
            "The medium-of-instruction code of %s is %s." % (code, medium),
            row, source_url, warnings, academic_year))

    impl_year = _value_text(row.get("implYear"))
    if impl_year:
        records.append(_evidence(
            "policy:estudent:%s:implementation-year" % code,
            "The implementation academic year of %s in eStudent is %s." % (code, impl_year),
            row, source_url, warnings, academic_year))

    records += _constraint_rows(row, "preRequisitesConstraintMap", "requires",
                                source_url, warnings, academic_year)
    records += _constraint_rows(row, "coRequisitesConstraintMap", "co-requires",
                                source_url, warnings, academic_year)
    records += _constraint_rows(row, "exclusionConstraintMap", "excludes",
                                source_url, warnings, academic_year)

    departments = []
    for offer in row.get("subjectOfferDepts") or []:
        if not isinstance(offer, dict):
            continue
        org = offer.get("organizationUnit") or {}
        if not isinstance(org, dict):
            continue
        for name in org.get("orgUnitTitles") or []:
            if not isinstance(name, dict) or name.get("language") != _EN_TITLE:
                continue
            if name.get("titleType") not in ("NAME", None):
                continue  # skip ABBR and other aliases: one stable department fact
            if name.get("titleName"):
                departments.append(_neutralise(name["titleName"]))
    for department in dict.fromkeys(departments):
        records.append(_evidence(
            "policy:estudent:%s:department" % code,
            "%s is offered by %s." % (code, department),
            row, source_url, warnings, academic_year))

    synopsis = _value_text(row.get("synopsisUrl"))
    if synopsis:
        records.append(_evidence(
            "policy:estudent:%s:synopsis-url" % code,
            "The eStudent synopsis URL recorded for %s is %s." % (code, synopsis),
            row, source_url, warnings, academic_year))

    return records


def search(query, acad_year_sem=None, fetcher=None, max_candidates=_DEFAULT_MAX_CANDIDATES):
    """Search the public eStudent catalogue and return a Policy search dict.

    Args:
        query: subject code (e.g. ``COMP5926``) or title keyword (e.g. ``Metaverse``).
        acad_year_sem: optional eStudent academic-year/semester token (e.g. ``20261``).
        fetcher: optional callable ``(method, url, payload) -> dict`` for offline tests.
        max_candidates: maximum summaries to enrich with detail calls.

    Returns:
        ``{"status", "results", "year_filters", "limitations",
        "requires_subject_clarification", "requires_year_clarification"}``.

    Raises:
        ValueError: if query is empty/oversized or max_candidates < 1.
        OSError / HTTPError / ValueError: network failure in the search phase,
        for the Supervisor to record as a failed branch.
    """
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a nonempty string")
    query = query.strip()
    if len(query) > 200:
        raise ValueError("query must be at most 200 characters")
    if not isinstance(max_candidates, int) or max_candidates < 1:
        raise ValueError("max_candidates must be a positive integer")
    if acad_year_sem is not None and not isinstance(acad_year_sem, (str, int)):
        raise ValueError("acad_year_sem must be a string or integer")
    fetch = fetcher or _default_fetcher

    code_match = _SUBJECT_CODE.match(query)
    payload = {}
    if code_match:
        payload["subjCode"] = query.upper()
    else:
        payload["title"] = query
    if acad_year_sem is not None:
        payload["acadYearSem"] = str(acad_year_sem)

    search_response = fetch("POST", API_ROOT + SEARCH_PATH, payload) or {}
    summaries = search_response.get("value")
    if not isinstance(summaries, list):
        summaries = []
    summaries = [row for row in summaries if isinstance(row, dict)]

    year_filters = {"acadYearSem": str(acad_year_sem)} if acad_year_sem is not None else {}
    limitations = [
        "Source: Hong Kong PolyU eStudent public subject search; read-only catalogue data.",
        "Constraint records reflect what eStudent registers, not an official waiver or degree audit.",
        "Exam timetable, Canvas data and personal enrolment are outside this source.",
    ]
    requires_subject_clarification = False

    if code_match and len(summaries) > 1:
        summaries = [row for row in summaries
                     if str(row.get("subjCode", "")).upper() == query.upper()] or summaries[:1]

    if not summaries:
        return {
            "status": "no_results",
            "results": [],
            "year_filters": year_filters,
            "limitations": limitations + ["No subject matched the query."],
            "requires_subject_clarification": False,
            "requires_year_clarification": False,
        }

    if not code_match and len(summaries) > 1:
        requires_subject_clarification = True
        limitations.append(
            "Multiple subjects matched the title; only the first %d were included. "
            "Ask the user for a subject code." % max_candidates)

    used = summaries[:max_candidates]
    academic_year = str(acad_year_sem) if acad_year_sem is not None else None
    results = []
    failed_details = 0
    for summary in used:
        code = summary.get("subjCode") or "subject"
        subject_id = summary.get("id")
        detail = summary
        source_url = LISTING_URL + "&subjCode=" + urllib.parse.quote(str(code))
        if subject_id is not None:
            detail_url = API_ROOT + DETAIL_PATH.format(id=urllib.parse.quote(str(subject_id), safe=""))
            try:
                detail_response = fetch("GET", detail_url, None) or {}
                if isinstance(detail_response.get("value"), dict):
                    detail = detail_response["value"]
            except Exception:  # detail is optional; keep the summary evidence
                failed_details += 1
        results.extend(_subject_evidence(detail, source_url, [], academic_year))

    if failed_details:
        limitations.append(
            "%d subject detail request(s) failed; prerequisite/corequisite fields may be incomplete."
            % failed_details)

    # One compact marker per requested subject so a failed constraint check is
    # visible to the Answerer even when no constraint evidence was produced.
    for summary in used:
        code = summary.get("subjCode") or "subject"
        if not any(item["evidence_id"].startswith("policy:estudent:%s:" % code)
                   for item in results):
            results.append(_evidence(
                "policy:estudent:%s:no-structured-evidence" % code,
                "No structured subject fields were available for %s in eStudent." % code,
                summary, LISTING_URL + "&subjCode=" + urllib.parse.quote(str(code)),
                [], academic_year))

    return {
        "status": "candidates_found",
        "results": results,
        "year_filters": year_filters,
        "limitations": limitations,
        "requires_subject_clarification": requires_subject_clarification,
        "requires_year_clarification": False,
    }
