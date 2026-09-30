from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.model_config import enable_thinking, main_slot, reasoning_effort
from app.schemas.decision import DecisionKind, PendingDecision
from app.schemas.design_stage import DesignStage
from app.schemas.session_state import ActiveAgent, ChatMessage, ChatRole, SessionState

from .analysis_agent import AnalysisAgent
from .context.session_context import SessionContext
from .modeling_agent import ModelingAgent
from .qwen_client import ModelResponse, QwenClient, StreamEvent, StreamEventType, ToolCall
from .tools import ToolContext, ToolInterrupt, build_openai_tools, dispatch
from .tools.express_tools import apply_analysis_result, apply_modeling_result

logger = logging.getLogger(__name__)

EXIT_COMMAND = "/exit"


@dataclass
class AgentResult:
    content: str
    session: SessionState
    tool_calls_made: list[str] = field(default_factory=list)
    tool_events: list[dict[str, Any]] = field(default_factory=list)
    active_agent: str = "none"
    noop: bool = False
    awaiting_decision: bool = False
    decision_id: str = ""


class AgentLoop:
    """主设计模型的 ReAct 循环。"""

    MAX_ITERATIONS = 60

    def __init__(
        self,
        session: SessionState,
        allowed_tools: frozenset[str] | None = None,
        experiment_flags: dict | None = None,
    ):
        self.session = session
        self.context = SessionContext(session)
        self.client = QwenClient.from_slot(
            main_slot(), reasoning_effort=reasoning_effort()
        )
        self.modeling = ModelingAgent()
        self.analysis = AnalysisAgent()
        self.messages: list[dict] = []
        self.tool_calls_made: list[str] = []
        self.tool_events: list[dict[str, Any]] = []
        self.enable_thinking = enable_thinking()
        # allowed_tools=None → 不限制（完整框架）；frozenset() → 无工具（B0）
        self.allowed_tools: frozenset[str] | None = allowed_tools
        self.experiment_flags: dict = experiment_flags or {}
        self.max_iterations = self.MAX_ITERATIONS

    # ------------------------------------------------------------------
    # 入口
    # ------------------------------------------------------------------

    async def run(
        self,
        user_input: str,
        stream_callback: Callable[[str, str], None] | None = None,
    ) -> AgentResult:
        stripped = user_input.strip()

        if stripped == EXIT_COMMAND:
            return self._handle_exit()

        # 有待决问题时，本次输入就是答复，优先走恢复路径
        if self.session.pending_decision is not None:
            return await self._resume_from_decision(user_input, stream_callback)

        if self.session.active_agent == ActiveAgent.MODELING:
            return await self._run_sticky_modeling(user_input, stream_callback)
        if self.session.active_agent == ActiveAgent.ANALYSIS:
            return await self._run_sticky_analysis(user_input, stream_callback)

        return await self._run_main(user_input, stream_callback)

    def _handle_exit(self) -> AgentResult:
        if self.session.active_agent == ActiveAgent.NONE:
            return AgentResult(content="", session=self.session, noop=True)
        prev = self.session.active_agent.value
        self.session.active_agent = ActiveAgent.NONE
        msg = (
            f"已退出「{prev}」子 agent，控制权交还主设计模型"
            "（子 agent 上下文已保留，可重新进入续接）。"
        )
        self._add_chat_history(ChatRole.ASSISTANT, msg)
        return AgentResult(content=msg, session=self.session, active_agent="none")

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    async def _run_main(
        self,
        user_input: str,
        stream_callback: Callable[[str, str], None] | None = None,
    ) -> AgentResult:
        self._init_messages(user_input)
        self._add_chat_history(ChatRole.USER, user_input)
        return await self._react(stream_callback)

    async def _react(
        self, stream_callback: Callable[[str, str], None] | None
    ) -> AgentResult:
        """ReAct 循环主体。消息栈已就绪，从这里开始推理—调用—观察。"""
        for _ in range(self.max_iterations):
            response = await self._call_model(stream_callback)

            if not response.tool_calls:
                content = response.content or "任务已完成。"
                self._add_chat_history(ChatRole.ASSISTANT, content)
                return self._result(content)

            self.messages.append(response.to_assistant_message())

            for tool_call in response.tool_calls:
                self.tool_calls_made.append(tool_call.name)
                if stream_callback:
                    stream_callback("system", f"\n[调用工具: {tool_call.name}]\n")

                try:
                    result = await self._execute_tool(tool_call, stream_callback)
                except ToolInterrupt as interrupt:
                    return self._suspend(
                        interrupt.decision,
                        tool_call,
                        response.content or "",
                        stream_callback,
                    )

                self.tool_events.append({
                    "name": tool_call.name,
                    "status": result.get("status", "unknown"),
                    "error": result.get("error", ""),
                    "reason": result.get("reason", ""),
                })
                self.messages.append(
                    QwenClient.build_tool_result_message(tool_call.id, result)
                )

        content = (
            "已达到最大工具调用轮次。当前设计进度已保存在会话状态中，"
            "请说明下一步希望我优先推进哪一项。"
        )
        self._add_chat_history(ChatRole.ASSISTANT, content)
        return self._result(content)

    def _result(self, content: str) -> AgentResult:
        return AgentResult(
            content=content,
            session=self.session,
            tool_calls_made=self.tool_calls_made,
            tool_events=self.tool_events,
            active_agent=self.session.active_agent.value,
        )

    # ------------------------------------------------------------------
    # 中断与恢复
    # ------------------------------------------------------------------

    def _suspend(
        self,
        decision: PendingDecision,
        tool_call: ToolCall,
        assistant_text: str,
        stream_callback: Callable[[str, str], None] | None,
    ) -> AgentResult:
        """把待决问题落到会话，交还控制权给用户。"""
        decision.suspended_messages = list(self.messages)
        decision.suspended_tool_call_id = tool_call.id
        self.session.pending_decision = decision

        question = decision.render_for_user()
        content = f"{assistant_text}\n\n{question}".strip()
        if stream_callback:
            stream_callback("assistant", f"\n{question}\n")

        self._add_chat_history(ChatRole.ASSISTANT, content)
        logger.info("会话 %s 因待决问题 %s 中断", self.session.session_id, decision.decision_id)

        return AgentResult(
            content=content,
            session=self.session,
            tool_calls_made=self.tool_calls_made,
            active_agent=self.session.active_agent.value,
            awaiting_decision=True,
            decision_id=decision.decision_id,
        )

    async def _resume_from_decision(
        self,
        user_input: str,
        stream_callback: Callable[[str, str], None] | None = None,
    ) -> AgentResult:
        """用户答复后从中断点续接消息栈。"""
        decision = self.session.pending_decision
        assert decision is not None

        self._add_chat_history(ChatRole.USER, user_input)
        self.session.decision_history.append(decision)
        self.session.pending_decision = None

        if decision.suspended_messages:
            self.messages = list(decision.suspended_messages)
            # 系统提示词按最新状态刷新，避免恢复后阶段信息过期
            if self.messages and self.messages[0].get("role") == "system":
                self.messages[0] = {
                    "role": "system",
                    "content": self.context.build_system_prompt(),
                }
            self.messages.append(
                QwenClient.build_tool_result_message(
                    decision.suspended_tool_call_id,
                    self._decision_answer_payload(decision, user_input),
                )
            )
        else:
            self._init_messages(user_input)

        if stream_callback:
            stream_callback("system", "\n[已收到用户答复，从中断点继续设计]\n")

        return await self._react(stream_callback)

    def _decision_answer_payload(
        self, decision: PendingDecision, user_input: str
    ) -> dict[str, Any]:
        matched = self._match_option(decision, user_input)
        payload: dict[str, Any] = {
            "status": "answered",
            "decision_id": decision.decision_id,
            "kind": decision.kind.value,
            "question": decision.question,
            "user_answer": user_input,
        }
        if matched is not None:
            payload["matched_option_index"] = matched
            payload["matched_option"] = decision.options[matched].label
        elif decision.options:
            payload["note"] = (
                "未能自动匹配到预设选项，请按用户原话理解其意图；"
                "若仍有歧义，再问一次而不要擅自选定"
            )

        follow_up = {
            DecisionKind.SCHEME_CHOICE: "若用户已选定方案，请调用 confirm_scheme 记录并通过 Gate 1",
            DecisionKind.GATE_APPROVAL: (
                "若用户已授权，请调用对应的关口工具记录"
                "（freeze_parameters / accept_verification）"
            ),
            DecisionKind.CLARIFY: "请把用户答复用 update_design_spec 记入设计任务书",
            DecisionKind.REWORK_PATH: (
                "若需修改已冻结参数，先 unfreeze_parameters，再重算受影响的项"
            ),
        }.get(decision.kind, "")
        if follow_up:
            payload["next"] = follow_up
        return payload

    @staticmethod
    def _match_option(decision: PendingDecision, answer: str) -> int | None:
        """把用户答复匹配到预设选项：序号、字母编号或标签关键词。

        匹配不上时返回 None——此时提示模型按用户原话理解，而不是硬猜一个选项。
        """
        if not decision.options:
            return None
        count = len(decision.options)
        text = answer.strip().lower()

        ordinal = re.match(
            r"^\s*(?:第|选项|方案|option|opt)?\s*(\d+)\s*(?:个|项|号|\.|、|）|\))?\s*$",
            text,
        )
        if ordinal:
            idx = int(ordinal.group(1)) - 1
            if 0 <= idx < count:
                return idx

        letter = re.match(r"^\s*[（(]?([a-z])[）).、]?\s*$", text)
        if letter:
            idx = ord(letter.group(1)) - ord("a")
            if 0 <= idx < count:
                return idx

        prefixed = re.search(r"(?:第|选项|方案)\s*(\d+)", text)
        if prefixed:
            idx = int(prefixed.group(1)) - 1
            if 0 <= idx < count:
                return idx

        best: tuple[int, int] | None = None
        for idx, option in enumerate(decision.options):
            head = re.split(r"[，,（(]", option.label.lower())[0].strip()
            if head and head in text:
                score = len(head)
                if best is None or score > best[0]:
                    best = (score, idx)
        return best[1] if best else None

    # ------------------------------------------------------------------
    # 子 Agent 粘滞模式
    # ------------------------------------------------------------------

    async def _run_sticky_modeling(
        self,
        user_input: str,
        stream_callback: Callable[[str, str], None] | None = None,
    ) -> AgentResult:
        self._add_chat_history(ChatRole.USER, user_input)

        def _stream(event: StreamEvent) -> None:
            if stream_callback and event.type in (
                StreamEventType.TEXT_DELTA,
                StreamEventType.THINKING_DELTA,
            ):
                stream_callback("modeling", event.data)

        self.session.design_stage = DesignStage.GEOMETRY
        if self.session.geometry_verification_report is not None:
            self.session.geometry_verification_report.stale = True
        self.session.geometry_file_hash = ""
        if self.session.modeling_plan is None and self.session.modeling_contract is not None:
            from app.services.modeling.compiler import compile_contract
            self.session.modeling_plan = compile_contract(self.session.modeling_contract)
        result = await self.modeling.build(
            execution_intent=user_input,
            session_id=str(self.session.session_id),
            stream_callback=_stream,
            prior_messages=self.session.modeling_messages or None,
            contract=self.session.modeling_contract,
            plan=self.session.modeling_plan,
        )
        tool_result = apply_modeling_result(self.session, result, stay=True)
        content = (
            tool_result.get("message")
            or "建模子 agent 已处理。输入 /exit 可返回主设计模型。"
        )
        self.tool_calls_made.extend(result.tool_calls)
        self._add_chat_history(ChatRole.ASSISTANT, content)
        return AgentResult(
            content=content,
            session=self.session,
            tool_calls_made=result.tool_calls,
            active_agent=self.session.active_agent.value,
        )

    async def _run_sticky_analysis(
        self,
        user_input: str,
        stream_callback: Callable[[str, str], None] | None = None,
    ) -> AgentResult:
        geometry_file = self.session.geometry_file
        self._add_chat_history(ChatRole.USER, user_input)
        if not geometry_file:
            msg = "尚无几何文件，无法仿真。输入 /exit 返回主设计模型后先完成建模。"
            self._add_chat_history(ChatRole.ASSISTANT, msg)
            return AgentResult(content=msg, session=self.session, active_agent="analysis")

        report = self.session.geometry_verification_report
        if report is None or report.status.value != "pass" or report.stale:
            msg = "几何未通过有效的结构化验证，无法继续仿真。输入 /exit 后重新建模验证。"
            self._add_chat_history(ChatRole.ASSISTANT, msg)
            return AgentResult(content=msg, session=self.session, active_agent="analysis")
        from app.services.modeling.verifier import file_sha256
        try:
            current_hash = file_sha256(geometry_file)
        except OSError:
            current_hash = ""
        if not current_hash or current_hash != self.session.geometry_file_hash:
            report.stale = True
            msg = "几何文件已变化，原验证证据失效。输入 /exit 后重新建模验证。"
            self._add_chat_history(ChatRole.ASSISTANT, msg)
            return AgentResult(content=msg, session=self.session, active_agent="analysis")

        def _stream(event: StreamEvent) -> None:
            if stream_callback and event.type in (
                StreamEventType.TEXT_DELTA,
                StreamEventType.THINKING_DELTA,
            ):
                stream_callback("analysis", event.data)

        self.session.design_stage = DesignStage.VERIFICATION
        result = await self.analysis.run(
            analysis_intent=user_input,
            geometry_file=geometry_file,
            session_id=str(self.session.session_id),
            stream_callback=_stream,
            prior_messages=self.session.analysis_messages or None,
        )
        tool_result = apply_analysis_result(
            self.session, result, geometry_file, stay=True
        )
        content = (
            tool_result.get("summary")
            or "仿真子 agent 已处理。输入 /exit 可返回主设计模型。"
        )
        self.tool_calls_made.extend(result.tool_calls)
        self._add_chat_history(ChatRole.ASSISTANT, content)
        return AgentResult(
            content=content,
            session=self.session,
            tool_calls_made=result.tool_calls,
            active_agent=self.session.active_agent.value,
        )

    # ------------------------------------------------------------------
    # 模型调用与工具分发
    # ------------------------------------------------------------------

    def _init_messages(self, user_input: str) -> None:
        self.messages = [
            {"role": "system", "content": self.context.build_system_prompt()}
        ]
        for msg in self._recent_history():
            role = "user" if msg.role == ChatRole.USER else "assistant"
            self.messages.append({"role": role, "content": msg.content})
        self.messages.append(
            {"role": "user", "content": self.context.build_user_message(user_input)}
        )

    def _recent_history(self, keep: int = 16) -> list[ChatMessage]:
        """只带最近若干轮原始对话——设计状态由结构化快照承载，不靠历史回读。"""
        history = [
            m for m in self.session.chat_history if m.role != ChatRole.SYSTEM
        ]
        return history[-keep:]

    async def _call_model(
        self,
        stream_callback: Callable[[str, str], None] | None = None,
    ) -> ModelResponse:
        def _on_event(event: StreamEvent) -> None:
            if not stream_callback:
                return
            if event.type == StreamEventType.THINKING_DELTA:
                stream_callback("chief_model", event.data)
            elif event.type == StreamEventType.TEXT_DELTA:
                stream_callback("assistant", event.data)

        # B0 条件下 allowed_tools 为空集合，传空列表给模型（无工具可调）
        tools = (
            build_openai_tools(allowed_tools=self.allowed_tools)
            if self.allowed_tools is None or len(self.allowed_tools) > 0
            else []
        )
        return await self.client.chat_stream_collect(
            messages=self.messages,
            tools=tools,
            enable_thinking=self.enable_thinking,
            on_event=_on_event,
        )

    async def _execute_tool(
        self,
        tool_call: ToolCall,
        stream_callback: Callable[[str, str], None] | None = None,
    ) -> dict[str, Any]:
        ctx = ToolContext(
            session=self.session,
            stream=stream_callback,
            tool_call_id=tool_call.id,
            extras={
                "modeling_agent": self.modeling,
                "analysis_agent": self.analysis,
                "experiment_flags": self.experiment_flags,
            },
        )
        return await dispatch(tool_call.name, tool_call.arguments, ctx, self.allowed_tools)

    def _add_chat_history(self, role: ChatRole, content: str) -> None:
        self.session.chat_history.append(ChatMessage(role=role, content=content))
