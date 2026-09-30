"""设计计算记录。

每次工程计算都必须留下一条 CalculationRecord：它同时承担三个职责——
  1. 参数溯源：台账条目的 basis 指向计算记录 ID
  2. 计算书素材：公式、出处、代入过程、判据直接渲染成文档章节
  3. 变更传播：depends_on 构成计算依赖图，参数变更时可推导哪些结论失效
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from .common import Quantity


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "n/a"


class CalcEngine(str, Enum):
    FORMULA_LIB = "formula_lib"
    SYMPY = "sympy"
    SCIPY = "scipy"
    TOLERANCE_CHAIN = "tolerance_chain"


class CalculationRecord(BaseModel):
    record_id: str
    title: str
    formula_id: str = ""
    expression: str = ""
    inputs: dict[str, Quantity] = Field(default_factory=dict)
    substitution: str = ""
    result: dict[str, Quantity] = Field(default_factory=dict)
    criterion: str = ""
    verdict: Verdict = Verdict.NOT_APPLICABLE
    margin_percent: float | None = None
    source: str = ""
    engine: CalcEngine = CalcEngine.FORMULA_LIB
    depends_on: list[str] = Field(default_factory=list)
    stale: bool = False
    stale_reason: str = ""
    notes: str = ""
    script: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def primary_result(self) -> Quantity | None:
        if not self.result:
            return None
        return next(iter(self.result.values()))

    def render_line(self) -> str:
        res = ", ".join(f"{k}={v.render()}" for k, v in self.result.items()) or "—"
        verdict = "" if self.verdict == Verdict.NOT_APPLICABLE else f"  {self.verdict.value}"
        stale = "  ⚠已失效" if self.stale else ""
        return f"{self.record_id}  {self.title}  {res}{verdict}{stale}"

    def render_full(self) -> str:
        """渲染为计算书章节。"""
        lines = [f"### {self.record_id} {self.title}"]
        if self.source:
            lines.append(f"依据：{self.source}")
        if self.expression:
            lines.append(f"公式：`{self.expression}`")
        if self.inputs:
            args = "，".join(f"{k} = {v.render()}" for k, v in self.inputs.items())
            lines.append(f"输入：{args}")
        if self.substitution:
            lines.append(f"代入：{self.substitution}")
        if self.result:
            res = "，".join(f"{k} = {v.render()}" for k, v in self.result.items())
            lines.append(f"结果：{res}")
        if self.criterion:
            verdict_cn = {"pass": "满足", "fail": "不满足", "n/a": "—"}[self.verdict.value]
            margin = (
                f"（余量 {self.margin_percent:.1f}%）"
                if self.margin_percent is not None
                else ""
            )
            lines.append(f"判据：{self.criterion} → {verdict_cn}{margin}")
        if self.notes:
            lines.append(f"备注：{self.notes}")
        return "\n\n".join(lines)
