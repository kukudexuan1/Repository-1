"""子 Agent 粘滞与上下文续接（不触达真实模型与 MCP）。

新架构下建模/仿真默认**不粘滞**：控制权在子 Agent 返回后立即交还主设计模型，
只有显式 stay_in_modeling/stay_in_analysis 时才停留。
"""

from __future__ import annotations

import uuid

import pytest

from app.agent.agent_loop import AgentLoop
from app.agent.modeling_agent import ModelingResult
from app.agent.tools import ToolContext, dispatch
from app.schemas.common import Quantity
from app.schemas.design_stage import Gate
from app.schemas.modeling_contract import BodySegment, CoordinateSystem, ModelingContract
from app.schemas.modeling_plan import GeometryVerificationReport, VerificationStatus
from app.schemas.parameter_ledger import ParameterSource, ParameterStatus
from app.schemas.session_state import ActiveAgent, SessionState


def _session() -> SessionState:
    session = SessionState(session_id=uuid.uuid4())
    session.ledger.commit(
        "d_shaft",
        Quantity(value=35.0, unit="mm"),
        ParameterSource.USER_GIVEN,
        status=ParameterStatus.FROZEN,
    )
    session.approve_gate(Gate.PARAMETERS_FROZEN, statement="test")
    return session


def _contract() -> ModelingContract:
    return ModelingContract(
        session_id="test",
        part_name="test_part",
        part_type="shaft",
        coordinate_system=CoordinateSystem(axis="X", origin="origin", radial_up="+Z"),
        body_segments=[
            BodySegment(
                name="shaft",
                axis_start_cm=0,
                axis_end_cm=3.5,
                diameter_cm=3.5,
            )
        ],
    )


def _fake_build(captured: dict, *, success: bool = True):
    async def build(
        execution_intent, session_id, stream_callback=None, prior_messages=None,
        contract=None, plan=None
    ):
        captured["prior"] = prior_messages
        captured["prior_len"] = len(prior_messages or [])
        msgs = list(prior_messages or [{"role": "system", "content": "sys"}])
        msgs.append({"role": "assistant", "content": "built"})
        return ModelingResult(
            success=success,
            geometry_file="D:/x.stp" if success else "",
            iterations=3,
            messages=msgs,
        )

    return build


@pytest.mark.asyncio
async def test_build_model_returns_control_by_default(monkeypatch):
    loop = AgentLoop(session=_session())
    loop.session.modeling_contract = _contract()
    captured: dict = {}
    monkeypatch.setattr(loop.modeling, "build", _fake_build(captured))

    ctx = ToolContext(session=loop.session, extras={"modeling_agent": loop.modeling})
    result = await dispatch("build_model", {"execution_intent": "make a flange"}, ctx)

    assert result["status"] == "success"
    assert result["control_returned"] is True
    assert loop.session.active_agent == ActiveAgent.NONE
    assert loop.session.modeling_messages[-1]["content"] == "built"
    assert captured["prior"] is None


@pytest.mark.asyncio
async def test_build_model_can_stay_sticky(monkeypatch):
    loop = AgentLoop(session=_session())
    loop.session.modeling_contract = _contract()
    monkeypatch.setattr(loop.modeling, "build", _fake_build({}))

    ctx = ToolContext(session=loop.session, extras={"modeling_agent": loop.modeling})
    result = await dispatch(
        "build_model",
        {"execution_intent": "调几何", "stay_in_modeling": True},
        ctx,
    )

    assert result["control_returned"] is False
    assert loop.session.active_agent == ActiveAgent.MODELING


@pytest.mark.asyncio
async def test_build_model_requires_contract():
    loop = AgentLoop(session=_session())
    ctx = ToolContext(session=loop.session, extras={"modeling_agent": loop.modeling})
    result = await dispatch("build_model", {"execution_intent": "x"}, ctx)
    assert result["status"] == "refused"
    assert "契约" in result["reason"]


@pytest.mark.asyncio
async def test_sticky_modeling_resumes_prior_messages(monkeypatch):
    session = _session()
    session.active_agent = ActiveAgent.MODELING
    session.modeling_messages = [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": "step1 done"},
    ]
    loop = AgentLoop(session=session)
    captured: dict = {}
    monkeypatch.setattr(loop.modeling, "build", _fake_build(captured))

    result = await loop.run("把倒角改小一点")

    assert captured["prior_len"] == 2
    assert loop.session.active_agent == ActiveAgent.MODELING
    assert result.active_agent == "modeling"


@pytest.mark.asyncio
async def test_exit_command_leaves_subagent_and_freezes_context():
    session = _session()
    session.active_agent = ActiveAgent.MODELING
    session.modeling_messages = [{"role": "system", "content": "sys"}]
    loop = AgentLoop(session=session)

    result = await loop.run("/exit")

    assert loop.session.active_agent == ActiveAgent.NONE
    assert result.noop is False
    assert loop.session.modeling_messages == [{"role": "system", "content": "sys"}]


@pytest.mark.asyncio
async def test_exit_at_main_agent_is_silent_noop():
    loop = AgentLoop(session=_session())
    result = await loop.run("/exit")
    assert result.noop is True
    assert result.content == ""
    assert loop.session.active_agent == ActiveAgent.NONE


@pytest.mark.asyncio
async def test_reentry_after_exit_resumes_frozen_context(monkeypatch):
    session = _session()
    session.active_agent = ActiveAgent.MODELING
    session.modeling_messages = [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": "earlier work"},
    ]
    loop = AgentLoop(session=session)
    await loop.run("/exit")
    assert loop.session.active_agent == ActiveAgent.NONE

    captured: dict = {}
    loop.session.modeling_contract = _contract()
    monkeypatch.setattr(loop.modeling, "build", _fake_build(captured))

    ctx = ToolContext(session=loop.session, extras={"modeling_agent": loop.modeling})
    await dispatch("build_model", {"execution_intent": "resume"}, ctx)

    assert captured["prior_len"] == 2
