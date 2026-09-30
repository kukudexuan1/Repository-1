"""流式对话接口，支持三种入口模式、历史会话续接与客户端中断。

mode 决定进入哪条链路，落到 SessionState.active_agent：
  plan       全系统流程：主设计模型编排，active_agent=none
  modeling   直接进入建模子 Agent：active_agent=modeling（粘滞）
  simulation 直接进入仿真子 Agent：active_agent=analysis（粘滞）

会话解析优先级：显式 session_id（续接历史会话）> session_key（浏览器本地键）>
新建。所有状态由 SessionStateManager 落 SQLite，进程重启后可原样续接。

AgentLoop.run 接收同步的 stream_callback，这里用一个线程安全队列把回调产生的
增量转成 SSE 事件异步吐给前端；run 结束后再补一个 final 事件带上完整结果。

客户端中断：前端点"停止"会 abort fetch，导致本生成器被关闭。此时取消正在运行
的 AgentLoop 任务以停止继续消耗模型额度，并把已产生的部分会话状态落库。
"""

from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent import AgentLoop
from app.core.experiment import resolve_condition
from app.schemas.common import CadTarget
from app.schemas.session_state import ActiveAgent, SessionState, UserIntent
from app.state import session_manager

router = APIRouter(prefix="/api/stream", tags=["stream"])

_MODE_TO_AGENT = {
    "plan": ActiveAgent.NONE,
    "modeling": ActiveAgent.MODELING,
    "simulation": ActiveAgent.ANALYSIS,
}


class StreamChatRequest(BaseModel):
    message: str
    session_key: str
    mode: str = "plan"
    target_cad: CadTarget = CadTarget.INVENTOR
    session_id: str | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _resolve_session(req: StreamChatRequest) -> SessionState:
    """按 session_id > session_key > 新建 的优先级取会话。"""
    if req.session_id:
        try:
            existing = session_manager.get(UUID(req.session_id))
        except ValueError:
            existing = None
        if existing is not None:
            session_manager.bind_session_key(req.session_key, existing.session_id)
            return existing

    state = session_manager.get_by_session_key(req.session_key)
    if state is not None:
        return state

    state = SessionState(
        session_id=uuid4(), user_intent=UserIntent(target_cad=req.target_cad)
    )
    session_manager.create(state)
    session_manager.bind_session_key(req.session_key, state.session_id)
    return state


@router.post("/chat")
async def stream_chat(
    req: StreamChatRequest,
    x_experiment_condition: str | None = Header(default=None),
) -> StreamingResponse:
    state = _resolve_session(req)

    # 指令模式：只在无待决问题、且不是 /exit 时切换入口 agent，避免打断中断恢复。
    desired = _MODE_TO_AGENT.get(req.mode, ActiveAgent.NONE)
    if state.pending_decision is None and req.message.strip() != "/exit":
        if desired != ActiveAgent.NONE:
            state.active_agent = desired
        elif req.message.strip():
            state.active_agent = ActiveAgent.NONE

    allowed_tools, flags = resolve_condition(x_experiment_condition)
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def stream_callback(agent: str, delta: str) -> None:
        if delta:
            loop.call_soon_threadsafe(
                queue.put_nowait, {"kind": "delta", "agent": agent, "delta": delta}
            )

    async def runner() -> None:
        agent = AgentLoop(session=state, allowed_tools=allowed_tools, experiment_flags=flags)
        try:
            result = await agent.run(req.message, stream_callback=stream_callback)
            session_manager.update(result.session)
            deliverables = [d.path for d in result.session.deliverables]
            if (
                result.session.geometry_file
                and result.session.geometry_file not in deliverables
            ):
                deliverables.append(result.session.geometry_file)
            await queue.put(
                {
                    "kind": "final",
                    "session_id": str(result.session.session_id),
                    "reply": result.content,
                    "design_stage": result.session.design_stage.value,
                    "active_agent": result.session.active_agent.value,
                    "tool_calls_made": result.tool_calls_made,
                    "deliverables": deliverables,
                    "awaiting_decision": result.awaiting_decision,
                    "decision_id": result.decision_id,
                }
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            await queue.put({"kind": "error", "message": str(exc)})
        finally:
            await queue.put({"kind": "__done__"})

    async def event_stream():
        task = asyncio.create_task(runner())
        try:
            while True:
                item = await queue.get()
                kind = item.get("kind")
                if kind == "__done__":
                    break
                if kind == "delta":
                    yield _sse("delta", {"agent": item["agent"], "delta": item["delta"]})
                elif kind == "final":
                    yield _sse("final", item)
                elif kind == "error":
                    yield _sse("error", item)
        finally:
            # 客户端中断时生成器被关闭：取消正在跑的 AgentLoop，避免继续消耗模型
            # 额度；并把已产生的部分会话状态落库，使已生成的上下文不丢失。
            if not task.done():
                task.cancel()
                try:
                    await task
                except BaseException:  # noqa: BLE001
                    pass
                try:
                    session_manager.update(state)
                except Exception:  # noqa: BLE001
                    pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
