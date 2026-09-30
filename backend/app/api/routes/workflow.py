from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.agent import AgentLoop
from app.core.experiment import resolve_condition
from app.schemas.session_state import SessionState
from app.state import session_manager

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


class RunWorkflowRequest(BaseModel):
    session_id: UUID
    user_prompt: str


class WorkflowResponse(BaseModel):
    session_id: str
    reply: str
    design_stage: str
    tool_calls_made: list[str]
    tool_events: list[dict] = Field(default_factory=list)
    awaiting_decision: bool = False
    decision_id: str = ""
    experiment_condition: str = ""


@router.post("/run")
async def run_workflow(
    req: RunWorkflowRequest,
    x_experiment_condition: str | None = Header(default=None),
    x_propagation_mode: str | None = Header(default=None),
    x_max_agent_iterations: int | None = Header(default=None),
) -> WorkflowResponse:
    state = session_manager.get(req.session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="session not found")

    allowed_tools, flags = resolve_condition(x_experiment_condition)
    if x_propagation_mode:
        mode = x_propagation_mode.strip().lower()
        if mode not in {"none", "full", "direct", "recursive"}:
            raise HTTPException(status_code=400, detail="invalid propagation mode")
        flags["propagation_mode"] = mode
    agent = AgentLoop(session=state, allowed_tools=allowed_tools, experiment_flags=flags)
    if x_max_agent_iterations is not None:
        if not 1 <= x_max_agent_iterations <= AgentLoop.MAX_ITERATIONS:
            raise HTTPException(status_code=400, detail="invalid max agent iterations")
        agent.max_iterations = x_max_agent_iterations
    result = await agent.run(req.user_prompt)
    session_manager.update(result.session)

    return WorkflowResponse(
        session_id=str(result.session.session_id),
        reply=result.content,
        design_stage=result.session.design_stage.value,
        tool_calls_made=result.tool_calls_made,
        tool_events=result.tool_events,
        awaiting_decision=result.awaiting_decision,
        decision_id=result.decision_id,
        experiment_condition=x_experiment_condition or "",
    )


@router.get("/{session_id}/state")
def get_state(session_id: UUID) -> SessionState:
    state = session_manager.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="session not found")
    return state
