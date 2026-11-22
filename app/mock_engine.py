"""Mock 引擎：在真实 pipeline 接进来之前，让前端可以独立开发与演示。

只要满足 contracts.FinalAnswer 的返回结构，前端无需任何改动即可从 mock 切到
真实引擎（见 app/real_engine.py）。

注意：这里的数据全部是**编造的样例**，用于跑通界面与录 demo 脚本，
      不是真实校方信息。前端会显示 MOCK 标识。
"""

from __future__ import annotations

from contracts import (
    AgentName, Evidence, FinalAnswer, RunContext, StudentProfile, TaskPlan, SubTask, Usage,
)

IS_MOCK = True

# ---------------------------------------------------------------- 样例学生
STUDENTS: dict[str, StudentProfile] = {
    "23045678D": StudentProfile(
        student_id="23045678D",
        programme="BSc (Hons) in Computing",
        year=3,
        completed=["COMP1011: B+", "COMP2011: A-", "COMP2432: B", "COMP3423: A"],
        gpa=3.32,
    ),
    "24051122D": StudentProfile(
        student_id="24051122D",
        programme="BSc (Hons) in Enterprise Information Systems",
        year=2,
        completed=["COMP1011: C+", "COMP2011: B-", "MM2021: B"],
        gpa=2.78,
    ),
    "22039001D": StudentProfile(
        student_id="22039001D",
        programme="BEng (Hons) in Computer Engineering",
        year=4,
        completed=["COMP1011: A", "COMP2011: A", "COMP2432: A-", "COMP3423: A", "COMP4432: B+"],
        gpa=3.61,
    ),
}


def _ev(claim, source, quote, page, authority, conf, agent) -> Evidence:
    return Evidence(claim=claim, source_id=source, quote=quote, page=page,
                    authority=authority, confidence=conf, agent=agent)


# ---------------------------------------------------------------- 场景 A：多跳 + 返工
def _scenario_planning(ctx: RunContext) -> FinalAnswer:
    s = ctx.student
    ev = [
        _ev("COMP5584 的先修要求为 COMP3423 或 COMP4432（二者其一即可）",
            "subject_description_COMP5584.pdf",
            "Prerequisite: COMP3423 Artificial Intelligence OR COMP4432 Machine Learning",
            2, "course_catalogue", 0.94, AgentName.CURRICULUM),
        _ev("BSc Computing 毕业需完成 30 学分选修，其中至少 12 学分为 level-4 科目",
            "programme_requirement_2025.pdf",
            "Students are required to complete 30 credits of elective subjects, of which at least "
            "12 credits must be at Level 4.",
            7, "programme_requirement", 0.91, AgentName.CURRICULUM),
        _ev("重修科目的成绩以最新一次成绩计入 GPA，原成绩不保留",
            "academic_regulation.pdf",
            "Where a subject is repeated, the latest grade obtained shall be used in the "
            "computation of the GPA and the previous grade shall not be retained.",
            23, "regulation", 0.88, AgentName.POLICY),
        _ev("COMP5584 于 2025/26 Semester 2 开设，subject group 121 为周三 10:30-13:20",
            "subject_timetable_api",
            "Subject Group 121 | Week 1-13 | Wed | 10:30-13:20 | PQ303",
            None, "official_web", 0.86, AgentName.SCHEDULE),
        _ev("学生已完成 COMP3423（成绩 A），满足 COMP5584 的先修条件",
            "student_record_23045678D",
            "COMP3423 Artificial Intelligence — Grade A — 2024/25 S1",
            None, "official_web", 0.99, AgentName.CURRICULUM),
    ]

    ctx.emit(AgentName.SUPERVISOR, "delegate", "拆解为 3 个子任务，并行派发", latency_ms=420)
    ctx.emit(AgentName.PLANNER, "result", "先修校验 / 学分缺口 / 时间冲突 三条依赖链", latency_ms=610)
    ctx.emit(AgentName.CURRICULUM, "retrieve", "课程目录：COMP5584 先修与开课学期", 2, 780)
    ctx.emit(AgentName.POLICY, "retrieve", "学则检索：重修与成绩计算规则", 1, 640)
    ctx.emit(AgentName.SCHEDULE, "retrieve", "课表接口：subject group 121 时间地点", 1, 1120)
    ctx.emit(AgentName.ANSWERER, "answer", "生成答案草稿（3 条 claim）", latency_ms=1580)
    ctx.emit(AgentName.VERIFIER, "reject",
             "未通过：claim 2 缺少学分缺口证据；总学分由模型口算，未经工具复算", latency_ms=1260)
    ctx.emit(AgentName.SUPERVISOR, "retry", "定向返工 → curriculum（仅重查缺口，不回退全局）", latency_ms=180)
    ctx.emit(AgentName.CURRICULUM, "retrieve", "复算：已修 27 学分，缺口 3 学分（含 0 学分 level-4）", 1, 720)
    ctx.emit(AgentName.ANSWERER, "answer", "生成修订稿（4 条 claim，全部带引用）", latency_ms=1420)
    ctx.emit(AgentName.VERIFIER, "result", "通过：4/4 claim 有证据，算术经工具复算一致", latency_ms=1180)
    ctx.emit(AgentName.SUPERVISOR, "answer", "合并并输出最终答案", latency_ms=210)

    text = (
        f"**结论：可以选，但你目前的学分缺口和这门课无关，需要另做安排。**\n\n"
        f"**1. 先修条件已满足** — COMP5584 要求 COMP3423 或 COMP4432 二选一 [1]，"
        f"你的记录显示 COMP3423 已取得 A [5]。\n\n"
        f"**2. 毕业学分仍有缺口** — {s.programme} 要求 30 学分选修、其中 level-4 至少 12 学分 [2]；"
        f"你已修 27 学分，**缺口 3 学分，且 level-4 学分为 0**。"
        f"所以下学期建议优先选 level-4 科目，而不是继续堆 level-3。\n\n"
        f"**3. 时间不冲突** — COMP5584 在 Semester 2 开设，subject group 121 为周三 10:30–13:20，"
        f"地点 PQ303 [4]。\n\n"
        f"⚠️ **风险提示**：若你之前修过 COMP3423 并打算重修，按学则成绩以最新一次计入 GPA、"
        f"原成绩不保留 [3]。这一点建议向 programme leader 确认后再操作。\n\n"
        f"*（置信度 0.86｜4 条证据｜其中 2 条来自教务规章与培养方案）*"
    )
    return FinalAnswer(
        status="ok", text=text, evidence=ev, confidence=0.86,
        trace=ctx.trace,
        usage=Usage(latency_ms=9480, tokens=7240, cost_usd=0.031, agent_calls=9),
    )


# ---------------------------------------------------------------- 场景 B：需要澄清
def _scenario_clarify(ctx: RunContext) -> FinalAnswer:
    ctx.emit(AgentName.SUPERVISOR, "delegate", "识别到查询缺少定位信息", latency_ms=380)
    ctx.emit(AgentName.PLANNER, "result", "无法确定 subject group，标记 need_clarify", latency_ms=460)
    ctx.emit(AgentName.SUPERVISOR, "clarify", "发起澄清，暂不派发检索任务", latency_ms=120)
    q = ("要查考试安排，我需要知道你具体修的是哪一门、以及你的 subject group。"
         "同一个 subject 的不同 group 考试时间可能不同，用错 group 会给出错误的考期。")
    return FinalAnswer(
        status="clarify",
        text="这个问题还差一个关键信息，我先问清楚再查，避免给你错的考期。",
        confidence=0.0, trace=ctx.trace, clarify_question=q,
        usage=Usage(latency_ms=960, tokens=310, cost_usd=0.002, agent_calls=2),
    )


# ---------------------------------------------------------------- 场景 C：应拒答
def _scenario_refuse(ctx: RunContext) -> FinalAnswer:
    ctx.emit(AgentName.SUPERVISOR, "delegate", "派发至 policy + curriculum", latency_ms=400)
    ctx.emit(AgentName.POLICY, "retrieve", "学则检索：无命中", 0, 700)
    ctx.emit(AgentName.CURRICULUM, "retrieve", "课程目录检索：无该科目编号", 0, 560)
    ctx.emit(AgentName.VERIFIER, "reject", "证据为 0 条，禁止生成答案，转拒答", latency_ms=340)
    ctx.emit(AgentName.SUPERVISOR, "answer", "输出拒答 + 建议路径", latency_ms=150)
    text = ("**没有找到可靠依据，我不回答。**\n\n"
            "现有资料里（学则、培养方案、课程目录、课表接口）都没有与该问题相关的内容。"
            "按设计规则，0 条证据时不允许生成推测性答案。\n\n"
            "**你可以这样继续：**\n"
            "- 确认科目编号是否写错（例如 COMP5xxx 与 COMP55xx 是不同层级的科目）\n"
            "- 如果是新开设的科目，课程目录可能尚未更新，建议直接问所属学系\n"
            "- 涉及个人成绩与考期，可在 eStudent 自行核对")
    return FinalAnswer(
        status="refused", text=text, evidence=[], confidence=0.0, trace=ctx.trace,
        usage=Usage(latency_ms=2150, tokens=1420, cost_usd=0.006, agent_calls=4),
    )


# ---------------------------------------------------------------- 场景 D：快通道
def _scenario_simple(ctx: RunContext) -> FinalAnswer:
    ctx.emit(AgentName.SUPERVISOR, "delegate", "命中快通道：单跳事实查询，跳过 Planner", latency_ms=210)
    ctx.emit(AgentName.CURRICULUM, "retrieve", "课程目录：COMP5584 学分", 1, 480)
    ctx.emit(AgentName.SUPERVISOR, "answer", "直接返回，未经过 Verifier", latency_ms=90)
    ev = [_ev("COMP5584 为 3 学分科目", "subject_description_COMP5584.pdf",
              "Credit Value: 3", 1, "course_catalogue", 0.97, AgentName.CURRICULUM)]
    return FinalAnswer(
        status="ok", text="COMP5584 是 **3 学分**科目 [1]。",
        evidence=ev, confidence=0.97, trace=ctx.trace,
        usage=Usage(latency_ms=780, tokens=420, cost_usd=0.002, agent_calls=2),
    )


# ---------------------------------------------------------------- 路由
def _route(query: str) -> str:
    q = query.lower()
    if any(k in query for k in ("考试", "考期", "exam")):
        return "clarify"
    if any(k in query for k in ("能不能选", "能否选", "先修", "下学期选", "选课", "毕业")):
        return "planning"
    if any(k in query for k in ("学分", "credit")):
        return "simple"
    return "refuse"


def simulate(query: str, student: StudentProfile) -> FinalAnswer:
    """按查询内容返回一个贴合场景的 mock 结果，用于前端联调与 demo 排练。"""
    ctx = RunContext(query=query, student=student)
    kind = _route(query)
    if kind == "planning":
        ans = _scenario_planning(ctx)
        ans.plan = TaskPlan(subtasks=[
            SubTask("t1", AgentName.CURRICULUM, f"查 COMP5584 先修与 {student.programme} 学分要求"),
            SubTask("t2", AgentName.POLICY, "查重修与成绩计算规则"),
            SubTask("t3", AgentName.SCHEDULE, "查 COMP5584 下学期开课时间与地点"),
        ])
        return ans
    if kind == "clarify":
        return _scenario_clarify(ctx)
    if kind == "simple":
        return _scenario_simple(ctx)
    return _scenario_refuse(ctx)


DEMO_QUERIES = [
    "我下学期能不能选 COMP5584？",
    "我这学期考试是什么时候？",
    "COMP5584 有几个学分？",
    "COMP9999 的给分比例是多少？",
]
