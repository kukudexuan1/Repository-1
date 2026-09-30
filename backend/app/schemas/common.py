"""跨模块共享的基础类型。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CadTarget(str, Enum):
    INVENTOR = "inventor"


class Quantity(BaseModel):
    """带单位的物理量。

    单位为空串表示无量纲。量纲换算与校验由 app.services.compute.units 负责，
    本模型只做序列化承载，不依赖 pint，保证 SessionState 可无损落库。
    """

    value: float
    unit: str = ""

    def render(self, digits: int = 4) -> str:
        num = f"{self.value:.{digits}g}"
        return f"{num} {self.unit}".strip()

    def __str__(self) -> str:  # pragma: no cover - 仅用于日志
        return self.render()


class Deliverable(BaseModel):
    """已产出的交付物（说明书、计算书、几何文件、BOM 等）。"""

    kind: str
    title: str
    path: str
    created_at: str = ""
    notes: str = ""


class GateRecord(BaseModel):
    """评审关口的通过记录，用于设计过程追溯。"""

    gate: str
    approved: bool = False
    approved_at: str = ""
    user_statement: str = ""
    conditions: list[str] = Field(default_factory=list)
