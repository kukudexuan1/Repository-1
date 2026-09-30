from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from app.agent import AgentLoop
from app.schemas.common import CadTarget
from app.schemas.session_state import SessionState, UserIntent
from app.state import session_manager

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessageRequest(BaseModel):
    message: str
    session_key: str
    target_cad: CadTarget = CadTarget.INVENTOR


class ChatMessageResponse(BaseModel):
    session_id: str
    reply: str
    design_stage: str
    tool_calls_made: list[str]
    deliverables: list[str]
    awaiting_decision: bool = False
    decision_id: str = ""


@router.post("/message")
async def chat_message(req: ChatMessageRequest) -> ChatMessageResponse:
    state = session_manager.get_by_session_key(req.session_key)
    if state is None:
        state = SessionState(
            session_id=uuid4(), user_intent=UserIntent(target_cad=req.target_cad)
        )
        session_manager.create(state)
        session_manager.bind_session_key(req.session_key, state.session_id)

    agent = AgentLoop(session=state)
    result = await agent.run(req.message)
    session_manager.update(result.session)

    deliverables = [d.path for d in result.session.deliverables]
    if result.session.geometry_file and result.session.geometry_file not in deliverables:
        deliverables.append(result.session.geometry_file)

    return ChatMessageResponse(
        session_id=str(result.session.session_id),
        reply=result.content,
        design_stage=result.session.design_stage.value,
        tool_calls_made=result.tool_calls_made,
        deliverables=deliverables,
        awaiting_decision=result.awaiting_decision,
        decision_id=result.decision_id,
    )
