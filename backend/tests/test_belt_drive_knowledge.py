from __future__ import annotations

import pytest

from app.services.compute import formula_lib
from app.services.knowledge import loader


def test_belt_family_exposes_complete_design_inputs() -> None:
    template = loader.get_spec_template("belt_drive")
    keys = {item["key"] for item in template["items"]}

    assert {
        "transmitted_power",
        "driver_speed",
        "driven_speed",
        "required_ratio",
        "belt_type",
        "driver_pulley_diameter",
        "driven_pulley_diameter",
        "center_distance",
        "belt_length",
        "wrap_angle_min",
        "belt_count",
        "initial_tension",
        "allowable_shaft_load",
        "key_connection",
        "tensioning_method",
        "guard_requirement",
    } <= keys


def test_belt_standard_lookup_filters_by_section() -> None:
    result = loader.select_part("v_belt", belt_type="A")

    assert result["candidate_count"] == 1
    assert result["candidates"][0]["section"] == "A"
    assert result["standard"] == "GB/T 11544-2012"


def test_belt_series_rounding() -> None:
    length = loader.round_to_series("belt_reference_lengths", 1830.4)
    diameter = loader.round_to_series("v_belt_pulley_diameters", 419)

    assert length["rounded_value"] == 1800
    assert diameter["rounded_value"] == 450


def solve(formula_id: str, inputs: dict[str, tuple[float, str]]):
    return formula_lib.solve(
        formula_id,
        {
            key: __import__("app.schemas.common", fromlist=["Quantity"]).Quantity(
                value=value, unit=unit
            )
            for key, (value, unit) in inputs.items()
        },
        record_id="calc#belt-test",
    )


def test_belt_formula_chain_matches_reference_design() -> None:
    speed = solve(
        "belt_speed",
        {"d_d1": (100, "mm"), "n_1": (1440, "r/min")},
    )
    length = solve(
        "belt_length_from_center",
        {
            "a_0": (500, "mm"),
            "d_d1": (100, "mm"),
            "d_d2": (400, "mm"),
        },
    )
    wrap = solve(
        "belt_wrap_angle",
        {"d_d1": (100, "mm"), "d_d2": (400, "mm"), "a": (554.8, "mm")},
    )

    assert speed.result["v"].value == pytest.approx(7.54, abs=0.01)
    assert length.result["L_d0"].value == pytest.approx(1830.4, abs=0.2)
    assert wrap.result["alpha_1"].value == pytest.approx(149.0, abs=0.2)
    assert wrap.verdict.value == "pass"


def test_belt_wrap_angle_rejects_insufficient_center_distance() -> None:
    record = solve(
        "belt_wrap_angle",
        {"d_d1": (100, "mm"), "d_d2": (400, "mm"), "a": (150, "mm")},
    )

    assert record.verdict.value == "fail"


def test_belt_power_and_tension_formulas() -> None:
    power = solve("belt_design_power", {"K_A": (1, ""), "P": (3.7, "kW")})
    tension = solve(
        "belt_initial_tension",
        {
            "K_alpha": (0.92, ""),
            "P_ca": (3.7, "kW"),
            "z": (3, ""),
            "v": (7.54, "m/s"),
            "q": (0.105, "kg/m"),
        },
    )

    assert power.result["P_ca"].value == pytest.approx(3.7)
    assert tension.result["F_0"].value == pytest.approx(146.4, abs=0.5)
