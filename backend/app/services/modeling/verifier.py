from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Awaitable, Callable

from app.mcp.result import ToolResult
from app.schemas.modeling_plan import (
    GeometryVerificationReport,
    ModelingPlan,
    SpatialConflict,
    SpatialConflictType,
    SpatialConflict,
    SpatialConflictType,
    VerificationCheck,
    VerificationStatus,
)

CallTool = Callable[[str, dict], Awaitable[ToolResult]]


def _close(actual: float, expected: float, tolerance: float = 0.02) -> bool:
    return abs(actual - expected) <= tolerance


def _axis_size(data: dict, axis: str) -> float | None:
    minimum = data.get("min")
    maximum = data.get("max")
    key = axis.lower()
    if not isinstance(minimum, dict) or not isinstance(maximum, dict):
        return None
    if key not in minimum or key not in maximum:
        return None
    return float(maximum[key]) - float(minimum[key])


async def verify_geometry(plan: ModelingPlan, call_tool: CallTool) -> GeometryVerificationReport:
    checks: list[VerificationCheck] = []
    conflicts: list[SpatialConflict] = []
    evidence: dict = {}

    body_result = await call_tool("get_body_count", {})
    evidence["body_count"] = body_result.to_dict()
    if body_result.success:
        actual = int(body_result.data.get("body_count", -1))
        status = VerificationStatus.PASS if actual == plan.expected_body_count else VerificationStatus.FAIL
        checks.append(VerificationCheck(name="body_count", status=status, expected=plan.expected_body_count, actual=actual))
        if status == VerificationStatus.FAIL:
            conflicts.append(SpatialConflict(
                conflict_type=SpatialConflictType.TOPOLOGY,
                target="model",
                detail="实体数量与契约拓扑预期不一致",
                expected=plan.expected_body_count,
                actual=actual,
                remedy="检查 new_body/join/cut 及试错残留实体",
            ))
    else:
        checks.append(VerificationCheck(name="body_count", status=VerificationStatus.INDETERMINATE, detail=body_result.error))

    bbox_result = await call_tool("get_bounding_box", {"target": "model"})
    evidence["bounding_box"] = bbox_result.to_dict()
    if bbox_result.success:
        size = bbox_result.data.get("size", {})
        for axis in ("x", "y", "z"):
            actual = float(size.get(axis, -1))
            expected = float(plan.expected_bbox_cm[axis])
            status = VerificationStatus.PASS if _close(actual, expected) else VerificationStatus.FAIL
            checks.append(VerificationCheck(name=f"bbox_{axis}", status=status, expected=expected, actual=actual))
            if status == VerificationStatus.FAIL:
                conflicts.append(SpatialConflict(
                    conflict_type=SpatialConflictType.EXTENT,
                    target=f"model.{axis}",
                    detail="模型包围盒尺寸与契约预期不一致",
                    expected=expected,
                    actual=actual,
                    remedy="定位产生该轴向偏差的最小特征并局部修正",
                ))
    else:
        checks.append(VerificationCheck(name="bounding_box", status=VerificationStatus.INDETERMINATE, detail=bbox_result.error))

    for section in plan.sections:
        result = await call_tool("measure_section", {"axis": plan.main_axis, "position_cm": section.axis_position_cm})
        evidence[f"section:{section.segment}"] = result.to_dict()
        if not result.success:
            checks.append(VerificationCheck(name=f"section:{section.segment}", status=VerificationStatus.INDETERMINATE, detail=result.error))
            continue
        actual = float(result.data.get("diameter_cm", -1))
        status = VerificationStatus.PASS if _close(actual, section.diameter_cm, section.tolerance_cm) else VerificationStatus.FAIL
        checks.append(VerificationCheck(name=f"section:{section.segment}", status=status, expected=section.diameter_cm, actual=actual))
        if status == VerificationStatus.FAIL:
            conflicts.append(SpatialConflict(
                conflict_type=SpatialConflictType.EXTENT,
                target=section.segment,
                detail="主体段截面尺寸与契约不一致",
                expected=section.diameter_cm,
                actual=actual,
                remedy="仅修正该主体段轮廓或生成特征",
            ))

    for feature in plan.features:
        result = await call_tool("inspect_feature", {"target": feature.name})
        evidence[f"feature:{feature.name}"] = result.to_dict()
        if not result.success:
            checks.append(VerificationCheck(name=f"feature:{feature.name}", status=VerificationStatus.INDETERMINATE, detail=result.error))
            continue
        data = result.data
        actual_type = str(data.get("type", "")).lower()
        type_ok = feature.feature_type.lower() in actual_type
        if feature.feature_type in {"keyway", "slot"}:
            type_ok = "extrude" in actual_type
        identity_ok = str(data.get("name", "")) == feature.name and type_ok
        main_size = _axis_size(data, plan.main_axis)
        length = feature.dimensions_cm.get("length")
        extent_ok = length is None or (main_size is not None and _close(main_size, length))
        status = VerificationStatus.PASS if identity_ok and extent_ok else VerificationStatus.FAIL
        checks.append(VerificationCheck(
            name=f"feature:{feature.name}",
            status=status,
            expected={"name": feature.name, "feature_type": feature.feature_type, "axis_length_cm": length},
            actual={**data, "axis_length_cm": main_size},
        ))

        if status == VerificationStatus.FAIL:
            conflicts.append(SpatialConflict(
                conflict_type=(SpatialConflictType.TARGET_AMBIGUITY if not identity_ok else SpatialConflictType.EXTENT),
                target=feature.name,
                detail="局部特征身份或空间范围与契约不一致",
                expected={"type": feature.feature_type, "axis_length_cm": length},
                actual={"name": data.get("name"), "type": data.get("type"), "axis_length_cm": main_size},
                remedy="重新解析语义目标，或仅修正该局部特征的位置和范围",
            ))

    statuses = {check.status for check in checks}
    if VerificationStatus.FAIL in statuses:
        status = VerificationStatus.FAIL
    elif VerificationStatus.INDETERMINATE in statuses or not checks:
        status = VerificationStatus.INDETERMINATE
    else:
        status = VerificationStatus.PASS
    return GeometryVerificationReport(
        status=status,
        contract_hash=plan.contract_hash,
        checks=checks,
        conflicts=conflicts,
        tool_evidence=evidence,
    )


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
