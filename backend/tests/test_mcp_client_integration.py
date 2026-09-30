"""Integration test: MCPClient against a real (mock) stdio MCP server subprocess."""

from __future__ import annotations

import sys

import pytest

from app.mcp.client import MCPClient
from app.mcp.config import MCPServerConfig


def _mock_config() -> MCPServerConfig:
    return MCPServerConfig(
        name="mock",
        command=sys.executable,
        args=["-m", "tests.mock_mcp_server"],
        cwd=None,
        init_timeout=30.0,
        call_timeout=30.0,
    )


@pytest.mark.asyncio
async def test_client_connect_list_call():
    client = MCPClient(_mock_config())
    await client.start()
    try:
        assert client.connected is True
        names = {t["name"] for t in client.tools}
        assert {"echo", "add"}.issubset(names)

        echo_result = await client.call_tool("echo", {"text": "hello"})
        assert echo_result.success is True
        assert echo_result.data.get("echo") == "hello"

        add_result = await client.call_tool("add", {"a": 2, "b": 3})
        assert add_result.success is True
        assert add_result.data.get("sum") == 5
    finally:
        await client.stop()
    assert client.connected is False


@pytest.mark.asyncio
async def test_client_unknown_tool_returns_error():
    client = MCPClient(_mock_config())
    await client.start()
    try:
        result = await client.call_tool("does_not_exist", {})
        assert result.success is False
    finally:
        await client.stop()
