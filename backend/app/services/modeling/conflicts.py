from __future__ import annotations

import math
from typing import Any

from app.schemas.modeling_contract import ModelingContract
from app.schemas.modeling_plan import SpatialConflict, SpatialConflictType


def _vector(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _norm(vector: list[float]) -> float:
    return math.sqrt(_dot(vector, vector))


def _parallel(left: list[float], right: list[float], tolerance: float = 1e-3) -> bool:
    denominator = _norm(left) * _norm(right)
    return denominator > 0 and abs(abs(_dot(left, right) / denominator) - 1.0) <= tolerance


def inspect_spatial_result(
    tool_name: str,
    arguments: dict[str, Any],
    result_data: dict[str, Any],
    contract: ModelingContract | None,
) -> list[SpatialConflict]:
    """Detect contradictions in observed tool facts without selecting a repair tool."""
    conflicts: list[SpatialConflict] = []
    data = result_data.get("data") if isinstance(result_data.get("data"), dict) else result_data

    if tool_name == "work_plane":
        plane = data.get("plane") if isinstance(data.get("plane"), dict) else data
        origin = _vector(plane.get("origin"))
        normal = _vector(plane.get("normal"))
        u = _vector(plane.get("u"))
        v = _vector(plane.get("v"))
        if not all((origin, normal, u, v)):
            conflicts.append(SpatialConflict(
                conflict_type=SpatialConflictType.PLANE_ORIENTATION,
                target=str(plane.get("name", arguments.get("reference1", ""))),
                detail="工作平面缺少完整的数值 origin/normal/u/v，不能安全映射草图坐标",
                actual={"origin": origin, "normal": normal, "u": u, "v": v},
                remedy="重新查询平面数值 frame；不要根据平面名称猜测朝向",
            ))
        elif not (_parallel(normal, [
            u[1] * v[2] - u[2] * v[1],
            u[2] * v[0] - u[0] * v[2],
            u[0] * v[1] - u[1] * v[0],
        ]) and abs(_dot(u, v)) <= 1e-3):
            conflicts.append(SpatialConflict(
                conflict_type=SpatialConflictType.PLANE_ORIENTATION,
                target=str(plane.get("name", "")),
                detail="工作平面的 u/v/normal 不构成一致的正交坐标框架",
                actual={"normal": normal, "u": u, "v": v},
                remedy="停止在该平面绘图并重新获取数值 frame",
            ))

    error_text = str(result_data.get("error", ""))
    lowered = error_text.lower()
    if "ambiguous" in lowered or "multiple" in lowered and "match" in lowered:
        conflicts.append(SpatialConflict(
            conflict_type=SpatialConflictType.TARGET_AMBIGUITY,
            target=str(arguments.get("target", "")),
            detail=error_text,
            remedy="使用稳定语义名称或唯一 ID 重新解析目标",
        ))
    if "intersect" in lowered or "outside" in lowered or "float" in lowered:
        conflicts.append(SpatialConflict(
            conflict_type=SpatialConflictType.INTERSECTION,
            target=str(arguments.get("target", arguments.get("name", ""))),
            detail=error_text,
            remedy="读取主体和候选特征包围盒，局部修正原点或方向",
        ))
    if "body" in lowered and ("count" in lowered or "multiple" in lowered):
        conflicts.append(SpatialConflict(
            conflict_type=SpatialConflictType.TOPOLOGY,
            target="model",
            detail=error_text,
            remedy="检查布尔操作及实体数，避免遗留 new_body",
        ))

    if contract and tool_name in {"extrude", "cut_keyway", "hole"}:
        direction = str(arguments.get("direction", arguments.get("radial_direction", ""))).upper()
        axis = str(getattr(contract.coordinate_system.axis, "value", contract.coordinate_system.axis))
        if direction.endswith(axis) and tool_name == "cut_keyway":
            conflicts.append(SpatialConflict(
                conflict_type=SpatialConflictType.DIRECTION,
                target=str(arguments.get("name", "")),
                detail="键槽径向方向与主轴平行",
                expected="垂直于主轴的径向方向",
                actual=direction,
                remedy="根据契约 angular_position 和真实平面 normal 重新确定方向",
            ))
    return conflicts
