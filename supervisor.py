"""Supervisor scheduler: dispatch branches, run answer/verify, decide the next step.

Injected callables only: this module never imports a Policy/Schedule agent or
touches Canvas credentials. Compatible with the flat ``agents.py`` layout and
with the packaged ``answer_verifier.agents`` layout.
"""
import re

try:
    from answer_verifier.agents import answer, collect_evidence, verify
except ImportError:
    from agents import answer, collect_evidence, verify


_SECRET = re.compile(r"(?i)\b(bearer|token|api[_-]?key|password|secret)\b[^\s,;]*")
_MAX_RETRIES = 1


def _safe_error(exc):
    """Return a short exception description with credential-like tokens masked."""
    masked = _SECRET.sub(lambda m: m.group(1) + " [REDACTED]", str(exc))
    return {"type": type(exc).__name__, "message": masked[:200]}


def _branch_state(plan, name, runner):
    """Call one requested branch and return (value, state).

    A missing runner, an exception, or an empty result are distinct states; the
    first two are reported upstream without being turned into evidence.
    """
    if runner is None:
        return (None, {"state": "failed", "error": {"type": "MissingRunner",
                "message": "No runner supplied for requested branch"}})
    query = plan.get("sub_queries", {}).get(name, plan["question"])
    try:
        value = runner(query)
    except Exception as exc:  # branch failure is observable, never fatal to the query
        return (None, {"state": "failed", "error": _safe_error(exc)})
    rows = value.get("results", []) if name == "policy" and isinstance(value, dict) else value
    state = "empty" if not rows else "ok"
    return (value, {"state": state, "error": None})


def _dispatch(plan, policy_search, schedule_search, previous=None):
    """Run requested branches; unrequested branches keep an explicit not_called state.

    On a retry, branches that already returned are reused so a successful
    retrieval or schedule call is never repeated.
    """
    requested = plan.get("branches", ("policy", "schedule"))
    runners = {"policy": policy_search, "schedule": schedule_search}
    values, states = {}, {}
    for name in ("policy", "schedule"):
        if name not in requested:
            values[name] = None
            states[name] = {"state": "not_called", "error": None}
            continue
        if previous and previous[1][name]["state"] != "failed":
            values[name], states[name] = previous[0][name], previous[1][name]
            continue
        values[name], states[name] = _branch_state(plan, name, runners[name])
    return values, states


def _failed_notice(name, state):
    label = "规章检索" if name == "policy" else "日程查询"
    return "%s失败（%s），该分支证据未纳入本次回答" % (
        label, state["error"]["type"] if state.get("error") else "未知错误")


def _decision(report, states, attempts, notices):
    """Map a verifier report to a display-safe, JSON-serializable result."""
    status = report.get("status")
    result = {
        "status": status,
        "approved": bool(report.get("approved")),
        "attempts": attempts,
        "branches": states,
        "notices": notices,
        "issues": report.get("issues", []),
        "unanswered": report.get("unanswered", []),
        "clarification_flags": report.get("clarification_flags", []),
    }
    if report.get("provenance"):
        result["provenance"] = report["provenance"]
    if status == "passed" and result["approved"]:
        result["answer"] = report["answer"]
        result["sources"] = report["sources"]
    return result


def run(plan, model, policy_gate=None, policy_search=None, schedule_search=None,
        max_retries=_MAX_RETRIES):
    """Orchestrate one user question and return the Supervisor's decision.

    plan = {"question": str, "branches": [str], "sub_queries": {str: str}}
    policy_search(sub_query) -> complete Part 1 search() dict, or None if not requested
    schedule_search(sub_query) -> evidence list (IDs prefixed with ``schedule:``)
    model(system, payload) -> parsed JSON object (same adapter for answer and verify)
    policy_gate -> Part 1 verify_claims, optional

    The full original question is reused verbatim for both Answerer and
    Verifier. Successful `passed` results carry answer and sources; every other
    status is display-safe and never leaks the unverified draft.
    """
    question = plan.get("question")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("plan.question must be a nonempty string")
    if not callable(model):
        raise ValueError("model must be callable")
    retries = 0
    notices = []
    previous = None

    while True:
        values, states = _dispatch(plan, policy_search, schedule_search, previous)
        previous = (values, states)
        for name in ("policy", "schedule"):
            if states[name]["state"] == "failed":
                notice = _failed_notice(name, states[name])
                if notice not in notices:
                    notices.append(notice)
        policy_value = values["policy"] if values["policy"] is not None else {}
        try:
            bundle = collect_evidence(policy_value, values["schedule"] or [])
            draft = answer(question, bundle, model)
            report = verify(question, bundle, draft, model, policy_gate=policy_gate)
        except Exception as exc:
            if retries < max_retries:
                retries += 1
                continue
            return {"status": "model_error", "approved": False, "attempts": retries + 1,
                    "branches": states, "notices": notices,
                    "issues": [_safe_error(exc)]}

        if report.get("approved") or report.get("status") == "passed":
            return _decision(report, states, retries + 1, notices)
        retryable = (report.get("status") == "rejected" or
                     any(s["state"] == "failed" for s in states.values()))
        if retryable and retries < max_retries:
            retries += 1
            continue
        return _decision(report, states, retries + 1, notices)
