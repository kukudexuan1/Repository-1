"""Convert MCP tool definitions into Qwen/OpenAI Function Calling tool schema."""

from __future__ import annotations

from typing import Any


def mcp_tool_to_function(tool: dict[str, Any]) -> dict[str, Any]:
    """Map a single MCP tool dict to an OpenAI-compatible function tool."""
    parameters = tool.get("input_schema") or {"type": "object", "properties": {}}
    if "type" not in parameters:
        parameters = {**parameters, "type": "object"}
    if "properties" not in parameters:
        parameters = {**parameters, "properties": {}}
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": parameters,
        },
    }


def mcp_tools_to_functions(
    tools: list[dict[str, Any]],
    *,
    include: set[str] | None = None,
    exclude: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Convert a list of MCP tools, optionally filtering by name."""
    result: list[dict[str, Any]] = []
    for tool in tools:
        name = tool.get("name", "")
        if include is not None and name not in include:
            continue
        if exclude is not None and name in exclude:
            continue
        result.append(mcp_tool_to_function(tool))
    return result
