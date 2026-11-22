"""Resolve user programme names through maintained, authoritative API mappings."""
import json
from pathlib import Path
import re
import unicodedata
from difflib import SequenceMatcher

try:
    from opencc import OpenCC
    _CONVERTER = OpenCC("t2s")
except ImportError:
    _CONVERTER = None

_BASIC_SIMPLIFIED = str.maketrans({"學": "学", "碩": "硕", "術": "术", "項": "项", "課": "课", "程": "程"})


def _key(value):
    value = unicodedata.normalize("NFKC", value).casefold()
    value = _CONVERTER.convert(value) if _CONVERTER else value.translate(_BASIC_SIMPLIFIED)
    return re.sub(r"[\W_]+", "", value)


def _core(value):
    value = _key(value.split("[", 1)[0])
    value = re.sub(r"(?:项目|课程|专业)$", "", value)
    value = re.sub(r"(?:理学硕士|文学硕士|工学硕士|理学学士|工学学士|硕士|学士)$", "", value)
    value = re.sub(r"^(?:masterofsciencein|masterofartsin|masterofengineeringin|msc|meng|bsc|beng)", "", value)
    return value.replace("技术", "科技")


def _names(row):
    return [row["name"], row.get("programme_title", ""), row.get("programme_code", ""), *row.get("aliases", [])]


def _score(query, title):
    if not query or not title:
        return 0
    if query == title:
        return 1
    if min(len(query), len(title)) >= 3 and (query in title or title in query):
        return .88 + .1 * min(len(query), len(title)) / max(len(query), len(title))
    return SequenceMatcher(None, query, title).ratio() if min(len(query), len(title)) >= 4 else 0


class ProgrammeResolver:
    def __init__(self, path=None, records=None):
        if records is None:
            path = Path(path) if path else Path(__file__).with_name("programmes.json")
            records = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError("Programme mappings must be a JSON list")
        for row in records:
            if (not isinstance(row, dict) or not isinstance(row.get("name"), str)
                    or not row["name"].strip() or type(row.get("programme_id")) is not int
                    or row["programme_id"] <= 0 or not isinstance(row.get("aliases", []), list)
                    or not all(isinstance(a, str) and a.strip() for a in row.get("aliases", []))
                    or not isinstance(row.get("programme_code", ""), str)):
                raise ValueError("Each mapping needs name, positive programme_id, and optional code/aliases")
        self.records = records
        self._index = [(row, {_key(name) for name in _names(row) if name.strip()},
                        {_core(name) for name in _names(row) if name.strip() and not re.fullmatch(r"\d{5}(?:-[A-Za-z0-9]+)?", name)})
                       for row in records]

    def resolve(self, programme, *, acad_year=None):
        if not programme or not programme.strip():
            return {"status": "clarification_required", "missing": [
                "请告诉我你就读哪个项目（项目全称或项目代码），以便查询该项目的课程。"]}
        key = _key(programme)
        matches = [row for row, exact, _ in self._index if key in exact]
        method = "normalized_exact"
        if not matches and not re.fullmatch(r"\d{5}(?:-[A-Za-z0-9]+)?", programme.strip()):
            core = _core(programme)
            if len(core) < 3:
                return {"status": "clarification_required", "missing": ["项目名称过短，请补充项目全称或项目代码。"]}
            scores = [(row, max((_score(core, title) for title in names), default=0))
                      for row, _, names in self._index]
            best = max((score for _, score in scores), default=0)
            matches = [row for row, score in scores if score >= max(.78, best - .06)]
            method = "fuzzy"
        if not matches:
            return {"status": "configuration_required", "programme": programme,
                    "issues": [f"已收到项目“{programme}”，目前还无法查询该项目的课程信息，请联系维护者完善该项目支持。"],
                    "required_configuration": ["由维护者补充该项目名称/别名与 eStudent programmeId 的可靠映射"]}
        # Search results include future implementations. Match the name first,
        # then exclude versions not yet implemented for the requested academic year.
        # last_admission_year is NOT used: continuing students may still attend.
        if acad_year is not None:
            year = int(acad_year)
            matches = [row for row in matches if
                       (not str(row.get("implementation_year", "")).isdigit() or int(row["implementation_year"]) <= year)
                       and (not str(row.get("last_operation_year", "")).isdigit() or int(row["last_operation_year"]) >= year)]
            if not matches:
                return {"status": "clarification_required", "missing": ["已找到相近项目，但其实施年份与查询学年不符，请确认入学年份或项目分支。"]}
        ids = {row["programme_id"] for row in matches}
        if len(ids) > 1:
            names = list(dict.fromkeys(row["name"] for row in matches))
            return {"status": "clarification_required", "missing": [
                "找到多个相近项目，请补充项目代码、分支或入学年份：" + "、".join(names[:8])],
                    "candidates": names[:8]}
        return {"status": "resolved", "programme": matches[0]["name"],
                "programme_id": matches[0]["programme_id"], "match_method": method}
