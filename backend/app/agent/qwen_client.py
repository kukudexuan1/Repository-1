"""OpenAI-compatible Chat Completions client used by all model slots."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, AsyncGenerator
from datetime import date, datetime
from decimal import Decimal

import httpx

if TYPE_CHECKING:
    from app.core.model_config import ModelSlot

logger = logging.getLogger(__name__)


def _json_default(obj):
    """Custom JSON serializer for objects not serializable by default."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

class StreamEventType(str, Enum):
    THINKING_DELTA = "thinking_delta"
    TEXT_DELTA = "text_delta"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_ARGS_DELTA = "tool_call_args_delta"
    TOOL_CALL_DONE = "tool_call_done"
    DONE = "done"
    ERROR = "error"


@dataclass
class StreamEvent:
    type: StreamEventType
    data: Any = None

    def to_dict(self) -> dict:
        return {"type": self.type.value, "data": self.data}


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }

    def parse_arguments(self) -> dict:
        try:
            return json.loads(self.arguments)
        except json.JSONDecodeError:
            return {}


@dataclass
class ModelResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    reasoning_content: str | None = None
    finish_reason: str | None = None
    # 服务端回执里的 model 字段：判断「实际是哪个模型答的」唯一可靠依据。
    # 不要用模型自述的身份 —— 它可能因训练数据污染而自称 Claude/GPT。
    served_model: str | None = None

    def to_assistant_message(self) -> dict:
        msg: dict[str, Any] = {"role": "assistant", "content": self.content if self.content is not None else ""}
        if self.reasoning_content is not None:
            msg["reasoning_content"] = self.reasoning_content
        if self.tool_calls:
            msg["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        return msg


class ModelAPIError(RuntimeError):
    """Sanitized error returned by an OpenAI-compatible endpoint."""

    def __init__(self, message: str, *, status_code: int | None = None, code: str = "", request_id: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.request_id = request_id


def resolve_chat_completions_endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/compatible-mode"):
        return f"{base}/v1/chat/completions"
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/chat/completions"


class QwenClient:
    """OpenAI-compatible client; name retained for import compatibility."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 120.0,
        sampling: dict[str, Any] | None = None,
        provider: str = "openai_compatible",
        reasoning_effort: str = "high",
        max_retries: int = 2,
    ):
        self.model = model or os.getenv("DEEPSEEK_MODEL", "")
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = (base_url or os.getenv("DEEPSEEK_ENDPOINT", "")).rstrip("/")
        self.timeout = timeout
        self.provider = provider
        self.reasoning_effort = reasoning_effort
        self.max_retries = max(0, max_retries)
        self.sampling: dict[str, Any] = {k: v for k, v in (sampling or {}).items() if v is not None}

        if not self.api_key:
            raise ValueError("API key is required")
        if not self.base_url:
            raise ValueError("Base URL is required")

    @classmethod
    def from_slot(
        cls,
        slot: "ModelSlot",
        timeout: float = 120.0,
        sampling: dict[str, Any] | None = None,
        reasoning_effort: str = "high",
    ) -> "QwenClient":
        """按 model_config 中的槽位配置构造客户端，并记录生效的模型。"""
        logger.info(
            "%s 使用 model=%s endpoint=%s", slot.label, slot.model, slot.base_url
        )
        return cls(
            model=slot.model,
            api_key=slot.api_key,
            base_url=slot.base_url,
            timeout=timeout,
            sampling=sampling,
            provider="deepseek" if slot.name == "main" else "openai_compatible",
            reasoning_effort=reasoning_effort,
        )

    def _apply_sampling(self, payload: dict[str, Any]) -> None:
        """Merge configured sampling params into the request payload.

        temperature/top_p/presence_penalty/frequency_penalty/max_tokens are
        standard fields; top_k/repetition_penalty are DashScope extensions that
        the OpenAI-compatible endpoint accepts as top-level keys.
        """
        for key, value in self.sampling.items():
            if value is not None:
                payload[key] = value

    def _get_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _resolve_endpoint(self) -> str:
        return resolve_chat_completions_endpoint(self.base_url)

    def _apply_thinking(self, payload: dict[str, Any], enabled: bool) -> None:
        if self.provider == "deepseek":
            if enabled and payload.get("tool_choice") == "required":
                raise ValueError("DeepSeek 思考模式不支持 tool_choice='required'，请使用 auto")
            payload["thinking"] = {"type": "enabled" if enabled else "disabled"}
            if enabled:
                payload["reasoning_effort"] = self.reasoning_effort
        elif enabled:
            payload["enable_thinking"] = True

    @staticmethod
    def _raise_api_error(response: httpx.Response) -> None:
        if response.is_success:
            return
        message = response.reason_phrase or "Model API request failed"
        code = ""
        try:
            body = response.json()
            error = body.get("error", body) if isinstance(body, dict) else {}
            if isinstance(error, dict):
                message = str(error.get("message") or message)
                code = str(error.get("code") or error.get("type") or "")
        except (ValueError, TypeError):
            pass
        request_id = response.headers.get("x-request-id", "")
        detail = f"HTTP {response.status_code}: {message}"
        if code:
            detail += f" (code={code})"
        if request_id:
            detail += f" (request_id={request_id})"
        raise ModelAPIError(detail, status_code=response.status_code, code=code, request_id=request_id)

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code == 429 or status_code >= 500

    async def _post_json(self, endpoint: str, payload: dict[str, Any]) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(endpoint, json=payload, headers=self._get_headers())
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self.max_retries:
                    raise ModelAPIError(f"Model API network error: {exc}") from exc
            else:
                if response.is_success or not self._is_retryable_status(response.status_code):
                    self._raise_api_error(response)
                    return response
                if attempt >= self.max_retries:
                    self._raise_api_error(response)
            await asyncio.sleep(0.5 * (2 ** attempt))
        raise ModelAPIError("Model API request failed after retries")

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        enable_thinking: bool = False,
        tool_choice: str | dict = "auto",
    ) -> ModelResponse:
        """Non-streaming chat completion with optional Function Calling."""
        endpoint = self._resolve_endpoint()

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        self._apply_thinking(payload, enable_thinking)
        
        self._apply_sampling(payload)

        response = await self._post_json(endpoint, payload)
        data = response.json()

        return self._parse_response(data)

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        enable_thinking: bool = False,
        tool_choice: str | dict = "auto",
    ) -> AsyncGenerator[StreamEvent, None]:
        """Streaming chat completion with Function Calling support."""
        endpoint = self._resolve_endpoint()

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        self._apply_thinking(payload, enable_thinking)

        self._apply_sampling(payload)

        tool_calls_buffer: dict[int, dict] = {}
        content_buffer = ""
        reasoning_buffer = ""
        served_model: str | None = None
        finish_reason: str | None = None

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", endpoint, json=payload, headers=self._get_headers()) as response:
                self._raise_api_error(response)

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    if line == "data: [DONE]":
                        break
                    if line.startswith("data:"):
                        line = line[5:].strip()
                    if not line or line == "[DONE]":
                        continue

                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if served_model is None and chunk.get("model"):
                        served_model = self._check_served_model(chunk["model"])

                    if not chunk.get("choices"):
                        continue

                    delta = chunk["choices"][0].get("delta", {})
                    finish_reason = chunk["choices"][0].get("finish_reason")

                    if delta.get("reasoning_content"):
                        reasoning_delta = delta["reasoning_content"]
                        reasoning_buffer += reasoning_delta
                        yield StreamEvent(StreamEventType.THINKING_DELTA, reasoning_delta)

                    if delta.get("content"):
                        content_delta = delta["content"]
                        content_buffer += content_delta
                        yield StreamEvent(StreamEventType.TEXT_DELTA, content_delta)

                    if delta.get("tool_calls"):
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            if idx not in tool_calls_buffer:
                                tool_calls_buffer[idx] = {
                                    "id": tc.get("id", ""),
                                    "name": "",
                                    "arguments": "",
                                }
                                if tc.get("id"):
                                    yield StreamEvent(
                                        StreamEventType.TOOL_CALL_START,
                                        {"index": idx, "id": tc["id"]},
                                    )

                            func = tc.get("function", {})
                            if func.get("name"):
                                tool_calls_buffer[idx]["name"] += func["name"]
                            if func.get("arguments"):
                                tool_calls_buffer[idx]["arguments"] += func["arguments"]
                                yield StreamEvent(
                                    StreamEventType.TOOL_CALL_ARGS_DELTA,
                                    {"index": idx, "delta": func["arguments"]},
                                )

                    if finish_reason:
                        break

        for idx, tc_data in sorted(tool_calls_buffer.items()):
            yield StreamEvent(
                StreamEventType.TOOL_CALL_DONE,
                ToolCall(id=tc_data["id"], name=tc_data["name"], arguments=tc_data["arguments"]),
            )

        yield StreamEvent(
            StreamEventType.DONE,
            ModelResponse(
                content=content_buffer or None,
                tool_calls=[
                    ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
                    for tc in tool_calls_buffer.values()
                ],
                reasoning_content=reasoning_buffer or None,
                finish_reason=finish_reason,
                served_model=served_model,
            ),
        )

    async def chat_stream_collect(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        enable_thinking: bool = False,
        tool_choice: str | dict = "auto",
        on_event: callable | None = None,
    ) -> ModelResponse:
        """Stream and collect final response, with optional event callback."""
        final_response: ModelResponse | None = None

        async for event in self.chat_stream(messages, tools, enable_thinking, tool_choice):
            if on_event:
                on_event(event)
            if event.type == StreamEventType.DONE:
                final_response = event.data

        if final_response is None:
            raise RuntimeError("No response received from model")

        return final_response

    def _parse_response(self, data: dict) -> ModelResponse:
        """Parse non-streaming response."""
        if not data.get("choices"):
            raise RuntimeError(f"Invalid response: {data}")

        choice = data["choices"][0]
        message = choice.get("message", {})

        tool_calls = []
        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                func = tc.get("function", {})
                tool_calls.append(
                    ToolCall(
                        id=tc.get("id", ""),
                        name=func.get("name", ""),
                        arguments=func.get("arguments", ""),
                    )
                )

        return ModelResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            reasoning_content=message.get("reasoning_content"),
            finish_reason=choice.get("finish_reason"),
            served_model=self._check_served_model(data.get("model")),
        )

    def _check_served_model(self, served: str | None) -> str | None:
        """服务端返回的模型与请求的不一致时告警。

        网关或代理可能把请求路由到另一个模型，这是「配置了 A 实际用了 B」
        除环境变量覆盖之外的另一条路径，只有比对回执才能发现。
        """
        if served and served != self.model:
            logger.warning(
                "模型不一致：请求 model=%s，服务端实际响应 model=%s（endpoint=%s）",
                self.model,
                served,
                self.base_url,
            )
        return served

    @staticmethod
    def build_tool_result_message(tool_call_id: str, result: Any) -> dict:
        """Build a tool result message for the conversation."""
        if isinstance(result, str):
            content = result
        else:
            content = json.dumps(result, ensure_ascii=False, default=_json_default)
        return {"role": "tool", "tool_call_id": tool_call_id, "content": content}
