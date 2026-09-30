from __future__ import annotations

import uuid

import pytest

from app.agent.agent_loop import AgentLoop
from app.agent.modeling_agent import ModelingResult
from app.schemas.modeling_contract import BodySegment, ModelingContract
from app.schemas.modeling_plan import GeometryVerificationReport, VerificationStatus
from app.schemas.session_state import ActiveAgent, SessionState


@pytest.mark.asyncio
async def test_sticky_edit_invalidates_previous_verification(monkeypatch) -> None:
    session = SessionState(session_id=uuid.uuid4())
    session.active_agent = ActiveAgent.MODELING
    session.modeling_contract = ModelingContract(
        session_id="test",
        part_name="shaft",
        body_segments=[BodySegment(name="shaft", axis_start_cm=0, axis_end_cm=3, diameter_cm=2)],
    )
    session.modeling_messages = [{"role": "system", "content": "sys"}]
    session.geometry_file_hash = "verified-hash"
    session.geometry_verification_report = GeometryVerificationReport(
        status=VerificationStatus.PASS,
        contract_hash="contract",
        geometry_hash="verified-hash",
    )
    loop = AgentLoop(session=session)

    async def build(**kwargs):
        assert kwargs["prior_messages"] == session.modeling_messages
        return ModelingResult(success=False, error="test", messages=session.modeling_messages)

    monkeypatch.setattr(loop.modeling, "build", build)

    await loop.run("把倒角改小一点")

    assert loop.session.geometry_file_hash == ""
    assert loop.session.geometry_verification_report is not None
    assert loop.session.geometry_verification_report.stale is True
