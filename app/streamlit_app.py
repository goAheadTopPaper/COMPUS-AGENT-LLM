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
from html import escape
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
  /* 录屏时不需要 Streamlit 自带的工具栏与 Deploy 按钮 */
  [data-testid="stToolbar"] {display: none;}
  [data-testid="stDecoration"] {display: none;}
  [data-testid="stStatusWidget"] {display: none;}
  #MainMenu {visibility: hidden;}
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
    selected = st.sidebar.selectbox("运行模式", ["真实 Agent", "界面演示（Mock）"])
    if selected == "界面演示（Mock）":
        from app import mock_engine
        return mock_engine, "mock"
    from app import pipeline_engine
    return pipeline_engine, "pipeline"


engine, mode = _pick_engine()
if st.session_state.pop("_clear_programme", False):
    st.session_state.programme_input = ""
if "_sync_programme" in st.session_state:
    st.session_state.programme_input = st.session_state.pop("_sync_programme")
if st.session_state.get("_engine_mode") != mode:
    st.session_state.history = []
    st.session_state.pop("_continuation_request", None)
    st.session_state["_engine_mode"] = mode

current_settings = None
configuration_changed = False
if mode == "pipeline":
    from app.settings import read_settings, configuration_signature
    current_settings = read_settings()
    signature = configuration_signature(current_settings)
    if st.session_state.get("_config_signature") != signature:
        configuration_changed = bool(st.session_state.get("history"))
        st.session_state.history = []
        st.session_state.pop("_continuation_request", None)
        st.session_state["_config_signature"] = signature

# 支持 ?q=...&anim=0 直接出结果：录屏与截图时不用手动点按钮
_qp = st.query_params.get("q")
_noanim = st.query_params.get("anim") == "0"

# ---------------------------------------------------------------- 侧栏
with st.sidebar:
    st.markdown("### 学生画像")
    if mode == "mock":
        from app.mock_engine import STUDENTS
    else:
        STUDENTS = {}  # 真实模式下由 pipeline 自己的数据源提供

    if STUDENTS:
        sid = st.selectbox("切换学生", list(STUDENTS), label_visibility="collapsed")
        stu = STUDENTS[sid]
        st.caption(f"{stu.programme}｜Year {stu.year}｜GPA {stu.gpa}")
        st.caption(f"已修 {len(stu.completed)} 门：" + "、".join(stu.completed_codes))
        st.caption("（示范用档案，未接入真实学籍系统）")
    else:
        from contracts import StudentProfile
        programme = st.text_input("所属项目（可留空）", key="programme_input",
                                  help="留空可直接查询全校课程；填写项目可缩小课程范围。")
        known = programme.strip() or st.session_state.get("known_programme", "")
        if known:
            st.caption("当前项目：" + known)
        stu = StudentProfile(student_id="", programme=known, year=0)
        if st.button("清空项目和查询记录"):
            st.session_state.pop("known_programme", None)
            st.session_state.history = []
            st.session_state.pop("_continuation_request", None)
            st.session_state["_clear_programme"] = True
            st.rerun()

    st.divider()
    st.markdown("### 演示设置")
    animate = st.toggle("逐条播放 trace", value=not _noanim)

    st.divider()
    st.markdown("### 引擎状态")
    if mode == "mock":
        st.warning("MOCK 数据\n\n答案内容为编造样例，非真实校方信息。", icon=None)
    elif mode == "demo":
        st.info("真实检索\n\n证据来自 Part 1 索引；答案为提取式拼装，未做生成改写。")
    elif mode == "pipeline":
        from app.settings import configuration_issues
        problems = configuration_issues(current_settings)
        if problems:
            st.error("真实 Agent 配置未就绪")
            for problem in problems:
                st.caption(problem)
        else:
            st.success("真实 Agent\n\nSupervisor → Policy / Schedule → Answerer → Verifier")
    else:
        st.success("真实 pipeline 已接入")

# ---------------------------------------------------------------- 主区
st.markdown("#### Multi-Agent University Information Assistant")
st.caption("Supervisor 派发 · Policy 检索 · Answerer 起草 · Verifier 核验后输出")
if configuration_changed:
    st.info("配置已更新，已清除旧查询结果，请重新提问。")

if "history" not in st.session_state:
    st.session_state.history = []

DEMO_DEFAULT = [
    "What should I do if illness prevents me from attending an examination in 2026/27?",
    "What GPA triggers academic probation in 2026/27?",
    "What are the subject withdrawal rules in 2020/21?",
]

clicked = None
st.caption("示例问题")
for _q in DEMO_DEFAULT:
    if st.button(_q, use_container_width=True, key=f"demo::{_q}"):
        clicked = _q

with st.form("ask", clear_on_submit=False):
    c1, c2 = st.columns([6, 1])
    query = c1.text_input("提问", value=clicked or "", label_visibility="collapsed",
                          placeholder="输入规章或课程问题，例如：COMP5584 在哪里上课？")
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
            f'{escape(ev.message)}</div>',
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
        if mode == "pipeline" and ans.continuation:
            st.caption("选择课程或补充信息后，会继续回答原问题，无需重新输入。")
            for i, option in enumerate(ans.clarification_options):
                if st.button(option["label"], key=f"clarify-choice:{len(st.session_state.history)}:{i}", use_container_width=True):
                    st.session_state["_continuation_request"] = {"state": ans.continuation, "reply": option["value"]}
                    st.rerun()
            with st.form(f"clarify-form:{len(st.session_state.history)}"):
                reply = st.text_input("补充信息", placeholder="例如：COMP5517，或补充所需的学年、范围")
                continue_clicked = st.form_submit_button("继续查询")
            if continue_clicked and reply.strip():
                st.session_state["_continuation_request"] = {"state": ans.continuation, "reply": reply.strip()}
                st.rerun()
        return

    st.markdown(ans.text)

    if ans.status == "ok":
        c1, c2 = st.columns([3, 1])
        c1.caption("已通过引用与语义核查；未提供校准后的正确率。")
        c2.caption(f"证据 {len(ans.evidence)} 条")

    if ans.evidence:
        st.markdown("##### 证据链")
        for tag, (i, e) in ans.citation_index().items():
            with st.expander(f"{tag}  {e.claim[:46]}{'…' if len(e.claim) > 46 else ''}"):
                st.caption(f"{e.title or e.citation}｜{e.authority}｜产出 {AGENT_LABEL.get(e.agent, e.agent)}")
                if e.source_id.startswith("https://"):
                    st.link_button("打开来源", e.source_id)
                st.text(e.quote)
                for warning in e.warnings:
                    st.warning(warning)


continuation_request = st.session_state.pop("_continuation_request", None)
if continuation_request:
    query = continuation_request["state"]["question"]
    submitted = True

if submitted and query.strip() and stu is not None:
    with st.spinner("agent 协作中…"):
        extra = {"continuation": continuation_request["state"], "clarification_reply": continuation_request["reply"]} if continuation_request else {}
        ans = engine.simulate(query.strip(), stu, settings=current_settings, **extra) if mode == "pipeline" else engine.simulate(query.strip(), stu)
    display_query = query.strip() + ("\n\n补充：" + continuation_request["reply"] if continuation_request else "")
    st.session_state.history.insert(0, (display_query, ans))
    if ans.programme:
        st.session_state.known_programme = ans.programme
        st.session_state["_sync_programme"] = ans.programme

if not st.session_state.history:
    st.caption("点上面的示例问题，或在上方输入框提问。答案、证据链与 agent 调度记录会同时出现。")
else:
    q, ans = st.session_state.history[0]
    if len(st.session_state.history) > 1:
        with st.expander("前面的对话"):
            for previous_query, previous_answer in reversed(st.session_state.history[1:]):
                st.markdown("**你：** " + previous_query)
                st.markdown("**助手：** " + previous_answer.text)
    st.divider()
    st.markdown(f"**问：{q}**")

    # 指标放在结果区顶部：录屏时一屏就能看到，不必滚动到底部
    m1, m2, m3, m4 = st.columns(4)
    lat = ans.usage.latency_ms
    m1.metric("端到端延迟", f"{lat / 1000:.1f} s" if lat >= 1000 else f"{lat} ms")
    m2.metric("agent 调用", ans.usage.agent_calls)
    m3.metric("token", f"{ans.usage.tokens:,}" if ans.usage.tokens else "—")
    m4.metric("估算成本", f"${ans.usage.cost_usd:.3f}" if ans.usage.cost_usd else "—")

    left, right = st.columns([1.45, 1], gap="large")
    with left:
        render_answer(ans)
    with right:
        render_trace(ans, animate and len(st.session_state.history) == 1, 0.16)
