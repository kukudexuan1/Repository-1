from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SimulationType(str, Enum):
    STEADY_STATE_THERMAL = "steady_state_thermal"
    TRANSIENT_THERMAL = "transient_thermal"
    STATIC_STRUCTURAL = "static_structural"
    TRANSIENT_STRUCTURAL = "transient_structural"
    MODAL = "modal"
    HARMONIC_RESPONSE = "harmonic_response"
    RESPONSE_SPECTRUM = "response_spectrum"
    RANDOM_VIBRATION = "random_vibration"
    CFX = "cfx"
    FLUENT = "fluent"


class SimulationStatus(str, Enum):
    NOT_RUN = "not_run"
    RUNNING = "running"
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


class SimulationResultItem(BaseModel):
    name: str
    value: float | None = None
    unit: str = ""
    limit: float | None = None
    passed: bool = True
    detail: str = ""


class SimulationReport(BaseModel):
    analysis_type: SimulationType | None = None
    status: SimulationStatus = SimulationStatus.NOT_RUN
    geometry_file: str = ""
    project_file: str = ""
    result_items: list[SimulationResultItem] = Field(default_factory=list)
    pass_or_fail: SimulationStatus = SimulationStatus.NOT_RUN
    issues: list[str] = Field(default_factory=list)
    recommended_adjustments: list[str] = Field(default_factory=list)
    solver_log_tail: str = ""
    raw_result: dict[str, Any] = Field(default_factory=dict)
    source: str = "subagent"
    override_reason: str = ""
