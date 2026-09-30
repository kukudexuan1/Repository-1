"""设计公式卡片。

公式库以 YAML 存放（app/services/knowledge/data/formulas/），每条公式带符号定义、
单位、适用条件与出处。这样计算结果天然可溯源，计算书里每个公式后面都能跟一个
教材条目或国标号。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class SymbolRole(str, Enum):
    INPUT = "input"
    OUTPUT = "output"


class SymbolSpec(BaseModel):
    name: str = ""
    desc: str = ""
    unit: str = ""
    role: SymbolRole = SymbolRole.INPUT
    default: float | None = None
    typical: list[float] | None = None
    note: str = ""

    def render(self) -> str:
        unit = f" [{self.unit}]" if self.unit else " [无量纲]"
        typical = f"，常用 {self.typical}" if self.typical else ""
        default = f"，默认 {self.default}" if self.default is not None else ""
        return f"{self.name}{unit}: {self.desc}{typical}{default}"


class FormulaCard(BaseModel):
    id: str
    name: str
    category: str = ""
    source: str = ""
    expression: str
    symbols: dict[str, SymbolSpec] = Field(default_factory=dict)
    applicability: str = ""
    criterion: str = ""
    # 可求值的判据表达式，如 "sigma_F <= sigma_FP"；is_check=True 时用于自动判定
    criterion_expr: str = ""
    is_check: bool = False
    notes: str = ""
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fill_symbol_names(self) -> "FormulaCard":
        for key, spec in self.symbols.items():
            if not spec.name:
                spec.name = key
        return self

    def outputs(self) -> list[str]:
        return [k for k, s in self.symbols.items() if s.role == SymbolRole.OUTPUT]

    def inputs(self) -> list[str]:
        return [k for k, s in self.symbols.items() if s.role == SymbolRole.INPUT]

    def required_inputs(self) -> list[str]:
        return [
            k
            for k, s in self.symbols.items()
            if s.role == SymbolRole.INPUT and s.default is None
        ]

    def render_for_model(self) -> str:
        """给主设计模型看的公式说明，让它照着填参数而不是靠记忆。"""
        lines = [
            f"公式 ID: {self.id}",
            f"名称: {self.name}",
            f"表达式: {self.expression}",
            f"出处: {self.source or '未标注'}",
        ]
        if self.applicability:
            lines.append(f"适用条件: {self.applicability}")
        if self.criterion:
            lines.append(f"判据: {self.criterion}")
        lines.append("符号:")
        for key in self.outputs():
            lines.append(f"  [求解] {self.symbols[key].render()}")
        for key in self.inputs():
            lines.append(f"  [输入] {self.symbols[key].render()}")
        if self.notes:
            lines.append(f"注意: {self.notes}")
        return "\n".join(lines)
