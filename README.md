# Answerer / Verifier 交接说明

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
