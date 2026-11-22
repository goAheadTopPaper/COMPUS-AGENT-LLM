# COMP5584 Agent 联调约定

## 已实现的调度入口

```python
from policy_agent import PolicyAgent
from schedule_agent import ScheduleAgent
from supervisor import SupervisorAgent

supervisor = SupervisorAgent(
    model,  # model(system, payload) -> parsed JSON dict
    policy_agent=PolicyAgent(r"D:\LLM-AGENT\part1_handoff"),
    schedule_agent=ScheduleAgent(),  # 默认读取 programmes.json 中维护的项目映射
)
report = supervisor.run("查询 COMP5584 的课程信息和上课地点", context={
    "programme": user_programme_name,  # 当前/之前由用户说明的项目，非根据课程推断
    "acad_year": "2026", "semester": "1", "week": 12,
})
```

Supervisor 的 `run()` 保留完整原问题，调用模型选择 policy/schedule 分支，并从用户自述中提取所属项目原文（附原文片段核对）。也可显式传入 `branches=["schedule"]`、`course_queries=["COMP5584"]`。context 中课程用 `programme`（用户已说明的名称/别名/代码）、`acad_year`、`semester`、`on_date`、`semester_start`、`week`；规章用 `programme_code`、`academic_year`（2026/27）、`admission_cohort` 及 Part 1 支持的其他过滤字段。

项目映射由 `ProgrammeResolver` 读取 `programmes.json`，每条需 name、programme_id，可选 aliases、programme_code。当前没有可靠内部 ID 对照，文件为空，需维护者补充映射或项目列表接口。不能把公开项目代码当内部 ID，也不能根据课程或模型知识猜 ID。未说明项目时追问“你就读哪个项目”；项目有歧义时要求全称/代码；缺映射时返回 `configuration_required`，不调用课程 API、不重试。调用方通过 context 复用之前用户说明的项目，当前自述优先。直接传 `programme_id` 仅保留为维护者/API 集成的显式低层覆盖；不再从环境设置全局 ID。有项目名称时必须通过其映射解析，避免套用旧项目 ID。

ScheduleAgent.search() 返回状态字典，`results` 为兼容原 Answerer 的证据列表；缺参返回 `clarification_required` + `missing`。Supervisor 对已请求分支失败保留状态，最多重试一次；全部检索成功后才调用 Answerer/Verifier。未匹配课程不能被模型忽略后批准，未经批准的草稿不返回给用户。

2026-11-22 公开接口实测：课程列表用 `subjCode` / `subjectTitles` / `subjCredit`，返回包在 `value`；批量上课安排请求必须使用 `queries: [query]`（对象格式返回 400），返回 `value: [[arrangement, ...]]`。Schedule 默认采用实测格式，`queries_as_list=False` 仅作其他版本兼容。原始 interface.md 保持原样。

Schedule 的范围为课程信息与上课安排，不查询考试安排或个人 Canvas 课表。`SEMESTER_START` 默认留空，由 UTC+8 当前日期与 `academic_calendar.json` 官方校历快照自动计算周次，2026/27 已覆盖，含春节停课周。显式 week 优先于手动起点，手动起点优先于校历；非教学期或校历未覆盖时保留全部周次并注明。query_scope 保留 week、teaching_status 及自动计算时的校历来源。相同安排的分组去重，不同安排和课程组成部分保留。未知返回结构会报错，不会被误认为“无课”。

适用 Python 3.10+。联调入口为三个普通 Python 函数。各模块可以用自己的 Agent 框架，跨模块交接统一使用可 JSON 序列化的字典和列表。同步 Supervisor 直接调用，异步 Supervisor 可在线程中调用同步模型适配器。

## 交付一：负责 Planner、Supervisor 或 Policy 的同学

- Planner 给 Supervisor 原始问题、要调用的分支和每条子查询。Supervisor 最终传给 Answerer 和 Verifier 的 `question` 必须是同一条完整用户问题。
- Policy 分支交付 Part 1 的完整 `PolicyRetriever.search()` 字典。保留 `results`、`status`、`year_filters`、`limitations` 和所有 `requires_*_clarification`。每条 evidence 保留原始 `evidence_id`、`text`、`citation.title`、来源链接、页码、学年和警告。ID 必须与索引一致。未调用该分支传 `None`，查无证据保留原始状态和空 `results`。
- Supervisor 负责调度、捕获检索或模型异常，以及决定是否重试。建议每题最多重试一次。若一个已请求的分支调用失败，保留失败状态并告知用户，再按需要重试。分支未调用、成功但为空、调用失败是三种情况。

## 交付二：负责 Schedule 的同学

返回列表。每条记录对应一项实际日程。ID 以 `schedule:` 开头，同一次查询中保持稳定。相同 ID 对应同一原始事件。示例使用模拟数据：

```json
[
  {
    "evidence_id": "schedule:mock-event-1",
    "text": "COMP5926 class: 2026-11-23 14:00 Asia/Hong_Kong; room A101.",
    "citation": {"title": "Mock schedule"},
    "course_code": "COMP5926",
    "start_at": "2026-11-23T14:00:00+08:00",
    "location": "A101",
    "warnings": ["Synthetic demo data"]
  }
]
```

`evidence_id`、`text`、`citation.title` 必填。已知的课程、日期、时间、时区和地点写入 `text`，以便逐字引用。结构化字段可一并保留。缺失字段省略或置为 `null`。真实数据可在 `citation.source_url` 提供适合展示的来源地址。仅提供当前用户已授权的查询结果，模型输入中不放 Canvas token 或个人资料。未调用或成功但无匹配传空列表，调用失败由 Supervisor 单独记录。

## 调用与验收

```python
from answer_verifier.agents import collect_evidence, answer, verify
from policy_rag.verify import verify_claims

bundle = collect_evidence(policy_response, schedule_rows)
draft = answer(question, bundle, model)
report = verify(question, bundle, draft, model, policy_gate=verify_claims)
```

`model(system, payload)` 是组内模型适配器，返回已解析的 JSON 对象。两个模块各自调用一次。打包目录作为仓库下的 `answer_verifier/` 使用。引用校验传入 Part 1 的 `verify_claims` 时，联调环境还需能访问原始资料和 SQLite 索引。

| Verifier 状态 | Supervisor 应如何处理 |
|---|---|
| `passed` 且 `approved=true` | 展示 `answer` 和按证据 ID 索引的 `sources` |
| `rejected` | 查看 `issues`，按失败原因决定是否重写或补查 |
| `insufficient_evidence` | 明确说明缺失信息，可使用报告中的 `unanswered` |
| `clarification_required` | 用 `clarification_flags` 或核查结果确定需要追问的条件 |

最低联合验收：规章单查、日程单查、混合查询、资料不足。混合查询检查两种引用均可展示。资料不足检查不会把未验证草稿展示为最终答案。针对时间错误再测一条「引文正确、草稿时间错误」的样例。
