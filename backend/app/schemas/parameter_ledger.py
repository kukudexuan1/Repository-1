"""设计参数台账。

这是把「建模系统」变成「设计系统」的核心机制：任何将进入几何或交付物的参数，
都必须在台账中有一条带来源与依据的记录。plan_modeling_contract 只接受台账中
状态为 confirmed / frozen 的参数，从机制上杜绝凭空报数。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from .common import Quantity


class ParameterSource(str, Enum):
    USER_GIVEN = "user_given"
    FROM_DRAWING = "from_drawing"
    CALCULATED = "calculated"
    STANDARD_LOOKUP = "standard_lookup"
    DESIGN_CHOICE = "design_choice"
    ASSUMED = "assumed"


class ParameterStatus(str, Enum):
    TENTATIVE = "tentative"
    CONFIRMED = "confirmed"
    FROZEN = "frozen"
    STALE = "stale"


# 允许直接落地而无需计算记录的来源
SOURCES_WITHOUT_CALC = {
    ParameterSource.USER_GIVEN,
    ParameterSource.FROM_DRAWING,
    ParameterSource.DESIGN_CHOICE,
    ParameterSource.ASSUMED,
}


class ParameterEntry(BaseModel):
    symbol: str
    name: str = ""
    value: Quantity
    source: ParameterSource
    basis: list[str] = Field(default_factory=list)
    rationale: str = ""
    status: ParameterStatus = ParameterStatus.TENTATIVE
    group: str = "其他"
    revision: int = 1
    superseded_value: str = ""
    stale_reason: str = ""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def usable_for_geometry(self) -> bool:
        return self.status in (ParameterStatus.CONFIRMED, ParameterStatus.FROZEN)

    def render_line(self) -> str:
        basis = f"  ← {', '.join(self.basis)}" if self.basis else ""
        note = f"「{self.rationale}」" if self.rationale else ""
        stale = "  ⚠已失效" if self.status == ParameterStatus.STALE else ""
        label = self.name or self.symbol
        return (
            f"{self.symbol:<12} = {self.value.render():<14}"
            f"[{self.source.value}]{basis} {note}{stale}   ({label})"
        )


class ParameterLedger(BaseModel):
    entries: dict[str, ParameterEntry] = Field(default_factory=dict)
    frozen_at: datetime | None = None
    freeze_statement: str = ""

    # ---- 查询 ----

    def get(self, symbol: str) -> ParameterEntry | None:
        return self.entries.get(symbol)

    def value_of(self, symbol: str) -> Quantity | None:
        entry = self.entries.get(symbol)
        return entry.value if entry else None

    def by_status(self, status: ParameterStatus) -> list[ParameterEntry]:
        return [e for e in self.entries.values() if e.status == status]

    def tentative(self) -> list[ParameterEntry]:
        return self.by_status(ParameterStatus.TENTATIVE)

    def stale(self) -> list[ParameterEntry]:
        return self.by_status(ParameterStatus.STALE)

    def assumed(self) -> list[ParameterEntry]:
        return [e for e in self.entries.values() if e.source == ParameterSource.ASSUMED]

    @property
    def is_frozen(self) -> bool:
        return self.frozen_at is not None

    def counts(self) -> dict[str, int]:
        out = {s.value: 0 for s in ParameterStatus}
        for entry in self.entries.values():
            out[entry.status.value] += 1
        return out

    # ---- 更新 ----

    def commit(
        self,
        symbol: str,
        value: Quantity,
        source: ParameterSource,
        *,
        name: str = "",
        basis: list[str] | None = None,
        rationale: str = "",
        group: str = "其他",
        status: ParameterStatus = ParameterStatus.TENTATIVE,
    ) -> ParameterEntry:
        existing = self.entries.get(symbol)
        if existing is not None:
            existing.superseded_value = existing.value.render()
            existing.revision += 1
            existing.value = value
            existing.source = source
            existing.basis = basis or []
            existing.rationale = rationale or existing.rationale
            existing.status = status
            existing.stale_reason = ""
            if name:
                existing.name = name
            if group != "其他":
                existing.group = group
            existing.updated_at = datetime.now(timezone.utc)
            return existing

        entry = ParameterEntry(
            symbol=symbol,
            name=name,
            value=value,
            source=source,
            basis=basis or [],
            rationale=rationale,
            group=group,
            status=status,
        )
        self.entries[symbol] = entry
        return entry

    def confirm(self, symbols: list[str] | None = None) -> list[str]:
        targets = symbols or list(self.entries.keys())
        changed = []
        for symbol in targets:
            entry = self.entries.get(symbol)
            if entry and entry.status == ParameterStatus.TENTATIVE:
                entry.status = ParameterStatus.CONFIRMED
                entry.updated_at = datetime.now(timezone.utc)
                changed.append(symbol)
        return changed

    def freeze(self, statement: str = "") -> list[str]:
        changed = []
        for entry in self.entries.values():
            if entry.status in (ParameterStatus.TENTATIVE, ParameterStatus.CONFIRMED):
                entry.status = ParameterStatus.FROZEN
                changed.append(entry.symbol)
        self.frozen_at = datetime.now(timezone.utc)
        self.freeze_statement = statement
        return changed

    def unfreeze(self, reason: str = "") -> None:
        """校核不通过需要返工时解冻，参数退回 confirmed 以便重算。"""
        for entry in self.entries.values():
            if entry.status == ParameterStatus.FROZEN:
                entry.status = ParameterStatus.CONFIRMED
        self.frozen_at = None
        self.freeze_statement = f"已解冻：{reason}" if reason else "已解冻"

    def mark_stale(self, symbol: str, reason: str) -> ParameterEntry | None:
        entry = self.entries.get(symbol)
        if entry is None:
            return None
        entry.status = ParameterStatus.STALE
        entry.stale_reason = reason
        entry.updated_at = datetime.now(timezone.utc)
        return entry

    # ---- 渲染 ----

    def render_snapshot(self, max_items: int = 60) -> str:
        if not self.entries:
            return "（台账为空）"
        groups: dict[str, list[ParameterEntry]] = {}
        for entry in self.entries.values():
            groups.setdefault(entry.group, []).append(entry)

        lines: list[str] = []
        shown = 0
        for group, entries in groups.items():
            lines.append(f"  [{group}]")
            for entry in entries:
                if shown >= max_items:
                    lines.append("  …（其余参数省略，可用 query_ledger 查询）")
                    return "\n".join(lines)
                lines.append(f"    {entry.render_line()}")
                shown += 1
        return "\n".join(lines)
