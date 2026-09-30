"""Autonomous CAD sub-agent with spatial conflict and verification gates."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.model_config import coder_slot
from app.mcp import MCPCAD, get_manager
from app.mcp.schema_bridge import mcp_tools_to_functions
from app.schemas.modeling_contract import ModelingContract
from app.schemas.modeling_plan import ModelingPlan, VerificationStatus
from app.services.modeling.compiler import compile_contract
from app.services.modeling.conflicts import inspect_spatial_result
from app.services.modeling.verifier import verify_geometry

from .prompt import (
    build_modeling_followup_user,
    build_modeling_system_prompt,
    build_modeling_user_content,
)
from .qwen_client import QwenClient, StreamEvent, StreamEventType

EXPORT_DIR = os.getenv("MCPCAD_EXPORT_DIR", "D:/Inventor_Export")


def _sampling_from_env(prefix: str) -> dict[str, Any]:
    def _float(name: str) -> float | None:
        raw = os.getenv(f"{prefix}_{name}", "").strip()
        return float(raw) if raw else None

    return {
        "temperature": _float("TEMPERATURE"),
        "top_p": _float("TOP_P"),
        "presence_penalty": _float("PRESENCE_PENALTY"),
        "repetition_penalty": _float("REPETITION_PENALTY"),
        "max_tokens": int(os.getenv(f"{prefix}_MAX_TOKENS"))
        if os.getenv(f"{prefix}_MAX_TOKENS", "").strip()
        else None,
    }


@dataclass
class ModelingResult:
    success: bool
    geometry_file: str | None = None
    feature_tree: dict[str, Any] | None = None
    tool_calls: list[str] = field(default_factory=list)
    verification_report: dict[str, Any] | None = None
    error: str | None = None
    iterations: int = 0
    messages: list[dict] = field(default_factory=list)


class ModelingAgent:
    MAX_LOOPS = 60
    MAX_REPAIRS = 3

    def __init__(self) -> None:
        self.client = QwenClient.from_slot(
            coder_slot(), sampling=_sampling_from_env("CODER")
        )
        self.manager = get_manager()

    async def build(
        self,
        execution_intent: str,
        session_id: str = "default",
        stream_callback: Callable[[StreamEvent], None] | None = None,
        prior_messages: list[dict] | None = None,
        contract: ModelingContract | None = None,
        plan: ModelingPlan | None = None,
    ) -> ModelingResult:
        if not self.manager.is_connected(MCPCAD):
            return ModelingResult(success=False, error="mcp-cad 未连接，无法驱动 Inventor")
        if contract is None:
            return ModelingResult(success=False, error="缺少 ModelingContract，无法进行空间推理")
        expectation = plan or compile_contract(contract)
        return await self._run(
            execution_intent,
            session_id,
            stream_callback,
            prior_messages,
            contract,
            expectation,
        )

    async def _run(
        self,
        execution_intent: str,
        session_id: str,
        stream_callback: Callable[[StreamEvent], None] | None,
        prior_messages: list[dict] | None,
        contract: ModelingContract,
        expectation: ModelingPlan,
    ) -> ModelingResult:
        tools = mcp_tools_to_functions(self.manager.tools(MCPCAD))
        messages = self._messages(
            execution_intent, session_id, contract, prior_messages
        )
        calls: list[str] = []
        repairs = 0
        last_report: dict[str, Any] | None = None

        for loop_index in range(1, self.MAX_LOOPS + 1):
            response = await self.client.chat_stream_collect(
                messages=messages,
                tools=tools,
                enable_thinking=False,
                on_event=stream_callback,
            )
            if not response.tool_calls:
                if response.content:
                    messages.append(response.to_assistant_message())
                messages.append({
                    "role": "user",
                    "content": (
                        "尚未请求导出。请继续自主规划和调用 mcp-cad；候选几何完成后"
                        "调用 export_step，系统将在真正导出前执行结构化验证。"
                    ),
                })
                continue

            messages.append(response.to_assistant_message())
            for tool_call in response.tool_calls:
                name = tool_call.name
                args = tool_call.parse_arguments()
                calls.append(name)
                self._emit(stream_callback, f"\n[mcp-cad: {name}]\n")
                if name in {"export_step", "export_stl"}:
                    report = await self._verify(expectation)
                    last_report = report.model_dump(mode="json")
                    if report.status != VerificationStatus.PASS:
                        repairs += 1
                        messages.append(QwenClient.build_tool_result_message(
                            tool_call.id,
                            {
                                "status": "blocked",
                                "error": "几何验证未通过，导出被拦截",
                                "verification_report": last_report,
                                "repair_attempt": repairs,
                                "max_repairs": self.MAX_REPAIRS,
                                "instruction": "根据证据局部修正冲突；不要重建无关特征。",
                            },
                        ))
                        if repairs >= self.MAX_REPAIRS:
                            return ModelingResult(
                                success=False,
                                tool_calls=calls,
                                verification_report=last_report,
                                error="几何验证连续失败，禁止导出",
                                iterations=loop_index,
                                messages=messages,
                            )
                        continue
                    path = str(args.get("path") or f"{EXPORT_DIR.rstrip('/')}/{session_id}.stp")
                    exported = await self.manager.call(MCPCAD, name, {**args, "path": path})
                    messages.append(QwenClient.build_tool_result_message(
                        tool_call.id, exported.to_dict()
                    ))
                    if not exported.success:
                        continue
                    return ModelingResult(
                        success=True,
                        geometry_file=path,
                        feature_tree=await self._feature_tree(),
                        tool_calls=calls,
                        verification_report=last_report,
                        iterations=loop_index,
                        messages=messages,
                    )

                result = await self.manager.call(MCPCAD, name, args)
                payload = result.to_dict()
                conflicts = inspect_spatial_result(name, args, payload, contract)
                if conflicts:
                    payload["spatial_conflicts"] = [
                        conflict.model_dump(mode="json") for conflict in conflicts
                    ]
                    payload["conflict_instruction"] = (
                        "先按事实优先级消解冲突，再继续；无法唯一消解时停止报告。"
                    )
                messages.append(QwenClient.build_tool_result_message(
                    tool_call.id, payload
                ))

        return ModelingResult(
            success=False,
            tool_calls=calls,
            verification_report=last_report,
            error="达到建模最大循环次数仍未通过验证并导出",
            iterations=self.MAX_LOOPS,
            messages=messages,
        )

    async def _verify(self, expectation: ModelingPlan):
        async def call(name: str, args: dict):
            return await self.manager.call(MCPCAD, name, args)

        return await verify_geometry(expectation, call)

    async def _feature_tree(self) -> dict[str, Any] | None:
        result = await self.manager.call(MCPCAD, "get_feature_tree", {})
        return result.data if result.success else None

    def _messages(
        self,
        execution_intent: str,
        session_id: str,
        contract: ModelingContract,
        prior_messages: list[dict] | None,
    ) -> list[dict]:
        if prior_messages:
            return [
                *prior_messages,
                {"role": "user", "content": build_modeling_followup_user(execution_intent)},
            ]
        export_path = f"{EXPORT_DIR.rstrip('/')}/{session_id}.stp"
        return [
            {
                "role": "system",
                "content": build_modeling_system_prompt(export_path, contract),
            },
            {"role": "user", "content": build_modeling_user_content(execution_intent)},
        ]

    @staticmethod
    def _emit(
        callback: Callable[[StreamEvent], None] | None,
        text: str,
    ) -> None:
        if callback:
            callback(StreamEvent(StreamEventType.TEXT_DELTA, text))


