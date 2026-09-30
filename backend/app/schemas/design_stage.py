"""设计过程阶段机与会话模式。

阶段推进采用「软推进 + 硬 Gate」：阶段切换由主设计模型按行动手册中的完成判据
自行判断（软），但三个评审关口由代码强制门控（硬）——未通过 Gate 时对应的
下游工具会直接拒绝执行。
"""

from __future__ import annotations

from enum import Enum


class SessionMode(str, Enum):
    """会话工作模式。

    DESIGN            正向设计：从设计需求出发，走完整设计计算链路
    REVERSE_MODELING  逆向建模：已有完整图纸，尺寸直接取自图纸，只补校核
    """

    DESIGN = "design"
    REVERSE_MODELING = "reverse_modeling"


class DesignScope(str, Enum):
    """设计对象的范围。

    决定流程形态，而不是决定流程严格度——两种范围都要走完整的
    契约、设计说明书与设计计算书。

    UNDECIDED    尚未判定。设计输入收敛阶段应尽早判定
    SINGLE_PART  单个零件：一份契约、一次建模，几何完成后直接进入零件级仿真
    ASSEMBLY     装配体：逐个零件建模，全部完成后须由用户手工装配，
                 再以装配体几何进入装配级仿真
    """

    UNDECIDED = "undecided"
    SINGLE_PART = "single_part"
    ASSEMBLY = "assembly"


SCOPE_LABELS: dict[DesignScope, str] = {
    DesignScope.UNDECIDED: "待判定",
    DesignScope.SINGLE_PART: "单个零件",
    DesignScope.ASSEMBLY: "装配体",
}


class DesignStage(str, Enum):
    SPEC_GATHERING = "spec_gathering"
    SCHEME_DESIGN = "scheme_design"
    DETAIL_CALCULATION = "detail_calculation"
    PARAMETER_FREEZE = "parameter_freeze"
    GEOMETRY = "geometry"
    ASSEMBLY_HANDOFF = "assembly_handoff"
    VERIFICATION = "verification"
    DELIVERY = "delivery"
    COMPLETED = "completed"


class Gate(str, Enum):
    """代码级门控点。

    ASSEMBLY_SUBMITTED 只在装配体范围下生效：当前 mcp-cad 的装配能力不足以
    自动装配，装配由用户手工完成，用户提交 iam/stp 后本关口才通过。
    单个零件范围下该关口不参与门控。
    """

    SCHEME_CONFIRMED = "gate1_scheme_confirmed"
    PARAMETERS_FROZEN = "gate2_parameters_frozen"
    ASSEMBLY_SUBMITTED = "gate2b_assembly_submitted"
    VERIFICATION_ACCEPTED = "gate3_verification_accepted"


DESIGN_STAGE_ORDER: list[DesignStage] = [
    DesignStage.SPEC_GATHERING,
    DesignStage.SCHEME_DESIGN,
    DesignStage.DETAIL_CALCULATION,
    DesignStage.PARAMETER_FREEZE,
    DesignStage.GEOMETRY,
    DesignStage.ASSEMBLY_HANDOFF,
    DesignStage.VERIFICATION,
    DesignStage.DELIVERY,
    DesignStage.COMPLETED,
]

# 单个零件不经过装配交接阶段
SINGLE_PART_STAGE_ORDER: list[DesignStage] = [
    s for s in DESIGN_STAGE_ORDER if s != DesignStage.ASSEMBLY_HANDOFF
]

STAGE_LABELS: dict[DesignStage, str] = {
    DesignStage.SPEC_GATHERING: "设计输入收敛",
    DesignStage.SCHEME_DESIGN: "方案设计",
    DesignStage.DETAIL_CALCULATION: "详细设计计算",
    DesignStage.PARAMETER_FREEZE: "参数冻结",
    DesignStage.GEOMETRY: "几何表达",
    DesignStage.ASSEMBLY_HANDOFF: "装配交接",
    DesignStage.VERIFICATION: "校核验证",
    DesignStage.DELIVERY: "交付物生成",
    DesignStage.COMPLETED: "已完成",
}

# 进入某阶段所要求的前置 Gate
STAGE_REQUIRED_GATE: dict[DesignStage, Gate] = {
    DesignStage.DETAIL_CALCULATION: Gate.SCHEME_CONFIRMED,
    DesignStage.GEOMETRY: Gate.PARAMETERS_FROZEN,
    DesignStage.DELIVERY: Gate.VERIFICATION_ACCEPTED,
}


def stage_order(scope: DesignScope | str = DesignScope.UNDECIDED) -> list[DesignStage]:
    """返回该设计范围实际经过的阶段序列。"""
    value = scope.value if isinstance(scope, DesignScope) else str(scope)
    if value == DesignScope.SINGLE_PART.value:
        return SINGLE_PART_STAGE_ORDER
    return DESIGN_STAGE_ORDER


def stage_index(
    stage: DesignStage, scope: DesignScope | str = DesignScope.UNDECIDED
) -> int:
    order = stage_order(scope)
    if stage not in order:
        return DESIGN_STAGE_ORDER.index(stage)
    return order.index(stage)


def next_stage(
    stage: DesignStage, scope: DesignScope | str = DesignScope.UNDECIDED
) -> DesignStage:
    order = stage_order(scope)
    if stage not in order:
        # 单个零件范围下误置于装配交接阶段时，直接落到校核验证
        return DesignStage.VERIFICATION
    idx = order.index(stage)
    if idx + 1 >= len(order):
        return DesignStage.COMPLETED
    return order[idx + 1]
