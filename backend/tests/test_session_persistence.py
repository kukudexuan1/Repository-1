"""会话持久化：设计台账、计算记录、Gate、待决问题都要能跨进程续接。"""

from __future__ import annotations

import uuid

from app.core.session_state_manager import SessionStateManager
from app.core.session_store import SessionStore
from app.schemas.calculation_record import CalculationRecord, Verdict
from app.schemas.common import Quantity
from app.schemas.decision import DecisionKind, DecisionOption, PendingDecision
from app.schemas.design_spec import SpecStatus
from app.schemas.design_stage import DesignStage, Gate, SessionMode
from app.schemas.parameter_ledger import ParameterSource, ParameterStatus
from app.schemas.session_state import SessionState


def _rich_session() -> SessionState:
    session = SessionState(session_id=uuid.uuid4(), mode=SessionMode.DESIGN)
    session.design_stage = DesignStage.DETAIL_CALCULATION
    session.design_spec.family = "gearbox_single_stage"
    session.design_spec.family_label = "单级圆柱齿轮减速器"
    session.design_spec.upsert(
        "transmitted_power", value="4 kW", status=SpecStatus.USER_GIVEN, label="输入功率"
    )
    session.add_calculation(
        CalculationRecord(
            record_id="calc#1",
            title="输入轴转矩",
            formula_id="shaft_torque_from_power",
            expression="T = 9550000 * P / n",
            result={"T": Quantity(value=26527.8, unit="N*mm")},
            verdict=Verdict.NOT_APPLICABLE,
            source="机械设计 式15-1",
        )
    )
    session.calc_seq = 1
    session.ledger.commit(
        "T_1",
        Quantity(value=26527.8, unit="N*mm"),
        ParameterSource.CALCULATED,
        name="小齿轮转矩",
        basis=["calc#1"],
        status=ParameterStatus.CONFIRMED,
        group="总体",
    )
    session.approve_gate(Gate.SCHEME_CONFIRMED, statement="选软齿面方案")
    session.pending_decision = PendingDecision(
        decision_id="dec-abc123",
        kind=DecisionKind.CLARIFY,
        question="每天工作几小时？",
        options=[DecisionOption(label="8 小时"), DecisionOption(label="16 小时")],
        suspended_messages=[{"role": "system", "content": "sys"}],
        suspended_tool_call_id="c9",
    )
    return session


def test_round_trip_preserves_design_evidence(tmp_path):
    store = SessionStore(tmp_path / "t.db")
    assert store.available

    original = _rich_session()
    store.save(original)
    loaded = store.load(original.session_id)

    assert loaded is not None
    assert loaded.design_stage == DesignStage.DETAIL_CALCULATION
    assert loaded.design_spec.family_label == "单级圆柱齿轮减速器"
    assert loaded.design_spec.get("transmitted_power").status == SpecStatus.USER_GIVEN

    entry = loaded.ledger.get("T_1")
    assert entry is not None
    assert entry.source == ParameterSource.CALCULATED
    assert entry.basis == ["calc#1"]
    assert entry.value.unit == "N*mm"
    assert abs(entry.value.value - 26527.8) < 1e-6

    record = loaded.calculations["calc#1"]
    assert record.source == "机械设计 式15-1"
    assert record.result["T"].unit == "N*mm"

    assert loaded.gate_passed(Gate.SCHEME_CONFIRMED)
    assert loaded.calc_seq == 1
    store.close()


def test_pending_decision_survives_restart(tmp_path):
    store = SessionStore(tmp_path / "t.db")
    original = _rich_session()
    store.save(original)

    loaded = store.load(original.session_id)
    assert loaded.pending_decision is not None
    assert loaded.pending_decision.decision_id == "dec-abc123"
    assert loaded.pending_decision.suspended_tool_call_id == "c9"
    assert len(loaded.pending_decision.options) == 2
    store.close()


def test_manager_falls_back_to_store_on_cache_miss(tmp_path):
    store = SessionStore(tmp_path / "t.db")
    manager = SessionStateManager(store=store)
    session = _rich_session()
    manager.create(session)
    manager.bind_session_key("front-end-key", session.session_id)

    # 模拟进程重启：新 manager，同一个数据库
    revived = SessionStateManager(store=SessionStore(tmp_path / "t.db"))
    by_id = revived.get(session.session_id)
    assert by_id is not None
    assert by_id.ledger.get("T_1") is not None

    by_key = revived.get_by_session_key("front-end-key")
    assert by_key is not None
    assert by_key.session_id == session.session_id
    store.close()


def test_list_recent_and_delete(tmp_path):
    store = SessionStore(tmp_path / "t.db")
    manager = SessionStateManager(store=store)
    session = _rich_session()
    manager.create(session)

    rows = manager.list_recent()
    assert any(r["session_id"] == str(session.session_id) for r in rows)
    assert rows[0]["family"] == "gearbox_single_stage"

    assert manager.delete(session.session_id) is True
    assert manager.get(session.session_id) is None
    store.close()


def test_store_degrades_gracefully_on_bad_path(tmp_path):
    """持久化不可用时应降级为内存模式，而不是让设计流程崩掉。"""
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    store = SessionStore(blocker / "nested" / "t.db")
    assert store.available is False

    manager = SessionStateManager(store=store)
    session = _rich_session()
    manager.create(session)
    assert manager.get(session.session_id) is not None
