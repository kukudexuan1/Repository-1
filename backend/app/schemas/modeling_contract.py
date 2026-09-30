"""建模契约：在 build_model 执行前确立全局坐标系和图元空间位置的结构化表示。

坐标系约定（所有数值单位 cm，与 Inventor COM API 一致）：
- 主轴方向：axis（X/Y/Z）
- 原点位置：origin_coords [x, y, z]（cm）
- 径向向上：radial_up（+Z/-Z/+Y/-Y 等）
- 径向侧向：由右手系从 axis × radial_up 推导

每个主体段（BodySegment）包含：
- 沿主轴的起止坐标（cm）
- 截面几何（圆柱/矩形/锥面）
- 草图平面声明（用于 sketch_create）

每个局部特征（LocalFeature）包含：
- 目标主体段名
- 草图平面（精确到坐标或面名）
- 切削/生成方向
- 轴向范围
- 周向位置
- 精确尺寸（cm）
- 验证条件
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Axis(str, Enum):
    X = "X"
    Y = "Y"
    Z = "Z"


class RadialDirection(str, Enum):
    POS_X = "+X"
    NEG_X = "-X"
    POS_Y = "+Y"
    NEG_Y = "-Y"
    POS_Z = "+Z"
    NEG_Z = "-Z"


class PlacementPolicy(str, Enum):
    ABSOLUTE = "absolute"
    RELATIVE = "relative"


class PlacementPolicy(str, Enum):
    ABSOLUTE = "absolute"
    RELATIVE = "relative"


class ContractProvenance(BaseModel):
    source_schema_version: int = 2
    migrated_from: str = ""
    migration_notes: list[str] = Field(default_factory=list)


class CoordinateSystem(BaseModel):
    """全局坐标系定义。"""

    axis: Axis = Axis.X
    """主轴方向：X / Y / Z。轴类零件默认 X。"""

    origin: str = "left_end_center"
    """原点语义描述，便于模型理解。"""

    origin_coords: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    """原点在 Inventor 全局坐标系中的坐标，单位 cm。"""

    radial_up: RadialDirection = RadialDirection.POS_Z
    """径向向上方向。决定草图平面的 Z 轴。"""

    radial_side: RadialDirection = RadialDirection.POS_Y
    """径向侧向，满足 axis × radial_side = radial_up。"""

    notes: str = ""
    """补充说明，如 '竖直放置时 +Z 向上'。"""


class BodySegment(BaseModel):
    """主体段——构成零件骨架的基础实体。"""

    name: str
    """语义名，如 'left_shaft'、'middle_shaft'、'flange'。在局部特征中通过此名引用。"""

    shape: str = "cylinder"
    """截面形状：cylinder / box / cone / custom。"""

    axis_start_cm: float
    """沿主轴起始坐标（cm），相对于 origin_coords。"""

    axis_end_cm: float
    """沿主轴终止坐标（cm）。"""

    diameter_cm: float | None = None
    """圆柱/圆锥直径（cm）。shape=cylinder/cone 时必填。"""

    diameter_end_cm: float | None = None
    """锥面大端直径（cm）。shape=cone 时填写，diameter_cm 为小端。"""

    width_cm: float | None = None
    """矩形截面宽度（cm）。shape=box 时必填。"""

    height_cm: float | None = None
    """矩形截面高度（cm）。shape=box 时必填。"""


class LocalFeature(BaseModel):
    """局部特征——附着在主体段上的切削或添加特征。"""

    name: str
    """特征语义名，如 'keyway_middle'、'through_hole_left'。"""

    feature_type: str
    """特征类型：keyway / hole / groove / chamfer / fillet / thread /
    boss / slot / notch / counterbore / countersink / custom。"""

    target_segment: str
    """目标主体段名，对应 BodySegment.name。"""

    anchor_global_cm: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    """特征语义锚点的全局坐标。Agent 必须用实测 frame 将该点映射为草图坐标。"""

    axis_start_cm: float
    """特征沿主轴的起始坐标（cm）。"""

    axis_end_cm: float
    """特征沿主轴的终止坐标（cm）。"""

    axis_centered: bool = False
    """是否在目标主体段上轴向居中。若为 True，axis_start/end 由系统自动计算。"""

    angular_position: str = "+Z"
    """周向位置语义描述。
    示例：'top(+Z)' / 'bottom(-Z)' / 'left(+Y)' / 'right(-Y)' / 'angle:45deg_from+Z'。"""

    dimensions_cm: dict[str, float] = Field(default_factory=dict)
    """特征精确尺寸（cm）。
    键槽示例：{'length': 3.0, 'width': 0.8, 'depth': 0.3}
    孔示例：  {'diameter': 1.0, 'depth': 2.0}
    倒角示例：{'distance': 0.1}
    圆角示例：{'radius': 0.05}
    """

    topology_effect: str = "remove"
    """目标拓扑效果：remove / add / intersect / separate_body。"""

    verification: dict[str, Any] = Field(default_factory=dict)
    """契约要求的可验证几何条件。"""

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_anchor(cls, data: Any) -> Any:
        if isinstance(data, dict):
            updates = dict(data)
            if "anchor_global_cm" not in updates and "sketch_origin_cm" in updates:
                updates["anchor_global_cm"] = updates["sketch_origin_cm"]
            if "topology_effect" not in updates and "operation" in updates:
                updates["topology_effect"] = {
                    "cut": "remove",
                    "join": "add",
                    "new_body": "separate_body",
                }.get(str(updates["operation"]), str(updates["operation"]))
            return updates
        return data


class UnitEntry(BaseModel):
    label: str
    mm: float
    cm: float


class UnitConversionTable(BaseModel):
    """所有尺寸的 mm→cm 换算表，建模 Agent 开始时直接引用，不重复计算。"""

    entries: list[UnitEntry] = Field(default_factory=list)

    def render(self) -> str:
        if not self.entries:
            return "（无换算条目）"
        lines = []
        for e in self.entries:
            lines.append(f"  {e.label}: {e.mm}mm → {e.cm}cm")
        return "\n".join(lines)


class ModelingContract(BaseModel):
    """建模契约——主 Agent 在调用 build_model 前生成，建模 Agent 必须严格遵守。"""

    schema_version: int = 3
    placement_policy: PlacementPolicy = PlacementPolicy.ABSOLUTE
    provenance: ContractProvenance = Field(default_factory=ContractProvenance)
    session_id: str
    part_name: str
    part_type: str = "custom"
    """零件类型：shaft / plate / housing / bracket / gear / custom。"""

    coordinate_system: CoordinateSystem = Field(default_factory=CoordinateSystem)
    body_segments: list[BodySegment] = Field(default_factory=list)
    local_features: list[LocalFeature] = Field(default_factory=list)
    unit_table: UnitConversionTable = Field(default_factory=UnitConversionTable)

    assumptions: list[str] = Field(default_factory=list)
    """建模过程中采用的默认假设，如 '键槽沿中间段轴向居中'。"""

    open_questions: list[str] = Field(default_factory=list)
    """尚未确认的问题，若非空则主 Agent 应先澄清再建模。"""

    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def render_for_prompt(self) -> str:
        """生成注入建模 Agent system_prompt 的文字块。"""
        cs = self.coordinate_system
        lines = [
            "═══════════════════════════════════════════",
            "【建模契约 — 目标几何权威来源】",
            "═══════════════════════════════════════════",
            f"零件名称：{self.part_name}（{self.part_type}）",
            f"放置策略：{self.placement_policy.value}",
            "",
            "▌全局坐标系",
            f"  主轴方向  ：{cs.axis.value}",
            f"  原点位置  ：{cs.origin}  坐标 {cs.origin_coords} cm",
            f"  径向向上  ：{cs.radial_up.value}",
            f"  径向侧向  ：{cs.radial_side.value}",
            "  右手关系  ：axis × radial_side = radial_up",
        ]
        if cs.notes:
            lines.append(f"  备注      ：{cs.notes}")

        lines += ["", "▌主体段（按主轴顺序）"]
        for seg in self.body_segments:
            if seg.shape == "cylinder":
                geo = f"φ{seg.diameter_cm}cm"
            elif seg.shape == "box":
                geo = f"{seg.width_cm}cm × {seg.height_cm}cm"
            elif seg.shape == "cone":
                geo = f"φ{seg.diameter_cm}~{seg.diameter_end_cm}cm"
            else:
                geo = seg.shape
            lines.append(
                f"  [{seg.name}]  {cs.axis.value}={seg.axis_start_cm}~{seg.axis_end_cm}cm  {geo}"
            )

        if self.local_features:
            lines += ["", "▌局部特征"]
            for feat in self.local_features:
                lines.append(f"  [{feat.name}] {feat.feature_type} → 附着段：{feat.target_segment}")
                lines.append(f"    全局锚点  ：{feat.anchor_global_cm} cm")
                lines.append(f"    轴向范围  ：{cs.axis.value}={feat.axis_start_cm}~{feat.axis_end_cm}cm"
                              + ("（居中）" if feat.axis_centered else ""))
                lines.append(f"    周向位置  ：{feat.angular_position}")
                dim_str = "  ".join(f"{k}={v}cm" for k, v in feat.dimensions_cm.items())
                lines.append(f"    尺寸      ：{dim_str}")
                lines.append(f"    拓扑效果  ：{feat.topology_effect}")
                if feat.verification:
                    v_str = "  ".join(f"{k}={v}" for k, v in feat.verification.items())
                    lines.append(f"    验证条件  ：{v_str}")

        lines += ["", "▌尺寸换算表（直接引用，禁止重复计算）"]
        lines.append(self.unit_table.render())

        if self.assumptions:
            lines += ["", "▌建模假设"]
            for a in self.assumptions:
                lines.append(f"  · {a}")

        if self.open_questions:
            lines += ["", "▌⚠ 未确认问题（建模前应已澄清）"]
            for q in self.open_questions:
                lines.append(f"  ? {q}")

        lines += [
            "",
            "▌目标与观测边界",
            "  1. 契约决定目标形状、尺寸、全局位置、语义归属和拓扑；不得为建模方便改动目标",
            "  2. Inventor 数值 origin/normal/u/v 决定当前执行 frame；必须据此映射全局目标点",
            "  3. absolute 策略要求最终包围盒位置与尺寸均匹配；relative 策略只允许整体平移，不允许换轴、镜像或比例变化",
            "  4. 局部特征用 anchor_global_cm 表示目标锚点，不要求 CAD 草图对象的原点等于该锚点",
            "  5. 切削与附加特征必须用 inspect_feature、实体数、特征范围和截面证据验证；整体包围盒只能作为辅助证据",
            "═══════════════════════════════════════════",
        ]
        return "\n".join(lines)
