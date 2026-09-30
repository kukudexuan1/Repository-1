"""Analysis sub-agent: drives ansys-workbench-mcp for real FEA simulation.

Replaces the former LLM "pseudo-FEA" validate_engineering. Uses the math
model as an ANSYS pre/post translator: natural language -> analysis system +
loads/boundaries; solver results -> pass/fail against engineering criteria.

Context persistence: run() accepts prior_messages (the sub-agent's running
conversation stored on the session) and returns the updated messages so the
agent can resume across multiple invocations without losing tool-call history.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.model_config import math_slot
from app.mcp import ANSYS, get_manager
from app.mcp.schema_bridge import mcp_tools_to_functions

from .prompt import (
    build_analysis_followup_user,
    build_analysis_system_prompt,
    build_analysis_user_content,
)
from .qwen_client import QwenClient, StreamEvent, StreamEventType

ANSYS_PROJECT_DIR = os.getenv("ANSYS_PROJECT_DIR", "D:/ansys-workbench-mcp/runs/agent")


def _sampling_from_env(prefix: str) -> dict[str, Any]:
    """Read optional sampling params from env, e.g. MATH_TEMPERATURE."""
    def _f(name: str) -> float | None:
        raw = os.getenv(f"{prefix}_{name}", "").strip()
        return float(raw) if raw else None
    return {
        "temperature": _f("TEMPERATURE"),
        "top_p": _f("TOP_P"),
        "presence_penalty": _f("PRESENCE_PENALTY"),
        "repetition_penalty": _f("REPETITION_PENALTY"),
        "max_tokens": (int(os.getenv(f"{prefix}_MAX_TOKENS")) if os.getenv(f"{prefix}_MAX_TOKENS", "").strip() else None),
    }


@dataclass
class AnalysisResult:
    success: bool
    status: str = "not_run"
    summary: str = ""
    result_data: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[str] = field(default_factory=list)
    error: str | None = None
    iterations: int = 0
    messages: list[dict] = field(default_factory=list)


class AnalysisAgent:
    """Inner agent loop that runs an ANSYS simulation through the bridge."""

    MAX_LOOPS = 25

    def __init__(self) -> None:
        self.client = QwenClient.from_slot(math_slot(), sampling=_sampling_from_env("MATH"))
        self.manager = get_manager()

    async def run(
        self,
        analysis_intent: str,
        geometry_file: str,
        analysis_type: str = "",
        session_id: str = "default",
        stream_callback: Callable[[StreamEvent], None] | None = None,
        prior_messages: list[dict] | None = None,
    ) -> AnalysisResult:
        if not self.manager.is_connected(ANSYS):
            return AnalysisResult(success=False, error="ansys-workbench 未连接，无法仿真")
        if not os.path.isfile(geometry_file):
            return AnalysisResult(
                success=False,
                error=f"几何文件不存在或不可访问: {geometry_file}",
            )

        tools = mcp_tools_to_functions(self.manager.tools(ANSYS))
        if prior_messages:
            messages = list(prior_messages)
            messages.append({"role": "user", "content": self._build_followup(analysis_intent, analysis_type)})
        else:
            messages = self._build_messages(analysis_intent, geometry_file, analysis_type, session_id)
        tool_calls_made: list[str] = []

        for loop_idx in range(1, self.MAX_LOOPS + 1):
            response = await self.client.chat_stream_collect(
                messages=messages,
                tools=tools,
                enable_thinking=False,
                on_event=stream_callback,
            )

            if not response.tool_calls:
                if response.content:
                    messages.append(response.to_assistant_message())
                elif not tool_calls_made:
                    return AnalysisResult(
                        success=False,
                        error=(
                            f"仿真模型 ({self.client.model}) 返回空响应，"
                            "无法调用 ANSYS 工具。请确认 QWEN_MATH_MODEL 支持 Function Calling"
                            "（如 deepseek-v4-pro、qwen3.5-plus），勿使用 qwen-math-plus。"
                        ),
                        tool_calls=tool_calls_made,
                        iterations=loop_idx,
                        messages=messages,
                    )
                verdict = self._extract_verdict(response.content or "")
                return AnalysisResult(
                    success=verdict.get("pass_or_fail") in {"pass", "fail"},
                    status=verdict.get("pass_or_fail", "unknown"),
                    summary=response.content or "",
                    result_data=verdict,
                    tool_calls=tool_calls_made,
                    iterations=loop_idx,
                    messages=messages,
                )

            messages.append(response.to_assistant_message())
            for tool_call in response.tool_calls:
                name = tool_call.name
                args = tool_call.parse_arguments()
                tool_calls_made.append(name)
                if stream_callback:
                    stream_callback(StreamEvent(StreamEventType.TEXT_DELTA, f"\n[ansys: {name}]\n"))
                result = await self.manager.call(ANSYS, name, args)
                messages.append(QwenClient.build_tool_result_message(tool_call.id, result.to_dict()))

        return AnalysisResult(
            success=False,
            tool_calls=tool_calls_made,
            iterations=self.MAX_LOOPS,
            error="达到仿真最大循环次数仍未完成",
            messages=messages,
        )

    def _build_messages(
        self,
        analysis_intent: str,
        geometry_file: str,
        analysis_type: str,
        session_id: str,
    ) -> list[dict]:
        project_dir = f"{ANSYS_PROJECT_DIR.rstrip('/')}/{session_id}"
        system_prompt = build_analysis_system_prompt(project_dir)
        user_content = build_analysis_user_content(
            analysis_intent, geometry_file, analysis_type
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    def _build_followup(self, analysis_intent: str, analysis_type: str) -> str:
        return build_analysis_followup_user(analysis_intent, analysis_type)

    @staticmethod
    def _extract_verdict(text: str) -> dict[str, Any]:
        import json
        import re

        cleaned = text.strip()
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.S)
        if fence:
            cleaned = fence.group(1)
        else:
            match = re.search(r"(\{.*\})", cleaned, flags=re.S)
            if match:
                cleaned = match.group(1)
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            return {"pass_or_fail": "unknown", "raw_output": text}
