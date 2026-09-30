"""设计系统数据契约。"""

from .calculation_record import CalcEngine, CalculationRecord, Verdict
from .common import CadTarget, Deliverable, GateRecord, Quantity
from .decision import DecisionKind, DecisionOption, PendingDecision
from .design_spec import DesignSpec, SpecItem, SpecStatus
from .design_stage import (
    DESIGN_STAGE_ORDER,
    STAGE_LABELS,
    STAGE_REQUIRED_GATE,
    SCOPE_LABELS,
    SINGLE_PART_STAGE_ORDER,
    DesignScope,
    DesignStage,
    Gate,
    SessionMode,
    next_stage,
    stage_index,
    stage_order,
)
from .formula_card import FormulaCard, SymbolRole, SymbolSpec
from .modeling_contract import ModelingContract
from .parameter_ledger import (
    ParameterEntry,
    ParameterLedger,
    ParameterSource,
    ParameterStatus,
)
from .session_state import (
    ActiveAgent,
    AssemblyHandoff,
    ChatMessage,
    ChatRole,
    DrawingArtifact,
    PartBuild,
    PartBuildStatus,
    SchemeAlternative,
    SessionState,
    TaskType,
    UserIntent,
)
from .simulation_report import SimulationReport, SimulationResultItem, SimulationStatus

__all__ = [
    "ActiveAgent",
    "AssemblyHandoff",
    "CadTarget",
    "CalcEngine",
    "CalculationRecord",
    "ChatMessage",
    "ChatRole",
    "DESIGN_STAGE_ORDER",
    "DecisionKind",
    "DecisionOption",
    "Deliverable",
    "DesignScope",
    "DesignSpec",
    "DesignStage",
    "DrawingArtifact",
    "FormulaCard",
    "Gate",
    "GateRecord",
    "ModelingContract",
    "ParameterEntry",
    "ParameterLedger",
    "ParameterSource",
    "ParameterStatus",
    "PartBuild",
    "PartBuildStatus",
    "PendingDecision",
    "Quantity",
    "SCOPE_LABELS",
    "SINGLE_PART_STAGE_ORDER",
    "STAGE_LABELS",
    "STAGE_REQUIRED_GATE",
    "SchemeAlternative",
    "SessionMode",
    "SessionState",
    "SimulationReport",
    "SimulationResultItem",
    "SimulationStatus",
    "SpecItem",
    "SpecStatus",
    "SymbolRole",
    "SymbolSpec",
    "TaskType",
    "UserIntent",
    "Verdict",
    "next_stage",
    "stage_index",
    "stage_order",
]
