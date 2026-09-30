from __future__ import annotations

import re
from typing import Any

from app.schemas.modeling_contract import (
    BodySegment,
    ContractProvenance,
    CoordinateSystem,
    LocalFeature,
    ModelingContract,
    UnitConversionTable,
)
from app.schemas.modeling_plan import ValidationIssue, ValidationReport

_DIRECTION_RE = re.compile(r"([+-][XYZ])")


def _direction(value: str) -> str:
    match = _DIRECTION_RE.search(value.upper())
    return match.group(1) if match else value.upper()


def _plane_direction(plane: str) -> str | None:
    match = re.match(r"(XY|XZ|YZ)@([XYZ])=([-+]?\d+(?:\.\d+)?)", plane.upper())
    if not match:
        return None
    normal = ({"XY": "Z", "XZ": "Y", "YZ": "X"})[match.group(1)]
    offset = float(match.group(3))
    return ("+" if offset >= 0 else "-") + normal


def migrate_v1_contract(raw: dict[str, Any]) -> tuple[ModelingContract | None, ValidationReport]:
    if int(raw.get("schema_version", 1)) >= 2:
        contract = ModelingContract.model_validate(raw)
        return contract, ValidationReport(valid=True)
    issues: list[ValidationIssue] = []
    cs = raw.get("coordinate_system", {})
    axis = str(cs.get("axis", "X")).upper()
    radial_up = _direction(str(cs.get("radial_up", "+Z")))
    radial_side = _direction(str(cs.get("radial_side", "+Y")))
    features: list[LocalFeature] = []
    for index, item in enumerate(raw.get("local_features", [])):
        item = dict(item)
        if item.get("feature_type") in {"keyway", "slot"}:
            angular = _direction(str(item.get("angular_position", radial_up)))
            plane_direction = _plane_direction(str(item.get("sketch_plane", "")))
            cut = _direction(str(item.get("cut_direction", "")))
            expected_cut = ("-" if angular.startswith("+") else "+") + angular[-1]
            conflicts: list[str] = []
            if angular[-1] == axis:
                conflicts.append("angular_position 与主轴平行")
            if plane_direction and plane_direction != angular:
                conflicts.append("sketch_plane 与 angular_position 不一致")
            if cut and cut != expected_cut:
                conflicts.append("cut_direction 未指向轴心")
            if conflicts:
                issues.append(ValidationIssue(
                    code="migration.spatial_conflict",
                    path=f"local_features.{index}",
                    message="；".join(conflicts),
                    remedy="根据目标段和唯一周向方向重新生成 v2 契约",
                ))
            item["angular_position"] = angular
        features.append(LocalFeature.model_validate(item))
    if issues:
        return None, ValidationReport(valid=False, issues=issues)
    contract = ModelingContract(
        schema_version=2,
        provenance=ContractProvenance(
            source_schema_version=1,
            migrated_from=str(raw.get("session_id", "legacy")),
            migration_notes=["派生平面、原点和切削方向将在 ModelingCompiler 中重新计算"],
        ),
        session_id=str(raw.get("session_id", "")),
        part_name=str(raw.get("part_name", "legacy_part")),
        part_type=str(raw.get("part_type", "custom")),
        coordinate_system=CoordinateSystem(
            axis=axis,
            origin=str(cs.get("origin", "left_end_center")),
            origin_coords=cs.get("origin_coords", [0.0, 0.0, 0.0]),
            radial_up=radial_up,
            radial_side=radial_side,
            notes=str(cs.get("notes", "")),
        ),
        body_segments=[BodySegment.model_validate(item) for item in raw.get("body_segments", [])],
        local_features=features,
        unit_table=UnitConversionTable.model_validate(raw.get("unit_table", {})),
        assumptions=list(raw.get("assumptions", [])),
        open_questions=list(raw.get("open_questions", [])),
    )
    return contract, ValidationReport(valid=True)
