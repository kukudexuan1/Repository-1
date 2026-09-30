from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.schemas.common import CadTarget
from app.schemas.design_stage import STAGE_LABELS, DesignStage, SessionMode
from app.schemas.session_state import SessionState, UserIntent
from app.state import session_manager

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    target_cad: CadTarget = CadTarget.INVENTOR
    mode: SessionMode = SessionMode.DESIGN


class SessionBrief(BaseModel):
    session_id: str
    design_stage: str
    stage_label: str
    mode: str
    family: str
    updated_at: str
    family_label: str = ""
    title: str = ""
    active_agent: str = "none"
    message_count: int = 0


@router.post("")
def create_session(req: CreateSessionRequest) -> SessionState:
    state = SessionState(
        session_id=uuid4(),
        mode=req.mode,
        user_intent=UserIntent(target_cad=req.target_cad),
    )
    return session_manager.create(state)


@router.get("")
def list_sessions(limit: int = 20) -> list[SessionBrief]:
    """列出最近的设计会话，用于恢复未完成的设计。"""
    out = []
    for row in session_manager.list_recent(limit):
        try:
            label = STAGE_LABELS[DesignStage(row["design_stage"])]
        except (ValueError, KeyError):
            label = row["design_stage"]
        out.append(SessionBrief(stage_label=label, **row))
    return out


@router.post("/{session_id}/clone")
def clone_session(session_id: UUID) -> SessionState:
    source = session_manager.get(session_id)
    if source is None:
        raise HTTPException(status_code=404, detail="session not found")
    clone = source.model_copy(deep=True, update={"session_id": uuid4()})
    clone.pending_decision = None
    clone.decision_history = []
    return session_manager.create(clone)


@router.get("/{session_id}")
def get_session(session_id: UUID) -> SessionState:
    state = session_manager.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="session not found")
    return state


@router.delete("/{session_id}")
def delete_session(session_id: UUID) -> dict:
    if not session_manager.delete(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return {"deleted": str(session_id)}
