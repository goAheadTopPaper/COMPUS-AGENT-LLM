# COMP5584 Agent 联调约定

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
    "text": "COMP5926 exam: 2026-11-23 14:00 Asia/Hong_Kong; room A101.",
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
