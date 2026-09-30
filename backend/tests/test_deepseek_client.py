from __future__ import annotations

import json

import httpx
import pytest

from app.agent.qwen_client import (
    ModelAPIError,
    ModelResponse,
    QwenClient,
    ToolCall,
    resolve_chat_completions_endpoint,
)


def test_resolve_chat_completions_endpoint() -> None:
    assert resolve_chat_completions_endpoint("https://api.deepseek.com") == (
        "https://api.deepseek.com/chat/completions"
    )
    assert resolve_chat_completions_endpoint("https://api.deepseek.com/v1") == (
        "https://api.deepseek.com/v1/chat/completions"
    )
    assert resolve_chat_completions_endpoint(
        "https://dashscope.aliyuncs.com/compatible-mode"
    ).endswith("/compatible-mode/v1/chat/completions")


def test_assistant_message_preserves_deepseek_reasoning() -> None:
    response = ModelResponse(
        content="",
        reasoning_content="need a tool",
        tool_calls=[ToolCall(id="call_1", name="lookup", arguments="{}")],
    )

    assert response.to_assistant_message() == {
        "role": "assistant",
        "content": "",
        "reasoning_content": "need a tool",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "lookup", "arguments": "{}"},
            }
        ],
    }


def test_deepseek_thinking_payload() -> None:
    client = QwenClient(
        model="deepseek-v4-pro",
        api_key="test",
        base_url="https://api.deepseek.com",
        provider="deepseek",
        reasoning_effort="max",
    )
    payload: dict = {}

    client._apply_thinking(payload, True)

    assert payload == {
        "thinking": {"type": "enabled"},
        "reasoning_effort": "max",
    }
    assert "enable_thinking" not in payload


def test_deepseek_thinking_rejects_required_tool_choice() -> None:
    client = QwenClient(
        model="deepseek-v4-pro",
        api_key="test",
        base_url="https://api.deepseek.com",
        provider="deepseek",
    )
    payload = {"tool_choice": "required"}

    with pytest.raises(ValueError, match="不支持"):
        client._apply_thinking(payload, True)


def test_model_api_error_extracts_safe_fields() -> None:
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    response = httpx.Response(
        400,
        request=request,
        headers={"x-request-id": "req-123"},
        json={"error": {"message": "reasoning_content is required", "code": "invalid_request"}},
    )

    with pytest.raises(ModelAPIError) as caught:
        QwenClient._raise_api_error(response)

    assert caught.value.status_code == 400
    assert caught.value.code == "invalid_request"
    assert caught.value.request_id == "req-123"
    assert "reasoning_content is required" in str(caught.value)


@pytest.mark.asyncio
async def test_non_streaming_retries_transient_server_error(monkeypatch) -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(503, json={"error": {"message": "busy"}})
        return httpx.Response(
            200,
            json={
                "model": "deepseek-v4-pro",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            },
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    async def no_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    monkeypatch.setattr("app.agent.qwen_client.asyncio.sleep", no_sleep)
    client = QwenClient(
        model="deepseek-v4-pro",
        api_key="test",
        base_url="https://api.deepseek.com",
        provider="deepseek",
    )

    response = await client.chat([{"role": "user", "content": "test"}])

    assert attempts["count"] == 2
    assert response.content == "ok"


@pytest.mark.asyncio
async def test_stream_collects_reasoning_content_and_tool_calls(monkeypatch) -> None:
    chunks = [
        {
            "model": "deepseek-v4-pro",
            "choices": [{"delta": {"reasoning_content": "check "}, "finish_reason": None}],
        },
        {
            "model": "deepseek-v4-pro",
            "choices": [{"delta": {"reasoning_content": "data"}, "finish_reason": None}],
        },
        {
            "model": "deepseek-v4-pro",
            "choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "look", "arguments": "{\"x\":"}}]}, "finish_reason": None}],
        },
        {
            "model": "deepseek-v4-pro",
            "choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "up", "arguments": "1}"}}]}, "finish_reason": "tool_calls"}],
        },
    ]
    body = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    client = QwenClient(
        model="deepseek-v4-pro",
        api_key="test",
        base_url="https://api.deepseek.com",
        provider="deepseek",
    )

    response = await client.chat_stream_collect(
        messages=[{"role": "user", "content": "test"}],
        tools=[{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}],
        enable_thinking=True,
    )

    assert captured["payload"]["thinking"] == {"type": "enabled"}
    assert captured["payload"]["reasoning_effort"] == "high"
    assert "enable_thinking" not in captured["payload"]
    assert response.reasoning_content == "check data"
    assert response.finish_reason == "tool_calls"
    assert response.tool_calls[0].name == "lookup"
    assert response.tool_calls[0].arguments == '{"x":1}'
