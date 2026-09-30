from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .calculation_record import CalculationRecord
from .common import CadTarget, Deliverable, GateRecord
from .decision import PendingDecision
from .design_spec import DesignSpec
from .design_stage import DesignScope, DesignStage, Gate, SessionMode
from .modeling_contract import ModelingContract
from .modeling_plan import GeometryVerificationReport, ModelingPlan, ValidationReport
from .parameter_ledger import ParameterLedger
from .simulation_report import SimulationReport


class TaskType(str, Enum):
    PART = "part"
    ASSEMBLY = "assembly"
    UNKNOWN = "unknown"


class UserIntent(BaseModel):
    task_type: TaskType = TaskType.UNKNOWN
    target_cad: CadTarget = CadTarget.INVENTOR
    constraints: list[str] = Field(default_factory=list)


class DrawingArtifact(BaseModel):
    file_id: UUID
    name: str
    uri: str
    ocr_ready: bool = False


class SchemeAlternative(BaseModel):
    """方案设计阶段的备选方案。"""

    name: str
    summary: str = ""
    structure: str = ""
    material: str = ""
    process: str = ""
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    cost_level: str = ""
    selected: bool = False


class PartBuildStatus(str, Enum):
    """装配体中单个零件的建模进度。"""

    PLANNED = "planned"
    CONTRACTED = "contracted"
    BUILT = "built"


class PartBuild(BaseModel):
    """装配体范围下的单个零件建模记录。

    装配体设计需要逐零件建契约、逐零件建模，本模型记录每个零件的进度与产物，
    使主设计模型能判断「是否所有零件都已建完，可以要求用户手工装配」。
    """

    part_name: str
    part_type: str = "custom"
    role: str = ""
    """在装配体中的功能角色，如 '输入轴'、'大齿轮'、'箱体上盖'。"""

    status: PartBuildStatus = PartBuildStatus.PLANNED
    geometry_file: str = ""
    geometry_hash: str = ""
    contract_file: str = ""
    note: str = ""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_built(self) -> bool:
        return self.status == PartBuildStatus.BUILT and bool(self.geometry_file)


class AssemblyHandoff(BaseModel):
    """用户手工装配的交接记录。

    当前 mcp-cad 的装配工具链不足以可靠地自动装配（缺面/边枚举、无姿态参数、
    无干涉与自由度检查），因此装配这一步交由用户在 Inventor 中手工完成。
    用户可提交 .iam（由系统打开并导出 STP）或直接提交已导出的 .stp。
    """

    submitted: bool = False
    source_kind: str = ""
    """iam=用户提交装配体源文件；stp=用户直接提交已导出的 STEP。"""

    iam_file: str = ""
    step_file: str = ""
    step_hash: str = ""
    user_statement: str = ""
    part_count: int = 0
    notes: list[str] = Field(default_factory=list)
    submitted_at: str = ""


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    message_id: UUID = Field(default_factory=uuid4)
    role: ChatRole
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActiveAgent(str, Enum):
    NONE = "none"
    MODELING = "modeling"
    ANALYSIS = "analysis"


class SessionState(BaseModel):
    session_id: UUID

    # ---- 会话与流程 ----
    mode: SessionMode = SessionMode.DESIGN
    design_stage: DesignStage = DesignStage.SPEC_GATHERING
    gates: dict[str, GateRecord] = Field(default_factory=dict)
    user_intent: UserIntent = Field(default_factory=UserIntent)
    design_scope: DesignScope = DesignScope.UNDECIDED
    """设计对象范围：单个零件 or 装配体。决定流程形态，不决定流程严格度。"""

    # ---- 设计层 ----
    design_spec: DesignSpec = Field(default_factory=DesignSpec)
    ledger: ParameterLedger = Field(default_factory=ParameterLedger)
    calculations: dict[str, CalculationRecord] = Field(default_factory=dict)
    calc_seq: int = 0
    alternatives: list[SchemeAlternative] = Field(default_factory=list)
    pending_decision: PendingDecision | None = None
    decision_history: list[PendingDecision] = Field(default_factory=list)

    # ---- 输入资料 ----
    drawing_artifacts: list[DrawingArtifact] = Field(default_factory=list)
    semantic_facts: dict[str, Any] = Field(default_factory=dict)

    # ---- 表达与校核 ----
    modeling_contract: ModelingContract | None = None
    modeling_contract_file: str = ""
    modeling_plan: ModelingPlan | None = None
    modeling_plan_file: str = ""
    contract_validation_report: ValidationReport | None = None
    geometry_verification_report: GeometryVerificationReport | None = None
    geometry_file: str = ""
    geometry_file_hash: str = ""
    simulation_report: SimulationReport | None = None

    # ---- 装配体范围专用 ----
    part_builds: list[PartBuild] = Field(default_factory=list)
    """装配体的零件清单与逐件建模进度。单个零件范围下保持为空。"""

    assembly_handoff: AssemblyHandoff = Field(default_factory=AssemblyHandoff)
    """用户手工装配的交接记录（提交的 iam / stp）。"""

    # ---- 交付 ----
    deliverables: list[Deliverable] = Field(default_factory=list)

    # ---- 会话运行时 ----
    chat_history: list[ChatMessage] = Field(default_factory=list)
    active_agent: ActiveAgent = ActiveAgent.NONE
    modeling_messages: list[dict[str, Any]] = Field(default_factory=list)
    analysis_messages: list[dict[str, Any]] = Field(default_factory=list)
    last_error: str = ""
    version: str = "v4.0.0"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # ---- 便捷方法 ----

    @property
    def is_assembly_scope(self) -> bool:
        return self.design_scope == DesignScope.ASSEMBLY

    @property
    def is_single_part_scope(self) -> bool:
        return self.design_scope == DesignScope.SINGLE_PART

    def built_parts(self) -> list[PartBuild]:
        return [p for p in self.part_builds if p.is_built]

    def unbuilt_parts(self) -> list[PartBuild]:
        return [p for p in self.part_builds if not p.is_built]

    def assembly_completeness_issues(self) -> list[str]:
        """检查单级减速器进入装配交接前的最小功能闭环。"""
        if not self.is_assembly_scope or self.design_spec.family != "gearbox_single_stage":
            return []

        roles = " ".join(p.role.lower() for p in self.part_builds)
        names = " ".join(p.part_name.lower() for p in self.part_builds)
        text = f"{roles} {names}"
        checks = [
            (("下箱体", "housing_lower", "箱座"), "缺少下箱体/箱座"),
            (("上箱体", "housing_upper", "箱盖"), "缺少上箱体/箱盖"),
            (("输入轴", "input_shaft"), "缺少输入轴"),
            (("输出轴", "output_shaft"), "缺少输出轴"),
            (("小齿轮", "pinion", "input_gear"), "缺少小齿轮"),
            (("大齿轮", "gear", "output_gear"), "缺少大齿轮"),
        ]
        issues = [message for needles, message in checks if not any(needle in text for needle in needles)]
        if not any(token in text for token in ("轴承", "bearing")):
            issues.append("缺少轴承支撑件声明；四个轴承可作为标准件，但必须登记支撑接口")
        if not any(token in text for token in ("端盖", "seal", "密封")):
            issues.append("缺少轴承端盖/密封接口声明")
        return issues

    def all_parts_built(self) -> bool:
        """装配体的全部零件是否已建模且通过最小功能闭环检查。"""
        return bool(self.part_builds) and not self.unbuilt_parts() and not self.assembly_completeness_issues()

    def find_part(self, part_name: str) -> PartBuild | None:
        needle = part_name.strip().lower()
        for part in self.part_builds:
            if part.part_name.strip().lower() == needle:
                return part
        return None

    def simulation_geometry(self) -> str:
        """当前应送入 CAE 的几何文件。

        装配体范围下取用户提交并导出的装配体 STEP；单个零件范围下取零件几何。
        """
        if self.is_assembly_scope and self.assembly_handoff.submitted:
            return self.assembly_handoff.step_file
        return self.geometry_file

    def next_calc_id(self) -> str:
        self.calc_seq += 1
        return f"calc#{self.calc_seq}"

    def add_calculation(self, record: CalculationRecord) -> CalculationRecord:
        self.calculations[record.record_id] = record
        return record

    def gate_passed(self, gate: Gate | str) -> bool:
        key = gate.value if isinstance(gate, Gate) else gate
        record = self.gates.get(key)
        return bool(record and record.approved)

    def approve_gate(
        self, gate: Gate | str, statement: str = "", conditions: list[str] | None = None
    ) -> GateRecord:
        key = gate.value if isinstance(gate, Gate) else gate
        record = GateRecord(
            gate=key,
            approved=True,
            approved_at=datetime.now(timezone.utc).isoformat(),
            user_statement=statement,
            conditions=conditions or [],
        )
        self.gates[key] = record
        return record

    def revoke_gate(self, gate: Gate | str) -> None:
        key = gate.value if isinstance(gate, Gate) else gate
        self.gates.pop(key, None)

    def check_verdicts(self) -> dict[str, int]:
        """统计校核类计算记录的通过情况。"""
        out = {"pass": 0, "fail": 0, "n/a": 0, "stale": 0}
        for record in self.calculations.values():
            if record.stale:
                out["stale"] += 1
            out[record.verdict.value] += 1
        return out

    def failed_checks(self) -> list[CalculationRecord]:
        return [r for r in self.calculations.values() if r.verdict.value == "fail"]
