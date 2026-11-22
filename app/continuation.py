"""Resume a clarification with the original question, date and validated choices."""
import copy
import re


def resume_request(state, reply):
    question = state["question"]
    if state.get("kind") != "course":
        return question + "\n补充信息：" + reply.strip(), None
    options = state.get("options", [])
    selected = [option for option in options if reply.strip().casefold() in {
        option["value"].casefold(), option["label"].casefold()} or re.search(
            r"(?<![A-Za-z0-9])" + re.escape(option["value"]) + r"(?![A-Za-z0-9])", reply, re.I)]
    if len(selected) != 1:
        raise ValueError("请点击一门候选课程，或输入其中一个完整课程代码。")
    choice = selected[0]
    plan = copy.deepcopy(state["plan"])
    targets = choice.get("queries", [choice["query"]])
    plan["course_queries"] = list(dict.fromkeys(choice["value"] if q in targets else q for q in plan["course_queries"]))
    plan.get("schedule_scope", {}).pop("needs_clarification", None)
    return question, plan
