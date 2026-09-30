from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class ValidationIssue(BaseModel):
    code: str
    path: str
    message: str
    remedy: str = ""
    severity: ValidationSeverity = ValidationSeverity.ERROR


class ValidationReport(BaseModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class SpatialConflictType(str, Enum):
    COORDINATE_SYSTEM = "coordinate_system"
    PLANE_ORIENTATION = "plane_orientation"
    DIRECTION = "direction"
    TARGET_AMBIGUITY = "target_ambiguity"
    INTERSECTION = "intersection"
    EXTENT = "extent"
    TOPOLOGY = "topology"


class SpatialConflict(BaseModel):
    conflict_type: SpatialConflictType
    target: str = ""
    detail: str
    expected: Any = None
    actual: Any = None
    remedy: str = ""


class SectionExpectation(BaseModel):
    segment: str
    axis_position_cm: float
    diameter_cm: float
    tolerance_cm: float = 0.01


class FeatureExpectation(BaseModel):
    name: str
    feature_type: str
    target_segment: str
    axis_start_cm: float
    axis_end_cm: float
    radial_direction: str
    dimensions_cm: dict[str, float] = Field(default_factory=dict)


class ModelingPlan(BaseModel):
    """Non-operational geometry expectations compiled from a contract."""

    plan_version: str = "4.0-expectations"
    contract_hash: str
    contract_schema_version: int = 3
    part_name: str
    part_type: str
    main_axis: str
    placement_policy: str = "absolute"
    expected_bbox_cm: dict[str, float] = Field(default_factory=dict)
    expected_bbox_min_cm: dict[str, float] = Field(default_factory=dict)
    expected_bbox_max_cm: dict[str, float] = Field(default_factory=dict)
    expected_body_count: int = 1
    sections: list[SectionExpectation] = Field(default_factory=list)
    features: list[FeatureExpectation] = Field(default_factory=list)


class VerificationStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INDETERMINATE = "indeterminate"


class VerificationCheck(BaseModel):
    name: str
    status: VerificationStatus
    expected: Any = None
    actual: Any = None
    detail: str = ""


class ReportSource(str, Enum):
    SUBAGENT = "subagent"
    MAIN_MODEL = "main_model"


class GeometryVerificationReport(BaseModel):
    status: VerificationStatus
    contract_hash: str
    geometry_hash: str = ""
    checks: list[VerificationCheck] = Field(default_factory=list)
    conflicts: list[SpatialConflict] = Field(default_factory=list)
    tool_evidence: dict[str, Any] = Field(default_factory=dict)
    stale: bool = False
    source: ReportSource = ReportSource.SUBAGENT
    override_reason: str = ""
