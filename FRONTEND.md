# COMP5584 Group Project —— 多智能体校园信息助手（前端 + 测试）

5 号位的脚手架：前端 demo、共享接口契约、评测集种子。
**目标：不依赖其他人进度，明天就能录出可用的 demo 画面。**

## 目录

```
contracts.py              全组共享接口契约（Evidence / TaskPlan / RunContext / FinalAnswer）
app/streamlit_app.py      前端：左答案 + 右 agent trace
app/mock_engine.py        Mock 引擎（编造样例数据，跑通界面用）
app/real_engine.py        真实 pipeline 适配层（只改这一个 import）
eval/benchmark_seed.jsonl 21 条评测种子，6 类场景
.streamlit/config.toml    dark 主题
```

## 跑起来

```bash
pip install streamlit
streamlit run app/streamlit_app.py
```

默认走 mock，界面顶部会显示 `MOCK 数据` 警告——**录正式视频时务必切到真实引擎**，
否则演示的是编造内容。

三种引擎按优先级自动选择：

| 优先级 | 引擎 | 条件 | 界面标识 |
|---|---|---|---|
| 1 | `app/real_engine.py` | `graph/pipeline.py` 存在 | 真实 pipeline 已接入 |
| 2 | `app/demo_engine.py` | 能 import `policy_rag` | 真实检索（提取式答案） |
| 3 | `app/mock_engine.py` | 兜底 | MOCK 数据 |

用真实检索：

```bash
POLICY_RAG_HOME=/path/to/part1 streamlit run app/streamlit_app.py
```

跑评测（24 条，输出 `eval/results.md` 可直接贴进 slides）：

```bash
POLICY_RAG_HOME=/path/to/part1 python3 eval/run_eval.py
```

接真实 pipeline：`·jx` 交付 `graph/pipeline.py` 的
`run_pipeline(query, student) -> FinalAnswer` 之后，`app/real_engine.py` 会自动
检测到并切换，前端代码一行不用改。

## 契约要点（发群里让所有人看这段）

1. **agent 之间只传 `list[Evidence]`，不传自由文本总结。** 这一个决定同时解决三件事：
   Verifier 能逐条核验、答案能自动带引用、上下文不会随 agent 数量膨胀。
2. **每个 agent 只实现 `run(task, ctx) -> list[Evidence]`，不准自己调别的 agent。**
   图的边只有 2 号位能改。
3. **所有动作必须走 `ctx.emit(agent, kind, message, ...)`。** 前端 trace 面板直接消费
   这个日志——也就是说，你们按契约写，演示画面自动就有了，不用额外接线。
4. **冲突按 `AUTHORITY_PRIORITY` 裁决**：学则 > 培养方案 > 课程目录 > 官网 > 第三方。
   不要各 agent 自己判断。
5. **数字不要靠模型算。** 学分加总、GPA、时间冲突一律用工具函数，Verifier 只认工具结果。

## 前端已经做了的三个"非正常态"

答辩最容易被问的是"它不会答的时候怎么办"，所以这三种状态都做成了可见界面：

| 状态 | 触发条件 | 界面表现 |
|---|---|---|
| `clarify` | Planner 判定信息不足 | 反问卡片，不派发检索 |
| `refused` | 证据 0 条 | 明说没有依据 + 给出下一步路径 |
| 校验返工 | Verifier 打回 | trace 里红色高亮 + 定向返工事件 |

## 评测（5 号位的另一半工作）

`eval/benchmark_seed.jsonl` 目前 21 条，目标扩到 80 条。六类：
`single_hop` / `multi_hop` / `constraint_planning` / `comparison` / `ambiguous` / `unanswerable`。

**现在就攒，不要等系统做完。** 从组里能想到的真实问题写起，每条填：
`expect_status`（期望的状态码，`ambiguous` 类填 `clarify`、`unanswerable` 类填 `refused`）
和 `must_have`（必须命中的证据来源）。

跑评测时要出的四组消融（写进 Analysis 那 15%）：

| 配置 | 观察指标 |
|---|---|
| 单 agent ReAct 全工具 | 基线，证明多 agent 确实有提升 |
| 去掉 Verifier | 幻觉率、引用错误率 |
| 去掉 Router 全量派发 | 延迟、成本代价 |
| 自由文本 vs 结构化证据 | 冲突未消解率 |

指标：事实正确率、引用正确率、完整度、`clarify`/`refused` 判对率、端到端延迟、token 成本。

## 5 号位 4 天计划

- **11/19 晚**：把 `contracts.py` 发群里，请 ·jx 确认字段；跑通 mock 前端
- **11/20**：跟 1 号位（henry）对齐 `retrieve()` 的真实返回，把 `real_engine.py` 接上；
  评测集补到 40 条
- **11/21**：接真实 pipeline，跑通端到端；补到 80 条并开始记录结果
- **11/22**：跑四组消融、出图；配合 6 号位录屏（trace 侧栏是视频的核心画面）
- **11/23**：缓冲、README、贡献声明
