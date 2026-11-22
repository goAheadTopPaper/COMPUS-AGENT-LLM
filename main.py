"""CLI for the complete agent pipeline; configuration stays local."""
import argparse
import json
import os
from pathlib import Path

from live_test import load_model
from policy_agent import PolicyAgent
from programme_resolver import ProgrammeResolver
from schedule_agent import ScheduleAgent
from supervisor import SupervisorAgent


def main():
    parser = argparse.ArgumentParser(description="PolyU 规章和课程信息查询")
    parser.add_argument("question")
    parser.add_argument("--handoff", default=os.environ.get("PART1_HANDOFF_PATH"))
    parser.add_argument("--programme", help="用户已说明的项目全称、别名或项目代码")
    parser.add_argument("--programme-map", default=os.environ.get("PROGRAMME_MAP_PATH"), help="项目名称与内部 ID 的映射 JSON")
    parser.add_argument("--programme-id", type=int, help="维护者调试用显式 ID；普通用户通过项目名称识别")
    parser.add_argument("--acad-year", help="学年起始年，例如 2026")
    parser.add_argument("--semester", choices=["1", "2", "3"])
    parser.add_argument("--semester-start", default=os.environ.get("SEMESTER_START"), help="教学第1周起始日 YYYY-MM-DD")
    parser.add_argument("--on-date", help="查询日期 YYYY-MM-DD，默认 UTC+8 今天")
    parser.add_argument("--week", type=int, help="显式查询教学周，覆盖日期计算")
    parser.add_argument("--programme-code", help="规章检索用五位项目代码，与 programmeId 不同")
    parser.add_argument("--academic-year", help="规章适用学年，例如 2026/27")
    parser.add_argument("--admission-cohort")
    parser.add_argument("--branch", action="append", choices=["policy", "schedule"], help="可重复；省略时模型自动路由")
    parser.add_argument("--course", action="append", help="课程代码或完整名称，可重复")
    parser.add_argument("--policy-query", help="手动路由时可提供英文检索问题")
    parser.add_argument("--queries-as-object", action="store_true", help="仅兼容其他接口版本；实测默认使用 queries 数组")
    parser.add_argument("--no-retry", action="store_true")
    args = parser.parse_args()
    # Same .env file as live_test.py; environment variables take precedence.
    settings = {}
    env_path = Path(__file__).with_name(".env")
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and not name.lstrip().startswith("#"):
                settings[name.strip()] = value.strip()
    def setting(name, supplied):
        return supplied if supplied is not None else settings.get(name) or None
    model = load_model()
    handoff = setting("PART1_HANDOFF_PATH", args.handoff)
    # Lazy initialization keeps course-only queries independent of the local index.
    class LazyPolicy:
        agent = None

        def search(self, *a, **kw):
            if self.agent is None:
                self.agent = PolicyAgent(handoff)
            return self.agent.search(*a, **kw)

        def verify_claims(self, payload):
            return self.agent.verify_claims(payload)
    schedule = ScheduleAgent(programme_id=args.programme_id,
                             programme_resolver=ProgrammeResolver(setting("PROGRAMME_MAP_PATH", args.programme_map)),
                             semester_start=setting("SEMESTER_START", args.semester_start),
                             queries_as_list=not args.queries_as_object)
    context = {k: getattr(args, k) for k in ("programme", "acad_year", "semester", "on_date", "week", "programme_code",
                                            "academic_year", "admission_cohort", "policy_query")
               if getattr(args, k) is not None}
    report = SupervisorAgent(model, LazyPolicy(), schedule, 0 if args.no_retry else 1).run(
        args.question, context=context, branches=args.branch, course_queries=args.course)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["approved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
