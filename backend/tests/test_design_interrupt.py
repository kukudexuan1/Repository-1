"""中断—恢复机制：主设计模型提问后暂停，用户答复后从中断点续接。"""

from __future__ import annotations

import uuid

import pytest

from app.agent.agent_loop import AgentLoop
from app.agent.qwen_client import ModelResponse, ToolCall
from app.schemas.session_state import SessionState

DECISION_ARGS = (
    '{"question":"齿轮材料方案选哪个？","kind":"scheme_choice",'
    '"options":[{"label":"软齿面 45钢调质，成本低"},{"label":"硬齿面 20CrMnTi，承载高"}],'
    '"recommended_index":0,"reasoning":"载荷平稳"}'
)


def _scripted_client(loop: AgentLoop, script: list[ModelResponse]):
    """把 LLM 换成按剧本返回的假客户端。"""
    calls = {"n": 0}

    async def fake(messages, tools=None, enable_thinking=False, on_event=None):
        idx = min(calls["n"], len(script) - 1)
        calls["n"] += 1
        return script[idx]

    loop.client.chat_stream_collect = fake  # type: ignore[method-assign]
    return calls


@pytest.mark.asyncio
async def test_request_decision_suspends_loop():
    session = SessionState(session_id=uuid.uuid4())
    loop = AgentLoop(session=session)
    _scripted_client(
        loop,
        [
            ModelResponse(
                content="材料方案需要你定一下。",
                tool_calls=[
                    ToolCall(id="c1", name="request_user_decision", arguments=DECISION_ARGS)
                ],
            )
        ],
    )

    result = await loop.run("帮我设计一个单级减速器")

    assert result.awaiting_decision is True
    assert result.decision_id
    assert session.pending_decision is not None
    assert "软齿面" in result.content
    # 中断时的消息栈被完整保存，供恢复使用
    assert session.pending_decision.suspended_messages
    assert session.pending_decision.suspended_tool_call_id == "c1"


@pytest.mark.asyncio
async def test_answer_resumes_from_interrupt_point():
    session = SessionState(session_id=uuid.uuid4())
    loop = AgentLoop(session=session)
    _scripted_client(
        loop,
        [
            ModelResponse(
                content="需要你定材料。",
                reasoning_content="需要调用用户决策工具确认材料方案。",
                tool_calls=[
                    ToolCall(id="c1", name="request_user_decision", arguments=DECISION_ARGS)
                ],
            )
        ],
    )
    await loop.run("设计一个减速器")
    suspended_len = len(session.pending_decision.suspended_messages)

    # 第二轮：新的 loop 实例（模拟新请求），用户答复"选第1个"
    loop2 = AgentLoop(session=session)
    seen: dict = {}

    async def fake(messages, tools=None, enable_thinking=False, on_event=None):
        seen["messages"] = list(messages)
        return ModelResponse(content="好，按软齿面方案继续。", tool_calls=[])

    loop2.client.chat_stream_collect = fake  # type: ignore[method-assign]
    result = await loop2.run("1")

    assert result.awaiting_decision is False
    assert session.pending_decision is None
    assert len(session.decision_history) == 1

    msgs = seen["messages"]
    # 恢复后消息栈 = 中断时的栈 + 一条 tool 结果，而不是重头再来
    assert len(msgs) == suspended_len + 1
    assert msgs[-2]["role"] == "assistant"
    assert msgs[-2]["reasoning_content"] == "需要调用用户决策工具确认材料方案。"
    assert msgs[-1]["role"] == "tool"
    assert msgs[-1]["tool_call_id"] == "c1"
    assert "matched_option_index" in msgs[-1]["content"]


@pytest.mark.asyncio
async def test_option_matching_by_index_and_keyword():
    session = SessionState(session_id=uuid.uuid4())
    loop = AgentLoop(session=session)
    _scripted_client(
        loop,
        [
            ModelResponse(
                content="",
                tool_calls=[
                    ToolCall(id="c1", name="request_user_decision", arguments=DECISION_ARGS)
                ],
            )
        ],
    )
    await loop.run("设计减速器")
    decision = session.pending_decision

    assert AgentLoop._match_option(decision, "2") == 1
    assert AgentLoop._match_option(decision, "第1个") == 0
    assert AgentLoop._match_option(decision, "用硬齿面 20CrMnTi") == 1
    assert AgentLoop._match_option(decision, "都不合适，我再想想") is None


@pytest.mark.asyncio
async def test_system_prompt_refreshed_on_resume():
    """恢复时系统提示词按最新状态重建，避免阶段信息过期。"""
    session = SessionState(session_id=uuid.uuid4())
    loop = AgentLoop(session=session)
    _scripted_client(
        loop,
        [
            ModelResponse(
                content="",
                tool_calls=[
                    ToolCall(id="c1", name="request_user_decision", arguments=DECISION_ARGS)
                ],
            )
        ],
    )
    await loop.run("设计减速器")

    from app.schemas.design_stage import DesignStage

    session.design_stage = DesignStage.DETAIL_CALCULATION

    loop2 = AgentLoop(session=session)
    seen: dict = {}

    async def fake(messages, tools=None, enable_thinking=False, on_event=None):
        seen["system"] = messages[0]["content"]
        return ModelResponse(content="继续", tool_calls=[])

    loop2.client.chat_stream_collect = fake  # type: ignore[method-assign]
    await loop2.run("1")

    assert "详细设计计算" in seen["system"]
