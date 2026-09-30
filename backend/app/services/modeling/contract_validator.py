from __future__ import annotations

from app.schemas.modeling_contract import ModelingContract
from app.schemas.modeling_plan import ValidationIssue, ValidationReport, ValidationSeverity


def _axis_name(value: object) -> str:
    return str(getattr(value, "value", value)).lstrip("+-").upper()


def _direction_vector(value: object) -> tuple[int, int, int]:
    raw = str(getattr(value, "value", value)).upper()
    sign = -1 if raw.startswith("-") else 1
    axis = raw.lstrip("+-")
    basis = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[axis]
    return tuple(sign * item for item in basis)


def _cross(left: tuple[int, int, int], right: tuple[int, int, int]) -> tuple[int, int, int]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _issue(code: str, path: str, message: str, remedy: str = "") -> ValidationIssue:
    return ValidationIssue(code=code, path=path, message=message, remedy=remedy)


def validate_contract(contract: ModelingContract) -> ValidationReport:
    issues: list[ValidationIssue] = []
    axis = _axis_name(contract.coordinate_system.axis)
    radial = _axis_name(contract.coordinate_system.radial_up)
    side = _axis_name(contract.coordinate_system.radial_side)
    if radial == axis:
        issues.append(_issue("coordinate.radial_parallel", "coordinate_system.radial_up", "径向方向不能与主轴平行"))
    if side in {axis, radial}:
        issues.append(_issue("coordinate.side_not_orthogonal", "coordinate_system.radial_side", "径向侧向必须与主轴和径向向上方向正交"))
    elif _cross(
        _direction_vector(contract.coordinate_system.axis),
        _direction_vector(contract.coordinate_system.radial_side),
    ) != _direction_vector(contract.coordinate_system.radial_up):
        issues.append(_issue(
            "coordinate.left_handed_frame",
            "coordinate_system.radial_side",
            "坐标方向必须满足 axis × radial_side = radial_up",
            "修正 radial_side 的符号以形成右手系",
        ))
    if len(contract.coordinate_system.origin_coords) != 3:
        issues.append(_issue("coordinate.origin_arity", "coordinate_system.origin_coords", "原点必须包含三个坐标"))
    elif any(abs(value) > 1e-9 for value in contract.coordinate_system.origin_coords):
        issues.append(ValidationIssue(
            code="coordinate.nonzero_origin",
            path="coordinate_system.origin_coords",
            message="使用非零全局原点，建模时必须按数值坐标框架映射局部坐标",
            remedy="读取平面的 origin/normal/u/v 后再映射草图坐标",
            severity=ValidationSeverity.WARNING,
        ))

    names: set[str] = set()
    previous_end: float | None = None
    for index, segment in enumerate(contract.body_segments):
        path = f"body_segments.{index}"
        if segment.name in names:
            issues.append(_issue("segment.duplicate_name", f"{path}.name", f"主体段名称重复: {segment.name}"))
        names.add(segment.name)
        if segment.axis_end_cm <= segment.axis_start_cm:
            issues.append(_issue("segment.invalid_range", path, "主体段终点必须大于起点"))
        if previous_end is not None and segment.axis_start_cm < previous_end - 1e-9:
            issues.append(_issue("segment.overlap", path, "主体段不允许重叠或逆序"))
        if previous_end is not None and segment.axis_start_cm > previous_end + 1e-9:
            issues.append(ValidationIssue(
                code="segment.gap",
                path=path,
                message="主体段之间存在间隙，请确认这是设计意图",
                remedy="若需连接，请补充连接段；若为独立实体，请明确 topology 预期",
                severity=ValidationSeverity.WARNING,
            ))
        previous_end = segment.axis_end_cm
        if segment.shape in {"cylinder", "cone"} and (segment.diameter_cm is None or segment.diameter_cm <= 0):
            issues.append(_issue("segment.invalid_diameter", f"{path}.diameter_cm", "回转段直径必须为正"))

    for index, feature in enumerate(contract.local_features):
        path = f"local_features.{index}"
        if len(feature.anchor_global_cm) != 3:
            issues.append(_issue("feature.anchor_arity", f"{path}.anchor_global_cm", "特征全局锚点必须包含三个坐标"))
        if feature.target_segment not in names:
            issues.append(_issue("feature.unknown_target", f"{path}.target_segment", f"目标主体段不存在: {feature.target_segment}"))
            continue
        target = next(segment for segment in contract.body_segments if segment.name == feature.target_segment)
        dims = feature.dimensions_cm
        if feature.axis_end_cm <= feature.axis_start_cm:
            issues.append(_issue("feature.invalid_range", path, "局部特征终点必须大于起点"))
        if feature.axis_start_cm < target.axis_start_cm - 1e-9 or feature.axis_end_cm > target.axis_end_cm + 1e-9:
            issues.append(_issue("feature.outside_target", path, "局部特征轴向范围必须完全位于目标段内"))
        if feature.feature_type in {"keyway", "slot"}:
            for key in ("length", "width", "depth"):
                if dims.get(key, 0) <= 0:
                    issues.append(_issue("keyway.invalid_dimension", f"{path}.dimensions_cm.{key}", f"键槽 {key} 必须为正"))
            if target.diameter_cm and dims.get("depth", 0) >= target.diameter_cm / 2:
                issues.append(_issue("keyway.depth_exceeds_radius", f"{path}.dimensions_cm.depth", "键槽深度必须小于目标段半径"))
            direction = str(feature.angular_position)
            normalized = next((item for item in ("+X", "-X", "+Y", "-Y", "+Z", "-Z") if item in direction), direction)
            if _axis_name(normalized) == axis:
                issues.append(_issue("keyway.radial_parallel", f"{path}.angular_position", "键槽周向方向不能与主轴平行"))
        if feature.topology_effect == "separate_body":
            issues.append(ValidationIssue(
                code="feature.multibody_risk",
                path=f"{path}.operation",
                message="局部特征会创建新实体",
                remedy="确认拓扑预期，或改用 join/cut",
                severity=ValidationSeverity.WARNING,
            ))

    if contract.open_questions:
        issues.append(_issue(
            "contract.open_questions",
            "open_questions",
            "权威建模契约仍包含未确认问题",
            "先由主设计 Agent 澄清并重新生成契约",
        ))
    if not contract.body_segments:
        issues.append(_issue("contract.empty_body", "body_segments", "契约至少需要一个主体段"))
    errors = [item for item in issues if item.severity == ValidationSeverity.ERROR]
    return ValidationReport(valid=not errors, issues=issues)
