"""多智能体校园信息助手 —— 前端 Demo

运行：
    streamlit run app/streamlit_app.py

特点：
1. 左侧答案、右侧 agent trace，录 demo 时一屏就能看出"这真是多智能体"
2. 引擎可在 mock / 真实 pipeline 之间切换，前端不依赖后端进度
3. 三种非正常态（澄清 / 拒答 / 校验返工）都做成了可见的界面状态，
   这比"只能答对的聊天框"更能说明系统设计
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts import AgentName, FinalAnswer  # noqa: E402

st.set_page_config(page_title="Campus Agent Demo", layout="wide",
                   initial_sidebar_state="expanded")

# ---------------------------------------------------------------- 样式
AGENT_LABEL = {
    AgentName.SUPERVISOR: "Supervisor",
    AgentName.PLANNER: "Planner",
    AgentName.POLICY: "Policy",
    AgentName.SCHEDULE: "Schedule",
    AgentName.CURRICULUM: "Curriculum",
    AgentName.ANSWERER: "Answerer",
    AgentName.VERIFIER: "Verifier",
}
AGENT_COLOR = {
    AgentName.SUPERVISOR: ("#3C3489", "#CECBF6"),
    AgentName.PLANNER: ("#3C3489", "#CECBF6"),
    AgentName.CURRICULUM: ("#0C447C", "#B5D4F4"),
    AgentName.POLICY: ("#0F6E56", "#9FE1CB"),
    AgentName.SCHEDULE: ("#0F6E56", "#9FE1CB"),
    AgentName.ANSWERER: ("#854F0B", "#FAC775"),
    AgentName.VERIFIER: ("#3B6D11", "#C0DD97"),
}
KIND_LABEL = {
    "delegate": "派发", "retrieve": "检索", "result": "返回",
    "reject": "打回", "retry": "返工", "answer": "生成", "clarify": "澄清",
}

st.markdown("""
<style>
  .block-container {padding-top: 2.2rem; padding-bottom: 2rem; max-width: 1480px;}
  .panel {border: 1px solid rgba(255,255,255,0.10); border-radius: 12px;
          padding: 14px 16px; margin-bottom: 10px;}
  .cite {color: #85B7EB; font-size: 11px; font-weight: 500;}
  .badge {display:inline-block; padding:1px 8px; border-radius:999px;
          font-size:11px; font-weight:500; letter-spacing:.02em;}
  .trace-row {border-left: 2px solid rgba(255,255,255,0.14);
              padding: 6px 0 6px 12px; margin-bottom: 2px; font-size: 12.5px;}
  .trace-meta {color: rgba(255,255,255,0.45); font-size: 11px;}
  .src {font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11.5px;
        color: rgba(255,255,255,0.55);}
  .quote {border-left: 2px solid rgba(255,255,255,0.18); padding-left: 10px;
          color: rgba(255,255,255,0.72); font-size: 12.5px;}
</style>
""", unsafe_allow_html=True)


def _pick_engine():
    """优先级：真实 pipeline（DeepSeek）> 其他 pipeline > 真实检索 > mock。"""
    try:
        from app import pipeline_engine
        if pipeline_engine.HAS_PIPELINE:
            return pipeline_engine, "pipeline"
    except Exception:  # noqa: BLE001
        pass
    try:
        from app import real_engine
        if real_engine.HAS_REAL:
            return real_engine, "real"
    except Exception:  # noqa: BLE001
        pass
    try:
        from app import demo_engine
        if demo_engine.HAS_DATA:
            return demo_engine, "demo"
    except Exception:  # noqa: BLE001
        pass
    from app import mock_engine
    return mock_engine, "mock"


engine, mode = _pick_engine()

# 支持 ?q=...&anim=0 直接出结果：录屏与截图时不用手动点按钮
_qp = st.query_params.get("q")
_noanim = st.query_params.get("anim") == "0"

# ---------------------------------------------------------------- 侧栏
with st.sidebar:
    st.markdown("### 学生画像")
    if mode in ("mock", "demo", "pipeline"):
        from app.mock_engine import STUDENTS
    else:
        STUDENTS = {}  # 真实模式下由 pipeline 自己的数据源提供

    if STUDENTS:
        sid = st.selectbox("切换学生", list(STUDENTS), label_visibility="collapsed")
        stu = STUDENTS[sid]
        st.caption(f"{stu.programme}｜Year {stu.year}｜GPA {stu.gpa}")
        st.caption(f"已修 {len(stu.completed)} 门：" + "、".join(stu.completed_codes))
    else:
        stu = None

    st.divider()
    st.markdown("### 演示设置")
    animate = st.toggle("逐条播放 trace", value=not _noanim)
    speed = st.slider("播放速度", 0.0, 0.5, 0.16, 0.02, disabled=not animate)

    st.divider()
    st.markdown("### 引擎状态")
    if mode == "mock":
        st.warning("MOCK 数据\n\n答案内容为编造样例，非真实校方信息。", icon=None)
    elif mode == "demo":
        st.info("真实检索\n\n证据来自 Part 1 索引；答案为提取式拼装，未做生成改写。")
    elif mode == "pipeline":
        st.success("真实 pipeline\n\nSupervisor 调度 · DeepSeek 生成 · Verifier 校验")
    else:
        st.success("真实 pipeline 已接入")

    st.divider()
    st.caption("角色分工：1 数据检索 / 2 编排 / 3 Policy / 4 Answer+Verifier / 5 前端+测试 / 6 交付物")

# ---------------------------------------------------------------- 主区
st.markdown("#### Multi-Agent University Information Assistant")
st.caption("Supervisor 派发 · Policy / Schedule / Curriculum 并行检索 · Verifier 校验后输出")

if "history" not in st.session_state:
    st.session_state.history = []

DEMO_DEFAULT = [
    "What should I do if illness prevents me from attending an examination in 2026/27?",
    "What GPA triggers academic probation in 2026/27?",
    "What are the subject withdrawal rules in 2020/21?",
]
cols = st.columns(len(DEMO_DEFAULT) + 2)
clicked = None
for i, q in enumerate(DEMO_DEFAULT):
    if cols[i].button(q, use_container_width=True):
        clicked = q

with st.form("ask", clear_on_submit=False):
    c1, c2 = st.columns([6, 1])
    query = c1.text_input("提问", value=clicked or "", label_visibility="collapsed",
                          placeholder="例如：我下学期能不能选 COMP5584？")
    submitted = c2.form_submit_button("提问", use_container_width=True)

if clicked:
    query, submitted = clicked, True

if _qp and st.session_state.get("_qp_used") != _qp:
    st.session_state["_qp_used"] = _qp
    query, submitted = _qp, True

# ---------------------------------------------------------------- 渲染
def render_trace(ans: FinalAnswer, animate: bool, delay: float):
    st.markdown("##### Agent trace")
    n = len(ans.trace)
    st.caption(f"{n} 个事件｜{ans.usage.agent_calls} 次 agent 调用")
    for ev in ans.trace:
        bg, fg = AGENT_COLOR.get(ev.agent, ("#444441", "#D3D1C7"))
        kind = KIND_LABEL.get(ev.kind, ev.kind)
        accent = "#E24B4A" if ev.kind in ("reject",) else "#FAC775" if ev.kind == "retry" else "rgba(255,255,255,0.14)"
        st.markdown(
            f'<div class="trace-row" style="border-left-color:{accent}">'
            f'<span class="badge" style="background:{bg};color:{fg}">'
            f'{AGENT_LABEL.get(ev.agent, ev.agent)}</span> '
            f'<span class="trace-meta">{kind}｜+{ev.t} s'
            f'{"｜" + str(ev.latency_ms) + " ms" if ev.latency_ms else ""}'
            f'{"｜" + str(ev.n_evidence) + " 条证据" if ev.n_evidence else ""}</span><br>'
            f'{ev.message}</div>',
            unsafe_allow_html=True,
        )
        if animate:
            time.sleep(delay)


def render_answer(ans: FinalAnswer):
    badge = {"ok": ("#3B6D11", "#C0DD97", "已通过校验"),
             "clarify": ("#854F0B", "#FAC775", "需要澄清"),
             "refused": ("#444441", "#D3D1C7", "拒答"),
             "failed": ("#A32D2D", "#F7C1C1", "失败")}[ans.status]
    st.markdown(
        f'<span class="badge" style="background:{badge[0]};color:{badge[1]}">{badge[2]}</span>',
        unsafe_allow_html=True)
    st.write("")

    if ans.status == "clarify":
        st.info(ans.clarify_question or ans.text)
        return

    html = ans.text
    for tag, (i, _e) in ans.citation_index().items():
        html = html.replace(tag, f'<span class="cite">{tag}</span>')
    st.markdown(html, unsafe_allow_html=True)

    if ans.status == "ok":
        c1, c2 = st.columns([3, 1])
        c1.progress(min(ans.confidence, 1.0), text=f"答案置信度 {ans.confidence:.2f}")
        c2.caption(f"证据 {len(ans.evidence)} 条")

    if ans.evidence:
        st.markdown("##### 证据链")
        for tag, (i, e) in ans.citation_index().items():
            with st.expander(f"{tag}  {e.claim[:46]}{'…' if len(e.claim) > 46 else ''}"):
                st.markdown(f'<div class="src">{e.citation}｜{e.authority}｜'
                            f'置信度 {e.confidence:.2f}｜产出 {AGENT_LABEL.get(e.agent, e.agent)}</div>',
                            unsafe_allow_html=True)
                st.markdown(f'<div class="quote">{e.quote}</div>', unsafe_allow_html=True)


if submitted and query.strip() and stu is not None:
    with st.spinner("agent 协作中…"):
        ans = engine.simulate(query.strip(), stu)
    st.session_state.history.insert(0, (query.strip(), ans))

if not st.session_state.history:
    st.info("在右上角输入问题，或点上面的示例问题开始。")
else:
    q, ans = st.session_state.history[0]
    st.divider()
    st.markdown(f"**问：{q}**")
    left, right = st.columns([1.45, 1], gap="large")
    with left:
        render_answer(ans)
    with right:
        render_trace(ans, animate and len(st.session_state.history) == 1, speed)

    m1, m2, m3, m4 = st.columns(4)
    lat = ans.usage.latency_ms
    m1.metric("端到端延迟", f"{lat / 1000:.1f} s" if lat >= 1000 else f"{lat} ms")
    m2.metric("agent 调用", ans.usage.agent_calls)
    m3.metric("token", f"{ans.usage.tokens:,}" if ans.usage.tokens else "—")
    m4.metric("估算成本", f"${ans.usage.cost_usd:.3f}" if ans.usage.cost_usd else "—")
