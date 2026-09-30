"""人在回路的待决问题。

主设计模型调用 request_user_decision 后，agent loop 会中断并把 PendingDecision
落到会话；用户答复后从中断点恢复消息栈续接，而不是重头再来。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class DecisionKind(str, Enum):
    CLARIFY = "clarify"
    SCHEME_CHOICE = "scheme_choice"
    GATE_APPROVAL = "gate_approval"
    REWORK_PATH = "rework_path"


class DecisionOption(BaseModel):
    label: str
    value: str = ""
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    applicability: str = ""


class PendingDecision(BaseModel):
    decision_id: str
    kind: DecisionKind = DecisionKind.CLARIFY
    question: str
    context: str = ""
    options: list[DecisionOption] = Field(default_factory=list)
    recommended_index: int | None = None
    reasoning: str = ""
    gate: str = ""
    stage: str = ""
    asked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # 中断时保存的消息栈，用户答复后据此恢复
    suspended_messages: list[dict] = Field(default_factory=list)
    suspended_tool_call_id: str = ""

    def render_for_user(self) -> str:
        lines = [self.question]
        if self.context:
            lines.append(f"\n{self.context}")
        if self.options:
            lines.append("")
            for idx, opt in enumerate(self.options, start=1):
                mark = " ← 推荐" if self.recommended_index == idx - 1 else ""
                lines.append(f"{idx}. {opt.label}{mark}")
                if opt.pros:
                    lines.append(f"   优点：{'；'.join(opt.pros)}")
                if opt.cons:
                    lines.append(f"   缺点：{'；'.join(opt.cons)}")
                if opt.applicability:
                    lines.append(f"   适用：{opt.applicability}")
        if self.reasoning:
            lines.append(f"\n推荐理由：{self.reasoning}")
        return "\n".join(lines)

    def render_for_prompt(self) -> str:
        opts = "；".join(
            f"{i+1}) {o.label}" for i, o in enumerate(self.options)
        ) or "（无预设选项，等待用户自由回答）"
        rec = (
            f"，你的推荐是第 {self.recommended_index + 1} 项"
            if self.recommended_index is not None
            else ""
        )
        return f"{self.question}\n  选项：{opts}{rec}"
