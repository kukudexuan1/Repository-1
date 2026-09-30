from __future__ import annotations

from uuid import uuid4

import pytest

from app.schemas.calculation_record import CalculationRecord
from app.schemas.common import Quantity
from app.schemas.parameter_ledger import ParameterSource, ParameterStatus
from app.schemas.session_state import SessionState
from app.services.compute import ledger
from app.services.report.renderer import ensure_report_inputs_current


def _baseline() -> SessionState:
    session = SessionState(session_id=uuid4())
    session.ledger.commit(
        "input_power_kW",
        Quantity(value=7.5, unit="kW"),
        ParameterSource.USER_GIVEN,
        status=ParameterStatus.CONFIRMED,
    )
    session.add_calculation(
        CalculationRecord(
            record_id="calc#1",
            title="torque",
            inputs={"input_power_kW": Quantity(value=7.5, unit="kW")},
            result={"torque": Quantity(value=75, unit="N*m")},
            depends_on=["input_power_kW"],
            source="test",
        )
    )
    session.ledger.commit(
        "torque",
        Quantity(value=75, unit="N*m"),
        ParameterSource.CALCULATED,
        basis=["calc#1"],
        status=ParameterStatus.CONFIRMED,
    )
    session.add_calculation(
        CalculationRecord(
            record_id="calc#2",
            title="shaft",
            inputs={"torque": Quantity(value=75, unit="N*m")},
            result={"shaft_diameter_mm": Quantity(value=40, unit="mm")},
            depends_on=["torque"],
            source="test",
        )
    )
    session.ledger.commit(
        "shaft_diameter_mm",
        Quantity(value=40, unit="mm"),
        ParameterSource.CALCULATED,
        basis=["calc#2"],
        status=ParameterStatus.CONFIRMED,
    )
    return session


def _change(session: SessionState, mode: str) -> None:
    ledger.commit_parameter(
        session,
        symbol="input_power_kW",
        value=Quantity(value=11, unit="kW"),
        source=ParameterSource.USER_GIVEN,
        propagation_mode=mode,
    )


def test_none_mode_leaves_gold_nodes_usable() -> None:
    session = _baseline()
    _change(session, "none")
    assert not session.calculations["calc#1"].stale
    assert ledger.resolve_for_geometry(session, "torque").value == 75
    ensure_report_inputs_current(session)


def test_direct_mode_marks_only_direct_dependents() -> None:
    session = _baseline()
    _change(session, "direct")
    assert session.calculations["calc#1"].stale
    assert not session.calculations["calc#2"].stale
    assert session.ledger.get("torque").status == ParameterStatus.CONFIRMED
    with pytest.raises(ValueError, match="calc#1"):
        ensure_report_inputs_current(session)


def test_recursive_mode_blocks_all_downstream_nodes() -> None:
    session = _baseline()
    _change(session, "recursive")
    assert session.calculations["calc#1"].stale
    assert session.ledger.get("torque").status == ParameterStatus.STALE
    assert session.calculations["calc#2"].stale
    assert session.ledger.get("shaft_diameter_mm").status == ParameterStatus.STALE
    with pytest.raises(ledger.LedgerError):
        ledger.resolve_for_geometry(session, "shaft_diameter_mm")
    with pytest.raises(ValueError):
        ensure_report_inputs_current(session)


def test_full_mode_marks_every_other_node_stale() -> None:
    session = _baseline()
    _change(session, "full")
    assert all(record.stale for record in session.calculations.values())
    assert session.ledger.get("torque").status == ParameterStatus.STALE
    assert session.ledger.get("shaft_diameter_mm").status == ParameterStatus.STALE
    assert session.ledger.get("input_power_kW").status == ParameterStatus.TENTATIVE
