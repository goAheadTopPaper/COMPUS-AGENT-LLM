"""Resolve user programme names through maintained, authoritative API mappings."""
import json
from pathlib import Path
import re
import unicodedata


def _key(value):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", value).casefold())


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

    def resolve(self, programme):
        if not programme or not programme.strip():
            return {"status": "clarification_required", "missing": [
                "请告诉我你就读哪个项目（项目全称或项目代码），以便查询该项目的课程。"]}
        key = _key(programme)
        matches = [row for row in self.records if key in {
            _key(name) for name in [row["name"], row.get("programme_code", ""), *row.get("aliases", [])]
            if name.strip()}]
        if not matches:
            return {"status": "configuration_required", "programme": programme,
                    "issues": [f"已收到项目“{programme}”，目前还无法查询该项目的课程信息，请联系维护者完善该项目支持。"],
                    "required_configuration": ["由维护者补充该项目名称/别名与 eStudent programmeId 的可靠映射"]}
        ids = {row["programme_id"] for row in matches}
        if len(ids) > 1:
            names = list(dict.fromkeys(row["name"] for row in matches))
            return {"status": "clarification_required", "missing": [
                "该项目名称对应多个项目，请补充项目全称或项目代码：" + "、".join(names)]}
        return {"status": "resolved", "programme": matches[0]["name"],
                "programme_id": matches[0]["programme_id"]}
