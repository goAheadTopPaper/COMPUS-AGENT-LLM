"""Frontend adapter for the same SupervisorAgent used by the CLI."""
from __future__ import annotations

import json
import re
import time
from http.client import IncompleteRead
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from urllib.error import HTTPError

from agents import ANSWER_PROMPT, VERIFY_PROMPT
from contracts import AgentName, FinalAnswer, RunContext, StudentProfile, Usage
from app.retrieval_adapter import to_evidence
from app.settings import configuration_issues, read_settings
from live_test import NoRedirect
from programme_resolver import ProgrammeResolver
from schedule_agent import ScheduleAgent
from supervisor import SupervisorAgent, PLAN_PROMPT
from model_errors import ModelRequestError
from course_matcher import COURSE_MATCH_PROMPT, COURSE_SEARCH_PROMPT
from app.continuation import resume_request

HAS_PIPELINE = not configuration_issues()


def _model_factory(settings):
    endpoint = settings["LLM_ENDPOINT"]
    url = urlsplit(endpoint)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("LLM_ENDPOINT 必须是完整 HTTPS URL")
    opener = build_opener(NoRedirect())
    usage = {"tokens": 0, "calls": 0}

    def model(system, payload):
        body = {"model": settings["LLM_MODEL"], "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}
        request = Request(endpoint, data=json.dumps(body).encode(), headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + settings["LLM_API_KEY"]})
        usage["calls"] += 1
        try:
            with opener.open(request, timeout=40) as response:
                try:
                    raw = response.read()
                except IncompleteRead as exc:
                    raw = exc.partial
        except HTTPError as exc:
            raise ModelRequestError(exc.code) from None
        result = json.loads(raw)
        usage["tokens"] += int((result.get("usage") or {}).get("total_tokens") or 0)
        parsed = json.loads(result["choices"][0]["message"]["content"])
        if not isinstance(parsed, dict):
            raise ValueError("Model must return a JSON object")
        return parsed
    return model, usage


def _prettify(answer, sources):
    order = {eid: i + 1 for i, eid in enumerate(sources)}
    return re.sub(r"\[([^\]]+)\]", lambda m: f"[{order[m[1]]}]" if m[1] in order else m[0], answer)


def simulate(query: str, student: StudentProfile, *, model=None, policy_agent=None,
             schedule_agent=None, settings=None, continuation=None, clarification_reply=None) -> FinalAnswer:
    """Dependencies injectable for frontend-to-agent tests without paid requests."""
    settings = settings if settings is not None else read_settings()
    ctx = RunContext(query=query, student=student)
    usage = {"tokens": 0, "calls": 0}
    started = time.monotonic()
    captured = {}
    programme = student.programme.strip()
    options, next_state, plan_override = [], {}, None

    def finish(status, text, evidence=None, clarification=""):
        return FinalAnswer(status=status, text=text, evidence=evidence or [], trace=ctx.trace,
            clarify_question=clarification, programme=programme,
            clarification_options=options, continuation=next_state,
            usage=Usage(latency_ms=int((time.monotonic() - started) * 1000),
                        tokens=usage["tokens"], agent_calls=usage["calls"]))

    if continuation and clarification_reply is not None:
        options = continuation.get("options", [])
        next_state = continuation
        try:
            query, plan_override = resume_request(continuation, clarification_reply)
        except ValueError as exc:
            return finish("clarify", str(exc), clarification=str(exc))
        programme = continuation.get("programme", programme)
        ctx.query = query
        ctx.emit(AgentName.SUPERVISOR, "result", "已收到补充信息，继续原问题")
        options, next_state = [], {}

    if model is None:
        issues = configuration_issues(settings)
        if issues:
            return finish("failed", "配置尚未就绪：\n\n" + "\n".join("- " + x for x in issues))
        try:
            model, usage = _model_factory(settings)
        except Exception as exc:
            return finish("failed", f"模型配置无效（{type(exc).__name__}），请检查本地配置。")

    def traced_model(system, payload):
        agent = {PLAN_PROMPT: AgentName.SUPERVISOR, ANSWER_PROMPT: AgentName.ANSWERER,
                 COURSE_MATCH_PROMPT: AgentName.SCHEDULE,
                 COURSE_SEARCH_PROMPT: AgentName.SCHEDULE,
                 VERIFY_PROMPT: AgentName.VERIFIER}.get(system, AgentName.SUPERVISOR)
        message = "开始任务规划" if system == PLAN_PROMPT else "根据真实课程列表识别课程名称" if system == COURSE_MATCH_PROMPT else "生成全校课程检索关键词" if system == COURSE_SEARCH_PROMPT else "开始生成草稿" if system == ANSWER_PROMPT else "开始核查草稿"
        ctx.emit(agent, "delegate" if system == PLAN_PROMPT else "answer", message)
        captured.update(payload.get("evidence", {}))
        began = time.monotonic()
        result = model(system, payload)
        ctx.emit(agent, "result", "模型调用完成", latency_ms=int((time.monotonic() - began) * 1000))
        return result

    class TracedPolicy:
        inner = policy_agent

        def search(self, question, **filters):
            if self.inner is None:
                from policy_agent import PolicyAgent
                self.inner = PolicyAgent(settings["PART1_HANDOFF_PATH"])
            ctx.emit(AgentName.POLICY, "retrieve", "查询本地规章与课程说明")
            response = self.inner.search(question, **filters)
            ctx.emit(AgentName.POLICY, "result", response["status"], n_evidence=len(response.get("results", [])))
            return response

        def verify_claims(self, payload):
            return self.inner.verify_claims(payload)

    class TracedSchedule:
        inner = schedule_agent

        def search(self, courses, **scope):
            if self.inner is None:
                self.inner = ScheduleAgent(programme_resolver=ProgrammeResolver(settings["PROGRAMME_MAP_PATH"]) if scope.get("programme") else None,
                                           model=traced_model,
                                           semester_start=settings.get("SEMESTER_START") or None)
            ctx.emit(AgentName.SCHEDULE, "retrieve", "按项目查询课程" if scope.get("programme") else "直接查询全校课程与课表")
            response = self.inner.search(courses, **scope)
            ctx.emit(AgentName.SCHEDULE, "result", response["status"], n_evidence=len(response.get("results", [])))
            return response

    try:
        out = SupervisorAgent(traced_model, TracedPolicy(), TracedSchedule()).run(
            query, context={"programme": programme} if programme else {}, plan_override=plan_override)
    except Exception as exc:
        return finish("failed", f"查询失败（{type(exc).__name__}），请检查配置与服务连接。")
    programme = (out.get("plan") or {}).get("programme") or programme
    for attempt in out.get("attempts", [])[1:]:
        ctx.emit(AgentName.SUPERVISOR, "retry", f"已执行第 {attempt['attempt']} 次尝试")
    status = out["status"]
    if out.get("approved") and status == "passed":
        sources = out["sources"]
        evs = []
        for eid in sources:
            row = captured[eid]
            ev = to_evidence(row, agent=row["kind"], confidence=0.0)
            ev.source_id = row["citation"].get("source_url") or row["citation"]["title"]
            evs.append(ev)
        ctx.emit(AgentName.VERIFIER, "result", "全部声明通过核查")
        return finish("ok", _prettify(out["answer"], sources), evs)
    details = out.get("missing") or out.get("unanswered") or out.get("issues") or out.get("clarification_flags") or ["现有证据不足"]
    messages = {"requires_year_clarification": "请补充适用学年或入学年份。",
                "requires_programme_clarification": "请补充项目全称。",
                "requires_entry_term_clarification": "请说明一月还是九月入学。",
                "requires_admission_pathway_clarification": "请补充入学途径。"}
    text = "\n\n".join(messages.get(x, x) if isinstance(x, str) else json.dumps(x, ensure_ascii=False) for x in details)
    ctx.emit(AgentName.SUPERVISOR, "clarify" if status == "clarification_required" else "reject", text)
    if status == "clarification_required":
        options = out.get("clarification_options", [])
        next_state = {"question": query, "plan": out.get("plan", {}),
                      "kind": "course" if options else "free_text", "options": options,
                      "programme": programme}
        return finish("clarify", text, clarification=text)
    if status in {"failed", "retrieval_failed", "configuration_required"}:
        return finish("failed", text)
    return finish("refused", text)
