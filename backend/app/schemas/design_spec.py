"""设计任务书（设计输入）。

DesignSpec 是多轮交互的收敛目标：把用户模糊的需求逐步固化为完整、无歧义、
可计算的设计输入。条目清单由零件族模板（YAML）定义，因此新增零件族不需要
改动本模块。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from .common import Quantity


class SpecStatus(str, Enum):
    """设计输入条目的确认状态。"""

    UNKNOWN = "unknown"
    USER_GIVEN = "user_given"
    FROM_DRAWING = "from_drawing"
    ASSUMED_PENDING_CONFIRM = "assumed_pending_confirm"
    CONFIRMED = "confirmed"


class SpecItem(BaseModel):
    """单条设计输入。"""

    key: str
    label: str = ""
    value: Quantity | str | float | bool | None = None
    status: SpecStatus = SpecStatus.UNKNOWN
    source: str = ""
    rationale: str = ""
    required: bool = True
    group: str = "其他"
    needed_by_stage: str = "spec_gathering"
    hint: str = ""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_known(self) -> bool:
        return self.status != SpecStatus.UNKNOWN and self.value is not None

    @property
    def needs_confirm(self) -> bool:
        return self.status == SpecStatus.ASSUMED_PENDING_CONFIRM

    def render_value(self) -> str:
        if self.value is None:
            return "—"
        if isinstance(self.value, Quantity):
            return self.value.render()
        return str(self.value)


class DesignSpec(BaseModel):
    """设计任务书。

    family 标识零件族（如 gearbox_single_stage），决定加载哪份模板。
    items 以 key 为索引，模板未覆盖的自定义条目也可直接写入。
    """

    family: str = ""
    family_label: str = ""
    title: str = ""
    items: dict[str, SpecItem] = Field(default_factory=dict)

    # ---- 查询 ----

    def get(self, key: str) -> SpecItem | None:
        return self.items.get(key)

    def missing_required(self, upto_stage: str = "") -> list[SpecItem]:
        """返回仍为 unknown 的必填条目。

        upto_stage 非空时只统计该阶段之前（含）需要的条目，避免在需求收敛阶段
        就追问详细计算阶段才用得到的参数。
        """
        from .design_stage import DESIGN_STAGE_ORDER, DesignStage

        limit = None
        if upto_stage:
            try:
                limit = DESIGN_STAGE_ORDER.index(DesignStage(upto_stage))
            except (ValueError, KeyError):
                limit = None

        out: list[SpecItem] = []
        for item in self.items.values():
            if not item.required or item.is_known:
                continue
            if limit is not None:
                try:
                    idx = DESIGN_STAGE_ORDER.index(DesignStage(item.needed_by_stage))
                except (ValueError, KeyError):
                    idx = 0
                if idx > limit:
                    continue
            out.append(item)
        return out

    def pending_confirm(self) -> list[SpecItem]:
        return [i for i in self.items.values() if i.needs_confirm]

    def known_count(self) -> int:
        return sum(1 for i in self.items.values() if i.is_known)

    def is_ready_for(self, stage: str) -> bool:
        return not self.missing_required(upto_stage=stage)

    # ---- 更新 ----

    def upsert(
        self,
        key: str,
        *,
        value: Quantity | str | float | bool | None = None,
        status: SpecStatus | None = None,
        source: str = "",
        rationale: str = "",
        label: str = "",
        group: str = "",
        required: bool | None = None,
        needed_by_stage: str = "",
        hint: str = "",
    ) -> SpecItem:
        item = self.items.get(key)
        if item is None:
            item = SpecItem(key=key, label=label or key)
            self.items[key] = item
        if value is not None:
            item.value = value
        if status is not None:
            item.status = status
        if source:
            item.source = source
        if rationale:
            item.rationale = rationale
        if label:
            item.label = label
        if group:
            item.group = group
        if required is not None:
            item.required = required
        if needed_by_stage:
            item.needed_by_stage = needed_by_stage
        if hint:
            item.hint = hint
        item.updated_at = datetime.now(timezone.utc)
        return item

    def confirm_all_assumed(self, statement: str = "") -> list[str]:
        """把所有待确认假设转为已确认，返回被确认的 key 列表。"""
        changed = []
        for item in self.items.values():
            if item.needs_confirm:
                item.status = SpecStatus.CONFIRMED
                if statement:
                    item.source = f"{item.source}；用户确认：{statement}".strip("；")
                changed.append(item.key)
        return changed

    # ---- 渲染 ----

    def render_snapshot(self, max_items: int = 40) -> str:
        if not self.items:
            return "（尚未记录任何设计输入）"
        groups: dict[str, list[SpecItem]] = {}
        for item in self.items.values():
            groups.setdefault(item.group, []).append(item)

        lines: list[str] = []
        shown = 0
        for group, items in groups.items():
            known = [i for i in items if i.is_known]
            if not known:
                continue
            lines.append(f"  [{group}]")
            for item in known:
                if shown >= max_items:
                    lines.append("  …（其余条目省略）")
                    return "\n".join(lines)
                flag = " ⚠待确认" if item.needs_confirm else ""
                lines.append(
                    f"    {item.label or item.key} = {item.render_value()}"
                    f"  [{item.status.value}]{flag}"
                )
                shown += 1
        return "\n".join(lines) if lines else "（尚未记录任何设计输入）"
