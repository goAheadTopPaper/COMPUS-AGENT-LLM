# 从前端提问到 Agent 回答

当前实际链路：

```text
浏览器 → Streamlit 表单 → app/pipeline_engine.py
      → SupervisorAgent（模型规划）
      → PolicyAgent（本地规章）/ ScheduleAgent（eStudent 课程）
      → Answerer（模型生成草稿）→ Verifier（引用校验 + 模型核查）
      → FinalAnswer → 页面答案、来源和调用记录
```

Streamlit 同时承担前端和 Python 服务端，不需要另开 FastAPI、Node 或 npm 服务。

## 本次检查与修复

- 原前端调用已经不存在的 supervisor.run，导致 5 个测试模块无法导入。已恢复旧版调用兼容入口；当前前端、CLI 均使用 SupervisorAgent。
- 原前端固定只调用 policy，Schedule 永远不会执行。已改为模型按问题选择分支。
- 原前端读取 POLICY_RAG_HOME，CLI 使用 PART1_HANDOFF_PATH，而且仓库带了一份没有数据的 policy_rag。现前端支持两种路径变量（优先 PART1_HANDOFF_PATH），默认读取同级 part1_handoff；检索与文件校验均显式使用外部数据路径，避免模块缓存造成串用。
- 原界面在真实模式下仍默认给用户套用示例学生档案。现真实模式只使用用户填写或在问题中说明的项目；留空时按实际问题决定是否追问。
- 原有引用编号与卡片顺序可能不同，检索分数被显示成答案置信度，警告也没有显示。现按 sources 的顺序统一编号、展示来源警告，移除未经校准的置信度显示。
- 不再在配置失败时自动退回 Mock。真实模式显示配置缺项；Mock 必须手动选择，页面会标明演示数据。

## 1. 安装与启动环境（PowerShell）

在项目根目录运行：

```powershell
Set-Location D:\LLM-AGENT\COMPUS-AGENT-LLM
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

本机已创建 .venv 并安装前端依赖，可直接使用；其他机器需要上述安装步骤。直接调用虚拟环境里的 python，不必激活环境或修改 PowerShell 执行策略。

## 2. 填写模型配置

本机已生成空白 .env 模板。其他机器上若不存在，可复制 .env.example；不要覆盖已有配置。

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

必填：

```dotenv
LLM_ENDPOINT=你的完整HTTPS聊天补全接口地址
LLM_MODEL=你的模型名称
LLM_API_KEY=你的本地密钥
PART1_HANDOFF_PATH=D:/LLM-AGENT/part1_handoff
```

接口必须支持 Chat Completions 的 messages、Bearer 鉴权及 response_format: json_object，返回 choices[0].message.content 为 JSON 字符串。接口地址必须是完整的聊天补全 URL，不能只填域名。环境变量优先于 .env。不要在前端填写 API 密钥。

Part 1 目录应有 policy_rag/retrieve.py、data/policy_index.sqlite 和 files/。现有 D:/LLM-AGENT/part1_handoff 满足条件，不需重建索引。检索使用 BM25；中文问题由规划模型生成英文检索子查询。

## 3. 先测试模型与命令行

```powershell
.\.venv\Scripts\python.exe -X utf8 -B live_test.py
.\.venv\Scripts\python.exe -X utf8 -B main.py "What is the prerequisite for COMP5926?" --branch policy
```

第一条用合成课程数据检查模型 JSON 输出、正确回答、错误时间拦截及缺信息处理；第二条使用真实 Part 1 资料和真实模型。第二条通过时应有 status: passed、approved: true、answer 和 sources。

资料不足或需要澄清会返回非通过状态，这是正常状态；不应输出未经批准的草稿。

## 4. 启动前端

```powershell
.\.venv\Scripts\python.exe -m streamlit run app/streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

保持终端运行，用浏览器打开 http://127.0.0.1:8501。停止服务按 Ctrl+C。修改 .env 后重新提问即可读取新配置；依赖或代码变更后建议重启服务。

左侧保持“真实 Agent”。配置完整时显示真实调用链；不完整时会显示具体缺项。首次检索需要载入索引，多次模型调用也会产生等待。答案和调用记录在整次执行完成后展示，trace 的逐条播放是结果回放，不是实时模型流式输出。

## 5. 建议按顺序验收

| 输入/操作 | 检查结果 |
|---|---|
| What is the prerequisite for COMP5926? | 调用 Policy、Answerer 和 Verifier；通过后显示引用。核对来源为课程说明及其中的 COMP5925 先修要求 |
| What are the subject withdrawal rules in 2020/21? | 对未覆盖学年说明资料不足；不套用其他学年的规则 |
| 项目栏留空，问“COMP5584 在哪里上课？” | Schedule 直接全校检索课程代码及内部 ID，再查课表，不要求所属项目 |
| 填写尚未配置映射的真实项目，再问课程安排 | 明确提示该项目尚不支持查询；不能编造 ID 或课程安排 |
| 配好真实项目映射后，问“我读X项目，COMP5584 的课程信息、上课时间和教室是什么？” | Schedule 查询该项目的真实课程；按问题需要合并 Policy 资料；通过核查后展示答案及来源 |
| 手动选择“界面演示（Mock）” | 明确显示 MOCK 提示，仅检查界面展示，不计作真实 Agent 验收 |

“所属项目”可以在侧栏填写，也可以写在问题里；识别成功后前端会保存到当前会话供后续查询使用。需要换项目时重新填写或明确说明，清除时点击“清空项目和查询记录”。

需要澄清时，结果卡片下会显示实际课程候选按钮和“补充信息”输入框。例如 HCI 可能对应 COMP3423 / COMP5517，直接点击其中一门，或输入代码后点“继续查询”。程序会保留原问题和已解析日期，继续执行；不必重新输入整个问题。无效选项会保留原候选供重选，不会发起模型请求。其他范围/学年澄清也可在补充框回答，原问题与补充信息会一起交给规划器。之前的问答保留在“前面的对话”中。这是澄清续问功能，尚不等同于任意主题的通用多轮聊天。

课程名称支持中文简称和英文标题间的语义识别：例如“元宇宙经济”可以识别为 AF5640 / METAVERSE ECONOMICS AND ECOSYSTEMS。项目栏留空时使用全校课程清单；填写项目时才缩小范围。全校课程多，先生成英文检索词、筛出少量候选，再做语义识别，避免把整份清单都发送给模型。最终 ID 必须属于候选列表，并通过本学期实时接口核对；有多个合理候选时追问课程代码，不要求先说明项目。

## 6. 课程查询还缺的配置

全校课程查询无需项目映射。`subjects.discovered.json` 已提供 2026/27 第一学期的 2546 门公开课程；其他学期缺少对应清单时，会通过实时关键词检索寻找候选，也可由维护者运行 `python scripts/fetch_subjects.py --year-sem 20262` 更新清单。代码查询始终直接调用实时接口。

仅按项目筛选时需要项目映射：可将 PROGRAMME_MAP_PATH 指向已导出的 programmes.discovered.json。Part 1 的公开项目代码不是 eStudent 内部 programmeId，不能直接互换。

每条映射包含：name、programme_id，可选 aliases、programme_code。不要将 interface.md 的 9134 当作用户默认项目。普通用户只说明自己就读的项目名称，无须知道内部 ID。

`SEMESTER_START` 可以留空：程序根据 UTC+8 当前日期及内置的官方校历自动计算教学周。目前已覆盖 2026/27 学年；2026-11-23 为第 13 周，且正确处理春节停课周。手动填写仍可覆盖起点，CLI 的 `--week` 可直接覆盖周数。考试期、假期和未覆盖学年不虚构教学周，会显示提示并保留学期安排；新学年由维护者更新 `academic_calendar.json`。单日公假或临时停课需核对学校通知。

## 7. 自动化测试与实际验证范围

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -v
```

test_frontend.py 额外覆盖前端状态转换、引用编号、缺项目追问、缺映射拦截，以及 Streamlit 表单提交到 Supervisor 再渲染答案。固定模型和 HTTP 样例不代表真实模型语义质量。真实数据通路可以用上述命令行问题实测；live_test.py 和前端正式提问会调用模型并产生服务商用量。

本机当前模型配置为空，所以还不能宣称真实 LLM 端到端验收通过。完成配置后按第 3～5 步检查；若失败，先查看页面左侧配置缺项、返回状态和右侧调用记录。
