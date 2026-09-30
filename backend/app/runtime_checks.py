"""Runtime checks for system availability."""

from __future__ import annotations

import httpx

from app.agent.qwen_client import resolve_chat_completions_endpoint
from app.core.model_config import ModelConfigError, main_slot
from app.mcp import ANSYS, MCPCAD, get_manager


def check_mcp_servers() -> list[dict[str, object]]:
    """Report connection status of the MCP servers."""
    manager = get_manager()
    results: list[dict[str, object]] = []
    for server in (MCPCAD, ANSYS):
        connected = manager.is_connected(server)
        results.append({
            "name": server,
            "status": "ok" if connected else "error",
            "connected": connected,
            "tool_count": len(manager.tools(server)) if connected else 0,
        })
    return results


async def check_main_model_available() -> dict[str, object]:
    """探活 DeepSeek 主设计模型，并回报实际响应模型。"""
    try:
        slot = main_slot()
    except ModelConfigError as exc:
        return {"name": "deepseek", "provider": "deepseek", "status": "error", "error": str(exc)}

    endpoint = slot.base_url
    url = resolve_chat_completions_endpoint(endpoint)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json={
                    "model": slot.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                },
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {slot.api_key}",
                },
            )
            response.raise_for_status()
            served = response.json().get("model", "")
    except Exception as exc:
        return {"name": "deepseek", "provider": "deepseek", "endpoint": endpoint, "model": slot.model, "status": "error", "error": str(exc)}

    result: dict[str, object] = {
        "name": "deepseek",
        "provider": "deepseek",
        "endpoint": endpoint,
        "model": slot.model,
        "served_model": served,
        "status": "ok",
    }
    if served and served != slot.model:
        result["status"] = "warning"
        result["error"] = f"服务端实际响应的模型是 {served}，与配置的 {slot.model} 不一致"
    return result


async def ensure_runtime_ready() -> list[dict[str, object]]:
    """Check all runtime dependencies."""
    services: list[dict[str, object]] = list(check_mcp_servers())
    services.append(await check_main_model_available())
    return services


async def ensure_cli_startup_ready() -> list[dict[str, object]]:
    """CLI startup: report MCP server connectivity."""
    return list(check_mcp_servers())
