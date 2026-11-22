"""COMP5584 Group Project —— 多智能体共享接口契约

全组只允许通过本文件中的类型通信。
硬规则：agent 之间传 Evidence 列表，不允许传自由文本总结。

Owner: 你(5) + ·jx(2) 共同维护。任何字段变更必须在群里同步。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal, Protocol

# --------------------------------------------------------------------------
# 权威优先级：冲突时按此顺序裁决，写在常量里，不要各 agent 自己判断
# --------------------------------------------------------------------------
AUTHORITY_PRIORITY: list[str] = [
    "regulation",             # 学则、教务规章
    "programme_requirement",  # 培养方案 / programme requirement document
    "course_catalogue",       # subject description form
    "official_web",           # 官网页面、FAQ、课表接口
    "third_party",            # 论坛、二手信息（仅供兜底，不进主答案）
]

Status = Literal["ok", "clarify", "refused", "failed"]


# --------------------------------------------------------------------------
# 证据：系统中唯一的信息载体
# --------------------------------------------------------------------------
@dataclass
class Evidence:
    claim: str                      # 一句可独立核验的事实陈述
    source_id: str                  # 文件名或接口标识，如 "academic_regulation_2025.pdf"
    quote: str                      # 支撑该 claim 的原文片段
    page: int | None = None         # PDF 页码，接口数据填 None
    authority: str = "official_web"  # 必须取自 AUTHORITY_PRIORITY
    confidence: float = 0.0         # 0~1，检索置信度（必须是概率，不是 BM25 原始分）
    agent: str = ""                 # 产出该证据的 agent 名
    # v1.1 新增：衔接 henry 的 Part 1 返回结构
    evidence_id: str = ""           # retriever 的 evidence_id，Verifier 复核/取相邻段落用
    title: str = ""                 # 文档标题，前端引用卡片显示
    section: str = ""               # 章节，如 "5. Subject Registration / C. Retaking"
    warnings: list[str] = field(default_factory=list)  # 年份/适用性警告，必须透传到答案

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def rank(self) -> int:
        return AUTHORITY_PRIORITY.index(self.authority) if self.authority in AUTHORITY_PRIORITY else 99

    @property
    def citation(self) -> str:
        """人类可读的引用标签，前端直接展示。"""
        tail = f" p.{self.page}" if self.page else ""
        return f"{self.source_id}{tail}"


def sort_by_authority(evidence: list[Evidence]) -> list[Evidence]:
    """冲突消解用：高权威在前，同权威按置信度降序。"""
    return sorted(evidence, key=lambda e: (e.rank, -e.confidence))


# --------------------------------------------------------------------------
# 任务分解
# --------------------------------------------------------------------------
@dataclass
class SubTask:
    id: str
    agent: str                      # 目标 agent 名，见 AgentName
    query: str                      # 交给该 agent 的子问题，要自包含
    depends_on: list[str] = field(default_factory=list)  # 依赖的 subtask id


@dataclass
class TaskPlan:
    subtasks: list[SubTask] = field(default_factory=list)
    need_clarify: bool = False
    clarify_question: str = ""      # need_clarify 时必填，交给前端展示


# --------------------------------------------------------------------------
# 学生画像：个性化规划的输入，前端可切换
# --------------------------------------------------------------------------
@dataclass
class StudentProfile:
    student_id: str
    programme: str
    year: int
    completed: list[str] = field(default_factory=list)   # "COMP1011: A-" 形式
    gpa: float = 0.0

    @property
    def completed_codes(self) -> list[str]:
        return [c.split(":")[0].strip().upper() for c in self.completed]


# --------------------------------------------------------------------------
# 运行上下文 = 共享黑板 + 追踪日志
# 所有 agent 必须通过 ctx.emit() 上报动作，前端 trace 面板直接消费
# --------------------------------------------------------------------------
@dataclass
class TraceEvent:
    t: float                        # 相对开始的秒数
    agent: str
    kind: str                       # delegate | retrieve | result | reject | retry | answer | clarify
    message: str
    n_evidence: int = 0
    latency_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RunContext:
    query: str
    student: StudentProfile
    board: list[Evidence] = field(default_factory=list)   # 共享证据黑板
    trace: list[TraceEvent] = field(default_factory=list)
    _t0: float = field(default_factory=__import__("time").time)

    def emit(self, agent: str, kind: str, message: str,
             n_evidence: int = 0, latency_ms: int = 0) -> None:
        import time
        self.trace.append(TraceEvent(
            t=round(time.time() - self._t0, 2),
            agent=agent, kind=kind, message=message,
            n_evidence=n_evidence, latency_ms=latency_ms,
        ))

    def add(self, evidence: list[Evidence]) -> None:
        self.board.extend(evidence)


# --------------------------------------------------------------------------
# 最终答案
# --------------------------------------------------------------------------
@dataclass
class Usage:
    latency_ms: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    agent_calls: int = 0


@dataclass
class FinalAnswer:
    status: Status
    text: str                                      # 支持 [1] [2] 引用标记
    evidence: list[Evidence] = field(default_factory=list)
    confidence: float = 0.0
    trace: list[TraceEvent] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    plan: TaskPlan | None = None
    clarify_question: str = ""
    programme: str = ""             # 用户自述项目，可由前端在后续查询复用
    clarification_options: list[dict] = field(default_factory=list)
    continuation: dict = field(default_factory=dict)

    def citation_index(self) -> dict[str, tuple[int, Evidence]]:
        """把 evidence 映射成 [1] -> (1, Evidence)，前端渲染引用卡片用。"""
        return {f"[{i + 1}]": (i + 1, e) for i, e in enumerate(self.evidence)}

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "text": self.text,
            "evidence": [e.to_dict() for e in self.evidence],
            "confidence": self.confidence,
            "trace": [t.to_dict() for t in self.trace],
            "usage": asdict(self.usage),
            "clarify_question": self.clarify_question,
            "programme": self.programme,
            "clarification_options": self.clarification_options,
            "continuation": self.continuation,
        }


# --------------------------------------------------------------------------
# 每个 agent 必须实现的接口（2 号位编排层按此调度）
# --------------------------------------------------------------------------
class Agent(Protocol):
    name: str

    def run(self, task: SubTask, ctx: RunContext) -> list[Evidence]:
        ...


# --------------------------------------------------------------------------
# agent 名字常量，避免各处手写字符串写错
# --------------------------------------------------------------------------
class AgentName:
    SUPERVISOR = "supervisor"
    PLANNER = "planner"
    POLICY = "policy"
    SCHEDULE = "schedule"
    CURRICULUM = "curriculum"
    ANSWERER = "answerer"
    VERIFIER = "verifier"
