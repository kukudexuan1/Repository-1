from __future__ import annotations

import hashlib

from app.schemas.modeling_contract import ModelingContract
from app.schemas.modeling_plan import FeatureExpectation, ModelingPlan, SectionExpectation


def contract_hash(contract: ModelingContract) -> str:
    payload = contract.model_dump_json(exclude={"created_at"})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def _bbox(contract: ModelingContract) -> tuple[dict[str, float], dict[str, float]]:
    origin = [float(value) for value in contract.coordinate_system.origin_coords]
    minimum = {"x": origin[0], "y": origin[1], "z": origin[2]}
    maximum = dict(minimum)
    if not contract.body_segments:
        return minimum, maximum

    axis = _value(contract.coordinate_system.axis).lower()
    starts = [segment.axis_start_cm for segment in contract.body_segments]
    ends = [segment.axis_end_cm for segment in contract.body_segments]
    minimum[axis] += min(starts)
    maximum[axis] += max(ends)

    radial_axes = [name for name in ("x", "y", "z") if name != axis]
    extents = []
    for segment in contract.body_segments:
        extents.append(max(
            float(segment.diameter_cm or 0.0) / 2.0,
            float(segment.diameter_end_cm or 0.0) / 2.0,
            float(segment.width_cm or 0.0) / 2.0,
            float(segment.height_cm or 0.0) / 2.0,
        ))
    radius = max(extents, default=0.0)
    for name in radial_axes:
        minimum[name] -= radius
        maximum[name] += radius
    return minimum, maximum


def compile_contract(contract: ModelingContract) -> ModelingPlan:
    """Compile target facts into verification expectations, never tool steps."""
    axis = _value(contract.coordinate_system.axis)
    axis_index = {"X": 0, "Y": 1, "Z": 2}[axis]
    origin_axis = float(contract.coordinate_system.origin_coords[axis_index])
    minimum, maximum = _bbox(contract)
    size = {name: maximum[name] - minimum[name] for name in ("x", "y", "z")}
    sections = [
        SectionExpectation(
            segment=segment.name,
            axis_position_cm=origin_axis + (segment.axis_start_cm + segment.axis_end_cm) / 2,
            diameter_cm=float(segment.diameter_cm or 0.0),
        )
        for segment in contract.body_segments
        if segment.shape in {"cylinder", "cone"} and segment.diameter_cm is not None
    ]
    features = [
        FeatureExpectation(
            name=feature.name,
            feature_type=feature.feature_type,
            target_segment=feature.target_segment,
            axis_start_cm=origin_axis + feature.axis_start_cm,
            axis_end_cm=origin_axis + feature.axis_end_cm,
            radial_direction=_value(feature.angular_position),
            dimensions_cm=feature.dimensions_cm,
        )
        for feature in contract.local_features
    ]
    return ModelingPlan(
        contract_hash=contract_hash(contract),
        part_name=contract.part_name,
        part_type=contract.part_type,
        main_axis=axis,
        placement_policy=_value(contract.placement_policy),
        expected_bbox_cm=size,
        expected_bbox_min_cm=minimum,
        expected_bbox_max_cm=maximum,
        sections=sections,
        features=features,
    )

