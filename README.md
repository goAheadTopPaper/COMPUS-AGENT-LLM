# 校园规章与课程查询 Agent

现已补齐 `SupervisorAgent`、`PolicyAgent` 和 `ScheduleAgent`，串联已有的 Answerer / Verifier。

```text
Supervisor → Policy（本地规章/课程说明）+ Schedule（eStudent课程及上课安排）
           → Answerer → Verifier → Supervisor → 最终回答 / 最多一次重试 / 澄清
```

Schedule 查询课程名称、学分、星期、上课时间、教室和适用周次。按用户课程代码或完整英文名称匹配；不会把规章中的课程说明当作当前上课安排。中文提问由 Supervisor 调用模型路由，并生成适合英文索引的检索子查询。最终回答和验证始终使用完整原问题。

## 运行完整流程

无需安装第三方 Python 包，使用 Python 3.10+。外部 Part 1 目录保持原样，默认读取本仓库同级的 `part1_handoff/`，不会重建或修改索引。

复制 `.env.example` 为 `.env`，填写模型接口配置。由维护者先配置下方的项目映射，然后运行：

```powershell
python -X utf8 -B main.py "我是某项目的学生，查询 COMP5584 的课程信息和上课地点" --acad-year 2026 --semester 1
```

用户说出自己所属项目后，Supervisor 提取其原文名称，Schedule 按已维护的名称、别名或项目代码映射找到内部 programmeId。未说明项目时返回 `clarification_required`，提示“请告诉我你就读哪个项目”。不能根据所查课程推断用户项目。已知用户项目可由调用方在 `context={"programme":"项目名称"}` 中随后续问题传入；命令行可使用 `--programme "项目名称"`。当前自述项目优先于之前的上下文。

默认读取 [programmes.json](programmes.json)，也可用 `PROGRAMME_MAP_PATH` 或 `--programme-map` 指定文件。该文件目前为空：Part 1 只有项目名称和公开项目代码，没有 eStudent 内部 ID。需要维护者提供可靠映射或项目列表接口，才能开启各项目的课程查询。映射格式如下（以下名称和 ID 均为虚构示意，不能直接作为真实配置）：

```json
[
  {"name":"测试计算硕士", "aliases":["MSc Test Computing"], "programme_code":"TEST01", "programme_id":111}
]
```

名称有歧义时追问全称或项目代码；名称已知但缺少映射时返回 `configuration_required` 及维护者所需数据，不调用课程接口，不让模型生成 ID。没有配置全局 programmeId；`--programme-id` 仅供维护者显式诊断使用。文档中的 9134 只是接口示例，没有绑定任何真实项目。2026-11-22 用它做过公开接口格式验证。

日期默认 UTC+8 今天，学年/学期按 `interface.md` 月份规则计算。模型会提取问题中的日期/学期；命令行显式参数优先。教学周按 `--semester-start YYYY-MM-DD`（学校教学第 1 周起始日）计算，或直接指定 `--week 12`。没有周历时保留所有周次、附带警告，不能将其表述为“当前周正在上课”。此计算不处理周历中的特殊停课/补课，需要准确周历支持。

可以手动选择分支，绕过模型路由（回答与核查仍使用模型）：

```powershell
python -X utf8 -B main.py "COMP5584 在哪里上课？" --branch schedule --course COMP5584 --programme "用户已说明的项目名称" --week 12
python -X utf8 -B main.py "COMP5926 的先修要求？" --branch policy --policy-query "What is the prerequisite for COMP5926?"
```

`python -X utf8 -B main.py --help` 查看学年、入学批次、Part 1 路径等参数。只有通过核查才返回 `answer`；缺参时返回 `missing`，检索失败时返回 `retrieval_failed`。规划失败、分支失败和验证失败都不会显示未批准草稿。重试最多一次，第二次生成会接收核查反馈；规章检索扩大候选数。

## 实际接口与待补数据

已实测的接口格式与原始 `interface.md` 有两处差异：

- 课程列表：`{"status":200,"size":20,"value":[...]}`；课程代码为 `subjCode`，名称为 `subjectTitles["UI_LANGUAGE||EN"]`，学分为 `subjCredit`。
- 上课安排：请求 `{"queries":[{"acadSemester":"1","acadYear":"2026","subjectId":41243}]}`；返回 `value` 为嵌套列表。`queries` 对象格式实测 HTTP 400，因此默认用数组。

同一分组内的所有安排会保留；只有整组安排相同时才去重，避免丢失 lecture/tutorial 或其他不同安排。星期和频率保留接口原值。返回的是项目下公开课程信息，不能当作个人已选课程确认。

仍需维护者补充：项目名称/别名与内部 programmeId 的可靠映射（或能返回映射的项目列表接口），以及教学周起算日或教学周历。普通用户只需说明自己的项目名称。模型调用还需本地 `LLM_ENDPOINT`、`LLM_MODEL`、`LLM_API_KEY`，密钥仅填写本地 `.env`。

接口单独诊断（无需模型）：

```powershell
python -X utf8 -B probe_api.py --programme-id 9134 --acad-year 2026 --semester 1 --subject-id 41243 --queries-as-list
```

输出样例保存到已忽略的 `.local/api_probe/`。示例 subjectId 41243 实际对应 AF5640，其他课程 ID 由课程列表自动解析，不需用户手动填写。

## 验证

```powershell
python -X utf8 -B -m unittest -v test_pipeline
python -X utf8 -B demo.py
python -X utf8 -B demo.py D:\LLM-AGENT\part1_handoff
```

30 项自动化测试覆盖项目自述提取、名称/别名/代码映射、缺项目追问、歧义、缺映射、上下文复用、项目变更，以及混合/单分支、失败不展示答案、重试、周次筛选、分组去重、真实接口结构等。测试中的模型输出和 HTTP 返回是固定样例；另已实测两个公开 API，并用真实 Part 1 数据验证 PolicyAgent 检索及文件哈希校验。尚未验证真实 LLM 的完整多 Agent 流程。

## 原有 Answerer / Verifier 接口

Supervisor 收集 Policy 和 Schedule 的结果，调用 Answerer 写出逐条带引文的草稿，再让 Verifier 独立核查。同一份证据同时传给两个 Agent。只有通过时才使用 Verifier 组装的答案及引用。要补证据、修草稿或向用户追问时，由 Supervisor 按返回状态决定下一步。

```python
from agents import collect_evidence, answer, verify

bundle = collect_evidence(policy_response, schedule_rows)
draft = answer(question, bundle, model)
report = verify(question, bundle, draft, model, policy_gate=verify_claims)
```

- `policy_response` 直接传 Part 1 的 `PolicyRetriever.search()` 完整字典。跳过 Policy 分支时传 `None`。
- `schedule_rows` 是列表。每条包含 `evidence_id`（以 `schedule:` 开头）、`text`（原始时间、课程、地点等实际可用字段）及 `citation`（至少有 `title`）。使用模拟数据时在来源标题中标明。没有数据时传空列表。
- `model(system, payload)` 是调用组内 LLM 并返回已解析 JSON 字典的函数。Answerer 和 Verifier 可共用一套模型服务，分别执行两次请求。Supervisor 应按项目已有方式处理网络、模型异常及重试。
- `verify_claims` 来自 `policy_rag.verify`。正式接入时传入它以核查原始文件哈希、引用和索引。省略时仅核对传入的证据，报告会标明 `supplied_evidence`。该工具校验引用真实性，语义判定由 Verifier 的模型调用完成。
- `passed` 提供可展示的 `answer` 和 `sources`。其他状态均为 `approved=False`。`rejected` 表示草稿有错误或验证输出无效，`insufficient_evidence` 表示现有材料无法回答全部问题，`clarification_required` 表示需要澄清范围，例如学年或入学批次。

运行 `python demo.py` 进行离线接口测试。运行 `python demo.py /path/to/extracted-part1` 可用真实 BM25 检索及原始文件校验。两种模式均使用固定模型输出测试流程。接入组内模型后应再实测语义验证效果。

## 真实模型测试

1. 复制 `.env.example` 为 `.env`（项目目录内已备好空白配置时直接编辑）。
2. 在本机填写 `LLM_ENDPOINT`（服务商完整 HTTPS 接口 URL）、`LLM_MODEL` 和 `LLM_API_KEY`。测试脚本使用支持 JSON object 响应格式及 Bearer 鉴权的 Chat Completions 兼容接口。自定义框架可直接传入自己的模型函数。
3. 运行 `python3 -B live_test.py`。输出三个用例的通过状态及服务商返回的 token 用量。此测试只发合成课表数据。

接口交付细节及联合验收见 [INTEGRATION.md](INTEGRATION.md)。上传 GitHub 时只提交模板，真实 `.env` 保留在本机。
